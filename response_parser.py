"""
API Management module for the Language Translator script.

This module handles interactions with the Anthropic and OpenAI APIs for text translation.

Features:
* Parses streaming and complete JSON responses
* Cleans and validates JSON strings
* Handles partial and incomplete JSON responses
* Implements alternative language key handling

Class Definitions:
     ResponseParser
        Methods:
            __init__
            _clean_json_string
            _is_json_complete
            _parse_partial_response
            _handle_alternative_language_keys
            _parse_translation_response

Logic Flows:
* The parse_stream method processes streaming responses and accumulates them until a complete JSON is received
* JSON cleaning and validation methods ensure proper formatting of responses
* The _parse_translation_response method handles various response formats and processes them into a standardized dictionary
* Incomplete JSON responses are fixed using the _fix_incomplete_json method
* Alternative language keys are handled to ensure correct mapping of translations

Notes:
* The class uses versioning decorators for method tracking
* Debug logging is implemented throughout the class for troubleshooting
* The class is designed to work with both complete and partial API responses

    
Lessons Learned:
* Problem: Partial API responses were being cleaned and parsed prematurely
  Solution: Implemented a loop in _translate_anthropic and _translate_openai to accumulate partial responses before cleaning and parsing the complete JSON

* Problem: Difficulty in handling continuation of partial translations
  Solution: Implemented a continuation prompt that includes the last characters of the previous response and asks to continue from that point

* Problem: Inconsistent handling of JSON responses between different API methods
  Solution: Standardized JSON handling across all API methods, using _clean_json_string and _is_json_complete consistently
"""

# Standard library imports
from typing import Union, List, Dict, Any, Set, Optional
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
    MAX_ALLOWED_TOKENS, versioned, LANGUAGE_ALTERNATIVES
)
from debug_logging import LTLogger
from rate_limiter import RateLimiter
from statistics_manager import StatisticsManager
from utils import is_json_complete, clean_json_string

