"""Local symbol archive directory helpers."""

from __future__ import annotations

import math
import os
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING

from binance_datatool.common.path import archive_path_parts

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence
    from pathlib import Path

    from binance_datatool.common import DataFrequency, DataType, TradeType

__all__ = ["SymbolArchiveDir", "create_symbol_archive_dir"]


@dataclass(slots=True)
class SymbolScanResult:
    """Per-symbol scan outcome used internally by archive workflows."""

    to_verify: list[Path]
    orphan_zips: list[Path]
    orphan_checksums: list[Path]
    skipped: int


def _source_freshness_timestamp(zip_mtime: float, checksum_mtime: float) -> int:
    """Round the newest source modification time up to marker precision."""
    return math.ceil(max(zip_mtime, checksum_mtime))


def _match_marker_to_zip(marker_name: str, zip_names: set[str]) -> str | None:
    """Match a marker filename to the zip filename it belongs to."""
    without_suffix = marker_name.removesuffix(".verified")
    if without_suffix in zip_names:
        return without_suffix

    last_dot = without_suffix.rfind(".")
    if last_dot != -1 and without_suffix[:last_dot] in zip_names:
        return without_suffix[:last_dot]

    return None


def _parse_marker_timestamps(
    verified_names: set[str],
    zip_names: set[str],
) -> dict[str, list[int]]:
    """Parse timestamped verified markers and group them by zip name."""
    markers: dict[str, list[int]] = defaultdict(list)
    for name in verified_names:
        without_suffix = name.removesuffix(".verified")
        last_dot = without_suffix.rfind(".")
        if last_dot == -1:
            continue

        ts_str = without_suffix[last_dot + 1 :]
        zip_name = without_suffix[:last_dot]
        try:
            ts = int(ts_str)
        except ValueError:
            continue

        if zip_name in zip_names:
            markers[zip_name].append(ts)

    return dict(markers)


def collect_markers_by_zip(zip_paths: Sequence[Path]) -> dict[Path, list[Path]]:
    """Collect all verification markers for a list of zip files."""
    dirs_to_zip_names: dict[Path, set[str]] = defaultdict(set)
    for zip_path in zip_paths:
        dirs_to_zip_names[zip_path.parent].add(zip_path.name)

    markers_by_zip: dict[Path, list[Path]] = defaultdict(list)
    for dir_path, zip_names in dirs_to_zip_names.items():
        for marker_path in dir_path.glob("*.verified"):
            zip_name = _match_marker_to_zip(marker_path.name, zip_names)
            if zip_name is not None:
                markers_by_zip[dir_path / zip_name].append(marker_path)

    return dict(markers_by_zip)


class SymbolArchiveDir:
    """One local symbol archive directory."""

    def __init__(self, path: Path) -> None:
        """Initialize the symbol archive directory helper."""
        self.path = path

    def zip_path(self, zip_name: str) -> Path:
        """Return the local path for a zip file in this directory."""
        return self.path / zip_name

    def checksum_path(self, zip_name: str) -> Path:
        """Return the local checksum path for a zip file in this directory."""
        return self.path / f"{zip_name}.CHECKSUM"

    def clear_markers(self, zip_name: str) -> None:
        """Delete all verification markers for one zip file."""
        self.clear_markers_many([zip_name])

    def clear_markers_many(self, zip_names: Collection[str]) -> None:
        """Delete verification markers for one or more zip files."""
        if not zip_names:
            return

        if len(zip_names) == 1:
            zip_name = next(iter(zip_names))
            (self.path / f"{zip_name}.verified").unlink(missing_ok=True)
            for marker_path in self.path.glob(f"{zip_name}.*.verified"):
                marker_path.unlink(missing_ok=True)
            return

        zip_name_set = set(zip_names)
        for marker_path in self.path.glob("*.verified"):
            if _match_marker_to_zip(marker_path.name, zip_name_set) is not None:
                marker_path.unlink(missing_ok=True)

    def max_source_mtime(self, zip_name: str) -> int:
        """Return the normalized freshness timestamp for a zip/checksum pair."""
        zip_path = self.zip_path(zip_name)
        checksum_path = self.checksum_path(zip_name)
        return _source_freshness_timestamp(zip_path.stat().st_mtime, checksum_path.stat().st_mtime)

    def is_marker_fresh(self, zip_name: str, timestamps: list[int]) -> bool:
        """Return True when any marker timestamp is fresh for this zip file."""
        return bool(timestamps) and max(timestamps) >= self.max_source_mtime(zip_name)

    def write_marker(self, zip_name: str) -> None:
        """Create a fresh timestamped marker for a verified zip file."""
        timestamp = max(int(time.time()), self.max_source_mtime(zip_name))
        (self.path / f"{zip_name}.{timestamp}.verified").touch()

    def discard_failed(self, zip_name: str) -> None:
        """Delete a failed zip/checksum pair."""
        self.zip_path(zip_name).unlink(missing_ok=True)
        self.checksum_path(zip_name).unlink(missing_ok=True)

    def remove_orphan_checksum(self, checksum_name: str) -> None:
        """Delete an orphan checksum file."""
        (self.path / checksum_name).unlink(missing_ok=True)

    def scan(self) -> SymbolScanResult:
        """Classify local verify work in one directory pass, sorting each path list."""
        try:
            entries = os.scandir(self.path)
        except (FileNotFoundError, NotADirectoryError):
            return SymbolScanResult(
                to_verify=[],
                orphan_zips=[],
                orphan_checksums=[],
                skipped=0,
            )

        zip_entries: dict[str, os.DirEntry[str]] = {}
        checksum_entries: dict[str, os.DirEntry[str]] = {}
        verified_names: set[str] = set()
        with entries:
            for entry in entries:
                name = entry.name
                if name.endswith(".zip"):
                    zip_entries[name] = entry
                elif name.endswith(".zip.CHECKSUM"):
                    checksum_entries[name] = entry
                elif name.endswith(".verified"):
                    verified_names.add(name)

        zip_names = set(zip_entries)
        marker_timestamps = _parse_marker_timestamps(verified_names, zip_names)

        to_verify: list[Path] = []
        orphan_zips: list[Path] = []
        skipped = 0

        for zip_name in sorted(zip_entries):
            checksum_entry = checksum_entries.get(f"{zip_name}.CHECKSUM")
            if checksum_entry is None:
                orphan_zips.append(self.path / zip_name)
                continue

            timestamps = marker_timestamps.get(zip_name)
            if timestamps and max(timestamps) >= _source_freshness_timestamp(
                zip_entries[zip_name].stat().st_mtime, checksum_entry.stat().st_mtime
            ):
                skipped += 1
            else:
                to_verify.append(self.path / zip_name)

        orphan_checksums = sorted(
            self.path / checksum_name
            for checksum_name in checksum_entries
            if checksum_name.removesuffix(".CHECKSUM") not in zip_names
        )

        return SymbolScanResult(
            to_verify=to_verify,
            orphan_zips=orphan_zips,
            orphan_checksums=orphan_checksums,
            skipped=skipped,
        )


def create_symbol_archive_dir(
    archive_home: Path,
    trade_type: TradeType,
    data_freq: DataFrequency,
    data_type: DataType,
    symbol: str,
    interval: str | None = None,
) -> SymbolArchiveDir:
    """Build the local directory helper that stores files for one symbol."""
    path = archive_home.joinpath(
        *archive_path_parts(trade_type, data_freq, data_type, symbol, interval)
    )

    return SymbolArchiveDir(path)
