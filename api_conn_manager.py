"""
API Management module for the Language Translator script.

This module handles interactions with the Anthropic and OpenAI APIs for text translation.

Features:
* Supports both Anthropic and ChatGPT APIs
* Implements API key validation
* Utilizes CacheManager for storing translations
* Integrates with various components like RateLimiter, ResponseParser, and TokenEstimator

Class Definitions:
    APIConnectionManager
        Methods:
            __init__
            validate_api_keys
            validate_anthropic_api_key
            validate_openai_api_key
            get_current_api
            switch_api
            cleanup

Logic Flows:
* The __init__ method initializes various components and validates API keys
* API key validation is performed for both Anthropic and OpenAI
* The class switches between APIs if one fails validation

Notes:
* The class integrates with other components like CacheManager, StatisticsManager, and Logger
* It uses RateLimiter for managing API request rates
* TokenEstimator is used for estimating token usage
* TranslationManager is initialized for handling translation processes

Lessons Learned:
* Implemented robust API key validation to handle potential API unavailability
* Integrated multiple components to create a comprehensive API connection management system
"""

# Standard library imports
from typing import Union, List, Dict, Any, Set, Optional
import json
import re
import sys
import traceback

# Third-party imports
import anthropic
from openai import OpenAI, AsyncOpenAI  # Add AsyncOpenAI to the import
import tiktoken

# Local application imports
from cache_manager import CacheManager
from config import (
    ANTHROPIC_API_KEY, CHATGPT_API_KEY, MAX_TOKENS, ANTHROPIC_MODEL, OPENAI_MODEL, 
    TARGET_LANGUAGES, ESTIMATION_RETRIES, SINGLE_RETRIES, MAX_CONTINUATION_ATTEMPTS,
    MAX_ALLOWED_TOKENS, versioned, PREFERRED_API, ANTHROPIC_API_ENABLED, OPENAI_API_ENABLED
)
from debug_logging import LTLogger
from rate_limiter import RateLimiter
from response_parser import ResponseParser
from statistics_manager import StatisticsManager
from token_estimator import TokenEstimator
from translation_manager import TranslationManager
from utils import is_json_complete, clean_json_string


