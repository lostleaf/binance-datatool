"""Workflow for downloading archive files."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from loguru import logger

from binance_datatool.archive import (
    ArchiveClient,
    DownloadRequest,
    SymbolArchiveDir,
    download_archive_files,
)

from .list_files import ArchiveListFilesWorkflow
from .results import DiffEntry, DiffResult, DownloadResult, SymbolListingError

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from binance_datatool.archive import Aria2DownloadResult
    from binance_datatool.common import DataFrequency, DataType, TradeType

    from .results import ListFilesResult


class ArchiveDownloadWorkflow:
    """Workflow for diffing and downloading archive files to the local archive store."""

    def __init__(
        self,
        trade_type: TradeType,
        data_freq: DataFrequency,
        data_type: DataType,
        symbols: Sequence[str],
        archive_home: Path,
        interval: str | None = None,
        dry_run: bool = False,
        inherit_aria2_proxy: bool = False,
        progress_bar: bool = False,
        client: ArchiveClient | None = None,
        download_func: Callable[..., Aria2DownloadResult] | None = None,
    ) -> None:
        """Initialize the download workflow.

        Args:
            trade_type: Market segment to query.
            data_freq: Partition frequency.
            data_type: Dataset type.
            symbols: Symbols to download, preserving caller order.
            archive_home: Root directory for local archive data storage.
            interval: Interval directory for kline-class data types.
            dry_run: When ``True``, compute the diff without downloading.
            inherit_aria2_proxy: Whether aria2c should inherit proxy env vars.
            progress_bar: Whether to display a tqdm progress bar on stderr.
            client: Optional pre-configured archive client.
            download_func: Optional download callable for dependency injection.
        """
        self.trade_type = trade_type
        self.data_freq = data_freq
        self.data_type = data_type
        self.symbols = list(symbols)
        self.archive_home = archive_home
        self.interval = interval
        self.dry_run = dry_run
        self.inherit_aria2_proxy = inherit_aria2_proxy
        self.progress_bar = progress_bar
        self.client = client or ArchiveClient()
        self.download_func = download_func or download_archive_files

    def _build_diff_result(self, list_result: ListFilesResult) -> DiffResult:
        """Compute the download diff from remote file listings."""
        to_download: list[DiffEntry] = []
        skipped = 0
        listing_errors: list[SymbolListingError] = []

        for entry in list_result.per_symbol:
            if entry.error is not None:
                listing_errors.append(SymbolListingError(symbol=entry.symbol, error=entry.error))
                continue

            for remote_file in entry.files:
                local_path = self.archive_home / Path(remote_file.key)
                if (
                    local_path.exists()
                    and local_path.stat().st_size == remote_file.size
                    and not local_path.with_name(f"{local_path.name}.aria2").exists()
                    and local_path.stat().st_mtime >= remote_file.last_modified.timestamp()
                ):
                    skipped += 1
                    continue

                reason: Literal["new", "updated"] = "updated" if local_path.exists() else "new"
                to_download.append(
                    DiffEntry(remote=remote_file, local_path=local_path, reason=reason)
                )

        return DiffResult(
            to_download=to_download,
            skipped=skipped,
            total_remote=list_result.total_remote_files,
            listing_errors=listing_errors,
        )

    def _invalidate_verified_markers(self, entries: Sequence[DiffEntry]) -> None:
        """Delete stale verify markers for updated zip or checksum files."""
        targets_by_dir: dict[Path, set[str]] = defaultdict(set)
        for entry in entries:
            if entry.reason != "updated":
                continue

            path = entry.local_path
            if path.name.endswith(".CHECKSUM"):
                targets_by_dir[path.parent].add(path.name.removesuffix(".CHECKSUM"))
            elif path.name.endswith(".zip"):
                targets_by_dir[path.parent].add(path.name)

        for dir_path, zip_names in targets_by_dir.items():
            SymbolArchiveDir(dir_path).clear_markers_many(zip_names)

    @staticmethod
    def _delete_updated_files(entries: Sequence[DiffEntry]) -> None:
        """Remove local files that are scheduled for re-download.

        Deleting stale copies before the download starts ensures that the
        downloader's per-file existence check treats every request uniformly
        as a "file does not yet exist" scenario.
        """
        for entry in entries:
            if entry.reason == "updated":
                entry.local_path.unlink(missing_ok=True)

    async def run(self) -> DiffResult | DownloadResult:
        """Execute the workflow and return either a diff or a download result.

        Returns:
            :class:`DiffResult` when ``dry_run`` is enabled, otherwise
            :class:`DownloadResult` with aggregated counts and errors.
        """
        list_workflow = ArchiveListFilesWorkflow(
            trade_type=self.trade_type,
            data_freq=self.data_freq,
            data_type=self.data_type,
            symbols=self.symbols,
            interval=self.interval,
            progress_bar=self.progress_bar,
            client=self.client,
        )
        list_result = await list_workflow.run()
        logger.info("scanning local store for diff")
        diff_result = self._build_diff_result(list_result)
        logger.info(
            "diff complete: {} up to date, {} to download",
            diff_result.skipped,
            len(diff_result.to_download),
        )

        if self.dry_run:
            return diff_result

        if not diff_result.to_download:
            return DownloadResult(
                total_remote=diff_result.total_remote,
                skipped=diff_result.skipped,
                downloaded=0,
                failed=0,
                listing_errors=diff_result.listing_errors,
            )

        self.archive_home.mkdir(parents=True, exist_ok=True)
        self._invalidate_verified_markers(diff_result.to_download)
        self._delete_updated_files(diff_result.to_download)

        requests = [
            DownloadRequest(url=entry.url, local_path=entry.local_path)
            for entry in diff_result.to_download
        ]

        logger.info("downloading {} file(s)", len(requests))
        aria2_result = self.download_func(
            requests,
            inherit_proxy=self.inherit_aria2_proxy,
            progress_bar=self.progress_bar,
        )

        return DownloadResult(
            total_remote=diff_result.total_remote,
            skipped=diff_result.skipped,
            downloaded=aria2_result.succeeded,
            failed=len(aria2_result.failed_requests),
            listing_errors=diff_result.listing_errors,
        )
