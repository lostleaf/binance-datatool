"""Workflow for verifying local archive files."""

from __future__ import annotations

import multiprocessing
import os
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import TYPE_CHECKING

from loguru import logger

from binance_datatool.archive import (
    SymbolArchiveDir,
    create_symbol_archive_dir,
    verify_single_file,
)
from binance_datatool.archive.symbol_dir import collect_markers_by_zip
from binance_datatool.common.progress import ProgressEvent, make_reporter

from ._shared import validate_interval
from .results import VerifyDiffResult, VerifyResult

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from binance_datatool.archive import VerifyFileResult
    from binance_datatool.common import DataFrequency, DataType, TradeType


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

    def _scan_symbol(self, symbol: str):
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
        marker_targets_by_dir: dict[Path, set[str]] = defaultdict(set)
        checksum_targets_by_dir: dict[Path, list[str]] = defaultdict(list)

        for zip_path in diff_result.orphan_zips:
            marker_targets_by_dir[zip_path.parent].add(zip_path.name)

        for checksum_path in diff_result.orphan_checksums:
            dir_path = checksum_path.parent
            checksum_targets_by_dir[dir_path].append(checksum_path.name)
            marker_targets_by_dir[dir_path].add(checksum_path.name.removesuffix(".CHECKSUM"))

        for dir_path, zip_names in marker_targets_by_dir.items():
            SymbolArchiveDir(dir_path).clear_markers_many(zip_names)

        for dir_path, checksum_names in checksum_targets_by_dir.items():
            dir_obj = SymbolArchiveDir(dir_path)
            for checksum_name in checksum_names:
                dir_obj.remove_orphan_checksum(checksum_name)

    def _verify_paths(self, zip_paths: list[Path]) -> list[VerifyFileResult]:
        """Verify zip files in parallel using a process pool."""
        if not zip_paths:
            return []

        with (
            make_reporter(
                self.progress_bar,
                total=len(zip_paths),
                description="Verify",
            ) as reporter,
            ProcessPoolExecutor(
                max_workers=self.n_workers,
                mp_context=multiprocessing.get_context("spawn"),
            ) as executor,
        ):
            futures = [executor.submit(verify_single_file, zip_path) for zip_path in zip_paths]
            results: list[VerifyFileResult] = []
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                reporter.tick(ProgressEvent(name=result.zip_path.name, ok=result.passed))

        result_by_path = {result.zip_path: result for result in results}
        return [result_by_path[zip_path] for zip_path in zip_paths]

    def _apply_all_verify_results(
        self,
        results: list[VerifyFileResult],
    ) -> tuple[int, dict[Path, str]]:
        """Apply filesystem side effects for all verify outcomes.

        Pre-collects markers per directory to avoid per-file glob calls.

        Returns:
            Tuple of (verified count, failed details mapping).
        """
        markers_by_zip = collect_markers_by_zip([result.zip_path for result in results])

        verified = 0
        failed_details: dict[Path, str] = {}

        for result in results:
            zip_path = result.zip_path
            dir_obj = SymbolArchiveDir(zip_path.parent)
            zip_name = zip_path.name

            for marker_path in markers_by_zip.get(zip_path, []):
                marker_path.unlink(missing_ok=True)

            if result.passed:
                dir_obj.write_marker(zip_name)
                verified += 1
                continue

            failed_details[zip_path] = result.detail
            if not self.keep_failed:
                dir_obj.discard_failed(zip_name)

        return verified, failed_details

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
        verify_results = self._verify_paths(diff_result.to_verify)
        verified, failed_details = self._apply_all_verify_results(verify_results)

        logger.info("verify complete: {} passed, {} failed", verified, len(failed_details))

        return VerifyResult(
            skipped=diff_result.skipped,
            verified=verified,
            orphan_zips=len(diff_result.orphan_zips),
            orphan_checksums=len(diff_result.orphan_checksums),
            failed_details=failed_details,
        )
