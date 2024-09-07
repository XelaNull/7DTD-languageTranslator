"""
Utility functions for the Language Translator script.

This module contains various utility functions used throughout the project.

Features:
* Dependency checking for required Python modules
* Graceful shutdown setup for handling interruptions
* JSON string cleaning and validation
* Retry mechanism with exponential backoff for API calls

Functions:
    check_dependencies: Checks if all required modules are installed
    setup_graceful_shutdown: Sets up signal handlers for graceful shutdown
    clean_json_string: Cleans and formats JSON strings
    is_json_complete: Validates if a JSON string is complete and valid
    retry_with_exponential_backoff: Decorator for retrying functions with exponential backoff

Notes:
* The check_dependencies function should be called at the start of the main script
* The setup_graceful_shutdown function should be used to ensure proper cleanup on script termination
* JSON-related functions are crucial for handling API responses
* The retry decorator is particularly useful for API calls that may fail intermittently

Lessons Learned:
* Problem: Script crashes due to missing dependencies
  Solution:
  - Implemented a comprehensive dependency check:
    def check_dependencies(logger: Logger):
        required_modules = [
            'anthropic', 'openai', 'rich', 'pandas', 'tiktoken'
        ]
        missing_modules = []
        for module in required_modules:
            try:
                __import__(module)
            except ImportError:
                missing_modules.append(module)
        
        if missing_modules:
            logger.error("The following required modules are missing:")
            for module in missing_modules:
                logger.error(f"- {module}")
            logger.error("Please install these modules and try again.")
            sys.exit(1)
        else:
            logger.info("All required modules are installed.")
  - This ensures all necessary modules are available before the script runs

* Problem: Unclean script termination leading to potential data loss
  Solution:
  - Implemented a graceful shutdown mechanism:
    def setup_graceful_shutdown(cleanup_functions: List[Callable], logger):
        def graceful_shutdown(signum, frame):
            logger.info("Received interrupt signal. Initiating graceful shutdown...")
            threading.Event().set()
            for cleanup_func in cleanup_functions:
                cleanup_func()
            logger.info("Graceful shutdown complete. Exiting...")
            exit(0)
        signal.signal(signal.SIGINT, graceful_shutdown)
        signal.signal(signal.SIGTERM, graceful_shutdown)
  - This allows for proper cleanup of resources and saving of data on script interruption

* Problem: Inconsistent handling of JSON strings from API responses
  Solution:
  - Created utility functions for JSON string cleaning and validation:


    def is_json_complete(json_string: str) -> bool:
        cleaned_string = clean_json_string(json_string)
        try:
            json.loads(cleaned_string)
            return True
        except json.JSONDecodeError:
            return False
  - These functions ensure consistent handling of JSON strings across the project

* Problem: API calls failing due to temporary issues
  Solution:
  - Implemented a retry decorator with exponential backoff:
    def retry_with_exponential_backoff(
        func: Callable,
        max_retries: int = 5,
        initial_wait: float = 1,
        exponential_base: float = 2,
        logger: Logger = None
    ) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            wait_time = initial_wait
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        if logger:
                            logger.error(f"Function {func.__name__} failed after {max_retries} attempts. Error: {str(e)}")
                        raise
                    if logger:
                        logger.warning(f"Attempt {attempt + 1} failed. Retrying in {wait_time:.2f} seconds. Error: {str(e)}")
                    time.sleep(wait_time)
                    wait_time *= exponential_base
        return wrapper
  - This decorator allows for automatic retrying of failed API calls with increasing wait times

* Problem: Difficulty in tracking function versions across the project
  Solution:
  - Implemented a versioning decorator:
    def versioned(version: str):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            wrapper.__version__ = version
            return wrapper
        return decorator
  - This allows for easy tracking of function versions throughout the project

* Problem: Inconsistent handling of file paths across different operating systems
  Solution:
  - Utilized pathlib for cross-platform path handling:
    from pathlib import Path
    cache_file = Path.home() / ".cache" / "language_translator" / "translation_cache.pkl"
  - This ensures consistent file path handling across different operating systems

* Problem: Difficulty in managing and updating required dependencies
  Solution:
  - Centralized the list of required modules in the check_dependencies function
  - Regularly review and update this list as the project evolves
  - Consider using a requirements.txt file for more complex dependency management

* Problem: Lack of type checking leading to runtime errors
  Solution:
  - Implemented type hints throughout the utility functions:
    def clean_json_string(json_string: str) -> str:
    def is_json_complete(json_string: str) -> bool:
  - This improves code readability and allows for static type checking

* Problem: Difficulty in debugging complex utility functions
  Solution:
  - Implemented comprehensive logging in utility functions:
    logger.debug(f"Cleaning JSON string: {json_string[:50]}...")
    logger.debug(f"JSON complete check result: {result}")
  - This provides valuable insights into the behavior of utility functions during runtime
"""

