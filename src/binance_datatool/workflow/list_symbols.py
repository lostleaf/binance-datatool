"""Workflow for listing archive symbols."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from binance_datatool.archive import ArchiveClient

from ._shared import infer_symbol_info
from .results import ListSymbolsResult

if TYPE_CHECKING:
    from binance_datatool.common import DataFrequency, DataType, MarketType, SymbolFilter


def _format_filter_values(
    symbol_filter: SymbolFilter | None,
) -> tuple[str | None, bool, bool, str | None]:
    """Return stable logging fields for the active symbol filter."""
    if symbol_filter is None:
        return None, False, False, None

    quote_assets = getattr(symbol_filter, "quote_assets", None)
    contract_type = getattr(symbol_filter, "contract_type", None)
    return (
        ",".join(sorted(quote_assets)) if quote_assets is not None else None,
        getattr(symbol_filter, "exclude_leverage", False),
        getattr(symbol_filter, "exclude_stable_pairs", False),
        contract_type.value if contract_type is not None else None,
    )


class ArchiveListSymbolsWorkflow:
    """Workflow for listing available symbols from the archive.

    Fetches raw symbols via :class:`ArchiveClient`, infers typed metadata
    per market type, and optionally applies a typed symbol filter.
    """

    def __init__(
        self,
        market_type: MarketType,
        data_freq: DataFrequency,
        data_type: DataType,
        symbol_filter: SymbolFilter | None = None,
        client: ArchiveClient | None = None,
    ) -> None:
        """Initialize the workflow.

        Args:
            market_type: Market type to query.
            data_freq: Partition frequency.
            data_type: Dataset type.
            symbol_filter: Optional typed symbol filter for inferred metadata.
            client: Optional pre-configured archive client. A default
                :class:`ArchiveClient` is created when ``None``.
        """
        self.market_type = market_type
        self.data_freq = data_freq
        self.data_type = data_type
        self.symbol_filter = symbol_filter
        self.client = client or ArchiveClient()

    async def run(self) -> ListSymbolsResult:
        """Execute the workflow and return structured symbol results.

        Returns:
            Raw symbols in archive order, with matched symbols, inference failures,
            and filter exclusions.
        """
        quote_assets, exclude_leverage, exclude_stable_pairs, contract_type = _format_filter_values(
            self.symbol_filter
        )
        logger.info(
            "listing symbols for market_type={} data_freq={} data_type={} quote_assets={} "
            "exclude_leverage={} exclude_stable_pairs={} contract_type={}",
            self.market_type.value,
            self.data_freq.value,
            self.data_type.value,
            quote_assets,
            exclude_leverage,
            exclude_stable_pairs,
            contract_type,
        )
        raw_symbols = await self.client.list_symbols(
            self.market_type, self.data_freq, self.data_type
        )

        inferred = []
        inference_failures: list[str] = []
        for symbol in raw_symbols:
            info = infer_symbol_info(self.market_type, symbol)
            if info is None:
                inference_failures.append(symbol)
                continue
            inferred.append(info)

        if self.symbol_filter is None:
            result = ListSymbolsResult(
                matched=inferred,
                inference_failures=inference_failures,
                filtered_out=[],
                raw_symbols=raw_symbols,
            )
        else:
            matched = []
            filtered_out = []
            for info in inferred:
                if self.symbol_filter.matches(info):
                    matched.append(info)
                else:
                    filtered_out.append(info)

            result = ListSymbolsResult(
                matched=matched,
                inference_failures=inference_failures,
                filtered_out=filtered_out,
                raw_symbols=raw_symbols,
            )

        logger.info(
            "listed symbols: total_raw_symbols={} matched_symbols={} filtered_out_symbols={} "
            "inference_failure_count={}",
            result.total_raw_symbols,
            result.matched_symbols,
            result.filtered_out_symbols,
            result.inference_failure_count,
        )
        return result