@versioned("2.4.0")
class APIConnectionManager:
    """
    Manages API connections and rate limiting for translation services.

    This class handles connections to various translation APIs, manages API keys,
    and implements rate limiting to prevent exceeding API quotas.

    Attributes:
        logger (Logger): Logger instance for debugging and error reporting.
        cache_manager (CacheManager): Manages caching of translation results.
        stats_manager (StatisticsManager): Tracks and reports usage statistics.
        anthropic_client (Anthropic): Client for Anthropic API.
        openai_client (OpenAI): Client for OpenAI API.
        rate_limiter (RateLimiter): Implements rate limiting for API calls.
        response_parser (ResponseParser): Parses API responses.
        token_estimator (TokenEstimator): Estimates token usage for requests.
        clients (dict): Dictionary of API clients.

    Dependencies:
        - CacheManager: Required for caching translation results to reduce API calls.
        - Logger: Used for logging debug information and errors.
        - RateLimiter: Needed to prevent exceeding API rate limits.
        - ResponseParser: Needed for parsing and processing API responses.
        - StatisticsManager: Needed for tracking API usage and performance metrics.
        - TokenEstimator: Helps in optimizing API usage by estimating token counts.

    Methods:
        validate_api_keys: Validate all API keys.
        validate_anthropic_api_key: Validate the Anthropic API key.
        validate_openai_api_key: Validate the OpenAI API key.
        get_current_api: Get the currently active API.
        switch_api: Switch to an alternative API if available.
        cleanup: Perform cleanup operations for the APIManager.
        close_all_clients: Close all API clients asynchronously.
        set_token_estimator: Set the TokenEstimator instance.

    Version History:
        1.0.0 - Initial implementation with basic API management.
        1.5.0 - Added support for multiple APIs and switching between them.
        1.8.0 - Implemented API key validation and error handling.
        2.0.0 - Refactored to use class variables for API status tracking.
        2.1.0 - Added comprehensive docstrings and improved error logging.
        2.2.0 - Implemented global API status tracking using config variables.
        2.3.0 - Updated API validation methods to use global variables.
        2.3.1 - Fixed variable naming inconsistencies with config.py
        2.4.0 - Removed TokenEstimator from __init__ and added set_token_estimator method.
    """
    
    from openai import AsyncOpenAI

    from config import ANTHROPIC_API_ENABLED, OPENAI_API_ENABLED

    @versioned("2.4.0")
    def __init__(self, logger: LTLogger, cache_manager: CacheManager, 
                 stats_manager: StatisticsManager, response_parser: ResponseParser):
        self.logger = logger
        self.cache_manager = cache_manager
        self.stats_manager = stats_manager
        self.response_parser = response_parser
        self.token_estimator = None  # Initialize as None
        self.rate_limiter = RateLimiter(logger)  # Pass the logger to RateLimiter
        self.anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.openai_client = OpenAI(api_key=CHATGPT_API_KEY)
        self.clients = {'anthropic': self.anthropic_client, 'openai': self.openai_client}

        self.logger.debug("[API] APIConnectionManager initialized")
        self.validate_api_keys()

    @versioned("2.4.0")
    def set_token_estimator(self, token_estimator: 'TokenEstimator'):
        self.token_estimator = token_estimator

    @versioned("2.2.0")
    def validate_api_keys(self):
        """
        Validate all API keys.
        """
        global ANTHROPIC_API_ENABLED, OPENAI_API_ENABLED
        if ANTHROPIC_API_ENABLED:
            self.validate_anthropic_api_key()
        if OPENAI_API_ENABLED:
            self.validate_openai_api_key()

    @versioned("2.1.0")
    def validate_anthropic_api_key(self):
        """
        Validate the Anthropic API key.
        """
        global ANTHROPIC_API_ENABLED
        if not ANTHROPIC_API_ENABLED:
            self.logger.info("[ANTHROPIC] Anthropic API is already disabled. Skipping validation.")
            return

        try:
            with self.rate_limiter.acquire('anthropic'):
                response = self.anthropic_client.completions.create(
                    model="claude-2.0",
                    max_tokens_to_sample=1,
                    prompt="Hello, World!"
                )
                if not response:
                    raise ValueError("[ANTHROPIC] No response received from Anthropic API")
            self.logger.info("[ANTHROPIC] Anthropic API key validated successfully.")
        except Exception as e:
            self.logger.error(f"[ANTHROPIC] Anthropic API key validation failed: {str(e)}")
            self.logger.error("[ANTHROPIC] Anthropic API key validation failed. Disabling Anthropic API.")
            ANTHROPIC_API_ENABLED = False

    @versioned("2.1.0")
    def validate_openai_api_key(self):
        """
        Validate the OpenAI API key.
        """
        global OPENAI_API_ENABLED
        if not OPENAI_API_ENABLED:
            self.logger.info("[OPENAI] OpenAI API is already disabled. Skipping validation.")
            return

        try:
            with self.rate_limiter.acquire('openai'):
                models = self.openai_client.models.list()
                if not models:
                    raise ValueError("[OPENAI] No response received from OpenAI API")
            self.logger.info("[OPENAI] OpenAI API key validated successfully.")
        except Exception as e:
            self.logger.error(f"[OPENAI] OpenAI API key validation failed: {str(e)}")
            self.logger.error("[OPENAI] OpenAI API key validation failed. Disabling OpenAI API.")
            OPENAI_API_ENABLED = False

    @versioned("1.5.7")
    def get_current_api(self) -> str:
        """
        Get the currently active API.

        Returns:
            str: The name of the currently active API ('openai', 'anthropic', or None).
        """
        return 'openai' if OPENAI_API_ENABLED else 'anthropic' if ANTHROPIC_API_ENABLED else None

    @versioned("1.5.7")
    def switch_api(self):
        """
        Switch to an alternative API if available.

        Returns:
            str: The name of the new active API, or the current one if no switch is possible.
        """
        current_api = self.get_current_api()
        if current_api == 'anthropic' and OPENAI_API_ENABLED:
            self.logger.info("Switched to OpenAI API")
            return 'openai'
        elif current_api == 'openai' and ANTHROPIC_API_ENABLED:
            self.logger.info("Switched to Anthropic API")
            return 'anthropic'
        else:
            self.logger.warning("Unable to switch API. No alternative API available.")
            return current_api

    @versioned("1.5.7")
    def cleanup(self):
        """
        Perform cleanup operations for the APIManager.
        """
        self.logger.info("Cleaning up APIManager resources...")
        # Add any specific cleanup operations here if needed
        self.logger.info("APIManager cleanup completed.")

    async def close_all_clients(self):
        """
        Close all API clients asynchronously.
        """
        tasks = []
        for client in self.clients.values():
            if hasattr(client, 'aclose'):
                tasks.append(asyncio.create_task(client.aclose()))
        await asyncio.gather(*tasks)
