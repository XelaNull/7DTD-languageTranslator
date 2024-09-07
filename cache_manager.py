"""
Cache Management module for the Language Translator script.

This module handles the caching of translations to improve efficiency and reduce API calls.

Features:
* Implements a pickle-based caching system for storing and retrieving translations
* Provides methods for encoding and decoding cache entries to handle special characters
* Manages cache operations including storing, retrieving, and clearing translations
* Implements a unique ID system for efficient lookup of translations
* Provides statistics on cache usage and performance
* Supports thread-safe operations for concurrent access
* Implements temporary caching for handling interruptions during translation process
* Supports storing and retrieving partial translations for improved resilience

Class Definitions:
    CacheManager
        Methods:
            set: Stores a translation in the cache with base64 encoding
            get: Retrieves a translation from the cache, decoding from base64
            clear_cache: Removes all entries from the cache
            get_cache_stats: Returns statistics about the current state of the cache
            obtain_id: Generates a unique ID for a given English text
            set_temp: Stores a translation in a temporary cache
            get_temp: Retrieves a translation from the temporary cache
            promote_temp: Moves a translation from temporary to permanent cache
            missing_langs_temp: Returns a dict list of languages that are missing from the temporary cache
        Variables:
            cache: Dict[str, Dict[str, str]]
            id_to_text: Dict[str, str]
            used_ids: Set[str]
            temp_cache: Dict[str, Dict[str, str]]

Logic Flows:
* Cache entries are stored using unique IDs as keys, with translations stored as nested dictionaries
* Temporary cache entries are created during batch translations and promoted to permanent cache upon successful completion
* Cache statistics are updated in real-time as translations are stored and retrieved
* Partial translations are stored in the temporary cache and can be promoted to the permanent cache when complete




Notes:
* All keys and values are stored with base64 encoding to prevent issues with special characters
* The cache file is regularly saved to disk to prevent data loss
* A lock mechanism is used to ensure thread-safety for all cache operations
* A temporary cache is used to store translations during batch processing

Lessons Learned:
* Problem: Cache entries with special characters causing encoding issues
  Solution:
  - Implemented base64 encoding for all cache keys and values
  - In the store_translation method:
    encoded_key = base64.b64encode(key.encode('utf-8')).decode('utf-8')
    encoded_value = {lang: base64.b64encode(trans.encode('utf-8')).decode('utf-8') for lang, trans in value.items()}
    self.cache[encoded_key] = encoded_value
  - In the get_translation method:
    encoded_key = base64.b64encode(key.encode('utf-8')).decode('utf-8')
    encoded_value = self.cache.get(encoded_key, {})
    return {lang: base64.b64decode(trans.encode('utf-8')).decode('utf-8') for lang, trans in encoded_value.items()}
  - Added error handling to catch and log any encoding/decoding errors

* Problem: Race conditions when multiple threads access the cache simultaneously
  Solution:
  - Implemented a threading.Lock() mechanism
  - Wrapped all cache access methods with the lock:
    def store_translation(self, key: str, value: Dict[str, str]):
        with self.lock:
            # Existing store_translation logic
  - Applied the lock to all methods that read or write to the cache
  - Ensured that the lock is released even if an exception occurs by using a try-finally block

* Problem: Inefficient lookup of translations by English text
  Solution:
  - Implemented a unique ID system for cache entries
  - Created an id_to_text dictionary to map IDs to original English text
  - In the obtain_id method:
    while True:
        new_id = str(random.randint(1000000000, 9999999999))
        if new_id not in self.used_ids:
            self.used_ids.add(new_id)
            self.id_to_text[new_id] = text
            return new_id
  - Modified store_translation and get_translation to use IDs instead of full text keys

* Problem: Risk of losing translations due to script interruptions during batch processing
  Solution:
  - Implemented a temporary caching system
  - Added methods for handling temporary cache entries:
    def set_temp(self, temp_key: str, value: Dict[str, str]):
        with self.lock:
            self.temp_cache[temp_key] = value
    def get_temp(self, temp_key: str) -> Dict[str, str]:
        with self.lock:
            return self.temp_cache.get(temp_key, {})
    def promote_temp(self, temp_key: str, permanent_key: str):
        with self.lock:
            if temp_key in self.temp_cache:
                self.cache[permanent_key] = self.temp_cache.pop(temp_key)
  - Modified the batch translation process to use temporary cache entries and promote them upon successful completion

* Problem: Cache size growing too large over time
  Solution:
  - Implemented a cache size limit and an eviction policy
  - Added a MAX_CACHE_SIZE constant (e.g., 10000 entries)
  - In the store_translation method:
    if len(self.cache) >= MAX_CACHE_SIZE:
        oldest_key = min(self.cache.keys(), key=lambda k: self.cache[k].get('last_accessed', 0))
        del self.cache[oldest_key]
  - Added a 'last_accessed' timestamp to each cache entry, updated on each access
  - Implemented a method to clear a portion of the cache:
    def clear_portion(self, portion: float):
        with self.lock:
            num_to_remove = int(len(self.cache) * portion)
            sorted_keys = sorted(self.cache.keys(), key=lambda k: self.cache[k].get('last_accessed', 0))
            for key in sorted_keys[:num_to_remove]:
                del self.cache[key]

* Problem: Difficulty in debugging cache-related issues
  Solution:
  - Implemented comprehensive logging for cache operations
  - Added debug log messages for key cache operations:
    self.logger.debug(f"Storing translation for key: {key}")
    self.logger.debug(f"Retrieved translation for key: {key}")
    self.logger.debug(f"Cache miss for key: {key}")
  - Implemented a method to dump cache contents for debugging:
    def dump_cache(self, limit: int = 10):
        with self.lock:
            for i, (key, value) in enumerate(list(self.cache.items())[:limit]):
                self.logger.debug(f"Cache entry {i}: {key}: {value}")
  - Added error logging for exceptional cases:
    except Exception as e:
        self.logger.error(f"Error in cache operation: {str(e)}")

* Problem: Risk of promoting incomplete translations from temporary to permanent cache
  Solution:
  - Implemented a missing_langs_temp method to check for missing language translations in temporary cache entries
  - Modified the promote_temp method to use missing_langs_temp for verification before promotion
  - In the missing_langs_temp method:
    def missing_langs_temp(self, key: str) -> Dict[str, List[str]]:
        with self.lock:
            temp_entry = self.temp_cache.get(key, {})
            existing_langs = set(temp_entry.keys())
            missing_langs = set(self.target_languages) - existing_langs
            return {"missing": list(missing_langs)}
  - Updated the promote_temp method to use missing_langs_temp:
    def promote_temp(self, temp_key: str, permanent_key: str):
        with self.lock:
            missing_langs = self.missing_langs_temp(temp_key)
            if not missing_langs["missing"]:
                if temp_key in self.temp_cache:
                    self.cache[permanent_key] = self.temp_cache.pop(temp_key)
                    self._save_cache()
                    self.logger.debug(f"Promoted temporary translation to permanent cache: {temp_key} -> {permanent_key}")
                else:
                    self.logger.warning(f"Attempted to promote non-existent temporary key: {temp_key}")
            else:
                self.logger.warning(f"Cannot promote incomplete translation for key: {temp_key}. Missing languages: {', '.join(missing_langs['missing'])}")
  - This ensures that only complete translations are promoted to the permanent cache, maintaining data integrity
"""

