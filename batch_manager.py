"""
Batch Management module for the Language Translator script.

This module handles the batching strategies for processing translations efficiently.

Features:
* Inherently supports multithreading, with each thread handling its own Localization.txt file to process
* Implements two-tier processing batching strategies: Estimation-Based and Single Language Translation
* Manages the translation process, including collecting translations, sanity cleanup, and writing out results
* Dynamically adjusts batch sizes based on token estimation and API responses
* Seamlessly switches between batching strategies based on API responses
* Tracks and manages remaining languages to translate
* Implements retry logic for failed translations
* Ensures immediate caching of translations to preserve paid results

Class Definitions:
    BatchManager
        Methods:
            translate
            _translate_token_based
            _translate_batch

    EntryProcessor
        Methods:
            MissingLanguageCount
            MissingLanguages
            CollectTranslations
            SanityCleanup
            WriteOutTranslations
            WriteOutStatistics
            WriteOutCache

Logic Flows:
* Each entry from a Localization.txt file starts with the Estimation strategy and moves to the Single Language Translation Strategy if estimation fails
* The Estimation-Based Batching Strategy attempts to process multiple languages at once, staying under the MAX_ALLOWED_TOKENS limit
* If a batch fails in the Estimation strategy, it reduces the batch size by half and retries, moving to Single Language strategy after 3 failures
* The Single Language Translation Strategy processes one language at a time
* The script alternates between Anthropic and ChatGPT APIs as needed
* A master loop ensures all languages are processed for each entry

Notes:
* The maximum number of threads that can run simultaneously is determined by an uppercase global variable
* Translations are immediately written to the pickle cache to ensure preservation of paid translations
* Debug logging is implemented to show token estimation and languages processed in each iteration

Lessons Learned:
* Problem: Difficulty in managing partial translations across different batching strategies
  Solution: 
  - Implemented a 'remaining_languages' list to keep track of languages yet to be translated
  - Updated the translate method to maintain a 'translation' dictionary that accumulates results
  - After each batch translation, update the 'translation' dictionary with new results
  - Remove successfully translated languages from 'remaining_languages'
  - Continue the translation process until 'remaining_languages' is empty
  - Implement a check in _translate_batch to compare the number of translated languages with the expected number
  - If incomplete, log a debug message and continue with the next batch

* Problem: Inefficient use of API tokens when translating all languages at once
  Solution: 
  - Implemented token estimation logic in _translate_token_based method
  - Use tiktoken library to estimate token count for each language translation
  - Implement a loop that adds languages to the current batch until reaching MAX_ALLOWED_TOKENS
  - Log token estimates for each language and cumulative total with debug messages
  - If estimation fails, log an error and switch to Single Language Translation Strategy
  - Adjust MAX_ALLOWED_TOKENS based on the specific API being used (Anthropic or OpenAI)
  - Implement a safety margin (e.g., 90% of MAX_ALLOWED_TOKENS) to account for estimation inaccuracies

* Problem: Frequent API failures when attempting large batches
  Solution:
  - Implement an adaptive batch size reduction mechanism in _translate_token_based
  - Start with an initial batch size based on token estimation
  - If a batch translation fails, reduce the batch size by half: initial_batch_size = max(1, initial_batch_size // 2)
  - Implement a retry counter: retry_count = 0
  - If batch translation fails, increment retry_count and retry with reduced batch size
  - If retry_count reaches MAX_ESTIMATION_RETRIES (e.g., 3), switch to Single Language Translation Strategy
  - Log each retry attempt and batch size reduction with debug messages
  - Implement exponential backoff between retries to avoid overwhelming the API

* Problem: Inconsistent handling of API responses between batching strategies
  Solution:
  - Centralize the translation logic in the _translate_batch method
  - Implement a common structure for handling API responses in both strategies
  - Use a while loop to handle partial responses: while len(translation) < len(languages) and continuation_attempts < MAX_CONTINUATION_ATTEMPTS
  - Within the loop, call self.api_manager.translate and update the translation dictionary
  - Implement continuation_attempts counter to limit the number of continuation attempts
  - Use the same error handling and logging mechanisms for both strategies
  - Standardize the return format: always return a dictionary with language codes as keys and translations as values

* Problem: Difficulty in resuming translations after API failures
  Solution:
  - Implement a continuation prompt system in _translate_batch
  - After a partial translation, extract the last completed language: last_language = self._get_last_language(partial_translation)
  - Determine remaining languages: remaining_languages = [lang for lang in languages if lang not in translation]
  - Construct a continuation prompt: f"Continue the {last_language} translation exactly where you left off, then provide translations for the remaining languages: {', '.join(remaining_languages)}."
  - Include the last 15 characters of the previous response in the continuation prompt
  - Pass the continuation prompt to the API for the next attempt
  - Implement logic to merge the continued translation with the existing partial translation

* Problem: Inefficient retrying of failed translations
  Solution:
  - Implement separate retry logic for Estimation-Based and Single Language strategies
  - For Estimation-Based strategy:
    - Implement a retry loop with a maximum number of attempts (e.g., MAX_ESTIMATION_RETRIES)
    - Reduce batch size after each failure: initial_batch_size = max(1, initial_batch_size - 1)
    - Log each retry attempt with current batch size
    - If all retries fail, switch to Single Language strategy
  - For Single Language strategy:
    - Implement a retry loop for each individual language
    - Use a separate MAX_SINGLE_RETRIES constant (e.g., 3)
    - If a single language fails after all retries, log an error and continue with the next language
    - Implement exponential backoff between retries: time.sleep(2 ** attempt)

* Problem: Lack of visibility into batching process
  Solution:
  - Implement comprehensive debug logging throughout the batching process
  - In _translate_token_based, log the token estimation for each language:
    self.logger.debug(f"[TOKEN] Estimated tokens for {lang}: {estimated_tokens}")
  - Log the cumulative token count for the current batch:
    self.logger.debug(f"[TOKEN] Cumulative tokens for current batch: {cumulative_tokens}")
  - Log when switching between strategies:
    self.logger.debug("[TOKEN] Switching to Single Language-Based Strategy")
  - Log each translation attempt:
    self.logger.debug(f"[{self.current_strategy}] Attempting translation for languages: {', '.join(batch_languages)}")
  - Log successful translations:
    self.logger.debug(f"[{self.current_strategy}] Successfully translated languages: {', '.join(translated_languages)}")
  - Implement a progress indicator showing the number of languages translated vs. total languages

* Problem: Risk of losing paid translations due to script interruptions
  Solution:
  - Implement a transaction-like system for caching translations
  - Before starting a batch translation, create a temporary cache entry:
    temp_cache_key = f"temp_{unique_id}_{timestamp}"
    self.cache_manager.set_temp(temp_cache_key, {})
  - After each successful language translation within a batch:
    temp_cache = self.cache_manager.get_temp(temp_cache_key)
    temp_cache.update({lang: translation})
    self.cache_manager.set_temp(temp_cache_key, temp_cache)
  - If the entire batch is successful, move the temporary cache to the permanent cache:
    self.cache_manager.promote_temp(temp_cache_key, unique_id)
  - If an interruption occurs, implement a recovery process that checks for and processes any existing temporary cache entries on startup
"""

