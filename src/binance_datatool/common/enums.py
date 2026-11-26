"""Shared enums for Binance market archive paths."""

from enum import StrEnum

__all__ = ["ContractType", "DataFrequency", "DataType", "MarketType"]


class MarketType(StrEnum):
    """Binance trading market type"""

    spot = "spot"  # Spot trading market
    um = "um"  # USDⓈ-M perpetual and delivery futures
    cm = "cm"  # COIN-M perpetual and delivery futures

    @property
    def s3_path(self) -> str:
        """Return the S3 directory path component for this market type.

        Returns:
            Path segment such as ``"spot"`` or ``"futures/um"``.
        """
        if self is MarketType.spot:
            return "spot"
        return f"futures/{self.value}"


class DataFrequency(StrEnum):
    """Partition frequency on data.binance.vision.

    Determines whether archive files are partitioned by day or by month.
    """

    daily = "daily"
    monthly = "monthly"


class DataType(StrEnum):
    """Dataset type on data.binance.vision.

    Each member name uses ``snake_case`` while the value matches the
    S3 path segment exactly (e.g. ``"fundingRate"``).
    """

    klines = "klines"
    agg_trades = "aggTrades"
    trades = "trades"
    funding_rate = "fundingRate"
    book_depth = "bookDepth"
    book_ticker = "bookTicker"
    index_price_klines = "indexPriceKlines"
    mark_price_klines = "markPriceKlines"
    premium_index_klines = "premiumIndexKlines"
    metrics = "metrics"
    liquidation_snapshot = "liquidationSnapshot"

    @property
    def has_interval_layer(self) -> bool:
        """Return whether this data type uses an interval directory layer.

        Returns:
            ``True`` for kline-class data types whose S3 path includes
            an interval directory segment (e.g. ``"1m"``, ``"1h"``);
            ``False`` otherwise.
        """
        return self in {
            DataType.klines,
            DataType.index_price_klines,
            DataType.mark_price_klines,
            DataType.premium_index_klines,
        }


class ContractType(StrEnum):
    """Futures contract settlement style."""

    perpetual = "perpetual"  # No expiry date; position stays open until closed
    delivery = "delivery"  # Expires on a fixed settlement date (e.g. 240927)