# Standard library imports
from functools import wraps
import signal
import sys
import os
import json
import re
import threading
import time
import asyncio
from typing import Any, Callable, List, Union, Dict

# Local application imports
from config import versioned
from debug_logging import LTLogger

# Global flag to indicate if the script should exit
should_exit = threading.Event()

@versioned("2.3.0")
def setup_graceful_shutdown(cleanup_functions: List[Callable], logger: LTLogger):
    def graceful_shutdown(signum, frame):
        logger.info("Received interrupt signal. Initiating graceful shutdown...")
        should_exit.set()  # Set the exit flag
        for cleanup_func in cleanup_functions:
            try:
                cleanup_func()
            except Exception as e:
                logger.error(f"Error during cleanup: {str(e)}")
        logger.info("Graceful shutdown complete. Exiting...")
        os._exit(0)  # Force exit

    signal.signal(signal.SIGINT, graceful_shutdown)
    signal.signal(signal.SIGTERM, graceful_shutdown)

@versioned("1.5.0")
def check_exit_flag():
    return should_exit.is_set()

@versioned("1.4.0")
def check_dependencies(logger: LTLogger):
    """
    Check if all required modules are installed.

    Args:
        logger (Logger): Logger instance for debugging.
    """
    required_modules = [
        'anthropic', 'openai', 'rich', 'pandas', 'tiktoken'
    ]
    missing_modules = []
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(module)
    
    if missing_modules:
        logger.error("The following required modules are missing:")
        for module in missing_modules:
            logger.error(f"- {module}")
        logger.error("Please install these modules and try again.")
        sys.exit(1)
    else:
        logger.info("All required modules are installed.")

@versioned("1.4.1")
def clean_json_string(json_string: str) -> str:
    # Remove ```json from the start and ``` from the end
    cleaned = re.sub(r'^```json\s*', '', json_string)
    cleaned = re.sub(r'\s*```$', '', cleaned)
    # Remove any leading/trailing whitespace
    cleaned = cleaned.strip()
    # Remove any trailing backticks that might be left
    cleaned = re.sub(r'`+$', '', cleaned)
    return cleaned

@versioned("1.4.0")
def is_json_complete(json_string: str) -> bool:
    cleaned_string = clean_json_string(json_string)
    try:
        json.loads(cleaned_string)
        return True
    except json.JSONDecodeError:
        return False

@versioned("1.4.1")
def retry_with_exponential_backoff(
    func: Callable,
    max_retries: int = 5,
    initial_wait: float = 1,
    exponential_base: float = 2
) -> Callable:
    """
    Retry a function with exponential backoff.

    Args:
        func (Callable): The function to retry.
        max_retries (int): Maximum number of retries.
        initial_wait (float): Initial wait time in seconds.
        exponential_base (float): Base for exponential backoff.

    Returns:
        Callable: Decorated function with retry logic.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        wait_time = initial_wait
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Function {func.__name__} failed after {max_retries} attempts. Error: {str(e)}")
                    raise
                logger.warning(f"Attempt {attempt + 1} failed. Retrying in {wait_time:.2f} seconds. Error: {str(e)}")
                time.sleep(wait_time)
                wait_time *= exponential_base
    return wrapper