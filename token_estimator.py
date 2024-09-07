"""
API Management module for the Language Translator script.

This module handles interactions with the Anthropic and OpenAI APIs for text translation.

Features:
* Supports both Anthropic and ChatGPT APIs with automatic alternation
* Implements rate limiting to prevent exceeding API quotas
* Handles API key validation
* Manages translation requests with retry logic and error handling
* Implements continuous response handling for incomplete API responses
* Provides methods for cleaning and validating JSON responses
* Handles partial responses and reassembles them into complete translations
* Implements robust continuation logic for incomplete API responses
* Utilizes CacheManager for storing partial translations

Class Definitions:
    TokenEstimator
        Methods:
            __init__
            estimate_tokens
            estimate_tokens_anthropic
            estimate_tokens_openai
            _estimate_tokens_tiktoken
            _manual_token_estimation
            _num_tokens_from_messages

Logic Flows:
* The translate method attempts to use the primary API (Anthropic) first, then falls back to the secondary API (OpenAI) if needed
* Both _translate_anthropic and _translate_openai methods use a loop to handle partial responses and continue until a complete response is received
* Partial responses are accumulated and reassembled into complete translations
* The CacheManager is used to store partial translations as they become available

Notes:
* Prompt Engineering:
    All prompts are sent in JSON format
    The AI is prompted to respond only with a JSON object where the key is the unique identifier provided and the value is an object containing translations for each target language
    The unique identifier is a 5-digit random number provided by the script and is used in place of the English text as the key
    Instructions include: "Do not include the original text in the response. Preserve all '\\n' sequences as they represent linefeeds. Do not convert '\\n' to actual linefeeds in your response."
* Implement Graceful CTRL-C Handler that will write out the cache entry, display current progress to the screen and then exit the script

Lessons Learned:
* Problem: Partial API responses were being cleaned and parsed prematurely
  Solution: Implemented a loop in _translate_anthropic and _translate_openai to accumulate partial responses before cleaning and parsing the complete JSON

* Problem: Difficulty in handling continuation of partial translations
  Solution: Implemented a continuation prompt that includes the last characters of the previous response and asks to continue from that point

* Problem: Inconsistent handling of JSON responses between different API methods
  Solution: Standardized JSON handling across all API methods, using _clean_json_string and _is_json_complete consistently

* Problem: Incomplete translations due to API response limitations
  Solution: Implemented a robust system to handle partial responses, reassemble them, and continue translation until all languages are completed
"""

# Standard library imports
from typing import Union, List, Dict, Any, Set, Optional, Callable
import json
import re
import sys
import traceback

# Third-party imports
import anthropic
from openai import OpenAI
import tiktoken

# Local application imports
from cache_manager import CacheManager
from config import (
    ANTHROPIC_API_KEY, CHATGPT_API_KEY, MAX_TOKENS, ANTHROPIC_MODEL, OPENAI_MODEL, 
    TARGET_LANGUAGES, ESTIMATION_RETRIES, SINGLE_RETRIES, MAX_CONTINUATION_ATTEMPTS,
    MAX_ALLOWED_TOKENS, versioned, TOKEN_ESTIMATION_METHODS
)
from debug_logging import LTLogger
from rate_limiter import RateLimiter
from statistics_manager import StatisticsManager
from translation_manager import TranslationManager
from utils import is_json_complete, clean_json_string

