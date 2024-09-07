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
    TranslationManager
        Methods:
            __init__
            translate
            _update_translations_and_cache
            _timeout_handler
            _translate_batch
            _translate_single
            _process_openai_stream
            _process_anthropic_stream
            _construct_prompt
            _construct_continuation_prompt
            retranslate_incomplete_entries

Logic Flows:
* The translate method attempts to use the primary API (Anthropic) first, then falls back to the secondary API (OpenAI) if needed
* Both _translate_anthropic and _translate_openai methods use a loop to handle partial responses and continue until a complete response is received
* Partial responses are accumulated and reassembled into complete translations
* The CacheManager is used to store partial translations as they become available

Batch Methodology:
* Attempt to translate using PREFERRED_API first and only fallback to the other API if the preferred API fails and the fallback API is enabled.
* OpenAI & Anthropic should both utilize streaming API requests to improve performance.
* The _translate_batch needs to expect that the API will return partial responses and be able to handle them, salvaging as much as possible from the partial response.
* As we receive each language translation, whether its from a batch or single language translation, we should immediately save the entry to the cache using both the unique ID and the english text as the key.
* If we receive a partial response, detected by an incomplete JSON object, we should delete the last line from it and then add on }} to close up the JSON object within the response.
* When each entry is processed, we should attempt a token estimation to try and intelligently determine how many languages we should ask for in the initial batch request.
* If the initial multi-language batch request fails, we should attempt to translate the remaining languages one at a time.
* As we capture and save to the cache each language translation, it should be displayed in a debug log the languages we have remaining.
* Our caching methodology must allow us to save one language translation at a time, as we may only receive one language translation at a time.
* The script should use the cache itself to discover how many language translations are missing and then attempt to translate the remaining languages one at a time.
* The script should loop until it has reached MAX_RETRIES attempts at translation. 


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
from typing import Union, List, Dict, Any, Set, Optional
import json
import re
import sys
import time
import signal
import traceback
import random

# Third-party imports
import anthropic
from openai import OpenAI, AsyncOpenAI
import asyncio
import tiktoken

# Local application imports
from cache_manager import CacheManager
from config import (
    ANTHROPIC_API_KEY, CHATGPT_API_KEY, MAX_TOKENS, ANTHROPIC_MODEL, OPENAI_MODEL, 
    TARGET_LANGUAGES, ESTIMATION_RETRIES, SINGLE_RETRIES, MAX_CONTINUATION_ATTEMPTS,
    MAX_ALLOWED_TOKENS, versioned, USE_OPENAI_STREAMING, PREFERRED_API, MAX_RETRIES, 
    RETRY_DELAY, ANTHROPIC_API_ENABLED, OPENAI_API_ENABLED
)
from debug_logging import LTLogger
from rate_limiter import RateLimiter
from response_parser import ResponseParser
from statistics_manager import StatisticsManager
from utils import is_json_complete, clean_json_string, check_exit_flag, truncate_text

