"""Logging setup for the Instagram Auto-Comment Bot."""

import logging
import sys


def setup_logger(name: str = "bot", level: int = logging.INFO) -> logging.Logger:
    """Configure and return a logger with timestamped format.

    Format: [TIMESTAMP] [LEVEL] message
    Output goes to stdout so GitHub Actions captures it in run logs.
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    logger.setLevel(level)

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


# Module-level logger instance for easy import
log = setup_logger()