# Standard library imports
from typing import List, Dict, Any, Optional, Union
import re

# Local application imports
from api_conn_manager import APIConnectionManager
from cache_manager import CacheManager
from config import (
    MAX_ALLOWED_TOKENS, INITIAL_BATCH_SIZE, TARGET_LANGUAGES, MAX_WORKERS, 
    versioned, SINGLE_RETRIES, MAX_CONTINUATION_ATTEMPTS, ESTIMATION_RETRIES, 
    SINGLE_RETRIES, MAX_CONTINUATION_ATTEMPTS, LANGUAGE_ALTERNATIVES, ANTHROPIC_API_ENABLED, OPENAI_API_ENABLED
)
from debug_logging import LTLogger
from response_parser import ResponseParser
from statistics_manager import StatisticsManager
from token_estimator import TokenEstimator
from translation_manager import TranslationManager


@versioned("2.3.1")
class BatchManager:
    """
    Manages the batch processing of translations.

    This class handles the batching of translation requests, including strategies
    for token estimation and single language translation.

    Attributes:
        logger (Logger): Logger instance for debugging and error reporting.
        api_connection_manager (APIConnectionManager): Manages API connections and rate limiting.
        cache_manager (CacheManager): Manages caching of translation results.
        stats_manager (StatisticsManager): Tracks and reports usage statistics.
        translation_manager (TranslationManager): Manages translation processes.

    Dependencies:
        - APIConnectionManager: Required for managing API connections and handling translations.
        - CacheManager: Needed for caching translation results and retrieving partial translations.
        - Logger: Used for logging debug information and errors throughout the batch process.
        - StatisticsManager: Used for tracking statistics related to batch translations.
        - TranslationManager: Core component for managing the actual translation process.

    Methods:
        translate_with_batching: Translates a batch of text to multiple languages.
        _translate_batch: Internal method to translate a batch of text.
        _translate_single: Translates a single piece of text to one language.
        _print_condensed_translations: Prints a condensed version of translations for debugging.

    Version History:
        1.0.0 - Initial implementation of batch translation management.
        2.0.0 - Added support for token estimation strategy.
        2.1.0 - Implemented single language translation strategy.
        2.2.0 - Added caching support for partial translations.
        2.2.1 - Improved error handling and logging in batch translation process.
        2.2.2 - Updated to use TranslationManager directly for translations.
        2.2.3 - Fixed issue with obtain_id method call.
        2.3.0 - Updated to pass unique_id to TranslationManager.
        2.3.1 - Updated method signatures to include unique_id.
    """

    @versioned("2.3.1")
    def __init__(self, logger: LTLogger, api_connection_manager: APIConnectionManager, 
                 cache_manager: CacheManager, stats_manager: StatisticsManager, 
                 translation_manager: TranslationManager):
        self.logger = logger
        self.api_connection_manager = api_connection_manager
        self.cache_manager = cache_manager
        self.stats_manager = stats_manager
        self.translation_manager = translation_manager
        self.token_estimator = TokenEstimator(logger)
        self.logger.debug("[BATCH] BatchManager initialized")

    @versioned("2.3.1")
    def translate_with_batching(self, text: str) -> Dict[str, str]:
        """
        Translate the given text to multiple languages using an efficient batching strategy.

        This method implements a smart batching algorithm that attempts to translate multiple
        languages in a single API call when possible, falling back to single-language translation
        when necessary. It uses token estimation to determine the optimal batch size and
        manages the translation process for all required languages.

        Args:
            text (str): The text to be translated.

        Returns:
            Dict[str, str]: A dictionary where keys are language codes and values are
            the corresponding translations.

        Raises:
            Exception: Any exception that occurs during the translation process is logged,
            but not raised to allow for continued processing of remaining languages.

        Version History:
            2.1.5 - Initial implementation with basic batching.
            2.1.6 - Added token estimation for optimal batch size.
            2.1.7 - Fixed issue with single language translation instead of batches.
            2.1.8 - Improved error handling and logging, added comprehensive docstring.
            2.1.9 - Added global API status checks.
            2.1.10 - Updated token estimation to pass api_connection_manager.
            2.2.3 - Fixed issue with obtain_id method call.
            2.3.0 - Updated to pass unique_id to TranslationManager.
            2.3.1 - Updated to obtain unique_id at the beginning of the method.

        Example:
            batch_manager = BatchManager(
                api_manager, cache_manager, logger)
            translations = batch_manager.translate_with_batching("Hello, world!")
            # translations might be {'fr': 'Bonjour, monde!', 'es': '¡Hola, mundo!', ...}

        Notes:
            - This method uses caching to avoid redundant translations.
            - It updates the cache after each successful translation (batch or single).
            - The method will attempt to translate all languages, logging errors for any
              that fail without stopping the entire process.
            - Performance may vary based on the efficiency of the token estimation and
              the reliability of the translation API.
        """
        unique_id = self.cache_manager.obtain_id(text)
        self.logger.debug(f"[BATCH] Starting translation for text: '{text[:50]}...'")
        self.logger.debug(f"[BATCH] Obtained unique ID: {unique_id}")
        
        # Check permanent cache first
        cached_translations = self.cache_manager.get(unique_id) or {}
        if cached_translations:
            self.logger.debug(f"[BATCH] Found {len(cached_translations)} cached translations in permanent cache")
            return cached_translations

        remaining_languages = self.cache_manager.missing_langs_temp(unique_id)['missing']

        while remaining_languages:
            self.logger.debug(f"[BATCH] Remaining languages: {remaining_languages}")
            
            # Estimate tokens and calculate optimal batch size
            total_tokens, optimal_batch_size, estimated_batch_tokens = self.token_estimator.estimate_tokens(
                text, remaining_languages, self.api_connection_manager
            )
            
            if optimal_batch_size > 0:
                batch_languages = remaining_languages[:optimal_batch_size]
                
                try:
                    if ANTHROPIC_API_ENABLED:
                        batch_translation = self.translation_manager.translate(text, batch_languages, unique_id)
                    elif OPENAI_API_ENABLED:
                        batch_translation = self.translation_manager.translate(text, batch_languages, unique_id)
                    else:
                        self.logger.error("[BATCH] Both APIs are disabled. Unable to process batch.")
                        return {}

                    if batch_translation:
                        for lang, translation in batch_translation.items():
                            self.cache_manager.set_temp(unique_id, {lang: translation})
                        remaining_languages = [lang for lang in remaining_languages if lang not in batch_translation]
                    else:
                        self.logger.warning("[BATCH] No translations returned from translation manager")
                        optimal_batch_size = 1  # Fall back to single language processing
                except Exception as e:
                    self.logger.error(f"[BATCH] Error in batch translation: {str(e)}")
                    optimal_batch_size = 1  # Fall back to single language processing
            else:
                self.logger.warning("[BATCH] Token estimation failed, falling back to single language processing")
                optimal_batch_size = 1

            if optimal_batch_size == 1:
                # Single language processing
                for lang in remaining_languages[:]:
                    try:
                        if ANTHROPIC_API_ENABLED:
                            single_translation = self.translation_manager.translate(text, [lang], unique_id)
                        elif OPENAI_API_ENABLED:
                            single_translation = self.translation_manager.translate(text, [lang], unique_id)
                        else:
                            self.logger.error("[BATCH] Both APIs are disabled. Unable to process single language.")
                            return {}

                        if single_translation:
                            self.cache_manager.set_temp(unique_id, single_translation)
                            self.logger.debug(f"[BATCH] Completed single language: {lang}")
                            remaining_languages.remove(lang)
                        else:
                            self.logger.warning(f"[BATCH] No translation returned for language: {lang}")
                    except Exception as e:
                        self.logger.error(f"[BATCH] Error in single language translation for {lang}: {str(e)}")

            if remaining_languages:
                self.logger.debug(f"[BATCH] Updated remaining languages: {remaining_languages}")

        if not remaining_languages:
            self.cache_manager.promote_temp(unique_id, unique_id)
            self.logger.debug(f"[BATCH] All languages translated, promoted temporary cache to permanent for ID: {unique_id}")
            self._print_condensed_translations(unique_id, text)
        else:
            self.logger.warning(f"[BATCH] Translation incomplete. Missing languages: {remaining_languages}")

        final_translations = self.cache_manager.get(unique_id) or {}
        return final_translations

    @versioned("2.3.1")
    def _translate_batch(self, text: str, unique_id: str, languages: List[str]) -> Dict[str, Dict[str, str]]:
        self.logger.debug(f"[TRANSLATE] Entering _translate_batch method with {len(languages)} languages")
        result = {}
        remaining_languages = languages.copy()

        try:
            translations = self.translation_manager.translate(text, languages, unique_id)
            if translations:
                result[unique_id] = translations
                for lang in translations.keys():
                    if lang in remaining_languages:
                        remaining_languages.remove(lang)
            
            # Save partial results to cache
            self.cache_manager.set_temp(unique_id, result.get(unique_id, {}))
            
            # Log remaining languages
            self.logger.debug(f"[TRANSLATE] Remaining languages: {remaining_languages}")
        except Exception as e:
            self.logger.error(f"[BATCH] Error in batch translation: {str(e)}")

        return result

    @versioned("2.3.1")
    def _translate_single(self, text: str, unique_id: str, language: str) -> Dict[str, str]:
        self.logger.debug(f"[TRANSLATE] Entering _translate_single method for language: {language}")
        translations = {}

        try:
            result = self.translation_manager.translate(text, [language], unique_id)
            if result:
                translations.update(result)
        except Exception as e:
            self.logger.error(f"[BATCH] Error in single language translation for {language}: {str(e)}")

        return translations

    @versioned("1.0.0")
    def _print_condensed_translations(self, unique_id: str, original_text: str):
        translations = self.cache_manager.get(unique_id)
        if translations:
            self.logger.info(f"Translations for '{original_text[:30]}...':")
            self.logger.info(f"  english: {original_text[:30]}...")
            for lang, trans in translations.items():
                self.logger.info(f"  {lang}: {trans[:30]}...")



