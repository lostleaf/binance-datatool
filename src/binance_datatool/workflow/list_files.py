"""Workflow for listing archive files."""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger

from binance_datatool.archive import ArchiveClient
from binance_datatool.common.path import validate_interval

from .results import ListFilesResult, SymbolListFilesResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from binance_datatool.common import DataFrequency, DataType, TradeType


class ArchiveListFilesWorkflow:
    """Workflow for listing archive files under one or more symbol directories.

    Fetches file metadata concurrently via :class:`ArchiveClient` while
    preserving the caller-provided symbol order and isolating per-symbol
    failures so that one bad symbol does not abort the entire batch.
    """

    def __init__(
        self,
        trade_type: TradeType,
        data_freq: DataFrequency,
        data_type: DataType,
        symbols: Sequence[str],
        interval: str | None = None,
        progress_bar: bool = False,
        client: ArchiveClient | None = None,
    ) -> None:
        """Initialize the workflow.

        Args:
            trade_type: Market segment to query.
            data_freq: Partition frequency.
            data_type: Dataset type.
            symbols: Symbols to list, preserving caller order.
            interval: Interval directory for kline-class data types.
            progress_bar: Whether to render an interactive tqdm progress bar.
            client: Optional pre-configured archive client.
        """
        validate_interval(data_type, interval)

        self.trade_type = trade_type
        self.data_freq = data_freq
        self.data_type = data_type
        self.symbols = list(symbols)
        self.interval = interval
        self.progress_bar = progress_bar
        self.client = client or ArchiveClient()

    async def run(self) -> ListFilesResult:
        """Execute the workflow and return per-symbol file results.

        Returns:
            Aggregate result whose ``per_symbol`` list preserves the
            caller-provided symbol order.
        """
        logger.info(
            "listing {} symbols for trade_type={} data_freq={} data_type={} interval={}",
            len(self.symbols),
            self.trade_type.value,
            self.data_freq.value,
            self.data_type.value,
            self.interval,
        )

        outcomes = await self.client.list_symbol_files_batch(
            self.trade_type,
            self.data_freq,
            self.data_type,
            self.symbols,
            self.interval,
            progress_bar=self.progress_bar,
        )
        per_symbol = [
            SymbolListFilesResult(symbol=symbol, files=files, error=error)
            for symbol, (files, error) in outcomes.items()
        ]
        result = ListFilesResult(per_symbol=per_symbol)
        logger.info(
            "listed files: requested_symbols={} successful_symbols={} failed_symbols={} "
            "total_remote_files={}",
            result.requested_symbols,
            result.successful_symbols,
            result.failed_symbols,
            result.total_remote_files,
        )
        return result
