"""Archive layout, interval validation, and local archive-home resolution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from binance_datatool.common.enums import DataFrequency, DataType, TradeType

ARCHIVE_HOME_ENV_VAR = "BINANCE_DATATOOL_ARCHIVE_HOME"


class ArchiveHomeNotConfiguredError(ValueError):
    """Raised when a command needs an archive home but none was configured."""


def resolve_archive_home(override: str | Path | None = None) -> Path:
    """Resolve the local archive home from CLI override or environment.

    Args:
        override: Optional CLI-provided override path.

    Returns:
        Expanded filesystem path for the local archive home directory.

    Raises:
        ArchiveHomeNotConfiguredError: If neither ``override`` nor the
            ``BINANCE_DATATOOL_ARCHIVE_HOME`` environment variable is set.
    """
    if override is not None:
        return Path(override).expanduser()

    env_value = os.getenv(ARCHIVE_HOME_ENV_VAR)
    if env_value:
        return Path(env_value).expanduser()

    msg = (
        "BINANCE_DATATOOL_ARCHIVE_HOME not configured.\n"
        "Set the BINANCE_DATATOOL_ARCHIVE_HOME environment variable or use --archive-home to specify "
        "where data files should be stored."
    )
    raise ArchiveHomeNotConfiguredError(msg)


def archive_path_parts(
    trade_type: TradeType,
    data_freq: DataFrequency,
    data_type: DataType,
    symbol: str | None = None,
    interval: str | None = None,
) -> tuple[str, ...]:
    """Build archive directory components for remote keys and local paths.

    Args:
        trade_type: Market segment.
        data_freq: Archive partition frequency.
        data_type: Dataset type.
        symbol: Optional symbol directory below the dataset prefix.
        interval: Optional interval directory below the symbol.

    Returns:
        Components to join with ``/`` for S3 keys or with a local ``Path``.
        Interval compatibility is validated separately at public entrypoints.
    """
    parts = ("data", trade_type.s3_path, data_freq.value, data_type.value)
    if symbol is not None:
        parts += (symbol,)
    if interval is not None:
        parts += (interval,)
    return parts


def validate_interval(data_type: DataType, interval: str | None) -> None:
    """Validate whether an interval matches the selected dataset's layout.

    Args:
        data_type: Dataset type whose interval layer is checked.
        interval: Requested interval directory, or ``None``.

    Raises:
        ValueError: If a kline-class dataset lacks an interval or another
            dataset is given one.
    """
    if data_type.has_interval_layer and interval is None:
        msg = "interval is required for kline-class data_type"
        raise ValueError(msg)
    if not data_type.has_interval_layer and interval is not None:
        msg = "interval is not applicable to non-kline data_type"
        raise ValueError(msg)
