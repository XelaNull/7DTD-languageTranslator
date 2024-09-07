"""
Statistics Management module for the Language Translator script.

This module handles the collection, storage, and reporting of various statistics related to the translation process.

Features:
* Implements Statistics as a Class with methods for setting, getting, and incrementing specific statistics
* Stores statistics in a JSON file for persistence across script runs
* Provides methods for calculating and displaying API usage averages
* Generates detailed API usage reports
* Supports thread-safe operations for concurrent access to statistics
* Implements real-time updating of statistics during the translation process
* Provides methods for displaying statistics in a user-friendly format

Class Definitions:
    StatisticsManager
        Methods:
            set_stat: Sets a specific statistic to a given value
            get_stat: Retrieves the value of a specific statistic
            increment_stat: Increments a specific statistic by a given value
            display_statistics: Prints current statistics to the console
            calculate_api_averages: Calculates and returns average API usage statistics
            generate_api_usage_report: Generates a detailed report of API usage
            load_statistics: Loads statistics from the JSON file
            save_statistics: Saves current statistics to the JSON file
        Variables:
            stats: Dict[str, Any] = {
                "localization_files_processed": int,
                "localization_entries_translated": int,
                "total_tokens_used": int,
                "total_api_calls": int,
                "successful_translations": int,
                "failed_translations": int,
                "api_anthropic_success": int,
                "api_anthropic_fail": int,
                "api_openai_success": int,
                "api_openai_fail": int,
                "estimation_strategy_success": int,
                "estimation_strategy_fail": int,
                "single_language_strategy_success": int,
                "single_language_strategy_fail": int,
                "cache_hits": int,
                "cache_misses": int,
                "start_time": Optional[float],
                "end_time": Optional[float],
                "script_execution_count": int
            }

Logic Flows:
* Statistics are updated in real-time as the translation process progresses
* The statistics are loaded from a JSON file at the start of the script execution
* Throughout the script execution, statistics are updated using thread-safe methods
* At the end of the script execution, final statistics are calculated and saved to the JSON file

Notes:
* The statistics file is stored in a predefined location (CACHE_DIR) for consistency
* A lock mechanism is used to ensure thread-safety for all statistics operations
* The script execution count is incremented each time the script is run

Lessons Learned:
* Problem: Race conditions when multiple threads update statistics simultaneously
  Solution:
  - Implemented a threading.Lock() mechanism in the StatisticsManager class
  - Wrapped all statistics access methods with the lock:
    def set_stat(self, key: str, value: Any):
        with self.lock:
            self.stats[key] = value
  - Applied the lock to all methods that read or write statistics
  - Ensured that the lock is released even if an exception occurs by using a try-finally block

* Problem: Loss of statistics data due to unexpected script termination
  Solution:
  - Implemented periodic saving of statistics to the JSON file
  - Added a save_interval parameter to control how often statistics are saved
  - In the set_stat and increment_stat methods:
    self._save_count += 1
    if self._save_count >= self.save_interval:
        self.save_statistics()
        self._save_count = 0
  - Implemented a cleanup method to ensure statistics are saved on script exit:
    def cleanup(self):
        self.stats['end_time'] = time.time()
        self.save_statistics()
  - Added signal handlers for SIGINT and SIGTERM to call the cleanup method

* Problem: Difficulty in tracking API-specific statistics
  Solution:
  - Added separate counters for each API (Anthropic and OpenAI) in the stats dictionary
  - Implemented methods to update API-specific statistics:
    def update_api_stats(self, api_name: str, success: bool, tokens_used: int):
        with self.lock:
            self.stats[f'api_{api_name}_{"success" if success else "fail"}'] += 1
            self.stats['total_tokens_used'] += tokens_used
            self.stats['total_api_calls'] += 1
  - Modified the generate_api_usage_report method to include API-specific statistics

* Problem: Inaccurate timing of script execution due to multi-threading
  Solution:
  - Implemented a more robust timing mechanism using time.perf_counter()
  - Added start_time and end_time fields to the stats dictionary
  - Updated the timing in the __init__ and cleanup methods:
    def __init__(self, ...):
        ...
        self.stats['start_time'] = time.perf_counter()
    def cleanup(self):
        self.stats['end_time'] = time.perf_counter()
  - Calculated total execution time in the display_statistics method:
    execution_time = self.stats['end_time'] - self.stats['start_time']

* Problem: Lack of visibility into translation strategy effectiveness
  Solution:
  - Added counters for each translation strategy (Estimation-Based and Single Language)
  - Implemented a method to update strategy statistics:
    def update_strategy_stats(self, strategy: str, success: bool):
        with self.lock:
            self.stats[f'{strategy}_strategy_{"success" if success else "fail"}'] += 1
  - Modified the generate_api_usage_report method to include strategy effectiveness statistics

* Problem: Difficulty in tracking progress across multiple script runs
  Solution:
  - Implemented a script_execution_count in the stats dictionary
  - Incremented the count in the __init__ method:
    def __init__(self, ...):
        ...
        self.stats['script_execution_count'] += 1
  - Added a method to retrieve historical statistics:
    def get_historical_stats(self) -> Dict[str, List[Any]]:
        # Implementation to retrieve statistics from previous runs

* Problem: Inefficient calculation of averages and percentages
  Solution:
  - Implemented caching for calculated statistics
  - Added a _cache dictionary to store calculated values
  - Modified methods like calculate_api_averages to use cached values:
    def calculate_api_averages(self):
        if 'api_averages' not in self._cache:
            # Perform calculations and store in self._cache['api_averages']
        return self._cache['api_averages']
  - Implemented a method to clear the cache when raw statistics are updated

* Problem: Lack of detailed performance metrics for optimization
  Solution:
  - Implemented more granular timing statistics
  - Added timing decorators for key methods:
    def timing_decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            result = func(*args, **kwargs)
            end_time = time.perf_counter()
            StatisticsManager.update_timing_stat(func.__name__, end_time - start_time)
            return result
        return wrapper
  - Applied the timing decorator to methods in other modules (e.g., BatchManager, APIManager)
  - Added a method to generate a performance report based on these timing statistics
"""

