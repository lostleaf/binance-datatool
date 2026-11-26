"""Shared helpers for archive workflows."""

from __future__ import annotations

from typing import TYPE_CHECKING

from binance_datatool.common import MarketType, infer_cm_info, infer_spot_info, infer_um_info

if TYPE_CHECKING:
    from binance_datatool.common import SymbolInfo


def infer_symbol_info(market_type: MarketType, symbol: str) -> SymbolInfo | None:
    """Infer typed symbol metadata for the requested market type.

    Args:
        market_type: Market type being listed.
        symbol: Raw symbol from the archive directory listing.

    Returns:
        Parsed symbol metadata, or ``None`` when inference fails.
    """
    match market_type:
        case MarketType.spot:
            return infer_spot_info(symbol)
        case MarketType.um:
            return infer_um_info(symbol)
        case MarketType.cm:
            return infer_cm_info(symbol)
