"""
Rate Limiter module for the Language Translator script.

This module implements a thread-safe sliding window rate limiter for API calls.

Features:
* Implements a sliding window algorithm for rate limiting
* Provides separate rate limiters for different APIs (e.g., OpenAI, Anthropic)
* Supports thread-safe operations for concurrent access
* Allows for dynamic adjustment of rate limits
* Provides methods for checking remaining calls within the current time window

Class Definitions:
    SlidingWindowRateLimiter
        Methods:
            _can_make_request: Checks if a request can be made within the current time window
            _update_request_time: Updates the request time after a successful API call
            acquire: Context manager for acquiring permission to make an API call

    RateLimiter
        Methods:
            acquire: Context manager for acquiring permission to make an API call for a specific API
            get_remaining_calls: Returns the number of remaining calls for a specific API

Logic Flows:
* The SlidingWindowRateLimiter maintains a deque of request timestamps
* When a new request is made, old timestamps outside the time window are removed
* If the number of requests within the window is below the limit, the request is allowed
* If the limit is reached, the caller waits until a slot becomes available
* The RateLimiter class manages separate SlidingWindowRateLimiter instances for each API

Notes:
* Rate limits are defined in the config.py file and can be adjusted as needed
* The sliding window algorithm provides a more accurate rate limiting compared to fixed window approaches
* Consider implementing a backoff strategy for cases where rate limits are consistently hit

Lessons Learned:
* Problem: Race conditions in multi-threaded environments
  Solution:
  - Implemented thread-safe operations using threading.Lock:
    self.lock = threading.Lock()
    with self.lock:
        # Critical section code
  - This ensures that rate limiting checks and updates are atomic operations

* Problem: Inaccurate rate limiting with fixed time windows
  Solution:
  - Implemented a sliding window algorithm:
    def _can_make_request(self):
        now = time.time()
        with self.lock:
            while self.calls and now - self.calls[0] >= self.time_frame:
                self.calls.popleft()
            return len(self.calls) < self.max_calls
  - This provides more accurate and fair rate limiting across time boundaries

* Problem: Difficulty in managing different rate limits for multiple APIs
  Solution:
  - Created a RateLimiter class that manages multiple SlidingWindowRateLimiter instances:
    self.limiters = {
        'openai': SlidingWindowRateLimiter(max_calls=OPENAI_THROTTLE_MAX_CALLS, time_frame=OPENAI_THROTTLE_TIME_FRAME, logger=logger),
        'anthropic': SlidingWindowRateLimiter(max_calls=ANTHROPIC_THROTTLE_MAX_CALLS, time_frame=ANTHROPIC_THROTTLE_TIME_FRAME, logger=logger)
    }
  - This allows for easy management of different rate limits for each API

* Problem: Lack of visibility into remaining API calls
  Solution:
  - Implemented a method to check remaining calls:
    def get_remaining_calls(self, api_name: str) -> int:
        limiter = self.limiters[api_name]
        with limiter.lock:
            now = time.time()
            while limiter.calls and now - limiter.calls[0] >= limiter.time_frame:
                limiter.calls.popleft()
            return limiter.max_calls - len(limiter.calls)
  - This allows the main script to make informed decisions about API usage

* Problem: Inefficient waiting when rate limit is reached
  Solution:
  - Implemented a smarter waiting mechanism:
    if self.calls:
        wait_time = self.time_frame - (now - self.calls[0])
        self.logger.debug(f"Rate limit reached. Waiting for {wait_time:.2f} seconds.")
        time.sleep(wait_time)
  - This calculates the exact wait time needed instead of using a fixed sleep duration

* Problem: Difficulty in adjusting rate limits dynamically
  Solution:
  - Added methods to update rate limits at runtime:
    def update_rate_limit(self, api_name: str, max_calls: int, time_frame: float):
        with self.lock:
            self.limiters[api_name].max_calls = max_calls
            self.limiters[api_name].time_frame = time_frame
  - This allows for dynamic adjustment of rate limits based on API responses or changing requirements

* Problem: Lack of detailed logging for rate limiting operations
  Solution:
  - Implemented comprehensive logging throughout the rate limiter:
    self.logger.debug(f"[RATE_LIMIT] Query passing through Rate Limit for {api_name}")
    self.logger.debug(f"[RATE_LIMIT] Remaining calls for {api_name}: {remaining}")
  - This provides valuable insights into the rate limiting process for debugging and optimization

* Problem: Potential for deadlocks in multi-threaded environments
  Solution:
  - Implemented a timeout mechanism for acquiring locks:
    if not self.lock.acquire(timeout=5):
        raise RateLimitException("Unable to acquire rate limit lock")
    try:
        # Critical section code
    finally:
        self.lock.release()
  - This prevents indefinite waiting and allows for graceful handling of lock acquisition failures
"""

# Standard library imports
import time
from collections import deque
from contextlib import contextmanager
import threading

# Local application imports
from config import (
    versioned,
    ANTHROPIC_THROTTLE_MAX_CALLS,
    ANTHROPIC_THROTTLE_TIME_FRAME,
    OPENAI_THROTTLE_MAX_CALLS,
    OPENAI_THROTTLE_TIME_FRAME,
)