class EntryProcessor:
    @versioned("1.8.0")
    def __init__(self, api_connection_manager: 'APIConnectionManager', cache_manager: 'CacheManager', logger: 'LTLogger'):
        self.logger = logger
        self.api_connection_manager = api_connection_manager
        self.cache_manager = cache_manager
        self.current_strategy = "TOKEN"

    @versioned("1.4.0")
    def missing_language_count(self, translations: Dict[str, str]) -> int:
        return len(TARGET_LANGUAGES) - len(translations)

    @versioned("1.7.8")
    def translate_with_batching(self, text: str, languages: List[str]) -> Dict[str, str]:
        self.logger.debug(f"[BATCH] Entering translate_with_batching method")
        unique_id = self.cache_manager.obtain_id(text)
        self.logger.debug(f"[TOKEN] Starting Token Estimation-Based Strategy for text: '{text[:30]}...'")
        self.logger.debug(f"[TOKEN] Current API: {self.api_connection_manager.get_current_api().upper()}")

        # Check cache first
        cached_translation = self.cache_manager.get(unique_id)
        if cached_translation:
            self.logger.debug(f"[TOKEN] Found cached translation for text: '{text[:30]}...'")
            if all(lang in cached_translation for lang in languages):
                return cached_translation

        # Estimate total tokens for all languages
        total_estimated_tokens, optimal_batch_size, estimated_batch_tokens = self.api_connection_manager.token_estimator.estimate_tokens(text, languages)
        
        self.logger.debug(f"[TOKEN] Total estimated tokens for all languages: {total_estimated_tokens}")
        self.logger.debug(f"[TOKEN] Optimal batch size: {optimal_batch_size} languages")
        self.logger.debug(f"[TOKEN] Estimated tokens for optimal batch: {estimated_batch_tokens}")

        translation = {}
        remaining_languages = languages.copy()

        for attempt in range(1, ESTIMATION_RETRIES + 1):
            try:
                self.logger.debug(f"[TOKEN] [RETRY {attempt}/{ESTIMATION_RETRIES}] Attempting translation with {len(remaining_languages[:optimal_batch_size])} languages")
                batch_translation = self.api_connection_manager.translation_manager.translate(text, remaining_languages[:optimal_batch_size], unique_id)
                self.logger.debug(f"[TOKEN] Received batch translation for {len(batch_translation)} languages")
                translation.update(batch_translation)
                
                remaining_languages = [lang for lang in remaining_languages if lang not in batch_translation]
                
                if not remaining_languages:
                    break
                else:
                    optimal_batch_size = max(1, optimal_batch_size - 1)
                    self.logger.debug(f"[TOKEN] Reducing batch size to {optimal_batch_size}")
            except Exception as e:
                self.logger.error(f"[TOKEN] Error in translation: {str(e)}")
                optimal_batch_size = max(1, optimal_batch_size - 1)
                self.logger.debug(f"[TOKEN] Reducing batch size to {optimal_batch_size}")

        if remaining_languages:
            self.logger.debug("[TOKEN] Switching to Single Language-Based Strategy")
            self.current_strategy = "SINGLE"
            for attempt in range(1, SINGLE_RETRIES + 1):
                try:
                    for lang in remaining_languages:
                        self.logger.debug(f"[SINGLE] [RETRY {attempt}/{SINGLE_RETRIES}] Translating {lang}")
                        single_translation = self.api_connection_manager.translation_manager.translate(text, [lang], unique_id)
                        translation.update(single_translation)
                    break
                except Exception as e:
                    self.logger.error(f"[SINGLE] Error in translation: {str(e)}")

        self.cache_manager.set(unique_id, translation)
        self.logger.debug(f"[BATCH] Exiting translate_with_batching method")
        return translation

    @versioned("1.4.0")
    def collect_translations(self, text: str, languages: List[str]) -> Dict[str, str]:
        return self.api_connection_manager.translate(text, languages, unique_id)

    @versioned("1.4.0")
    def sanity_cleanup(self, translations: Dict[str, str]) -> Dict[str, str]:
        return {lang: translation.replace('"', '\\"').replace('\n', '\\n') 
                for lang, translation in translations.items()}

    @versioned("1.4.0")
    def write_out_translations(self, translations: Dict[str, str]):
        # Implement translation writing logic (e.g., using LocalizationWriter)
        pass

    @versioned("1.4.0")
    def write_out_statistics(self):
        self.stats_manager.save_stats()

    @versioned("1.4.0")
    def write_out_cache(self, key: str, translations: Dict[str, str]):
        for lang, translation in translations.items():
            self.cache_manager.add_to_cache(key, lang, translation)

class EstimationBasedStrategy:
    @versioned("1.4.0")
    def __init__(self, entry_processor: EntryProcessor, logger: LTLogger):
        self.entry_processor = entry_processor
        self.logger = logger

class SingleLanguageStrategy:
    @versioned("1.4.0")
    def __init__(self, entry_processor: EntryProcessor, logger: LTLogger):
        self.entry_processor = entry_processor
        self.logger = logger

    @versioned("1.4.0")
    def single_language_translation(self, text: str, missing_languages: List[str]) -> Dict[str, str]:
        translations = {}
        for lang in missing_languages:
            try:
                self.logger.debug(f"Attempting to translate single language: {lang}")
                translation = self.entry_processor.collect_translations(text, [lang])
                translations.update(translation)
            except Exception as e:
                self.logger.error(f"Error translating {lang}: {str(e)}")
        return translations