class TranslationManager:
    """
    Manages the translation process using various APIs.

    This class handles the translation of text using either the Anthropic or OpenAI API,
    with support for batch processing, continuation of partial responses, and caching.

    Attributes:
        api_connection_manager (APIConnectionManager): Manages API connections and rate limiting.
        response_parser (ResponseParser): Parses and processes API responses.
        cache_manager (CacheManager): Manages the translation cache.
        stats_manager (StatisticsManager): Tracks and manages statistics.
        logger (Logger): Handles logging for the class.
        token_estimator (TokenEstimator): Estimates token usage for translations.
        show_openai_stream_chunks (bool): Controls detailed logging of OpenAI stream chunks.
            DO NOT REMOVE: This variable is required for OpenAI streaming functionality.

    Methods:
        translate: Main method to translate text to multiple languages.
        _update_translations_and_cache: Updates translations and cache with partial results.
        _timeout_handler: Handles translation request timeouts.
        _translate_batch: Handles batch translation of text to multiple languages.
        _translate_single: Handles translation of text to a single language.
        _process_openai_stream: Processes the OpenAI API stream response.
        _process_anthropic_stream: Processes the Anthropic API stream response.
        _construct_prompt: Constructs the prompt for the translation API.
        _construct_continuation_prompt: Constructs a prompt for continuing incomplete translations.
        retranslate_incomplete_entries: Retranslate incomplete entries.
    """

    from debug_logging import LTLogger
  

    @versioned("2.8.2")
    def __init__(self, logger: 'LTLogger', api_connection_manager: 'APIConnectionManager', 
                 cache_manager: 'CacheManager', response_parser: 'ResponseParser', 
                 stats_manager: 'StatisticsManager', token_estimator: 'TokenEstimator'):
        self.logger = logger
        self.api_connection_manager = api_connection_manager
        self.cache_manager = cache_manager
        self.response_parser = response_parser
        self.stats_manager = stats_manager
        self.token_estimator = token_estimator
        self.logger.debug("[TRANSLATE] TranslationManager initialized")
        
        # Control detailed logging of OpenAI stream chunks
        self.show_openai_stream_chunks = False

    @versioned("2.7.0")
    def _process_openai_stream(self, prompt: str) -> str:
        """
        Process the OpenAI stream response synchronously.

        This method uses the OpenAI client to handle streaming responses.
        """
        content = ""
        client = OpenAI(api_key=CHATGPT_API_KEY)
        stream = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": prompt}],
            stream=True
        )
        for chunk in stream:
            if chunk.choices[0].delta.content is not None:
                content += chunk.choices[0].delta.content
                if self.show_openai_stream_chunks:
                    self.logger.debug(f"[OPENAI] Received chunk: {chunk.choices[0].delta.content}")
        
        return content

    @versioned("2.8.6")
    def _translate_openai(self, text: str, languages: List[str], unique_id: str) -> Dict[str, str]:
        prompt = self._construct_prompt(text, unique_id, languages)
        try:
            response = self._process_openai_stream(prompt)
            parsed_response = self.response_parser._parse_translation_response(response)
            
            # Check for error fragments
            if parsed_response and self.response_parser.check_for_error_fragments(parsed_response):
                self.logger.error("[OPENAI] Error fragments detected in translation. Discarding result.")
                return {}
            
            return parsed_response
        except Exception as e:
            self.logger.error(f"[OPENAI] Error in translation: {str(e)}")
            raise

    @versioned("2.8.6")
    def _translate_anthropic(self, text: str, languages: List[str], unique_id: str) -> Dict[str, str]:
        prompt = self._construct_prompt(text, unique_id, languages)
        try:
            response = self._process_anthropic_stream(prompt)
            parsed_response = self.response_parser._parse_translation_response(response)
            
            # Check for error fragments
            if parsed_response and self.response_parser.check_for_error_fragments(parsed_response):
                self.logger.error("[ANTHROPIC] Error fragments detected in translation. Discarding result.")
                return {}
            
            return parsed_response
        except Exception as e:
            self.logger.error(f"[ANTHROPIC] Error in translation: {str(e)}")
            raise

    @versioned("2.6.0")
    def _process_anthropic_stream(self, prompt: str) -> str:
        content = ""
        with anthropic.Anthropic(api_key=ANTHROPIC_API_KEY).completions.create(
            model=ANTHROPIC_MODEL,
            max_tokens_to_sample=MAX_TOKENS,
            prompt=prompt,
            stream=True
        ) as stream:
            for completion in stream:
                if completion.completion:
                    content += completion.completion
        return content

    @versioned("1.0.0")
    def _get_current_api(self):
        """
        Determine the current API to use based on availability and preference.

        Returns:
            str: The API to use ('anthropic', 'openai', or None if both are disabled)
        """
        global ANTHROPIC_API_ENABLED, OPENAI_API_ENABLED, PREFERRED_API
        if PREFERRED_API == 'anthropic' and ANTHROPIC_API_ENABLED:
            return 'anthropic'
        elif PREFERRED_API == 'openai' and OPENAI_API_ENABLED:
            return 'openai'
        elif ANTHROPIC_API_ENABLED:
            return 'anthropic'
        elif OPENAI_API_ENABLED:
            return 'openai'
        else:
            return None

    @versioned("1.1.0")
    def _disable_api(self, api: str):
        """
        Disable the specified API and check if any APIs remain available.
        """
        global ANTHROPIC_API_ENABLED, OPENAI_API_ENABLED
        if api == 'anthropic':
            ANTHROPIC_API_ENABLED = False
        else:  # api == 'openai'
            OPENAI_API_ENABLED = False
        self.logger.warning(f"Disabling {api.capitalize()} API due to error.")
        
        if not ANTHROPIC_API_ENABLED and not OPENAI_API_ENABLED:
            self.logger.error("No remaining APIs are available. Exiting.")
            sys.exit(1)

    @versioned("2.9.2")
    def translate(self, text: str, languages: List[str], unique_id: str) -> Dict[str, str]:
        """
        Translate the given text into multiple languages.

        This method handles the core translation functionality, interfacing with the
        chosen API (OpenAI or Anthropic) to perform the translations. It constructs
        the appropriate prompt, processes the API response, and parses the results.

        Args:
            text (str): The text to be translated.
            languages (List[str]): A list of language codes to translate the text into.
            unique_id (str): A unique identifier for this translation.

        Returns:
            Dict[str, str]: A dictionary where keys are language codes and values are
            the corresponding translations.

        Raises:
            Exception: Any exception during the translation process is caught, logged,
            and not re-raised to allow for partial results.

        Version History:
            1.9.0 - Initial implementation with basic translation functionality.
            1.9.3 - Added support for multiple languages in a single API call.
            1.9.5 - Improved error handling and logging.
            1.9.6 - Added comprehensive docstring and version history.
            1.9.7 - Updated to match new _construct_prompt signature and added API selection.
            1.9.8 - Further refined _construct_prompt call to match its actual signature.
            2.0.0 - Implemented global API status checks and error handling.
            2.1.0 - Updated to use global API availability flags.
            2.5.0 - Added optional 'api' parameter to specify which API to use.
            2.8.0 - Updated to use _translate_openai and _translate_anthropic methods.
            2.10.0 - Improved API selection and fallback logic.
            2.12.0 - Refactored to use _get_current_api method and handle API fallback.
            2.12.1 - Added checks for remaining APIs after disabling one.
            2.9.1 - Updated to accept unique_id as a parameter.
            2.9.2 - Added extraction of translations from nested structure.
        """
        current_api = self.api_connection_manager.get_current_api()
        self.logger.debug(f"[TRANSLATE] Translating text: {truncate_text(text, 100)}")
        self.logger.debug(f"[TRANSLATE]       to {len(languages)} languages: {', '.join(languages)}")
        
        if current_api is None:
            self.logger.error("Both APIs are disabled. Unable to translate.")
            sys.exit(1)  # Exit here as well

        try:
            if current_api == 'anthropic':
                translations = self._translate_anthropic(text, languages, unique_id)
            else:  # current_api == 'openai'
                translations = self._translate_openai(text, languages, unique_id)
            
            self.logger.debug(f"[TRANSLATE] Received translations: {translations}")
            
            # Extract the translations from the nested structure
            extracted_translations = {}
            for lang, trans in translations.items():
                if isinstance(trans, dict):
                    extracted_translations.update(trans)
                else:
                    extracted_translations[lang] = trans
            
            self.logger.debug(f"[TRANSLATE] Extracted translations: {extracted_translations}")
            return extracted_translations
        except Exception as e:
            self.logger.error(f"{current_api.capitalize()} translation failed: {str(e)}")
            self._disable_api(current_api)
            
            # Try the other API if available
            alternative_api = self._get_current_api()
            if alternative_api:
                self.logger.info(f"Falling back to {alternative_api.capitalize()} API.")
                return self.translate(text, languages, unique_id)  # Recursive call with the new API
            else:
                self.logger.error("No enabled API available for translation.")
                sys.exit(1)  # Exit here as well

    @versioned("2.3.0")
    def _update_translations_and_cache(self, translations: Dict[str, Dict[str, str]], partial_translations: Dict[str, Dict[str, str]], 
                                    remaining_languages: List[str], text: str):
        unique_id = self.cache_manager.obtain_id(text)
        for lang, trans in partial_translations.get(unique_id, {}).items():
            if trans and len(trans) > 1:
                if unique_id not in translations:
                    translations[unique_id] = {}
                translations[unique_id][lang] = trans
                if lang in remaining_languages:
                    remaining_languages.remove(lang)
                    self.cache_manager.set_temp(unique_id, {lang: trans})
                    self.logger.debug(f"[TRANSLATE] Successfully translated and cached in temporary pickle cache: {lang}")
                else:
                    self.logger.debug(f"[TRANSLATE] Language {lang} not in remaining_languages")
            else:
                self.logger.warning(f"[TRANSLATE] Received invalid or empty translation for {lang}")
        
        self.logger.debug(f"[TRANSLATE] Remaining languages after update: {remaining_languages}")

    @versioned("1.0.0")
    def _timeout_handler(self):
        self.logger.error("[TRANSLATE] Translation request timed out")
        # You might want to implement additional logic here, such as
        # setting a flag to indicate that the operation should be aborted

    @versioned("2.3.1")
    def _translate_batch(self, text: str, unique_id: str, languages: List[str], api: str) -> Dict[str, Dict[str, str]]:
        self.logger.debug(f"[TRANSLATE] Entering _translate_batch method with {len(languages)} languages")
        result = {}
        remaining_languages = languages.copy()

        for language in languages:
            try:
                prompt = self._construct_prompt(text, unique_id, [language])
                
                with self.api_connection_manager.rate_limiter.acquire(api):
                    if api == "openai":
                        partial_result = self._process_openai_stream(prompt)
                    elif api == "anthropic":
                        partial_result = self._process_anthropic_stream(prompt)
                    
                    parsed_result = self.response_parser._parse_translation_response(partial_result)
                    self._update_translations_and_cache(result, parsed_result, remaining_languages, text)
                    
            except Exception as e:
                self.logger.error(f"[TRANSLATE] Error translating {language}: {str(e)}")

        if remaining_languages:
            self.logger.warning(f"[TRANSLATE] Incomplete translation. Missing languages: {remaining_languages}")

        self.logger.debug(f"[TRANSLATE] _translate_batch returning: {result}")
        return result
    
    @versioned("1.9.4")
    def _translate_single(self, text: str, unique_id: str, language: str, api: str) -> Dict[str, str]:
        """
        Translate text to a single language.

        Args:
            text (str): The text to be translated.
            unique_id (str): The unique identifier for this translation.
            language (str): The target language.
            api (str): The API to use for translation.

        Returns:
            Dict[str, str]: A dictionary with a single translation (language code as key).

        Notes:
            - Uses streaming API calls for better performance.
            - Handles partial responses and continuation if needed.
        """
        self.logger.debug(f"[TRANSLATE] Entering _translate_single method for language: {language}")
        prompt = self._construct_prompt(text, unique_id, [language])
        translations = {}

        try:
            with self.api_connection_manager.rate_limiter.acquire(api):
                if api == 'openai':
                    content = self._process_openai_stream(prompt)
                elif api == 'anthropic':
                    content = self._process_anthropic_stream(prompt)
                else:
                    raise ValueError(f"Unknown API: {api}")

            content = self.response_parser._clean_json_string(content)
            self.logger.debug(f"[{api.upper()}] Received response: {content[:100]}...")

            if not self.response_parser._is_json_complete(content):
                self.logger.debug(f"[{api.upper()}] Partial response detected")
                raise ValueError("Incomplete JSON response")

            partial_translations = self.response_parser._parse_translation_response(content)
            translations.update(partial_translations)

        except Exception as e:
            self.logger.error(f"[TRANSLATE] Error in single language translation: {str(e)}")
            raise

        return translations

    @versioned("1.9.8")
    def _construct_prompt(self, text: str, unique_id: str, languages: List[str]) -> str:
        """
        Construct the prompt for the translation API.

        Args:
            text (str): The text to be translated.
            unique_id (str): A unique identifier for this translation.
            languages (List[str]): A list of language codes to translate the text into.

        Returns:
            str: The constructed prompt for the API.

        Version History:
            1.9.0 - Initial implementation.
            1.9.8 - Updated signature to remove 'api' parameter.
        """
        language_list = ", ".join(languages)
        prompt = f"""Respond only with a JSON object where the key is the unique identifier '{unique_id}' and the value is another JSON object.
        In this inner object, each key should be a language code, and its value should be the translation.
        Do not include the original text or any additional fields in the response. Do not repeat yourself.
        Preserve all '\\n' sequences as they represent linefeeds. Do not convert '\\n' to actual linefeeds.
        
        Example format:
        {{
            "{unique_id}": {{
                "german": "German translation here",
                "french": "French translation here",
                ...
            }}
        }}

        Translate the text below to {language_list}.
        Text to translate: {text}"""
        return prompt

    @versioned("1.9.4")
    def _construct_continuation_prompt(self, partial_response: str, unique_id: str, remaining_languages: List[str], api: str) -> Union[str, Dict]:
        last_chars = partial_response[-15:]
        continuation_prompt = f"""
        Your last response was cut off due to a message limit. Continue your JSON response, translations for the remaining languages: {', '.join(remaining_languages)}, exactly where you left off. Here are the last characters of the previous response:
        {last_chars}
        """
        self.logger.debug(f"[{api.upper()}] [PROMPT] Continuation prompt: {continuation_prompt}")
        
        if api == 'openai':
            return {
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant that translates text."},
                    {"role": "user", "content": continuation_prompt}
                ]
            }
        else:              return continuation_prompt

    @versioned("1.0.0")
    def _log_raw_response(self, response: str):
        """Log the raw API response, truncating if it's too long."""
        max_length = 1000  # Adjust this value as needed
        truncated_response = response[:max_length] + "..." if len(response) > max_length else response
        self.logger.debug(f"[API] Raw API Response: {truncated_response}")

    @versioned("2.9.1")
    def retranslate_incomplete_entries(self, incomplete_entries: List[Dict[str, str]]) -> Dict[str, Dict[str, str]]:
        """
        Retranslate incomplete entries.

        Args:
            incomplete_entries (List[Dict[str, str]]): List of entries with incomplete translations.

        Returns:
            Dict[str, Dict[str, str]]: Dictionary of completed translations.
        """
        self.logger.info(f"[TRANSLATE] Attempting to retranslate {len(incomplete_entries)} incomplete entries")
        completed_translations = {}

        for entry in incomplete_entries:
            key = entry['Key']
            text_to_translate = entry.get('english', '')
            
            if not text_to_translate:
                self.logger.warning(f"[TRANSLATE] No English text to translate for key: {key}. Skipping retranslation.")
                continue
            
            try:
                unique_id = self.cache_manager.obtain_id(text_to_translate)
                new_translations = self.translate(text_to_translate, TARGET_LANGUAGES, unique_id)
                completed_translations[key] = new_translations
                self.logger.info(f"[TRANSLATE] Successfully retranslated entry for key: {key}")
            except Exception as e:
                self.logger.error(f"[TRANSLATE] Failed to retranslate entry for key: {key}. Error: {str(e)}")

        self.logger.info(f"[TRANSLATE] Completed retranslation attempts for {len(incomplete_entries)} entries")
        return completed_translations

    @versioned("2.3.0")
    async def close(self):
        await self.api_connection_manager.close_all_clients()
        