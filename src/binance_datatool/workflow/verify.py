"""Workflow for verifying local archive files."""

from __future__ import annotations

import multiprocessing
import os
import signal
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from contextlib import contextmanager
from typing import TYPE_CHECKING

from loguru import logger

from binance_datatool.archive import (
    SymbolArchiveDir,
    create_symbol_archive_dir,
    verify_single_file,
)
from binance_datatool.common.path import validate_interval
from binance_datatool.common.progress import ProgressEvent, make_reporter

from .results import VerifyDiffResult, VerifyResult

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from pathlib import Path

    from binance_datatool.archive.symbol_dir import SymbolScanResult
    from binance_datatool.common import DataFrequency, DataType, TradeType


@contextmanager
def _defer_sigint() -> Iterator[None]:
    """Keep pool construction/submission atomic against parent SIGINT on POSIX."""
    if (
        not hasattr(signal, "pthread_sigmask")
        or threading.current_thread() is not threading.main_thread()
    ):
        yield
        return
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT})
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def _initialize_verify_worker() -> None:
    """Let the parent coordinate Ctrl-C, including signals deferred at spawn."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    if hasattr(signal, "pthread_sigmask"):
        signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGINT})


class ArchiveVerifyWorkflow:
    """Workflow for verifying local archive zip files against SHA256 checksums."""

    def __init__(
        self,
        trade_type: TradeType,
        data_freq: DataFrequency,
        data_type: DataType,
        symbols: Sequence[str],
        archive_home: Path,
        interval: str | None = None,
        keep_failed: bool = False,
        dry_run: bool = False,
        n_workers: int | None = None,
        progress_bar: bool = False,
    ) -> None:
        """Initialize the verify workflow.

        Args:
            trade_type: Market segment to query.
            data_freq: Partition frequency.
            data_type: Dataset type.
            symbols: Symbols to verify, preserving caller order.
            archive_home: Root directory for local archive data storage.
            interval: Interval directory for kline-class data types.
            keep_failed: When ``True``, retain failed zip and checksum files
                instead of deleting them.
            dry_run: When ``True``, scan and classify files without verifying
                or mutating the filesystem.
            n_workers: Process pool size. Defaults to ``max(1, cpu_count - 2)``.
            progress_bar: Whether to display a tqdm progress bar on stderr.
        """
        validate_interval(data_type, interval)

        self.trade_type = trade_type
        self.data_freq = data_freq
        self.data_type = data_type
        self.symbols = list(symbols)
        self.archive_home = archive_home
        self.interval = interval
        self.keep_failed = keep_failed
        self.dry_run = dry_run
        self.n_workers = n_workers or max(1, (os.cpu_count() or 1) - 2)
        self.progress_bar = progress_bar
        self._markers_by_zip: dict[Path, list[Path]] = {}

    def _scan_symbol(self, symbol: str) -> SymbolScanResult:
        """Scan one symbol directory and classify its files."""
        dir_obj = create_symbol_archive_dir(
            self.archive_home,
            self.trade_type,
            self.data_freq,
            self.data_type,
            symbol,
            self.interval,
        )
        return dir_obj.scan()

    def _scan(self) -> VerifyDiffResult:
        """Scan local symbol directories and classify verify work."""
        self._markers_by_zip = {}
        if not self.symbols:
            return VerifyDiffResult(to_verify=[], skipped=0, orphan_zips=[], orphan_checksums=[])

        to_verify: list[Path] = []
        orphan_zips: list[Path] = []
        orphan_checksums: list[Path] = []
        skipped = 0

        with make_reporter(
            self.progress_bar,
            total=len(self.symbols),
            description="Scan",
        ) as reporter:
            for symbol in self.symbols:
                result = self._scan_symbol(symbol)
                self._markers_by_zip.update(result._markers_by_zip)
                to_verify.extend(result.to_verify)
                orphan_zips.extend(result.orphan_zips)
                orphan_checksums.extend(result.orphan_checksums)
                skipped += result.skipped
                reporter.tick(ProgressEvent(name=symbol, ok=True))

        return VerifyDiffResult(
            to_verify=to_verify,
            skipped=skipped,
            orphan_zips=orphan_zips,
            orphan_checksums=orphan_checksums,
        )

    def _clean_orphans(self, diff_result: VerifyDiffResult) -> None:
        """Apply orphan cleanup rules before verification."""
        for zip_path in diff_result.orphan_zips:
            self._clear_scanned_markers(zip_path)
        for checksum_path in diff_result.orphan_checksums:
            self._clear_scanned_markers(checksum_path.with_suffix(""))
            SymbolArchiveDir(checksum_path.parent).remove_orphan_checksum(checksum_path.name)

    def _clear_scanned_markers(self, zip_path: Path) -> None:
        """Clear markers already discovered by the symbol scan."""
        for marker_path in self._markers_by_zip.pop(zip_path, []):
            marker_path.unlink(missing_ok=True)

    def _verify_paths(self, zip_paths: list[Path]) -> tuple[int, dict[Path, str]]:
        """Apply completed worker outcomes before reporting their progress."""
        verified = 0
        failed_details: dict[Path, str] = {}
        if not zip_paths:
            return verified, failed_details

        with make_reporter(
            self.progress_bar, total=len(zip_paths), description="Verify"
        ) as reporter:
            executor = None
            try:
                # A signal between starting a process and registering it with the pool
                # can orphan that process. Defer delivery until ownership is recorded.
                with _defer_sigint():
                    executor = ProcessPoolExecutor(
                        max_workers=self.n_workers,
                        mp_context=multiprocessing.get_context("spawn"),
                        initializer=_initialize_verify_worker,
                    )
                futures = []
                for zip_path in zip_paths:
                    with _defer_sigint():
                        futures.append(executor.submit(verify_single_file, zip_path))
                for future in as_completed(futures):
                    result = future.result()
                    zip_path = result.zip_path
                    self._clear_scanned_markers(zip_path)
                    directory = SymbolArchiveDir(zip_path.parent)
                    if result.passed:
                        directory.write_marker(zip_path.name)
                        verified += 1
                    else:
                        failed_details[zip_path] = result.detail
                        if not self.keep_failed:
                            directory.discard_failed(zip_path.name)
                    reporter.tick(ProgressEvent(name=zip_path.name, ok=result.passed))
                executor.shutdown(wait=True)
            except BaseException:
                if executor is not None:
                    # Cancel before waiting; __exit__ would otherwise drain the backlog.
                    executor.shutdown(wait=True, cancel_futures=True)
                raise

        return verified, {
            path: failed_details[path] for path in zip_paths if path in failed_details
        }

    def run(self) -> VerifyDiffResult | VerifyResult:
        """Run the local verify workflow.

        Returns:
            :class:`VerifyDiffResult` when ``dry_run`` is enabled, otherwise
            :class:`VerifyResult` with aggregated counts and per-file failure
            details.
        """
        logger.info("scanning local store for verify work")
        diff_result = self._scan()
        logger.info(
            "scan complete: {} already verified, {} to verify, {} orphan zip(s),"
            " {} orphan checksum(s)",
            diff_result.skipped,
            len(diff_result.to_verify),
            len(diff_result.orphan_zips),
            len(diff_result.orphan_checksums),
        )

        if self.dry_run:
            return diff_result

        if diff_result.orphan_zips or diff_result.orphan_checksums:
            logger.info(
                "cleaning {} orphan zip(s) and {} orphan checksum(s)",
                len(diff_result.orphan_zips),
                len(diff_result.orphan_checksums),
            )
        self._clean_orphans(diff_result)

        logger.info(
            "verifying {} file(s) with {} worker(s)", len(diff_result.to_verify), self.n_workers
        )
        verified, failed_details = self._verify_paths(diff_result.to_verify)

        logger.info("verify complete: {} passed, {} failed", verified, len(failed_details))

        return VerifyResult(
            skipped=diff_result.skipped,
            verified=verified,
            orphan_zips=len(diff_result.orphan_zips),
            orphan_checksums=len(diff_result.orphan_checksums),
            failed_details=failed_details,
        )