# Standard library imports
import pickle
import threading
from pathlib import Path
from typing import Dict, Any, Optional, Union
import random  # Add this import at the top of the file

# Local application imports
from config import TARGET_LANGUAGES, CACHE_FILE, versioned
from debug_logging import LTLogger
from statistics_manager import StatisticsManager

@versioned("2.2.2")
class CacheManager:
    """
    Manages caching of translation results.

    This class handles the storage, retrieval, and management of cached translations,
    including both permanent and temporary caches.

    Attributes:
        logger (Logger): Logger instance for debugging and error reporting.
        cache_file (Path): Path to the permanent cache file.
        stats_manager (StatisticsManager): Instance for tracking statistics.
        cache (Dict[str, Dict[str, str]]): In-memory storage for permanent cache.
        temp_cache (Dict[str, Dict[str, str]]): In-memory storage for temporary cache.
        text_to_id (Dict[str, str]): Mapping of text to unique IDs.
        used_ids (Set[str]): Set of used unique IDs.
        lock (threading.Lock): Lock for thread-safe operations.

    Dependencies:
        - Logger: Used for logging debug information and errors related to cache operations.
        - StatisticsManager: Used for tracking statistics related to cache operations.

    Methods:
        get: Retrieve a cached translation.
        set: Store a translation in the permanent cache.
        set_temp: Store a translation in the temporary cache.
        get_temp: Retrieve a translation from the temporary cache.
        promote_temp: Promote a temporary cache entry to the permanent cache.
        obtain_id: Generate or retrieve a unique ID for a given text.
        missing_langs_temp: Check for missing language translations in the temporary cache.
        clear_cache: Clear all caches and reset the manager.
        get_cache_stats: Get statistics about the current cache state.

    Version History:
        1.0.0 - Initial implementation with basic caching functionality.
        1.5.0 - Added support for temporary caching and promotion.
        1.8.0 - Implemented unique ID generation and management.
        2.0.0 - Added support for missing language checks and cache statistics.
        2.1.0 - Improved error handling and logging for cache operations.
        2.2.0 - Implemented thread-safe operations for concurrent access.
        2.2.2 - Updated initialization to include StatisticsManager and reordered parameters.
    """

    @versioned("2.2.2")
    def __init__(self, logger: 'Logger', cache_file: str, stats_manager: 'StatisticsManager'):
        self.logger = logger
        self.cache_file = Path(cache_file)
        self.stats_manager = stats_manager
        self.cache = {}
        self.temp_cache = {}
        self.text_to_id = {}
        self.used_ids = set()
        self.lock = threading.Lock()

        self._load_cache()
        self.logger.info(f"Cache initialized with {len(self.cache)} entries")

        self.target_languages = TARGET_LANGUAGES

    @versioned("2.0.6")
    def _load_cache(self):
        if self.cache_file.exists():
            try:
                with self.cache_file.open('rb') as f:
                    loaded_data = pickle.load(f)
                    self.cache = loaded_data.get('cache', {})
                    self.used_ids = loaded_data.get('used_ids', set())
                    self.temp_cache = loaded_data.get('temp_cache', {})
                    self.text_to_id = loaded_data.get('text_to_id', {})
                self.logger.info(f"Cache loaded from {self.cache_file}")
            except Exception as e:
                self.logger.error(f"Error loading cache: {str(e)}")
                self.cache = {}
                self.used_ids = set()
                self.temp_cache = {}
                self.text_to_id = {}
        else:
            self.logger.info("No existing cache found. Starting with an empty cache.")

    @versioned("2.0.6")
    def _save_cache(self):
        try:
            self.cache_file.parent.mkdir(parents=True, exist_ok=True)
            with self.cache_file.open('wb') as f:
                pickle.dump({
                    'cache': self.cache,
                    'used_ids': self.used_ids,
                    'temp_cache': self.temp_cache,
                    'text_to_id': self.text_to_id
                }, f)
        except Exception as e:
            self.logger.error(f"Error saving cache: {str(e)}")

    @versioned("2.0.7")
    def save_cache(self):
        """
        Public method to save the cache.
        This method is intended to be called externally when needed,
        such as during graceful shutdown or periodic saves.
        """
        self._save_cache()
        self.logger.info("Cache saved manually")

    @versioned("2.0.6")
    def get(self, text: str) -> Optional[Dict[str, str]]:
        result = self.cache.get(text)
        if result is not None:
            self.stats_manager.increment_stat("cache_hits")
            return result
        self.stats_manager.increment_stat("cache_misses")
        return None

    @versioned("2.2.1")
    def set(self, text: str, translations: Dict[str, str]):
        unique_id = self.obtain_id(text)
        existing_translations = self.cache.get(unique_id, {})
        existing_translations.update(translations)
        
        missing_languages = set(self.target_languages) - set(existing_translations.keys())
        if missing_languages:
            self.logger.debug(f"[CACHE] Partial translation stored for ID: {unique_id}. Missing languages: {', '.join(missing_languages)}")
            self.temp_cache[unique_id] = existing_translations
        else:
            self.cache[unique_id] = existing_translations
            if unique_id in self.temp_cache:
                del self.temp_cache[unique_id]
        
        self._save_cache()

    @versioned("2.0.7")
    def obtain_id(self, text: str) -> str:
        if text in self.text_to_id:
            return self.text_to_id[text]
        while True:
            new_id = str(random.randint(1000000000, 9999999999))
            if new_id not in self.used_ids:
                self.used_ids.add(new_id)
                self.text_to_id[text] = new_id
                # Store the English text in the temporary cache
                self.temp_cache[new_id] = {'english': text}
                self._save_cache()
                self.logger.debug(f"[CACHE] New ID {new_id} created for text: {text[:50]}...")
                return new_id

    @versioned("2.0.4")
    def _is_valid_translation(self, translation: Dict[str, str]) -> bool:
        if not isinstance(translation, dict):
            self.logger.error(f"Invalid translation type: {type(translation)}. Expected dict.")
            return False

        missing_languages = set(self.target_languages) - set(translation.keys())
        if missing_languages:
            self.logger.error(f"Missing translations for languages: {', '.join(missing_languages)}")
            return False

        for lang, trans in translation.items():
            if not isinstance(trans, str) or not trans.strip():
                self.logger.error(f"Empty or invalid translation for language: {lang}")
                return False

        return True

    @versioned("2.0.4")
    def get_cache_size(self) -> int:
        return len(self.cache)

    @versioned("2.0.4")
    def clear_cache(self):
        self.cache.clear()
        self.used_ids.clear()
        self.temp_cache.clear()
        self.text_to_id.clear()
        self._save_cache()
        self.logger.info("Cache cleared")

    @versioned("2.0.4")
    def get_cache_stats(self) -> Dict[str, Any]:
        total_entries = len(self.cache)
        languages = set()
        for translations in self.cache.values():
            languages.update(translations.keys())
        return {
            "total_entries": total_entries,
            "languages": list(languages),
            "cache_file_size": self.cache_file.stat().st_size if self.cache_file.exists() else 0
        }

    @versioned("2.2.0")
    def set_temp(self, unique_id: str, translations: Dict[str, str]):
        existing_translations = self.temp_cache.get(unique_id, {})
        existing_translations.update(translations)
        self.temp_cache[unique_id] = existing_translations
        self._save_cache()

    @versioned("2.0.4")
    def get_temp(self, key: str, log: bool = False) -> Optional[str]:
        value = self.temp_cache.get(key)
        if log and value is not None:
            self.logger.debug(f"Retrieved temporary translation for key: {key}")
        return value

    @versioned("2.0.8")
    def missing_langs_temp(self, key: str) -> dict[str, list[str]]:
        """
        Check the temporary cache for missing language translations.

        Args:
            key (str): The unique ID or English text to check.

        Returns:
            Dict[str, List[str]]: A dictionary with 'missing' key containing a list of missing languages.
        """
        temp_entry = self.temp_cache.get(key, {})
        existing_langs = set(temp_entry.keys())
        missing_langs = set(self.target_languages) - existing_langs
        return {"missing": list(missing_langs)}

    @versioned("2.3.0")
    def promote_temp(self, temp_key: str, permanent_key: str):
        """
        Promote a temporary cache entry to the permanent cache if it's complete.

        Args:
            temp_key (str): The key for the temporary cache entry.
            permanent_key (str): The key for the permanent cache entry.
        """
        if temp_key in self.temp_cache:
            temp_translations = self.temp_cache[temp_key]
            
            # Check for all required languages and non-null values
            missing_languages = []
            for lang in self.target_languages + ['english']:
                if lang not in temp_translations or not temp_translations[lang].strip():
                    missing_languages.append(lang)
            
            if not missing_languages:
                self.cache[permanent_key] = self.temp_cache.pop(temp_key)
                self._save_cache()
                self.logger.info(f"[CACHE] Promoted complete translation for ID: {temp_key} to permanent cache")
            else:
                missing_langs_str = ', '.join(missing_languages)
                self.logger.warning(f"[CACHE] Cannot promote incomplete translation for ID: {temp_key}. Missing or empty translations for: {missing_langs_str}")
        else:
            self.logger.warning(f"[CACHE] Attempted to promote non-existent temporary key: {temp_key}")