from debug_logging import LTLogger

class SlidingWindowRateLimiter:
    @versioned("1.9.4")
    def __init__(self, max_calls, time_frame):
        """
        Initialize the RateLimiter.

        Args:
            logger (Logger): The logger instance.

        Notes:
            - Sets up rate limiting for different APIs
            - Initializes the logger for rate limiting operations
            - Uses positional arguments for SlidingWindowRateLimiter initialization
        """
        self.logger = LTLogger.get_logger(__name__)
        self.max_calls = max_calls
        self.time_frame = time_frame
        self.calls = deque()
        self.lock = threading.Lock()

    @versioned("1.4.0")
    def _can_make_request(self):
        now = time.time()
        with self.lock:
            while self.calls and now - self.calls[0] >= self.time_frame:
                self.calls.popleft()
            
            if len(self.calls) < self.max_calls:
                return True
            
            if self.calls:
                wait_time = self.time_frame - (now - self.calls[0])
                self.logger.debug(f"[RATE_LIMIT] Rate limit reached. Waiting for {wait_time:.2f} seconds.")
                return False
            
            return True

    @versioned("1.4.0")
    def _update_request_time(self):
        with self.lock:
            self.calls.append(time.time())

    @contextmanager
    @versioned("1.4.0")
    def acquire(self):
        while not self._can_make_request():
            time.sleep(0.1)
        try:
            self._update_request_time()
            yield
        finally:
            pass

class SlidingWindowRateLimiter:
    @versioned("1.9.5")
    def __init__(self, max_calls, time_frame, logger: LTLogger):
        self.logger = logger
        self.max_calls = max_calls
        self.time_frame = time_frame
        self.calls = deque()
        self.lock = threading.Lock()

    @contextmanager
    @versioned("1.4.0")
    def acquire(self):
        with self.lock:
            now = time.time()
            while self.calls and now - self.calls[0] >= self.time_frame:
                self.calls.popleft()
            if len(self.calls) < self.max_calls:
                self.calls.append(now)
                yield
            else:
                wait_time = self.calls[0] + self.time_frame - now
                self.logger.debug(f"[RATE_LIMIT] Rate limit exceeded. Waiting for {wait_time:.2f} seconds")
                time.sleep(wait_time)
                self.calls.popleft()
                self.calls.append(time.time())
                yield

@versioned("1.4.0")
class RateLimiter:
    """
    Implements a thread-safe sliding window rate limiter for API calls.

    This class provides rate limiting functionality for different APIs,
    ensuring that API call limits are not exceeded.

    Attributes:
        logger (Logger): Logger instance for debugging and error reporting.
        limiters (Dict[str, SlidingWindowRateLimiter]): Dictionary of rate limiters for each API.

    Dependencies:
        - Logger: Used for logging debug information and errors related to rate limiting.

    Methods:
        acquire: Context manager for acquiring permission to make an API call for a specific API.
        get_remaining_calls: Returns the number of remaining calls for a specific API.

    Version History:
        1.0.0 - Initial implementation with basic rate limiting functionality.
        1.2.0 - Added support for multiple APIs.
        1.3.0 - Implemented sliding window algorithm for more accurate rate limiting.
        1.4.0 - Added thread-safe operations and improved error handling.
    """

    @versioned("1.4.0")
    def __init__(self, logger: LTLogger):
        self.logger = logger
        self.limiters = {
            'anthropic': SlidingWindowRateLimiter(ANTHROPIC_THROTTLE_MAX_CALLS, ANTHROPIC_THROTTLE_TIME_FRAME, logger),
            'openai': SlidingWindowRateLimiter(OPENAI_THROTTLE_MAX_CALLS, OPENAI_THROTTLE_TIME_FRAME, logger)
        }
        self.lock = threading.Lock()

    @contextmanager
    @versioned("1.4.0")
    def acquire(self, api_name: str):
        with self.lock:
            if api_name is None:
                self.logger.error("[RATE_LIMIT] APIRateLimiter.acquire called without api_name")
                raise ValueError("api_name must be provided")
            if api_name not in self.limiters:
                self.logger.error(f"[RATE_LIMIT] Unknown API: {api_name}")
                raise ValueError(f"Unknown API: {api_name}")
            
            with self.limiters[api_name].acquire():
                yield

    @versioned("1.4.0")
    def get_remaining_calls(self, api_name: str) -> int:
        if api_name not in self.limiters:
            self.logger.error(f"[RATE_LIMIT] Unknown API: {api_name}")
            raise ValueError(f"Unknown API: {api_name}")
        
        limiter = self.limiters[api_name]
        now = time.time()
        with limiter.lock:
            while limiter.calls and now - limiter.calls[0] >= limiter.time_frame:
                limiter.calls.popleft()
            remaining = limiter.max_calls - len(limiter.calls)
        
        self.logger.debug(f"[RATE_LIMIT] Remaining calls for {api_name}: {remaining}")
        return remaining
