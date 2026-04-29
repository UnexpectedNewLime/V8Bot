"""Logging setup for the application."""

import logging
from typing import Final


LOG_FORMAT: Final[str] = (
    "%(asctime)s %(levelname)s %(name)s %(message)s"
)


def configure_logging(log_level: str = "INFO") -> None:
    """Configure process-wide structured-friendly logging."""

    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format=LOG_FORMAT,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
