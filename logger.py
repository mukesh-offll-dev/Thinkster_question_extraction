# =============================================================================
# logger.py – Centralised Logging Configuration
# =============================================================================
# Sets up a logger that writes to both the console and a rotating log file.
# Import `get_logger` in any module to obtain a configured logger instance.
# =============================================================================

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_DIR  = Path("logs")
LOG_FILE = LOG_DIR / "thinkster_automation.log"

# Colour codes for console output (Windows-compatible via ANSI)
_COLOURS = {
    "DEBUG":    "\033[36m",   # Cyan
    "INFO":     "\033[32m",   # Green
    "WARNING":  "\033[33m",   # Yellow
    "ERROR":    "\033[31m",   # Red
    "CRITICAL": "\033[35m",   # Magenta
    "RESET":    "\033[0m",
}


class _ColouredFormatter(logging.Formatter):
    """Formatter that adds ANSI colour codes to levelname for console output."""

    def format(self, record: logging.LogRecord) -> str:
        colour = _COLOURS.get(record.levelname, "")
        reset  = _COLOURS["RESET"]
        record.levelname = f"{colour}{record.levelname:<8}{reset}"
        return super().format(record)


def get_logger(name: str = "thinkster") -> logging.Logger:
    """
    Return a configured logger.

    Parameters
    ----------
    name : str
        Logger name (defaults to "thinkster").

    Returns
    -------
    logging.Logger
        Configured logger instance shared across the application.
    """
    logger = logging.getLogger(name)

    # Prevent duplicate handlers if called multiple times
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Ensure log directory exists
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Console handler – INFO and above, coloured
    # ------------------------------------------------------------------
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_fmt = _ColouredFormatter(
        fmt="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    console_handler.setFormatter(console_fmt)

    # ------------------------------------------------------------------
    # File handler – DEBUG and above, plain text, rotated at 5 MB
    # ------------------------------------------------------------------
    file_handler = RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(module)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    file_handler.setFormatter(file_fmt)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger
