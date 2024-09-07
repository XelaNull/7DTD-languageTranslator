#!/usr/bin/env python3

#!/usr/bin/env python3

"""
Language Translator for 7 Days to Die Localization Files

This script recursively locates Localization.txt files, translates English text to other languages
using both Anthropic and ChatGPT APIs, and caches results to prevent duplicate API queries.

Features:
- Support for both Anthropic and ChatGPT APIs with automatic alternation
- Two batching strategies: Token Estimation and Single Language Translation
- Smart caching using pickle to store API responses
- Intelligent Python module dependency management
- Multithreading for processing multiple Localization.txt files simultaneously
- Progress tracking with per-file and overall progress bars
- Comprehensive error handling and logging
- Command-line interface for various operations

Usage:
./languageTranslator.py [source_path] [options]

Options:
  --debug             Enable debug mode
  --help              Display help message
  --cache-details     Show detailed cache statistics
  --cache-clear N     Clear N random entries from the cache
  --cache-wipe        Wipe the entire cache
  --cache-performance Display cache performance statistics

Author: Zen Python Master
Version: 1.4.0
Last Updated: 2024-09-02

Notes:
- Ensure all sensitive information (like API keys) are stored as environment variables
- Update VERSION and LAST_UPDATED whenever significant changes are made to the script
- Adjust MAX_ALLOWED_TOKENS based on the specific requirements of the APIs being used
- Debug logging should be used judiciously to avoid performance impacts
- Consider using environment variables or command-line arguments to control debug mode
- Be mindful of memory usage when processing large files
- Regularly review and update the list of required dependencies in the check_dependencies function

Lessons Learned:
1. API Interaction:
   Problem: Inefficient API usage leading to high costs and frequent failures due to rate limiting
   Solution:
   - Implemented smart batching strategies to optimize API calls:
     def translate_with_batching(self, text, target_languages):
         if self._can_use_estimation_strategy(text, target_languages):
             return self._translate_estimation_based(text, target_languages)
         else:
             return self._translate_single_language(text, target_languages)
   - Implemented a rate limiter with exponential backoff:
     @retry_with_exponential_backoff
     def _make_api_call(self, api_func, *args, **kwargs):
         with self.rate_limiter.acquire(api_func.__name__):
             return api_func(*args, **kwargs)
   - Always use try-except blocks when making API calls to handle potential errors gracefully
   - Implemented token estimation for batching decisions:
     def _estimate_tokens(self, text):
         return len(text.split()) + 20  # rough estimate
   - Standardized API response handling:
     def _handle_api_response(self, response):
         if 'error' in response:
             raise APIError(response['error'])
         return self._extract_translations(response)

2. File Handling:
   Problem: Inefficient file processing and inconsistent handling across platforms
   Solution:
   - Use 'with' statements when opening files to ensure they are properly closed after use
   - Always specify the encoding (e.g., utf-8) when reading/writing files to avoid encoding issues
   - Use pathlib for cross-platform compatibility when dealing with file paths:
     output_file = Path(file_path).with_suffix('.translated.txt')

3. Error Handling and Logging:
   Problem: Difficulty in debugging complex multi-threaded operations
   Solution:
   - Implemented comprehensive logging:
     logger = Logger(debug_mode=args.debug)
     logger.debug(f"Starting translation for file: {file_path}")
   - Use logging to record important events and errors for easier debugging
   - Consider different logging levels (DEBUG, INFO, WARNING, ERROR) for various scenarios
   - Implement graceful handling of KeyboardInterrupt (CTRL-C) to allow clean script termination:
     def graceful_shutdown(signum, frame):
         logger.info("Received interrupt signal. Cleaning up...")
         cache_manager.save_cache()
         stats_manager.save_stats()
         sys.exit(0)

4. User Interface:
   Problem: Lack of visibility into script progress and limited user control
   Solution:
   - Implemented progress bars using tqdm:
     with tqdm(total=len(localization_files), desc="Overall Progress") as pbar:
         for file in localization_files:
             process_file(file)
             pbar.update(1)
   - Added command-line arguments for greater flexibility and control
   - Use rich library for enhanced console output and formatting

5. Code Structure and Maintainability:
   Problem: Difficulty in managing complex codebase and tracking versions
   Solution:
   - Break down complex operations into smaller, reusable functions
   - Use @versioned decorator on all functions to keep track of versions:
     @versioned("1.4.0")
     def main():
         # Function implementation
   - Use type hints to improve code readability and catch potential type-related errors
   - Write docstrings for functions to explain their purpose, parameters, and return values

6. Performance Optimization:
   Problem: Slow processing of large files and inefficient use of system resources
   Solution:
   - Use batch processing of languages when possible to reduce the number of API calls
   - Implement pickle caching mechanism to store and reuse language translations
   - Profile the code to identify and optimize performance bottlenecks
   - Use threading to improve performance:
     threads = []
     for file_path in localization_files:
         thread = threading.Thread(target=file_locator.process_file, args=(file_path,))
         threads.append(thread)
         thread.start()

7. Dependency Management:
   Problem: Difficulty in managing dependencies across different environments
   Solution:
   - Implemented a dependency check function:
     def check_dependencies():
         required_modules = ['anthropic', 'openai', 'rich', 'tqdm']
         for module in required_modules:
             try:
                 __import__(module)
             except ImportError:
                 print(f"Missing required module: {module}")
                 sys.exit(1)

8. Caching:
   Problem: Inefficient caching leading to unnecessary API calls
   Solution:
   - Implement pickle caching mechanism to store and reuse language translations
   - Use a wrapper function for API calls to handle timeouts and interruptions
   - Implement immediate caching of translations to preserve paid results

9. Statistics and Reporting:
   Problem: Lack of insights into script performance and API usage
   Solution:
   - Implement comprehensive statistics tracking:
     stats_manager.increment_stat('script_execution_count')
   - Generate detailed API usage reports:
     logger.info(stats_manager.generate_api_usage_report())
   - Calculate and display API usage averages:
     logger.info("\n" + stats_manager.calculate_api_averages())

10. Graceful Shutdown:
    Problem: Risk of data loss during script interruptions
    Solution:
    - Implemented a graceful shutdown mechanism:
      def graceful_shutdown(signum, frame):
          logger.info("Received interrupt signal. Cleaning up...")
          cache_manager.save_cache()
          stats_manager.save_stats()
          sys.exit(0)
      
      signal.signal(signal.SIGINT, graceful_shutdown)
      signal.signal(signal.SIGTERM, graceful_shutdown)
"""

# Standard library imports
import argparse
import os
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional
import threading
import time
import asyncio

# Third-party imports (install via pip)
from anthropic import Anthropic
from openai import OpenAI, AsyncOpenAI
from rich import print
import pandas as pd
import tiktoken

# Import custom modules
from api_conn_manager import APIConnectionManager
from batch_manager import BatchManager
from cache_manager import CacheManager
from config import (
    ANTHROPIC_API_KEY, CHATGPT_API_KEY, CACHE_DIR, CACHE_FILE, MAX_TOKENS,
    MAX_ALLOWED_TOKENS, INITIAL_BATCH_SIZE, MAX_WORKERS, EXPECTED_HEADER,
    TARGET_LANGUAGES, QUOTED_COLUMNS, VERSION, LAST_UPDATED, STATS_FILE
)
from debug_logging import LTLogger
from file_locator import FileLocator
from response_parser import ResponseParser
from rate_limiter import RateLimiter
from statistics_manager import StatisticsManager
from token_estimator import TokenEstimator
from translation_manager import TranslationManager
from writer_localization import LocalizationWriter
from utils import versioned, check_dependencies, setup_graceful_shutdown, check_exit_flag

def parse_arguments():
    parser = argparse.ArgumentParser(description="Language Translator for 7 Days to Die Localization Files")
    parser.add_argument("source_path", nargs="?", default=".", help="Source path for Localization.txt files")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--cache-details", action="store_true", help="Show detailed cache statistics")
    parser.add_argument("--cache-clear", type=int, metavar="N", help="Clear N random entries from the cache")
    parser.add_argument("--cache-wipe", action="store_true", help="Wipe the entire cache")
    parser.add_argument("--cache-performance", action="store_true", help="Display cache performance statistics")
    return parser.parse_args()

