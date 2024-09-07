"""
Configuration file for the Language Translator script.

This module contains global configuration settings and constants used throughout the project.

Features:
* Centralizes all configuration settings in one place
* Defines API keys and authentication settings
* Sets cache and file paths
* Defines API token limitations and batch processing settings
* Sets multithreading parameters
* Defines expected file headers and target languages
* Sets version information
* Defines API models and rate limiting parameters
* Implements a versioning decorator for functions

Variables:
* ANTHROPIC_API_KEY: The API key for the Anthropic API
* CHATGPT_API_KEY: The API key for the ChatGPT API
* CACHE_DIR: The directory for the Pickle cache specific to this script
* CACHE_FILE: The file for the Pickle cache stored within the script-specific cache directory
* STATS_FILE: The file for storing statistics
* MAX_TOKENS: Maximum number of tokens allowed in a single API call
* MAX_ALLOWED_TOKENS: Adjusted maximum tokens for safety margin
* INITIAL_BATCH_SIZE: Initial number of languages to process in a batch
* ESTIMATION_RETRIES: Number of retries for the estimation-based strategy
* SINGLE_RETRIES: Number of retries for the single language strategy
* MAX_CONTINUATION_ATTEMPTS: Maximum attempts for requesting continuation of incomplete responses
* MAX_WORKERS: Maximum number of concurrent workers for processing
* EXPECTED_HEADER: Expected header for Localization.txt files
* TARGET_LANGUAGES: List of target languages for translation
* QUOTED_COLUMNS: Columns that should be quoted in the output
* VERSION: Current version of the script
* LAST_UPDATED: Date of last update
* OPENAI_MODEL: Specified OpenAI model to use
* ANTHROPIC_MODEL: Specified Anthropic model to use
* ANTHROPIC_THROTTLE_MAX_CALLS: Maximum calls allowed for Anthropic API in the time frame
* ANTHROPIC_THROTTLE_TIME_FRAME: Time frame for Anthropic API rate limiting
* OPENAI_THROTTLE_MAX_CALLS: Maximum calls allowed for OpenAI API in the time frame
* OPENAI_THROTTLE_TIME_FRAME: Time frame for OpenAI API rate limiting

Functions:
* versioned: Decorator to add version information to functions

Notes:
* Ensure all sensitive information (like API keys) are stored as environment variables
* Update VERSION and LAST_UPDATED whenever significant changes are made to the script
* Adjust MAX_ALLOWED_TOKENS based on the specific requirements of the APIs being used

Lessons Learned:
* Problem: Hardcoded configuration values scattered throughout the codebase
  Solution:
  - Centralized all configuration in this single file
  - Used uppercase names for constants to distinguish them from variables
  - Grouped related settings together for better organization

* Problem: Inconsistent versioning across functions
  Solution:
  - Implemented a versioned decorator:
    def versioned(version: str):
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            wrapper.__version__ = version
            return wrapper
        return decorator
  - This ensures consistent version tracking across all decorated functions

* Problem: Difficulty in adjusting API rate limits
  Solution:
  - Defined separate constants for each API's rate limiting:
    ANTHROPIC_THROTTLE_MAX_CALLS = 10
    ANTHROPIC_THROTTLE_TIME_FRAME = 10  # in seconds
    OPENAI_THROTTLE_MAX_CALLS = 10
    OPENAI_THROTTLE_TIME_FRAME = 10  # in seconds
  - This allows for easy adjustment of rate limits for each API independently

* Problem: Lack of flexibility in file paths
  Solution:
  - Used pathlib for cross-platform compatibility:
    CACHE_DIR = Path.home() / ".cache" / "language_translator"
    CACHE_FILE = CACHE_DIR / "translation_cache.pkl"
  - This ensures the script works correctly across different operating systems

* Problem: Difficulty in managing target languages
  Solution:
  - Derived TARGET_LANGUAGES from EXPECTED_HEADER:
    TARGET_LANGUAGES = EXPECTED_HEADER[7:]  # This will include all languages starting from 'german'
  - This ensures that target languages are always in sync with the expected file format

* Problem: Inconsistent token limits leading to API errors
  Solution:
  - Implemented a safety margin for token limits:
    MAX_ALLOWED_TOKENS = int(MAX_TOKENS * 0.65)
  - This helps prevent exceeding token limits due to inaccurate estimations

* Problem: Difficulty in tracking script versions
  Solution:
  - Added VERSION and LAST_UPDATED constants:
    VERSION = "1.0.0"
    LAST_UPDATED = "2024-09-02"
  - This makes it easy to track when the script was last updated and what version is currently in use

* Problem: Inconsistent quoting in output files
  Solution:
  - Defined QUOTED_COLUMNS to specify which columns should be quoted:
    QUOTED_COLUMNS = ['english', 'Context / Alternate Text'] + TARGET_LANGUAGES
  - This ensures consistent quoting across all output files
"""