@versioned("2.0.0")
class ResponseParser:
    """
    ResponseParser class for handling and parsing API responses in the Language Translator application.

    This class is responsible for parsing, cleaning, and validating JSON responses from translation APIs.
    It handles both streaming and complete JSON responses, manages partial and incomplete JSON data,
    and implements error detection and alternative language key handling.

    Attributes:
        logger (Logger): An instance of the Logger class for logging operations.
        current_response (str): Stores the current accumulated response from streaming APIs.
        error_fragments_dict (Dict[str, str]): Dictionary of error message fragments for each supported language.

    Dependencies:
        - Logger: Used for logging debug information and errors during response parsing.

    Methods:
        parse_stream: Processes streaming responses and accumulates them until a complete JSON is received.
        _clean_json_string: Cleans and formats JSON strings.
        _is_json_complete: Checks if a JSON string is complete and valid.
        check_for_error_fragments: Detects error responses based on predefined error fragments.
        _parse_translation_response: Parses and processes translation responses.
        _fix_incomplete_json: Attempts to fix and complete partial JSON responses.
        _handle_alternative_language_keys: Manages alternative language keys in responses.
        _preprocess_response: Preprocesses the API response.
        _escape_backslashes: Escapes unescaped backslashes in JSON strings.
        _extract_valid_json: Extracts valid JSON object from a potentially larger string.

    Version History:
        1.0.0 - Initial implementation
        1.5.0 - Added support for streaming responses
        1.6.0 - Implemented JSON cleaning and validation methods
        1.7.0 - Implemented error detection mechanism
        1.9.0 - Added handling for alternative language keys
        2.0.0 - Major refactor: improved error handling, added comprehensive docstrings
    """
       
    from config import ANTHROPIC_API_ENABLED, OPENAI_API_ENABLED

    @versioned("1.9.7")
    def __init__(self, logger: LTLogger):
        self.logger = logger
        self.current_response = ""
        self.error_fragments_dict = {
            "spanish": "Responder solo con un objeto JSON",
            "korean": "JSON 객체로만 응답하고",
            "russian": "Ответьте только объектом JSON",
            "latam": "Responder solo con un objeto JSON",
            "italian": "Rispondere solo con un oggetto JSON",
            "french": "Répondre uniquement avec un objet JSON",
            "brazilian": "Responder somente com um objeto JSON",
            "tchinese": "僅通過JSON對象響應",
            "japanese": "JSONオブジェクトでのみ応答してください",
            "schinese": "只能用JSON對象來回答",
            "polish": "Odpowiadaj tylko obiektem JSON",
            "german": "Antworte nur mit einem JSON-Objekt",
            "turkish": "Yalnızca JSON nesnesi ile yanıt verin"
        }


    @versioned("1.2.2")
    def check_for_error_fragments(self, translations: Dict[str, str]) -> bool:
        for lang, translation in translations.items():
            if lang in self.error_fragments_dict and self.error_fragments_dict[lang] in translation:
                self.logger.error(f"[PARSER] Detected error response in {lang} translation")
                return True
        return False

    @versioned("1.5.0")
    def parse_stream(self, stream):
        for chunk in stream:
            if chunk.choices[0].delta.content:
                self.current_response += chunk.choices[0].delta.content
                
            if self._is_complete_json(self.current_response):
                parsed_json = json.loads(self.current_response)
                self.logger.debug(f"[PARSER] Received complete JSON: {parsed_json}")
                self.current_response = ""
                return parsed_json

        self.logger.warning("[PARSER] Stream ended without complete JSON")
        return None

    @versioned("1.6.0")
    def _is_complete_json(self, json_string):
        try:
            json.loads(json_string)
            return True
        except json.JSONDecodeError:
            return False

    @versioned("1.7.1")
    def _clean_json_string(self, json_string: str) -> str:
        json_string = re.sub(r'^```json\s*', '', json_string)
        json_string = re.sub(r'^json\s*', '', json_string)
        json_string = re.sub(r'^```\s*', '', json_string)
        json_string = re.sub(r'\s*```$', '', json_string)
        cleaned_string = json_string.strip()
        return cleaned_string

    @versioned("1.0.0")
    def _clean_translations(self, translations: Dict[str, str]) -> Dict[str, str]:
        """
        Remove trailing newline characters from translations.
        """
        return {lang: trans.rstrip('\n') for lang, trans in translations.items()}

    @versioned("2.1.1")
    def _parse_translation_response(self, response: Union[Dict[str, Any], str]) -> Dict[str, str]:
        self.logger.debug("[PARSER] Parsing translation response")
        try:
            preprocessed_response = self._preprocess_response(response)
            cleaned_response = self._clean_json_string(preprocessed_response)
            try:
                parsed_response = json.loads(cleaned_response)
            except json.JSONDecodeError as json_error:
                self.logger.error(f"[PARSER] JSON parsing error: {str(json_error)}")
                self.logger.error(f"[PARSER] Raw response: {cleaned_response}")
                return {}
            
            self.logger.debug(f"[PARSER] Successfully parsed JSON API Response")

            if isinstance(parsed_response, dict):
                if len(parsed_response) == 1:
                    translations = next(iter(parsed_response.values()))
                else:
                    translations = parsed_response
            else:
                self.logger.error(f"Unexpected response format: {parsed_response}")
                return {}

            # Check for error response
            if self.check_for_error_fragments(translations):
                self.logger.error("[PARSER] Detected error response, returning empty dictionary")
                return {}

            # Handle alternative language keys
            updated_translations = self._handle_alternative_language_keys(translations)
            
            # Clean translations by removing trailing newlines
            cleaned_translations = self._clean_translations(updated_translations)
            
            return cleaned_translations
        except Exception as e:
            self.logger.error(f"[PARSER] Unexpected error in parsing response: {str(e)}")
            self.logger.error(f"[PARSER] Error details: {traceback.format_exc()}")
            self.logger.error(f"[PARSER] Raw response: {response}")
            return {}

    @versioned("1.0.0")
    def _fix_incomplete_json(self, response: str) -> str:
        complete_entries = re.findall(r'"(\w+)"\s*:\s*"([^"]*)"', response)
        if not complete_entries:
            raise ValueError("No complete language entries found")

        fixed_response = '{'
        for lang, translation in complete_entries[:-1]:
            fixed_response += f'"{lang}": "{translation}",'
        fixed_response = fixed_response.rstrip(',') + '}'

        self.logger.debug(f"[PARSER] Fixed incomplete JSON. Original entries: {len(complete_entries)}, Used entries: {len(complete_entries) - 1}")
        return fixed_response

    @versioned("1.6.0")
    def _handle_alternative_language_keys(self, translations: Dict[str, str]) -> Dict[str, str]:
        updated_translations = {}
        for target_lang, alternatives in LANGUAGE_ALTERNATIVES.items():
            for alt in alternatives:
                if alt in translations:
                    updated_translations[target_lang] = translations[alt]
                    if alt != target_lang:
                        self.logger.debug(f"Used alternative key '{alt}' for language '{target_lang}'")
                    break
            else:
                if target_lang in translations:
                    updated_translations[target_lang] = translations[target_lang]
        
        for lang, trans in translations.items():
            if lang not in updated_translations:
                updated_translations[lang] = trans
        
        return updated_translations

    @versioned("1.0.0")
    def _preprocess_response(self, response: Union[Dict[str, Any], str]) -> str:
        """
        Preprocess the API response.
        """
        if isinstance(response, dict):
            return json.dumps(response)
        return response

    @versioned("1.0.0")
    def _escape_backslashes(self, json_string: str) -> str:
        """
        Escape any unescaped backslashes in the JSON string.
        """
        return re.sub(r'(?<!\\)\\(?!["\\])', r'\\\\', json_string)

    @versioned("1.0.0")
    def _extract_valid_json(self, json_string: str) -> str:
        """
        Extract the valid JSON object from a potentially larger string.
        """
        json_start = json_string.find('{')
        json_end = json_string.rfind('}') + 1
        if json_start != -1 and json_end != -1:
            return json_string[json_start:json_end]
        return json_string

# At the end of the file, add:
sys.setrecursionlimit(1000)  # Default is usually 1000, but we're setting it explicitly
