"""Shared public types and constants for binance_datatool."""

from typing import TYPE_CHECKING

from binance_datatool.common.constants import (
    LEVERAGE_EXCLUDES,
    LEVERAGE_SUFFIXES,
    QUOTE_ASSETS,
    S3_DOWNLOAD_PREFIX,
    S3_HTTP_TIMEOUT_SECONDS,
    S3_LISTING_PREFIX,
    STABLECOINS,
)
from binance_datatool.common.enums import ContractType, DataFrequency, DataType, MarketType
from binance_datatool.common.enums import __getattr__ as __getattr__
from binance_datatool.common.filter import (
    CmSymbolFilter,
    SpotSymbolFilter,
    SymbolFilter,
    UmSymbolFilter,
    build_symbol_filter,
)
from binance_datatool.common.logging import configure_cli_logging
from binance_datatool.common.path import ArchiveHomeNotConfiguredError, resolve_archive_home
from binance_datatool.common.symbols import infer_cm_info, infer_spot_info, infer_um_info
from binance_datatool.common.types import (
    CmSymbolInfo,
    SpotSymbolInfo,
    SymbolInfo,
    SymbolInfoBase,
    UmSymbolInfo,
)

if TYPE_CHECKING:
    TradeType = MarketType

__all__ = [
    "ArchiveHomeNotConfiguredError",
    "CmSymbolFilter",
    "CmSymbolInfo",
    "ContractType",
    "DataFrequency",
    "DataType",
    "LEVERAGE_EXCLUDES",
    "LEVERAGE_SUFFIXES",
    "MarketType",
    "QUOTE_ASSETS",
    "S3_DOWNLOAD_PREFIX",
    "S3_HTTP_TIMEOUT_SECONDS",
    "S3_LISTING_PREFIX",
    "STABLECOINS",
    "SpotSymbolFilter",
    "SpotSymbolInfo",
    "SymbolFilter",
    "SymbolInfo",
    "SymbolInfoBase",
    "TradeType",
    "UmSymbolFilter",
    "UmSymbolInfo",
    "build_symbol_filter",
    "configure_cli_logging",
    "infer_cm_info",
    "infer_spot_info",
    "infer_um_info",
    "resolve_archive_home",
]
