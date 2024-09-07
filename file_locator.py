"""
File Locator module for the Language Translator script.

This module implements a system for locating and processing Localization.txt files,
supporting multithreading and integration with batch management.

Features:
* Recursively searches for Localization.txt files in a given directory
* Processes each Localization.txt file, extracting entries for translation
* Integrates with BatchManager for efficient translation processing
* Supports multithreading for parallel file processing
* Implements error handling and logging for file operations
* Writes translated content back to new files

Class Definitions:
    FileLocator
        Methods:
            list_localization_files: Recursively finds all Localization.txt files in a directory
            process_file: Processes a single Localization.txt file
            _parse_localization_file: Parses the content of a Localization.txt file
            process_directory: Processes all Localization.txt files in a directory
            _safe_process_file: Wrapper method for safe file processing with error handling

Logic Flows:
* The process_directory method initiates the file processing workflow
* For each Localization.txt file found, a new thread is created to process it
* Each file is parsed to extract entries needing translation
* Translations are obtained using the BatchManager
* Translated content is written back to new .translated.txt files

Notes:
* Ensure proper error handling when dealing with file operations
* Consider implementing a progress tracking system for large directories
* Be mindful of memory usage when processing large files

Lessons Learned:
* Problem: Inefficient file searching in large directories
  Solution:
  - Implemented a more efficient recursive search using os.walk:
    def list_localization_files(self, directory: str) -> List[str]:
        localization_files = []
        for root, _, files in os.walk(directory):
            for file in files:
                if file.lower() == "localization.txt":
                    localization_files.append(os.path.join(root, file))
        return localization_files
  - This approach is more memory-efficient and faster for large directory structures

* Problem: Memory issues when processing large Localization.txt files
  Solution:
  - Implemented a generator-based parsing method:
    def _parse_localization_file(self, file_path: str):
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)  # Skip header
            for row in reader:
                # Check if the row has at least 6 columns (up to and including 'english')
                if len(row) >= 6:
                    entry = {
                        'Key': row[0],
                        'File': row[1],
                        'Type': row[2],
                        'UsedInMainMenu': row[3],
                        'NoTranslate': row[4],
                        'english': row[5],
                        'Context / Alternate Text': row[6] if len(row) > 6 else ''
                    }
                    # Add translations if they exist
                    for i, lang in enumerate(header[7:], start=7):
                        if i < len(row):
                            entry[lang] = row[i]
                    yield entry
                else:
                    self.logger.warning(f"Skipping malformed row in {file_path}: {row}")
  - This allows for processing files line by line, reducing memory usage

* Problem: Lack of error handling in file processing
  Solution:
  - Implemented a _safe_process_file method with comprehensive error handling:
    def _safe_process_file(self, file_path: str):
        try:
            self.process_file(file_path)
        except Exception as e:
            self.logger.error(f"Error processing file {file_path}: {str(e)}")
            self.logger.exception("Exception details:")
  - This ensures that errors in processing one file don't crash the entire script

* Problem: Inefficient use of multithreading
  Solution:
  - Implemented a thread pool for controlled concurrency:
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = [executor.submit(self._safe_process_file, file_path) for file_path in localization_files]
        concurrent.futures.wait(futures)
  - This allows for better control over the number of concurrent file processing operations

* Problem: Lack of progress tracking for large directories
  Solution:
  - Implemented a progress bar using the tqdm library:
    from tqdm import tqdm
    with tqdm(total=len(localization_files), desc="Processing files") as pbar:
        for file_path in localization_files:
            self._safe_process_file(file_path)
            pbar.update(1)
  - This provides visual feedback on the progress of file processing

* Problem: Inconsistent handling of file paths across different operating systems
  Solution:
  - Used pathlib for cross-platform compatibility:
    from pathlib import Path
    output_file = Path(file_path).with_suffix('.translated.txt')
  - This ensures consistent file path handling across different operating systems

* Problem: Difficulty in resuming interrupted processing
  Solution:
  - Implemented a checkpointing system:
    def _save_checkpoint(self, processed_files):
        with open('checkpoint.json', 'w') as f:
            json.dump(processed_files, f)
    
    def _load_checkpoint(self):
        if os.path.exists('checkpoint.json'):
            with open('checkpoint.json', 'r') as f:
                return set(json.load(f))
        return set()
  - This allows the script to resume from where it left off if interrupted

* Problem: Inefficient repeated translations of common phrases
  Solution:
  - Implemented a local cache for common phrases:
    self.phrase_cache = {}
    
    def _get_translation(self, text):
        if text in self.phrase_cache:
            return self.phrase_cache[text]
        translation = self.batch_manager.translate_with_batching(text, TARGET_LANGUAGES)
        self.phrase_cache[text] = translation
        return translation
  - This reduces API calls for frequently occurring phrases within a file

"""