@versioned("1.0.2")
def main():
    args = parse_arguments()
    logger = LTLogger(__name__)
    logger.set_debug_mode(args.debug)
    
    logger.info(f"Language Translator v{VERSION} starting up...")
    check_dependencies(logger)

    stats_manager = StatisticsManager(logger, STATS_FILE)
    cache_manager = CacheManager(logger, CACHE_FILE, stats_manager)
    
    # Handle cache-related arguments
    if args.cache_details:
        cache_manager.display_cache_details()
        return

    if args.cache_clear:
        cache_manager.clear_random_entries(args.cache_clear)
        logger.info(f"{args.cache_clear} random entries cleared from the cache.")
        return

    if args.cache_wipe:
        cache_manager.clear_cache()
        logger.info("Cache wiped completely.")
        return

    if args.cache_performance:
        logger.info(stats_manager.calculate_cache_performance())
        return

    # Proceed with translation-related setup
    stats_manager.increment_stat('script_execution_count')
    
    # Set up graceful shutdown
    cleanup_functions = [
        cache_manager.save_cache,
        stats_manager.save_stats
    ]
    setup_graceful_shutdown(cleanup_functions, logger)

    # Create instances of required classes
    response_parser = ResponseParser(logger)
    token_estimator = TokenEstimator(logger)

    # Update the APIConnectionManager initialization
    api_connection_manager = APIConnectionManager(
        logger,
        cache_manager,
        stats_manager,
        response_parser
    )

    translation_manager = TranslationManager(logger, api_connection_manager, cache_manager, response_parser, stats_manager, token_estimator)
    
    # Set the TranslationManager in TokenEstimator
    token_estimator.set_translation_manager(translation_manager)
    
    # Set the TokenEstimator in APIConnectionManager
    api_connection_manager.set_token_estimator(token_estimator)
    
    batch_manager = BatchManager(logger, api_connection_manager, cache_manager, stats_manager, translation_manager)
    localization_writer = LocalizationWriter(logger, translation_manager)
    file_locator = FileLocator(logger, batch_manager, stats_manager, translation_manager)

    # Validate API keys
    api_connection_manager.validate_api_keys()

    # Process files
    source_path = Path(args.source_path)
    if not source_path.exists():
        logger.error(f"Source path does not exist: {source_path}")
        return

    localization_files = file_locator.list_localization_files(str(source_path))
    if not localization_files:
        logger.warning(f"No Localization.txt files found in {source_path}")
        return

    logger.info(f"Found {len(localization_files)} Localization.txt files")

    file_locator.process_directory(args.source_path)

    logger.info("Main process exiting")

    # Display final statistics and reports
    stats_manager.display_statistics()
    logger.info("\n" + stats_manager.calculate_api_averages())
    logger.info(stats_manager.generate_api_usage_report())

    logger.info("Translation process completed")

    # Save statistics at the end of the script
    stats_manager.save_stats()
    logger.info(f"Found {len(localization_files)} Localization.txt files")

    file_locator.process_directory(args.source_path)

    logger.info("Main process exiting")

    # Display final statistics and reports
    stats_manager.display_statistics()
    logger.info("\n" + stats_manager.calculate_api_averages())
    logger.info(stats_manager.generate_api_usage_report())

    logger.info("Translation process completed")

    # Save statistics at the end of the script
    stats_manager.save_stats()

    api_connection_manager.set_token_estimator(token_estimator)

if __name__ == "__main__":
    main()
