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
            "spanish": "con un objeto JSON",
            "korean": "JSON 객체로만",
            "russian": "только объектом JSON",
            "latam": "con un objeto JSON",
            "italian": "con un oggetto JSON",
            "french": "avec un objet JSON",
            "brazilian": "com um objeto JSON",
            "tchinese": "僅通過JSON對象響應",
            "japanese": "JSONオブジェクトでのみ応答してください",
            "schinese": "只能用JSON對象來回答",
            "polish": "Odpowiadaj tylko obiektem JSON",
            "german": "mit einem JSON-Objekt",
            "turkish": "Yalnızca JSON nesnesi ile"
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

    @versioned("2.1.7")
    def _parse_translation_response(self, response: Union[Dict[str, Any], str]) -> Dict[str, str]:
        try:
            preprocessed_response = self._preprocess_response(response)
            cleaned_response = self._clean_json_string(preprocessed_response)
            fixed_response = self._fix_incomplete_json(cleaned_response)
            try:
                parsed_response = json.loads(fixed_response)
                self.logger.debug(f"[PARSER] Parsed response: {parsed_response}")
            except json.JSONDecodeError as json_error:
                self.logger.error(f"[PARSER] JSON parsing error: {str(json_error)}")
                self.logger.error(f"[PARSER] Raw response: {fixed_response}")
                return {}
            
            # Extract translations from the parsed response
            translations = {}
            if isinstance(parsed_response, dict):
                for outer_key, outer_value in parsed_response.items():
                    if isinstance(outer_value, dict):
                        translations = outer_value
                        break  # We only expect one unique ID per response
            
            self.logger.debug(f"[PARSER] Extracted translations: {translations}")
            return translations

        except Exception as e:
            self.logger.error(f"[PARSER] Unexpected error in parsing response: {str(e)}")
            self.logger.error(f"[PARSER] Error details: {traceback.format_exc()}")
            return {}

    @versioned("1.2.4")
    def _fix_incomplete_json(self, response: str) -> str:
        """
        Attempts to fix and validate an incomplete or malformed JSON string.

        This method expects the input to be a JSON string representing translations,
        and attempts to fix it to conform to the following structure:

        {
            "unique_id": {
                "language_code1": "translation1",
                "language_code2": "translation2",
                ...
            }
        }

        Where:
        - "unique_id" is a string of digits representing a unique identifier for this set of translations.
        - "language_code" is a string representing the language code (e.g., "en", "es", "fr").
        - "translation" is the translated text for the corresponding language.

        The method will attempt to:
        1. Parse the JSON as-is first.
        2. If parsing fails, extract the unique identifier and complete key-value pairs.
        3. Remove any incomplete entries (e.g., languages without translations).
        4. Reconstruct the JSON in the correct format.
        5. Properly encode unicode characters.

        Args:
            response (str): The potentially incomplete or malformed JSON string.

        Returns:
            str: A string representing a valid JSON object in the expected format.
                 If fixing fails, it returns the best attempt at fixing the JSON.
        """
        self.logger.debug(f"[PARSER] Attempting to fix incomplete JSON: {response[:100]}...")

        try:
            # Try to parse the JSON as-is first
            parsed_json = json.loads(response)
            self.logger.debug("[PARSER] JSON is already valid")
            return json.dumps(parsed_json)
        except json.JSONDecodeError:
            self.logger.debug("[PARSER] JSON is invalid, attempting to fix")

        def fix_nested_json(json_str):
            # Fix missing commas between nested objects
            json_str = re.sub(r'}\s*{', '},{', json_str)
            
            # Fix missing commas between key-value pairs
            json_str = re.sub(r'"\s*}\s*"', '"},"', json_str)
            
            # Remove trailing commas in objects
            json_str = re.sub(r',\s*}', '}', json_str)
            
            # Remove trailing commas in arrays
            json_str = re.sub(r',\s*]', ']', json_str)
            
            return json_str

        # Original fix for incomplete entries
        complete_entries = re.findall(r'"(\w+)"\s*:\s*"([^"]*)"', response)
        if complete_entries:
            fixed_response = '{'
            for lang, translation in complete_entries[:-1]:
                fixed_response += f'"{lang}": "{translation}",'
            fixed_response = fixed_response.rstrip(',') + '}'
            self.logger.debug(f"[PARSER] Applied original fix. Entries: {len(complete_entries)}")
        else:
            fixed_response = response

        # Apply nested fixes
        fixed_response = fix_nested_json(fixed_response)

        # Additional common JSON error fixes
        try:
            self.logger.debug("[PARSER] Attempting to fix unquoted keys...")
            fixed_response = re.sub(r'(\w+)(?=\s*:)', r'"\1"', fixed_response)
        except Exception as e:
            self.logger.debug(f"[PARSER] Error fixing unquoted keys: {str(e)}")

        try:
            self.logger.debug("[PARSER] Attempting to fix single quotes...")
            fixed_response = fixed_response.replace("'", '"')
        except Exception as e:
            self.logger.debug(f"[PARSER] Error fixing single quotes: {str(e)}")

        try:
            self.logger.debug("[PARSER] Attempting to fix trailing commas in nested structures...")
            fixed_response = re.sub(r',(\s*[\]}])', r'\1', fixed_response)
        except Exception as e:
            self.logger.debug(f"[PARSER] Error fixing trailing commas: {str(e)}")

        # Validate the fixed JSON
        try:
            json.loads(fixed_response)
            self.logger.info("[PARSER] Successfully fixed and validated JSON")
        except json.JSONDecodeError as e:
            self.logger.error(f"[PARSER] Failed to fix JSON completely. Error: {str(e)}")

        self.logger.debug(f"[PARSER] Fixed JSON: {fixed_response}")
        return fixed_response

    @versioned("1.0.0")
    def _handle_alternative_language_keys(self, translations: Dict[str, str]) -> Dict[str, str]:
        updated_translations = {}
        for target_lang, alternatives in LANGUAGE_ALTERNATIVES.items():
            for alt in alternatives:
                if alt in translations:
                    updated_translations[target_lang] = translations[alt]
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
