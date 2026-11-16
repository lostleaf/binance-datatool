"""Local symbol archive directory helpers."""

from __future__ import annotations

import math
import os
import time
from collections import defaultdict
from dataclasses import dataclass, field
from fnmatch import fnmatchcase
from typing import TYPE_CHECKING

from binance_datatool.common.path import archive_path_parts

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence
    from pathlib import Path

    from binance_datatool.common import DataFrequency, DataType, TradeType

__all__ = ["SymbolArchiveDir", "create_symbol_archive_dir"]


class _DownloadSnapshot:
    """Operation-local requested entries, with bounded work for sparse selections."""

    def __init__(self, path: Path, names: Collection[str]) -> None:
        self.path = path
        self.entries: dict[str, os.DirEntry[str]] = {}
        self.complete = False
        # Opening a large directory costs more than direct lookup for small
        # selections, even when iteration is bounded (see docs/reference/performance.md).
        if len(names) <= 16:
            return
        wanted = set(names)
        wanted.update(f"{name}.aria2" for name in names)
        visit_limit = max(8, len(wanted) * 4)
        try:
            with os.scandir(path) as entries:
                for index, entry in enumerate(entries):
                    if entry.name in wanted:
                        self.entries[entry.name] = entry
                    if index >= visit_limit or (index >= 7 and not self.entries):
                        return
        except OSError:
            # Enumeration can fail while individual paths remain accessible.
            # Discard partial metadata and retain Path.exists/stat error policy
            # through direct lookups, including this runtime's absent-path rules.
            self.entries.clear()
            return
        self.complete = True

    def stat(self, name: str) -> os.stat_result | None:
        """Follow links and reuse entry metadata, preserving Path.exists errors."""
        entry = self.entries.get(name)
        if entry is None and self.complete:
            return None
        try:
            return entry.stat() if entry is not None else os.stat(os.path.join(self.path, name))
        except OSError:
            # Path.exists ignores selected errors through 3.13 and all OSError
            # failures from 3.14. Delegate only exceptional cases to that policy.
            if not (self.path / name).exists():
                return None
            raise

    def control_exists(self, name: str) -> bool:
        """Recognize ordinary control entries without a separate stat query."""
        name = f"{name}.aria2"
        entry = self.entries.get(name)
        if entry is not None and not entry.is_symlink():
            return True
        if entry is None and self.complete:
            return False
        return (self.path / name).exists()


@dataclass(slots=True)
class SymbolScanResult:
    """Per-symbol scan outcome used internally by archive workflows."""

    to_verify: list[Path]
    orphan_zips: list[Path]
    orphan_checksums: list[Path]
    skipped: int
    _markers_by_zip: dict[Path, list[Path]] = field(default_factory=dict, repr=False)


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

    def download_snapshot(self, names: Collection[str]) -> _DownloadSnapshot:
        """Read requested download entries once without verification classification.

        Dense selections reuse directory entries. Sparse selections bound unrelated
        visits and use direct lookups for entries outside the partial snapshot.
        Metadata is read lazily so callers retain their comparison order.
        """
        return _DownloadSnapshot(self.path, names)

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
        checksum_zip_names = {name.removesuffix(".CHECKSUM") for name in checksum_entries}
        marker_targets = zip_names | checksum_zip_names
        orphan_targets = zip_names ^ checksum_zip_names
        single_orphan = next(iter(orphan_targets)) if len(orphan_targets) == 1 else None
        markers_by_zip: dict[Path, list[Path]] = defaultdict(list)
        for marker_name in verified_names:
            # Single-orphan cleanup historically uses the broader single-target
            # glob, including malformed suffixes with multiple dots.
            if single_orphan is not None and (
                marker_name == f"{single_orphan}.verified"
                or fnmatchcase(marker_name, f"{single_orphan}.*.verified")
            ):
                zip_name = single_orphan
            else:
                zip_name = _match_marker_to_zip(marker_name, marker_targets)
            if zip_name is not None:
                markers_by_zip[self.path / zip_name].append(self.path / marker_name)
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
            _markers_by_zip=dict(markers_by_zip),
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