# Standard library imports
import os
import csv
import asyncio
import concurrent.futures
from typing import List, Dict, Any
import traceback
import functools

# Third-party imports
# Local application imports
from config import TARGET_LANGUAGES, versioned, MAX_WORKERS, deprecated
from batch_manager import BatchManager  
from debug_logging import LTLogger
from writer_localization import LocalizationWriter 
from statistics_manager import StatisticsManager  
from translation_manager import TranslationManager
from utils import check_exit_flag

@versioned("1.5.2")
class FileLocator:
    """
    Locates and processes Localization.txt files for translation.

    This class implements a system for finding Localization.txt files in a given directory,
    processing their contents, and managing the translation process for each file.

    Attributes:
        logger (Logger): Logger instance for debugging and error reporting.
        batch_manager (BatchManager): Manages batch translation processes.
        stats_manager (StatisticsManager): Tracks and reports usage statistics.
        translation_manager (TranslationManager): Manages translation processes.

    Dependencies:
        - BatchManager: Required for managing batch translation processes of file contents.
        - Logger: Used for logging debug information and errors throughout the file processing.
        - StatisticsManager: Used for tracking statistics related to file processing and translations.
        - TranslationManager: Core component for managing the actual translation process of file contents.

    Methods:
        list_localization_files: Recursively finds all Localization.txt files in a directory.
        process_file: Processes a single Localization.txt file.
        _is_valid_entry: Checks if an entry has all required fields.
        _process_entry: Processes a single entry for translation.
        process_directory: Processes all Localization.txt files in a directory.
        _safe_process_file: Wrapper method for safe file processing with error handling.

    Version History:
        1.0.0 - Initial implementation with basic file locating and processing.
        1.3.0 - Implemented error handling and logging for file operations.
        1.4.0 - Added integration with BatchManager for efficient translation processing.
        1.5.0 - Improved parsing of Localization.txt files.
        1.5.1 - Enhanced error reporting and handling during file processing.
        1.5.2 - Removed multithreading support to align with application-wide changes.
        2.0.0 - Major refactor of process_file method.
        2.0.1 - Added _is_valid_entry and _process_entry methods for better entry handling.
    """

    @versioned("1.5.2")
    def __init__(self, logger: LTLogger, batch_manager: BatchManager, 
                 stats_manager: StatisticsManager, translation_manager: TranslationManager):
        self.logger = logger
        self.batch_manager = batch_manager
        self.stats_manager = stats_manager
        self.translation_manager = translation_manager
        self.logger.debug("[FILE] FileLocator initialized")

    @versioned("1.4.0")
    def list_localization_files(self, directory: str) -> List[str]:
        localization_files = []
        for root, _, files in os.walk(directory):
            for file in files:
                if file.lower() == "localization.txt":
                    localization_files.append(os.path.join(root, file))
        return localization_files

    @versioned("2.0.2")
    def process_file(self, file_path: str):
        self.logger.info(f"Processing file: {file_path}")
        output_file = file_path.replace('.txt', '.translated.txt')
        
        entries = []
        translations = {}
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if self._is_valid_entry(row):
                    entries.append(row)
                    # Initialize translations for this entry
                    translations[row['Key']] = {'english': row['english']}
                    for lang in TARGET_LANGUAGES:
                        if lang in row and row[lang]:
                            translations[row['Key']][lang] = row[lang]
                else:
                    self.logger.warning(f"Skipping invalid entry: {row}")

        self.logger.debug(f"[FILE_LOCATOR] Parsed {len(entries)} entries from {file_path}")
        self.logger.debug(f"[FILE_LOCATOR] Sample entry: {entries[0] if entries else 'No entries found'}")

        for entry in entries:
            if not all(lang in translations[entry['Key']] and translations[entry['Key']][lang] not in (None, '') for lang in TARGET_LANGUAGES):
                new_translations = self._process_entry(entry)
                translations[entry['Key']].update(new_translations)
        
        self.logger.debug(f"[FILE_LOCATOR] Translations: {list(translations.keys())[:5]}...")
        
        localization_writer = LocalizationWriter(self.logger, self.translation_manager)
        localization_writer.write_translations(file_path, output_file, entries, translations)
        
        self.logger.info(f"Translations written to {output_file}")

    def _is_valid_entry(self, row):
        required_fields = ['Key', 'File', 'Type', 'UsedInMainMenu', 'NoTranslate', 'english']
        return all(field in row and row[field] is not None for field in required_fields)

    def _process_entry(self, entry):
        english_text = entry['english']
        key = self.batch_manager.cache_manager.obtain_id(english_text)
        cached_translation = self.batch_manager.cache_manager.get(english_text)
        
        if cached_translation:
            return cached_translation

        new_translation = self.batch_manager.translate_with_batching(english_text)
        
        # Filter the translations to include only TARGET_LANGUAGES
        filtered_translation = {lang: trans for lang, trans in new_translation.items() if lang in TARGET_LANGUAGES}

        if not isinstance(filtered_translation, dict):
            self.logger.error(f"Invalid translation type: {type(filtered_translation)}. Expected dict.")
            return {}

        self.batch_manager.cache_manager.set(english_text, filtered_translation)
        return filtered_translation

    @versioned("1.5.2")
    def process_directory(self, directory: str):
        localization_files = self.list_localization_files(directory)
        self.logger.info(f"Found {len(localization_files)} Localization.txt files")

        for file_path in localization_files:
            if check_exit_flag():
                self.logger.info("Exiting file processing due to interrupt")
                break
            self._safe_process_file(file_path)

    @versioned("1.5.2")
    def _safe_process_file(self, file_path: str):
        if check_exit_flag():
            return
        try:
            self.process_file(file_path)
        except Exception as e:
            self.logger.error(f"Error processing file {file_path}: {str(e)}")
            self.logger.error(f"Exception details: {traceback.format_exc()}")

    @deprecated
    def _parse_localization_file(self, file_path: str):
        entries = []
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            header = next(reader)  # Skip header
            for row in reader:
                # Check if the row has at least 6 columns (up to and including 'english')
                if len(row) >= 6:
                    entry = {
                        'Key': row[0],
                        'File': row[1],
                        'Type': row[2],
                        'UsedInMainMenu': row[3],
                        'NoTranslate': row[4],
                        'english': row[5],
                        'Context / Alternate Text': row[6] if len(row) > 6 else ''
                    }
                    # Add translations if they exist
                    for i, lang in enumerate(header[7:], start=7):
                        if i < len(row):
                            entry[lang] = row[i]
                    yield entry
                else:
                    self.logger.warning(f"[FILE_LOCATOR] Skipping malformed row in {file_path}: {row}")
        self.logger.debug(f"[FILE_LOCATOR] Parsed {len(entries)} entries from {file_path}")
        self.logger.debug(f"[FILE_LOCATOR] Sample entry: {entries[0] if entries else 'No entries found'}")
        return entries

    @deprecated
    def process_directory(self, directory: str):
        localization_files = self.list_localization_files(directory)
        self.logger.info(f"Found {len(localization_files)} Localization.txt files")

        for file_path in localization_files:
            if check_exit_flag():
                self.logger.info("Exiting file processing due to interrupt")
                break
            self._safe_process_file(file_path)

    @deprecated
    def _safe_process_file(self, file_path: str):
        if check_exit_flag():
            return
        try:
            self.process_file(file_path)
        except Exception as e:
            self.logger.error(f"Error processing file {file_path}: {str(e)}")
            self.logger.error(f"Exception details: {traceback.format_exc()}")        
