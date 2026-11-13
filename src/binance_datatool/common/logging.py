"""CLI logging helpers."""

from __future__ import annotations

import sys

from loguru import logger
from tqdm import tqdm

_FORMAT = (
    "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level}</level> | "
    "<cyan>{module}</cyan> - "
    "{message}"
)


def configure_cli_logging(verbosity: int) -> None:
    """Configure loguru for a CLI invocation.

    Args:
        verbosity: 0 = WARNING, 1 = INFO, 2+ = DEBUG.
    """
    logger.remove()

    if verbosity >= 2:
        level = "DEBUG"
    elif verbosity == 1:
        level = "INFO"
    else:
        level = "WARNING"

    stderr = sys.stderr

    def write_log_line(message: str) -> None:
        tqdm.write(str(message), file=stderr, end="")

    logger.add(write_log_line, level=level, format=_FORMAT, colorize=stderr.isatty())
