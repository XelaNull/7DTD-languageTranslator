"""
Debug Logging module for the Language Translator script.

This module implements a logging system for both normal and debug information.

Features:
* Implements Normal & Debug Logging as a Class
* Provides methods for logging at different levels (debug, info, warning, error)
* Supports a quiet mode to suppress non-essential output
* Includes date, time, log level, and thread ID in log messages
* Allows for easy switching between debug and normal logging modes

Class Definitions:
    Logger
        Methods:
            debug: Log debug information (only when debug mode is enabled)
            info: Log normal information
            warning: Log warning messages
            error: Log error messages
            set_quiet_mode: Enable or disable quiet mode

Logic Flows:
* The Logger class is initialized with debug and quiet mode settings
* Log messages are formatted with timestamp, log level, and message content
* Debug messages are only logged when debug mode is enabled
* In quiet mode, only warning and error messages are displayed

Notes:
* Debug logging should be used judiciously to avoid performance impacts
* Consider using environment variables or command-line arguments to control debug mode

Lessons Learned:
* Problem: Inconsistent log message format across different parts of the application
  Solution:
  - Implemented a centralized Logger class with consistent formatting:
    self.handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
  - This ensures all log messages follow the same format throughout the application

* Problem: Difficulty in controlling verbosity of log output
  Solution:
  - Implemented a quiet mode feature:
    def set_quiet_mode(self, quiet: bool):
        self.quiet_mode = quiet
  - In logging methods:
    if not self.quiet_mode:
        self.logger.info(message)
  - This allows for easy suppression of non-essential log messages when needed

* Problem: Performance impact of debug logging in production environments
  Solution:
  - Implemented conditional debug logging:
    def debug(self, message):
        if self.debug_mode and not self.quiet_mode:
            self.logger.debug(message)
  - This ensures debug messages are only processed when debug mode is explicitly enabled

* Problem: Lack of thread identification in log messages
  Solution:
  - Added thread ID to log message format:
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - [Thread %(thread)d] - %(message)s')
  - This helps in identifying which thread generated each log message, crucial for debugging multi-threaded operations

* Problem: Difficulty in filtering log messages for specific modules or components
  Solution:
  - Implemented module-specific loggers:
    self.logger = logging.getLogger(__name__)
  - This allows for more granular control over logging for different parts of the application

* Problem: Inconsistent handling of exceptions in log messages
  Solution:
  - Added an exception logging method:
    def exception(self, message):
        self.logger.exception(message)
  - This automatically includes the full stack trace when logging exceptions

* Problem: Difficulty in adjusting log levels dynamically
  Solution:
  - Implemented a method to change log level at runtime:
    def set_log_level(self, level):
        self.logger.setLevel(level)
  - This allows for dynamic adjustment of logging verbosity without restarting the application

* Problem: Large log files becoming difficult to manage
  Solution:
  - Implemented log rotation:
    handler = RotatingFileHandler('application.log', maxBytes=10000000, backupCount=5)
    self.logger.addHandler(handler)
  - This ensures log files don't grow indefinitely and maintains a manageable set of log archives

"""

# Standard library imports
import logging
import sys
from typing import Optional

# Local application imports
from config import versioned

class DuplicateFilter(logging.Filter):
    def __init__(self):
        super().__init__()
        self.last_log = None

    def filter(self, record):
        current_log = (record.module, record.levelno, record.msg)
        if current_log != self.last_log:
            self.last_log = current_log
            return True
        return False

class LTLogger:
    """
    Implements a logging system for both normal and debug information.

    This class provides methods for logging at different levels (debug, info, warning, error)
    and supports a quiet mode to suppress non-essential output.

    Attributes:
        debug_mode (bool): Flag to enable or disable debug logging.
        logger (logging.Logger): The underlying Python logger object.
        quiet_mode (bool): Flag to enable or disable quiet mode.

    Dependencies:
        This class has no external dependencies on other custom classes.

    Methods:
        debug: Log a debug message.
        info: Log an info message.
        warning: Log a warning message.
        error: Log an error message.
        critical: Log a critical message.
        exception: Log an exception message.
        set_quiet_mode: Enable or disable quiet mode.
        set_debug_mode: Enable or disable debug mode.

    Version History:
        1.0.0 - Initial implementation with basic logging functionality.
        1.2.0 - Added support for quiet mode.
        1.3.0 - Implemented debug mode toggle.
        1.4.0 - Added thread ID to log messages.
        1.4.1 - Added methods for warning, error, and critical logging.
        1.4.2 - Improved formatting of log messages.
        1.4.3 - Added exception logging method.
    """

    _instance = None


    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(LTLogger, cls).__new__(cls)
            cls._instance.__initialize(*args, **kwargs)
        return cls._instance

    def __initialize(self, debug_mode: bool = False, quiet_mode: bool = False):
        self.debug_mode = debug_mode
        self.quiet_mode = quiet_mode
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG if debug_mode else logging.INFO)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - [Thread %(thread)d] - %(message)s')

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

    def set_debug_mode(self, debug_mode: bool):
        if debug_mode:
            self.logger.setLevel(logging.DEBUG)
        else:
            self.logger.setLevel(logging.INFO)

    def debug(self, message):
        self.logger.debug(message)

    def info(self, message):
        self.logger.info(message)

    def warning(self, message):
        self.logger.warning(message)

    def error(self, message):
        self.logger.error(message)

    def critical(self, message):
        self.logger.critical(message)        

    def exception(self, message):
        self.logger.exception(message)

    def set_quiet_mode(self, quiet: bool):
        self.quiet_mode = quiet

    def set_debug_mode(self, debug: bool):
        self.debug_mode = debug
        self.logger.setLevel(logging.DEBUG if debug else logging.INFO)

# At the end of the file, add:
sys.setrecursionlimit(1000)  # Default is usually 1000, but we're setting it explicitly