# Standard library imports
import os
import pickle
import json
import time
from pathlib import Path
from typing import Dict, Any
from datetime import datetime

# Third-party imports
from rich.console import Console
from rich.table import Table

# Local application imports
from config import CACHE_DIR, versioned
from debug_logging import LTLogger  # Make sure to import the Logger class

@versioned("1.9.5")
class StatisticsManager:
    """
    Manages statistics collection and reporting for the Language Translator application.

    This class handles the collection, storage, and reporting of various statistics
    related to the translation process, including API usage, token counts, and performance metrics.

    Attributes:
        logger (Logger): Logger instance for debugging and error reporting.
        stats (Dict[str, Any]): Dictionary storing various statistics.
        stats_file (str): Path to the JSON file for storing persistent statistics.

    Dependencies:
        - Logger: Used for logging debug information and errors related to statistics management.

    Methods:
        set_stat: Sets a specific statistic to a given value.
        get_stat: Retrieves the value of a specific statistic.
        increment_stat: Increments a specific statistic by a given value.
        display_statistics: Prints current statistics to the console.
        calculate_api_averages: Calculates and returns average API usage statistics.
        generate_api_usage_report: Generates a detailed report of API usage.
        load_statistics: Loads statistics from the JSON file.
        save_statistics: Saves current statistics to the JSON file.

    Version History:
        1.0.0 - Initial implementation with basic statistics tracking.
        1.1.0 - Added persistent storage of statistics in JSON file.
        1.2.0 - Implemented API usage reporting and averages calculation.
        1.3.0 - Added thread-safe operations for concurrent access to statistics.
        1.4.0 - Improved error handling and logging for statistics operations.
        1.5.0 - Added detailed API usage report generation.
        1.5.1 - Updated initialization to accept logger as first argument.
        1.5.2 - Fixed argument order in __init__ method.
    """


    @versioned("1.5.2")
    def __init__(self, logger: 'LTLogger', stats_file: str):
        self.logger = logger
        self.stats_file = stats_file
        self.stats = self._initialize_stats()
        self.load_statistics()

    @versioned("1.5.1")
    def _initialize_stats(self):
        return {
            "localization_files_processed": 0,
            "localization_entries_translated": 0,
            "total_tokens_used": 0,
            "total_api_calls": 0,
            "successful_translations": 0,
            "failed_translations": 0,
            "api_anthropic_success": 0,
            "api_anthropic_fail": 0,
            "api_openai_success": 0,
            "api_openai_fail": 0,
            "estimation_strategy_success": 0,
            "estimation_strategy_fail": 0,
            "single_language_strategy_success": 0,
            "single_language_strategy_fail": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "start_time": None,
            "end_time": None,
            "script_execution_count": 0
        }
        self.stats["script_execution_count"] += 1
        self.stats["start_time"] = time.time()

    @versioned("1.5.0")
    def load_statistics(self) -> None:
        self.logger.debug("[STATS] Loading statistics from file")
        if not os.path.exists(self.stats_file):
            self.logger.warning("[STATS] Statistics file not found. Using default values.")
            return

        try:
            with open(self.stats_file, 'r', encoding='utf-8') as f:
                saved_stats = json.load(f)
                self.stats.update(saved_stats)
        except UnicodeDecodeError:
            self.logger.error("[STATS] Error decoding statistics file as UTF-8. Attempting to read as binary.")
            try:
                with open(self.stats_file, 'rb') as f:
                    saved_stats = json.loads(f.read().decode('utf-8', errors='ignore'))
                    self.stats.update(saved_stats)
            except json.JSONDecodeError:
                self.logger.error("[STATS] Error decoding statistics file as JSON. Using default values.")
            except Exception as e:
                self.logger.error(f"[STATS] Unexpected error loading statistics: {str(e)}. Using default values.")
        except json.JSONDecodeError:
            self.logger.error("[STATS] Error decoding statistics file as JSON. Using default values.")
        except Exception as e:
            self.logger.error(f"[STATS] Unexpected error loading statistics: {str(e)}. Using default values.")

    @versioned("1.4.0")
    def reset_stats(self):
        self.stats = {
            "localization_files_processed": 0,
            "localization_entries_translated": 0,
            "total_tokens_used": 0,
            "total_api_calls": 0,
            "successful_translations": 0,
            "failed_translations": 0,
            "api_anthropic_success": 0,
            "api_anthropic_fail": 0,
            "api_openai_success": 0,
            "api_openai_fail": 0,
            "estimation_strategy_success": 0,
            "estimation_strategy_fail": 0,
            "single_language_strategy_success": 0,
            "single_language_strategy_fail": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "start_time": datetime.now(),
            "end_time": None,
            "script_execution_count": 1  # Initialize to 1 for the current run
        }

    @versioned("1.4.0")
    def _load_stats(self):
        if self.stats_file.exists():
            try:
                with self.stats_file.open('rb') as f:
                    loaded_stats = pickle.load(f)
                    self.stats.update(loaded_stats)
            except Exception as e:
                print(f"Error loading statistics: {str(e)}")

    @versioned("1.4.0")
    def _save_stats(self):
        try:
            self.stats_file.parent.mkdir(parents=True, exist_ok=True)
            with self.stats_file.open('wb') as f:
                pickle.dump(self.stats, f)
        except Exception as e:
            print(f"Error saving statistics: {str(e)}")

    @versioned("1.4.0")
    def increment_stat(self, stat_name: str, value: int = 1):
        if stat_name in self.stats:
            self.stats[stat_name] += value
        else:
            self.logger.warning(f"[STATS] Attempted to increment unknown statistic: {stat_name}")

    @versioned("1.4.0")
    def set_stat(self, stat_name: str, value: Any):
        if stat_name in self.stats:
            self.stats[stat_name] = value
        else:
            self.logger.warning(f"[STATS] Attempted to set unknown statistic: {stat_name}")

    @versioned("1.4.0")
    def get_stat(self, stat_name: str) -> Any:
        return self.stats.get(stat_name, None)

    @versioned("1.4.0")
    def increment_tokens_used(self, tokens: int):
        self.increment_stat("total_tokens_used", tokens)

    @versioned("1.4.0")
    def increment_api_calls(self):
        self.increment_stat("total_api_calls")

    @versioned("1.4.0")
    def increment_successful_translations(self):
        self.increment_stat("successful_translations")

    @versioned("1.4.0")
    def increment_failed_translations(self):
        self.increment_stat("failed_translations")

    @versioned("1.4.0")
    def record_end_time(self):
        self.set_stat("end_time", datetime.now())

    @versioned("1.8.37")
    def display_statistics(self):
        console = Console()
        table = Table(title="Translation Statistics")
        table.add_column("Statistic", style="cyan")
        table.add_column("Value", style="magenta")

        for key, value in self.stats.items():
            if key in ['start_time', 'end_time']:
                if isinstance(value, (int, float)):
                    value = datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    value = "N/A"
            table.add_row(key, str(value))

        console.print(table)

    @versioned("1.4.0")
    def save_stats(self):
        self._save_stats()

    @versioned("1.4.0")
    def calculate_api_averages(self) -> str:
        """
        Calculate and return a string representation of API usage averages.

        Returns:
            str: A formatted string containing API usage averages.
        """
        anthropic_success = self.stats.get('api_anthropic_success', 0)
        anthropic_fail = self.stats.get('api_anthropic_fail', 0)
        openai_success = self.stats.get('api_openai_success', 0)
        openai_fail = self.stats.get('api_openai_fail', 0)

        total_calls = anthropic_success + anthropic_fail + openai_success + openai_fail
        total_tokens = self.stats.get('total_tokens_used', 0)

        if total_calls == 0:
            return "No API calls made yet."

        avg_tokens_per_call = total_tokens / total_calls if total_calls > 0 else 0
        anthropic_percentage = ((anthropic_success + anthropic_fail) / total_calls) * 100 if total_calls > 0 else 0
        openai_percentage = ((openai_success + openai_fail) / total_calls) * 100 if total_calls > 0 else 0

        anthropic_success_rate = (anthropic_success / (anthropic_success + anthropic_fail)) * 100 if (anthropic_success + anthropic_fail) > 0 else 0
        openai_success_rate = (openai_success / (openai_success + openai_fail)) * 100 if (openai_success + openai_fail) > 0 else 0

        return f"""API Usage Averages:
        Total API Calls: {total_calls}
        Average Tokens per Call: {avg_tokens_per_call:.2f}
        Anthropic API Usage: {anthropic_percentage:.2f}% (Success Rate: {anthropic_success_rate:.2f}%)
        OpenAI API Usage: {openai_percentage:.2f}% (Success Rate: {openai_success_rate:.2f}%)
        """

    @versioned("1.4.0")
    def generate_api_usage_report(self) -> str:
        """
        Generate a detailed report of API usage.

        Returns:
            str: A formatted string containing a detailed API usage report.
        """
        anthropic_success = self.stats.get('api_anthropic_success', 0)
        anthropic_fail = self.stats.get('api_anthropic_fail', 0)
        openai_success = self.stats.get('api_openai_success', 0)
        openai_fail = self.stats.get('api_openai_fail', 0)

        total_calls = anthropic_success + anthropic_fail + openai_success + openai_fail
        total_tokens = self.stats.get('total_tokens_used', 0)

        if total_calls == 0:
            return "No API calls made yet."

        report = "API Usage Report:\n"
        report += f"Total API Calls: {total_calls}\n"
        report += f"Total Tokens Used: {total_tokens}\n\n"

        report += "Anthropic API:\n"
        report += f"  Successful Calls: {anthropic_success}\n"
        report += f"  Failed Calls: {anthropic_fail}\n"
        anthropic_success_rate = (anthropic_success / (anthropic_success + anthropic_fail)) * 100 if (anthropic_success + anthropic_fail) > 0 else 0
        report += f"  Success Rate: {anthropic_success_rate:.2f}%\n\n"

        report += "OpenAI API:\n"
        report += f"  Successful Calls: {openai_success}\n"
        report += f"  Failed Calls: {openai_fail}\n"
        openai_success_rate = (openai_success / (openai_success + openai_fail)) * 100 if (openai_success + openai_fail) > 0 else 0
        report += f"  Success Rate: {openai_success_rate:.2f}%\n\n"

        avg_tokens_per_call = total_tokens / total_calls if total_calls > 0 else 0
        report += f"Average Tokens per Call: {avg_tokens_per_call:.2f}\n"

        return report