# Standard library imports
from pathlib import Path
import os
from functools import wraps

# Version information
VERSION = "1.0.0"
LAST_UPDATED = "2024-09-02"

# Cache settings
CACHE_DIR = Path.home() / ".cache" / "language_translator"
CACHE_FILE = CACHE_DIR / "translation_cache.pkl"
STATS_FILE = CACHE_DIR / "translation_stats.json"


# Add these lines at the top of the file, after the imports
ANTHROPIC_API_ENABLED = True
OPENAI_API_ENABLED = True

###### API Keys ######
# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CHATGPT_API_KEY = os.getenv("CHATGPT_API_KEY")
# API Models
#OPENAI_MODEL = "gpt-3.5-turbo"
OPENAI_MODEL = "gpt-3.5-turbo-0125"
ANTHROPIC_MODEL = "claude-3-opus-20240229"

# API Token Limitations
MAX_TOKENS = 1000
MAX_ALLOWED_TOKENS = int(MAX_TOKENS * 0.65)

# API Rate Limiting
ANTHROPIC_THROTTLE_MAX_CALLS = 10
ANTHROPIC_THROTTLE_TIME_FRAME = 10  # in seconds
OPENAI_THROTTLE_MAX_CALLS = 10
OPENAI_THROTTLE_TIME_FRAME = 10  # in seconds

# Add this near the other configuration variables
USE_OPENAI_STREAMING = True

# Add this near the top of the file, with other configuration variables
PREFERRED_API = 'openai'  # or 'anthropic', depending on your preference

###### Batch Settings ######
# Batch Settings
INITIAL_BATCH_SIZE = 13 # How many languages to process at a time in the first batch
ESTIMATION_RETRIES = 3 # How many times to retry the estimation-based strategy
SINGLE_RETRIES = 3 # How many times to retry the single language strategy
MAX_CONTINUATION_ATTEMPTS = 10  # Maximum number of times to request continuation for incomplete JSON responses

# Multithreading settings
MAX_WORKERS = os.cpu_count() or 1 # How many Localization files to process at a time

MAX_RETRIES = 3
RETRY_DELAY = 1  # in seconds

# Add this near the other token-related configurations
TOKEN_ESTIMATION_METHODS = ['ExpansionFactor', 'API', 'Tiktoken']

###### Language Settings ######
# Localization.txt standard file header
EXPECTED_HEADER = ['Key', 'File', 'Type', 'UsedInMainMenu', 'NoTranslate', 'english', 'Context / Alternate Text', 'german', 'latam', 'french', 'italian', 'japanese', 'koreana', 'polish', 'brazilian', 'russian', 'turkish', 'schinese', 'tchinese', 'spanish']

# Languages to translate to
TARGET_LANGUAGES = EXPECTED_HEADER[7:]  # This will include all languages starting from 'german'

# Columns that should be quoted in the Localization.translated.txt
QUOTED_COLUMNS = ['english', 'Context / Alternate Text'] + TARGET_LANGUAGES

# Language alternative keys
LANGUAGE_ALTERNATIVES = {
    'german': ['de'],
    'latam': ['latin american spanish','es-419'],
    'french': ['fr'],
    'italian': ['it'],
    'japanese': ['ja'],
    'koreana': ['korean','ko'],
    'polish': ['pl'],
    'brazilian': ['portuguese','pt-br'],
    'russian': ['ru'],
    'turkish': ['tr'],
    'schinese': ['simplified chinese','zh-cn'],
    'tchinese': ['traditional chinese','zh-tw'], 
    'spanish': ['es'],
}


# This is defined here so that it is loaded in the correct order for all other modules.
def versioned(version: str):
    """
    Decorator to add version information to functions.
    All functions should use this decorator to ensure version information is available.
    Any time a function is updated, the version within this decorator should be updated on that function.

    Args:
        version (str): Version string to add to the function.

    Returns:
        Callable: Decorated function with version information.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        wrapper.__version__ = version
        return wrapper
    return decorator

