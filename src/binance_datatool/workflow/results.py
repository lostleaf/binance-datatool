"""Result models for archive workflows."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

from binance_datatool.common import S3_DOWNLOAD_PREFIX

if TYPE_CHECKING:
    from pathlib import Path

    from binance_datatool.archive import ArchiveFile
    from binance_datatool.common import SymbolInfo


@dataclass(slots=True)
class ListSymbolsResult:
    """Structured result for archive symbol listing."""

    matched: list[SymbolInfo]
    unmatched: list[str]
    filtered_out: list[SymbolInfo]
    raw_symbols: list[str] = field(default_factory=list)

    @property
    def matched_symbols(self) -> int:
        """Return the number of inferred symbols that passed filtering."""
        return len(self.matched)

    @property
    def filtered_out_symbols(self) -> int:
        """Return the number of inferred symbols excluded by filters."""
        return len(self.filtered_out)

    @property
    def inference_failed_symbols(self) -> int:
        """Return the number of raw symbols that failed symbol inference."""
        return len(self.unmatched)

    @property
    def total_raw_symbols(self) -> int:
        """Return the total number of raw symbols returned by the archive."""
        return self.matched_symbols + self.filtered_out_symbols + self.inference_failed_symbols

    @property
    def unmatched_symbols(self) -> int:
        """Return the number of raw symbols that failed symbol inference."""
        return self.inference_failed_symbols


@dataclass(slots=True)
class SymbolListFilesResult:
    """Result for listing files under one symbol.

    A successful listing of an empty directory is represented by ``files``
    equal to ``[]`` with ``error`` still ``None``; this is distinct from a
    failed listing, which also carries an empty ``files`` list but sets
    ``error`` to a non-empty description of the failure.
    """

    symbol: str
    files: list[ArchiveFile]
    error: str | None = None


@dataclass(slots=True)
class ListFilesResult:
    """Aggregate result for listing files across multiple symbols."""

    per_symbol: list[SymbolListFilesResult]

    @property
    def requested_symbols(self) -> int:
        """Return the number of requested symbols."""
        return len(self.per_symbol)

    @property
    def has_failures(self) -> bool:
        """Return whether any requested symbol failed."""
        return any(entry.error is not None for entry in self.per_symbol)

    @property
    def failed_symbols(self) -> int:
        """Return the number of symbols whose listing failed."""
        return sum(entry.error is not None for entry in self.per_symbol)

    @property
    def successful_symbols(self) -> int:
        """Return the number of symbols whose listing succeeded."""
        return self.requested_symbols - self.failed_symbols

    @property
    def total_remote_files(self) -> int:
        """Return the total number of successfully listed remote files."""
        return sum(len(entry.files) for entry in self.per_symbol if entry.error is None)


@dataclass(slots=True)
class SymbolListingError:
    """Structured per-symbol listing error."""

    symbol: str
    error: str


@dataclass(slots=True)
class DiffEntry:
    """One file selected for download."""

    remote: ArchiveFile
    local_path: Path
    reason: Literal["new", "updated"]

    @property
    def url(self) -> str:
        """Return the direct download URL for this remote file."""
        return f"{S3_DOWNLOAD_PREFIX}/{self.remote.key}"


@dataclass(slots=True)
class DiffResult:
    """Structured diff result for archive downloads."""

    to_download: list[DiffEntry]
    skipped: int
    total_remote: int
    listing_errors: list[SymbolListingError]

    @property
    def listing_failed_symbols(self) -> int:
        """Return the number of symbols whose remote listing failed."""
        return len(self.listing_errors)


@dataclass(slots=True)
class DownloadResult:
    """Structured result for a download run."""

    total_remote: int
    skipped: int
    downloaded: int
    failed: int
    listing_errors: list[SymbolListingError]

    @property
    def listing_failed_symbols(self) -> int:
        """Return the number of symbols whose remote listing failed."""
        return len(self.listing_errors)


@dataclass(slots=True)
class VerifyDiffResult:
    """Scan-phase result for archive verify dry-runs."""

    to_verify: list[Path]
    skipped: int
    orphan_zips: list[Path]
    orphan_checksums: list[Path]

    @property
    def total_zips(self) -> int:
        """Return the number of discovered zip files."""
        return len(self.to_verify) + self.skipped + len(self.orphan_zips)


@dataclass(slots=True)
class VerifyResult:
    """Structured result for a verify run."""

    skipped: int
    verified: int
    orphan_zips: int
    orphan_checksums: int
    failed_details: dict[Path, str]

    @property
    def failed(self) -> int:
        """Return the number of failed verifications."""
        return len(self.failed_details)

    @property
    def total_zips(self) -> int:
        """Return the number of discovered zip files."""
        return self.skipped + self.verified + self.failed + self.orphan_zips
