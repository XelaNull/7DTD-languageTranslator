"""
Localization Writing module for the Language Translator script.

This module handles the writing of translated content back into Localization.txt files.

Features:
* Implements a custom CSV writer to handle the specific format of Localization.txt files
* Manages the writing of translations while preserving the original file structure
* Handles proper quoting of fields as per the Localization.txt standards
* Implements error handling and logging for file writing operations
* Supports writing of partial translations (only translated fields are updated)

Class Definitions:
    LocalizationWriter
        Methods:
            write_translations: Writes translated content to a new Localization.txt file
            _format_value: Formats a value for writing, including proper quoting and escaping
            _write_row: Writes a single row to the CSV file
            sanity_check: Performs a sanity check on the written file

Logic Flows:
* The write_translations method reads the original file, updates translations, and writes to a new file
* Each row is processed individually, updating only the translated fields
* The _format_value method ensures proper formatting of each field before writing
* After writing, a sanity check is performed to verify the integrity of the output file

Notes:
* The standard header for all Localization.txt files is:
  Key,File,Type,UsedInMainMenu,NoTranslate,english,Context / Alternate Text,german,latam,french,italian,japanese,koreana,polish,brazilian,russian,turkish,schinese,tchinese,spanish
* The following fields/columns should have double quotes around non-null values:
  english,Context / Alternate Text,german,latam,french,italian,japanese,koreana,polish,brazilian,russian,turkish,schinese,tchinese,spanish
* Linefeed should be presented in the value as \n
* Both " and \n are expected to show up in the values and are handled appropriately

Lessons Learned:
* Problem: Standard CSV writers don't handle the specific requirements of Localization.txt files
  Solution:
  - Implemented a custom writing method that doesn't rely on csv.writer
  - Created a _write_row method to handle the specifics of each row:
    def _write_row(self, file, row):
        formatted_row = [self._format_value(field, i) for i, field in enumerate(row)]
        file.write(','.join(formatted_row) + '\n')
  - This allows for fine-grained control over quoting and escaping

* Problem: Inconsistent handling of linefeeds in translations
  Solution:
  - Implemented a consistent approach to handling linefeeds in the _format_value method:
    value = value.replace('\n', '\\n')  # Replace actual linefeeds with \n
    if column in QUOTED_COLUMNS:
        value = value.replace('"', '""')  # Escape existing double quotes
        return f'"{value}"'
  - This ensures that linefeeds are always represented as \n in the output file

* Problem: Difficulty in verifying the integrity of written files
  Solution:
  - Implemented a sanity_check method to verify the output file:
    def sanity_check(self, file_path):
        with open(file_path, 'r', encoding='utf-8') as file:
            reader = csv.reader(file)
            header = next(reader)
            if header != EXPECTED_HEADER:
                raise ValueError("Header does not match expected format")
            # Additional checks for each row...
  - This helps catch any issues with the writing process immediately

* Problem: Performance issues when writing large files
  Solution:
  - Implemented buffered writing to improve performance:
    buffer = []
    for row in reader:
        # Process row...
        buffer.append(formatted_row)
        if len(buffer) >= 1000:
            file.writelines(buffer)
            buffer = []
    if buffer:
        file.writelines(buffer)
  - This reduces the number of write operations, significantly improving performance for large files

* Problem: Difficulty in handling partial translations
  Solution:
  - Modified the write_translations method to update only translated fields:
    for i, lang in enumerate(TARGET_LANGUAGES, start=7):
        if lang in translations.get(key, {}):
            row[i] = translations[key][lang]
  - This allows for writing files even when only some languages have been translated

* Problem: Inconsistent handling of empty fields
  Solution:
  - Updated the _format_value method to handle empty fields consistently:
    if not value:
        return '""' if column in QUOTED_COLUMNS else ''
  - This ensures that empty fields are properly quoted or left blank as appropriate

* Problem: Difficulty in debugging writing issues
  Solution:
  - Implemented detailed logging throughout the writing process:
    self.logger.debug(f"Writing translations to {output_file}")
    self.logger.debug(f"Total rows to write: {len(list(reader))}")
    self.logger.debug(f"Sample row after translation: {row}")
  - This provides visibility into the writing process, making it easier to identify and resolve issues
"""

# Standard library imports
from typing import List, Dict, Optional
from pathlib import Path
import csv

# Local application imports
from config import EXPECTED_HEADER, QUOTED_COLUMNS, versioned, TARGET_LANGUAGES
from debug_logging import LTLogger
from translation_manager import TranslationManager