@versioned("2.3.2")
class TokenEstimator:
    """
    Estimates token usage for API requests in the Language Translator application.

    This class provides methods to estimate the number of tokens that will be used
    in API requests, helping to optimize API usage and prevent exceeding token limits.

    Attributes:
        logger (Logger): Logger instance for debugging and error reporting.
        anthropic_cl100k_base (Encoding): Tokenizer for Anthropic's Claude model.
        gpt2_tokenizer (Encoding): Tokenizer for OpenAI's GPT models.
        translation_manager (TranslationManager): Instance for prompt construction.

    Dependencies:
        - Logger: Used for logging debug information and errors during token estimation.
        - TranslationManager: Used for constructing prompts.

    Methods:
        estimate_tokens: Estimates the number of tokens for a given text and languages.
        _estimate_tokens_api: Estimates tokens using the current API's token counting method.
        _estimate_tokens_tiktoken: Estimates tokens using the tiktoken library.
        _estimate_tokens_expansion_factor: Estimates tokens using an expansion factor method.
        _num_tokens_from_messages: Calculates the number of tokens in a list of messages.

    Version History:
        1.0.0 - Initial implementation with basic token estimation.
        1.5.0 - Added support for different estimation methods.
        1.8.0 - Implemented API-specific token estimation.
        1.9.3 - Added expansion factor estimation method.
        2.0.0 - Major refactor: improved error handling, added comprehensive docstrings.
        2.1.0 - Updated to accept api_connection_manager in estimate_tokens method.
        2.2.0 - Updated to use TOKEN_ESTIMATION_METHODS from config.py
        2.3.0 - Added minimal TranslationManager for prompt construction.
        2.3.2 - Updated to initialize translation_manager as None and added set_translation_manager method.
    """

    def __init__(self, logger: LTLogger):
        self.logger = logger
        try:
            self.anthropic_cl100k_base = tiktoken.get_encoding("cl100k_base")
            self.gpt2_tokenizer = tiktoken.encoding_for_model("gpt-3.5-turbo")
        except Exception as e:
            self.logger.error(f"Error initializing tokenizers: {str(e)}")
            raise
        self.translation_manager = None  # Initialize as None

    @versioned("2.3.2")
    def set_translation_manager(self, translation_manager: 'TranslationManager'):
        self.translation_manager = translation_manager

    @versioned("2.3.2")
    def estimate_tokens(self, text: str, languages: List[str], api_connection_manager) -> tuple[int, int, int]:
        """
        Estimate the number of tokens for the given text and languages.

        Args:
            text (str): The text to be translated.
            languages (List[str]): The list of target languages.
            api_connection_manager: The API connection manager instance.

        Returns:
            tuple[int, int, int]: Total tokens, optimal batch size, and estimated batch tokens.
        """
        current_api = api_connection_manager.get_current_api()
        total_tokens = 0
        
        for method in TOKEN_ESTIMATION_METHODS:
            try:
                if method == 'API':
                    total_tokens = self._estimate_tokens_api(text, languages, current_api, api_connection_manager)
                elif method == 'Tiktoken':
                    total_tokens = self._estimate_tokens_tiktoken(text, languages, current_api)
                elif method == 'ExpansionFactor':
                    total_tokens = self._estimate_tokens_expansion_factor(text, languages)
                
                if total_tokens > 0:
                    break
            except Exception as e:
                self.logger.warning(f"[TOKEN] {method} token estimation failed: {str(e)}. Trying next method.")
        
        if total_tokens == 0:
            self.logger.error(f"[TOKEN] All token estimation methods failed.")
            return 0, 0, 0
        
        tokens_per_language = total_tokens // len(languages) if languages else 0
        max_languages = min(len(languages), MAX_ALLOWED_TOKENS // tokens_per_language) if tokens_per_language > 0 else 0
        
        optimal_batch_size = max(1, min(max_languages, MAX_ALLOWED_TOKENS // tokens_per_language))
        estimated_batch_tokens = optimal_batch_size * tokens_per_language
        
        self.logger.debug(f"[TOKEN] Per language: {tokens_per_language} | Optimal batch size: {optimal_batch_size} | Optimal batch tokens: {estimated_batch_tokens}")
        return total_tokens, optimal_batch_size, estimated_batch_tokens

    @versioned("2.3.3")
    def _estimate_tokens_api(self, text: str, languages: List[str], api: str, api_connection_manager) -> int:
        if self.translation_manager is None:
            raise ValueError("TranslationManager not set. Call set_translation_manager first.")
        
        unique_id = "12345"  # Dummy unique_id for estimation purposes
        if api == 'anthropic':
            prompt = self.translation_manager._construct_prompt(text, unique_id, languages)
            total_tokens = api_connection_manager.anthropic_client.count_tokens(prompt)
        elif api == 'openai':
            prompt = self.translation_manager._construct_prompt(text, unique_id, languages)
            total_tokens = self._num_tokens_from_messages([{"role": "user", "content": prompt}], OPENAI_MODEL)
        else:
            raise ValueError(f"Unknown API: {api}")
        
        self.logger.debug(f"[TOKEN] API token estimation: {total_tokens}")
        return total_tokens

    @versioned("1.9.3")
    def _estimate_tokens_tiktoken(self, text: str, languages: List[str], api: str) -> int:
        unique_id = "12345"  # Dummy unique_id for estimation purposes
        model = ANTHROPIC_MODEL if api == 'anthropic' else OPENAI_MODEL
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            self.logger.warning(f"[TOKEN] Model {model} not found. Using cl100k_base encoding.")
            encoding = tiktoken.get_encoding("cl100k_base")
        
        prompt = self._construct_prompt(text, unique_id, languages)
        token_count = len(encoding.encode(prompt))
        self.logger.debug(f"[TOKEN] Tiktoken estimation: {token_count}")
        return token_count

    @versioned("1.9.3")
    def _estimate_tokens_expansion_factor(self, text: str, languages: List[str]) -> int:
        base_tokens = len(text.split())
        estimated_expansion_factor = 1.2  # Assume translations might be 20% longer
        tokens_per_language = base_tokens * estimated_expansion_factor
        total_tokens = int(tokens_per_language * len(languages))
        
        # Adjust based on text complexity
        if any(char in text for char in '!@#$%^&*()_+-=[]{}|;:,.<>?'):
            total_tokens = int(total_tokens * 1.1)  # Increase estimate for complex text
        
        return total_tokens

    @versioned("1.9.3")
    def _num_tokens_from_messages(self, messages: List[Dict[str, Any]], model: str = "gpt-3.5-turbo-0613") -> int:
        """Return the number of tokens used by a list of messages."""
        try:
            encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            print("Warning: model not found. Using cl100k_base encoding.")
            encoding = tiktoken.get_encoding("cl100k_base")
        if model in {
            "gpt-3.5-turbo-0613",
            "gpt-3.5-turbo-16k-0613",
            "gpt-4-0314",
            "gpt-4-32k-0314",
            "gpt-4-0613",
            "gpt-4-32k-0613",
            }:
            tokens_per_message = 3
            tokens_per_name = 1
        elif model == "gpt-3.5-turbo-0301":
            tokens_per_message = 4
            tokens_per_name = -1
        elif "gpt-3.5-turbo" in model:
            return self._num_tokens_from_messages(messages, model="gpt-3.5-turbo-0613")
        elif "gpt-4" in model:
            return self._num_tokens_from_messages(messages, model="gpt-4-0613")
        else:
            raise NotImplementedError(
                f"""num_tokens_from_messages() is not implemented for model {model}. See https://github.com/openai/openai-python/blob/main/chatml.md for information on how messages are converted to tokens."""
            )
        num_tokens = 0
        for message in messages:
            num_tokens += tokens_per_message
            for key, value in message.items():
                num_tokens += len(encoding.encode(value))
                if key == "name":
                    num_tokens += tokens_per_name
        num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
        return num_tokens

# At the end of the file, add:
sys.setrecursionlimit(1000)  # Default is usually 1000, but we're setting it explicitly
