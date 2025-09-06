"""Logging utilities (simple wrapper)."""

from __future__ import annotations
import logging
from typing import Optional

_LOGGER: Optional[logging.Logger] = None


def get_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is None:
        logger = logging.getLogger("yt_downloader")
        handler = logging.StreamHandler()
        fmt = logging.Formatter("[%(asctime)s] %(levelname)s %(message)s")
        handler.setFormatter(fmt)
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        _LOGGER = logger
    return _LOGGER