class LocalizationWriter:
    """
    Handles writing translated content to localization files.

    This class is responsible for writing translated content to appropriate
    localization files, managing file operations, and ensuring proper formatting.

    Attributes:
        logger (Logger): Logger instance for debugging and error reporting.
        translation_manager (TranslationManager): Manages translation processes.

    Dependencies:
        - Logger: Used for logging debug information and errors during file writing.
        - TranslationManager: Used for managing translations and retrieving translated content.

    Methods:
        write_translations: Writes translated content to localization files.
        _format_value: Formats a single value for writing.
        _write_row: Writes a single row to the output file.
        _append_completed_translations: Appends completed translations to the output file.
        sanity_check: Performs a sanity check on the written file.
        _count_entries: Counts the number of entries in a file.
        _split_line: Splits a CSV line into fields.

    Version History:
        1.0.0 - Initial implementation with basic file writing functionality.
        1.9.3 - Added support for multiple language files and improved formatting.
        2.0.0 - Implemented error handling and logging for file operations.
        2.3.0 - Improved sanity checking and error reporting.
        2.5.0 - Enhanced write_translations method with better error handling and retranslation support.
    """

    @versioned("2.0.0")
    def __init__(self, logger: LTLogger, translation_manager: Optional[TranslationManager] = None):
        self.logger = logger
        self.translation_manager = translation_manager
        self.logger.debug("[WRITER] LocalizationWriter initialized")

    @versioned("1.9.3")
    def _format_value(self, column: str, value: str) -> str:
        if value is None or value == '':
            return ''
        
        value = str(value).replace('\n', '\\n')  # Replace actual linefeeds with \n
        
        if column in QUOTED_COLUMNS:
            value = value.replace('"', '""')  # Escape existing double quotes
            return f'"{value}"'
        
        return value

    @versioned("1.9.3")
    def _write_row(self, file, row: List[str]):
        formatted_row = [self._format_value(EXPECTED_HEADER[i], field) for i, field in enumerate(row)]
        file.write(','.join(formatted_row) + '\n')

    @versioned("2.5.6")
    def write_translations(self, source_file: str, output_file: str, entries: List[Dict[str, str]], translations: Dict[str, Dict[str, str]], translation_manager: Optional[TranslationManager] = None) -> None:
        """
        Write translations to the output file.

        Args:
            source_file (str): Path to the source file.
            output_file (str): Path to the output file.
            entries (List[Dict[str, str]]): List of entry dictionaries.
            translations (Dict[str, Dict[str, str]]): Dictionary of translations.
            translation_manager (Optional[TranslationManager]): Translation manager instance.

        Raises:
            ValueError: If sanity check fails.

        Version History:
            2.5.5: Updated logging format for better readability and information.
            2.5.6: Improved logic for detecting incomplete translations.
        """
        if translation_manager:
            self.translation_manager = translation_manager
        
        self.logger.debug(f'[WRITER] Writing translations to {output_file}')
        self.logger.debug(f'[WRITER] Number of entries: {len(entries)}')
        self.logger.debug(f'[WRITER] Number of translations: {len(translations)}')
        
        expected_translation_count = len(entries) * len(TARGET_LANGUAGES)
        actual_translation_count = sum(len(trans) for trans in translations.values())
        
        self.logger.info(f'[WRITER] Expected translations: {expected_translation_count}')
        self.logger.info(f'[WRITER] Actual translations: {actual_translation_count}')
        
        if len(entries) != len(translations):
            self.logger.warning(f'[WRITER] Mismatch in entry count. Entries: {len(entries)}, Translations: {len(translations)}')
            self.logger.warning('[WRITER] Attempting to continue with available translations.')
        
        if expected_translation_count != actual_translation_count:
            self.logger.warning(f'[WRITER] Mismatch in translation count. Some entries may be missing translations.')
        
        incomplete_entries = []
        complete_count = 0
        for entry in entries:
            key = entry.get('Key')
            if key not in translations:
                self.logger.debug(f'[WRITER] Entry {key:<40} ** MISSING ALL TRANSLATIONS **')
                incomplete_entries.append(entry)
            else:
                present_translations = [lang for lang in TARGET_LANGUAGES if lang in translations[key] and translations[key][lang]]
                if len(present_translations) < len(TARGET_LANGUAGES):
                    missing_languages = set(TARGET_LANGUAGES) - set(present_translations)
                    self.logger.debug(f'[WRITER] Entry {key:<40} ** MISSING TRANSLATIONS: {", ".join(missing_languages)} **')
                    incomplete_entries.append(entry)
                else:
                    complete_count += 1
                    self.logger.debug(f'[WRITER] Entry {key:<40} Complete [{complete_count:3d}] ({len(present_translations)} languages)')
        
        if incomplete_entries:
            if self.translation_manager:
                self.logger.warning(f'[WRITER] Found {len(incomplete_entries)} entries with incomplete translations. Attempting to retranslate.')
                completed_translations = self.translation_manager.retranslate_incomplete_entries(incomplete_entries)
                translations.update(completed_translations)
            else:
                self.logger.error(f'[WRITER] Found {len(incomplete_entries)} entries with incomplete translations, but no TranslationManager available for retranslation.')
                raise ValueError('Incomplete translations and no TranslationManager available')
        
        for key, trans in translations.items():
            missing_languages = [lang for lang in TARGET_LANGUAGES if lang not in trans or not trans[lang]]
            if missing_languages:
                self.logger.warning(f'[WRITER] Incomplete translations for key: {key}. Missing: {", ".join(missing_languages)}')
            else:
                self.logger.debug(f'[WRITER] Complete translations for key: {key}')
        
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            # Write header
            f.write(','.join(EXPECTED_HEADER) + '\n')
            
            for entry in entries:
                key = entry['Key']
                trans = translations.get(key, {})
                self.logger.debug(f'[WRITER] Writing translations for entry: {key}')
                self.logger.debug(f'[WRITER] Available translations: {list(trans.keys())}')
                
                row = [
                    key,
                    entry.get('File', ''),
                    entry.get('Type', ''),
                    entry.get('UsedInMainMenu', ''),
                    entry.get('NoTranslate', ''),
                    trans.get('english') or entry.get('english', ''),
                    entry.get('Context / Alternate Text', ''),
                ]
                for lang in TARGET_LANGUAGES:
                    if lang in trans and trans[lang]:
                        row.append(trans[lang])
                    else:
                        self.logger.warning(f'[WRITER] Missing translation for {lang} in entry {key}')
                        row.append('[MISSING TRANSLATION]')
                self._write_row(f, row)

        self.logger.info(f'[WRITER] All translations written to {output_file}')
        self.sanity_check(Path(source_file), Path(output_file))

    @versioned("1.0.0")
    def _append_completed_translations(self, output_file: str, completed_translations: Dict[str, Dict[str, str]]):
        """
        Append completed translations to the output file.

        Args:
            output_file (str): Path to the output file.
            completed_translations (Dict[str, Dict[str, str]]): Dictionary of completed translations.
        """
        with open(output_file, 'a', encoding='utf-8', newline='') as f:
            for key, trans in completed_translations.items():
                row = [
                    key,
                    '',  # File
                    '',  # Type
                    '',  # UsedInMainMenu
                    '',  # NoTranslate
                    trans.get('english', ''),
                    '',  # Context / Alternate Text
                ]
                for lang in TARGET_LANGUAGES:
                    row.append(trans.get(lang, ''))
                self._write_row(f, row)
        
        self.logger.info(f"[WRITER] Appended {len(completed_translations)} completed translations to {output_file}")

    @versioned("2.3.0")
    def sanity_check(self, source_file: Path, destination_file: Path):
        self.logger.debug(f"[WRITER] Performing sanity check on {destination_file}")
        try:
            source_entries = self._count_entries(source_file)
            destination_entries = self._count_entries(destination_file)

            if source_entries != destination_entries:
                error_message = f"[WRITER] CRITICAL: Mismatch in entry count. Source: {source_entries}, Destination: {destination_entries}"
                self.logger.critical(error_message)
                raise ValueError(error_message)

            with destination_file.open('r', encoding='utf-8') as file:
                lines = file.readlines()
                header = lines[0].strip().split(',')
                if header != EXPECTED_HEADER:
                    raise ValueError(f"Header does not match expected format. Got: {header}, Expected: {EXPECTED_HEADER}")
                
                for i, line in enumerate(lines[1:], start=2):
                    fields = self._split_line(line.strip())
                    if len(fields) != len(EXPECTED_HEADER):
                        self.logger.error(f"[WRITER] Line {i} has incorrect number of fields. Expected {len(EXPECTED_HEADER)}, got {len(fields)}")
                        self.logger.error(f"[WRITER] Problematic line: {line.strip()}")
                        raise ValueError(f"Line {i} has incorrect number of fields")
                    
                    # Check for non-empty translations for all target languages
                    for lang_index, lang in enumerate(TARGET_LANGUAGES, start=7):
                        if not fields[lang_index].strip('""'):
                            raise ValueError(f"Line {i} is missing translation for {lang}")
                    
                    for field, value in zip(EXPECTED_HEADER, fields):
                        if field in QUOTED_COLUMNS:
                            if value and not (value.startswith('"') and value.endswith('"')):
                                raise ValueError(f"Line {i}, field '{field}' is not properly quoted")
                        if '\\n' in value and '\n' in value:
                            raise ValueError(f"Line {i}, field '{field}' contains both escaped and unescaped linefeeds")
                        if '"' in value.strip('"') and '""' not in value:
                            raise ValueError(f"Line {i}, field '{field}' contains unescaped quotes")
            self.logger.info(f"[WRITER] Sanity check passed for {destination_file}")
        except Exception as e:
            self.logger.critical(f"[WRITER] Sanity check failed for {destination_file}: {str(e)}")
            raise

    @versioned("1.0.0")
    def _count_entries(self, file_path: Path) -> int:
        with file_path.open('r', encoding='utf-8') as file:
            return sum(1 for line in file if line.strip() and not line.startswith('Key,'))

    @versioned("1.9.3")
    def _split_line(self, line: str) -> List[str]:
        fields = []
        field = ''
        in_quotes = False
        for char in line:
            if char == '"':
                if in_quotes and field.endswith('"'):
                    field += char
                else:
                    in_quotes = not in_quotes
                field += char
            elif char == ',' and not in_quotes:
                fields.append(field)
                field = ''
            else:
                field += char
        fields.append(field)
        return fields