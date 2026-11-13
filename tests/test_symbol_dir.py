"""Tests for symbol archive directory helpers."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from binance_datatool.archive import SymbolArchiveDir, create_symbol_archive_dir
from binance_datatool.archive.symbol_dir import collect_markers_by_zip
from binance_datatool.common import DataFrequency, DataType, TradeType


def _write_verify_pair(base_dir: Path, name: str) -> Path:
    """Create a zip/checksum pair used by symbol-dir tests."""
    zip_path = base_dir / name
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path.write_bytes(b"zip-bytes")
    (base_dir / f"{name}.CHECKSUM").write_text("checksum  placeholder\n", encoding="utf-8")
    return zip_path


@pytest.mark.parametrize(
    ("trade_type", "data_freq", "data_type", "symbol", "interval", "expected"),
    [
        (
            TradeType.spot,
            DataFrequency.daily,
            DataType.klines,
            "BTCUSDT",
            "1m",
            Path("data/spot/daily/klines/BTCUSDT/1m"),
        ),
        (
            TradeType.um,
            DataFrequency.monthly,
            DataType.funding_rate,
            "BTCUSDT",
            None,
            Path("data/futures/um/monthly/fundingRate/BTCUSDT"),
        ),
        (
            TradeType.cm,
            DataFrequency.daily,
            DataType.metrics,
            "BTCUSD_PERP",
            None,
            Path("data/futures/cm/daily/metrics/BTCUSD_PERP"),
        ),
    ],
)
def test_create_symbol_archive_dir_builds_expected_path(
    tmp_path: Path,
    trade_type: TradeType,
    data_freq: DataFrequency,
    data_type: DataType,
    symbol: str,
    interval: str | None,
    expected: Path,
) -> None:
    """The symbol directory helper should match the archive local storage layout."""
    dir_obj = create_symbol_archive_dir(
        tmp_path,
        trade_type,
        data_freq,
        data_type,
        symbol,
        interval,
    )

    assert dir_obj.path == tmp_path / expected


def test_clear_markers_removes_legacy_and_timestamped_markers(tmp_path: Path) -> None:
    """Single-zip cleanup should delete both legacy and timestamped marker formats."""
    dir_obj = SymbolArchiveDir(tmp_path)
    _write_verify_pair(tmp_path, "sample.zip")
    legacy_marker = tmp_path / "sample.zip.verified"
    fresh_marker = tmp_path / "sample.zip.100.verified"
    stale_marker = tmp_path / "sample.zip.200.verified"
    legacy_marker.write_text("", encoding="utf-8")
    fresh_marker.write_text("", encoding="utf-8")
    stale_marker.write_text("", encoding="utf-8")

    dir_obj.clear_markers("sample.zip")

    assert not legacy_marker.exists()
    assert not fresh_marker.exists()
    assert not stale_marker.exists()


def test_clear_markers_many_single_zip_cleans_malformed_marker(tmp_path: Path) -> None:
    """Single-target cleanup should still remove malformed markers for that zip."""
    dir_obj = SymbolArchiveDir(tmp_path)
    _write_verify_pair(tmp_path, "sample.zip")
    _write_verify_pair(tmp_path, "other.zip")
    malformed_marker = tmp_path / "sample.zip.bad.verified"
    unrelated_marker = tmp_path / "other.zip.100.verified"
    malformed_marker.write_text("", encoding="utf-8")
    unrelated_marker.write_text("", encoding="utf-8")

    dir_obj.clear_markers_many({"sample.zip"})

    assert not malformed_marker.exists()
    assert unrelated_marker.exists()


def test_clear_markers_many_multiple_zips_keeps_unrelated_markers(tmp_path: Path) -> None:
    """Multi-target cleanup should delete all matching markers and keep unrelated ones."""
    dir_obj = SymbolArchiveDir(tmp_path)
    _write_verify_pair(tmp_path, "a.zip")
    _write_verify_pair(tmp_path, "b.zip")
    _write_verify_pair(tmp_path, "c.zip")

    a_legacy = tmp_path / "a.zip.verified"
    a_legacy.write_text("", encoding="utf-8")
    b_timestamped = tmp_path / "b.zip.100.verified"
    b_timestamped.write_text("", encoding="utf-8")
    b_malformed = tmp_path / "b.zip.bad.verified"
    b_malformed.write_text("", encoding="utf-8")
    c_marker = tmp_path / "c.zip.200.verified"
    c_marker.write_text("", encoding="utf-8")

    dir_obj.clear_markers_many({"a.zip", "b.zip"})

    assert not a_legacy.exists()
    assert not b_timestamped.exists()
    assert not b_malformed.exists()
    assert c_marker.exists()


@pytest.mark.parametrize(
    ("zip_mtime", "checksum_mtime", "expected"),
    [
        (1000.9, 1000.1, 1001),
        (1000.1, 1000.9, 1001),
    ],
)
def test_max_source_mtime_uses_newer_source_mtime(
    tmp_path: Path,
    zip_mtime: float,
    checksum_mtime: float,
    expected: int,
) -> None:
    """The source freshness timestamp should use the newer zip/checksum mtime."""
    dir_obj = SymbolArchiveDir(tmp_path)
    zip_path = _write_verify_pair(tmp_path, "sample.zip")
    checksum_path = tmp_path / "sample.zip.CHECKSUM"
    os.utime(zip_path, (zip_mtime, zip_mtime))
    os.utime(checksum_path, (checksum_mtime, checksum_mtime))

    assert dir_obj.max_source_mtime("sample.zip") == expected


def test_write_marker_creates_fresh_timestamped_marker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Written markers should use a timestamp no older than the source pair."""
    dir_obj = SymbolArchiveDir(tmp_path)
    _write_verify_pair(tmp_path, "sample.zip")
    zip_path = tmp_path / "sample.zip"
    checksum_path = tmp_path / "sample.zip.CHECKSUM"
    os.utime(zip_path, (1000.1, 1000.1))
    os.utime(checksum_path, (1000.9, 1000.9))
    monkeypatch.setattr("binance_datatool.archive.symbol_dir.time.time", lambda: 1000.0)

    dir_obj.write_marker("sample.zip")

    markers = list(tmp_path.glob("sample.zip.*.verified"))
    assert len(markers) == 1
    timestamp = int(markers[0].name.removeprefix("sample.zip.").removesuffix(".verified"))
    assert timestamp >= dir_obj.max_source_mtime("sample.zip")


def test_is_marker_fresh_returns_true_when_timestamp_equals_source_mtime(tmp_path: Path) -> None:
    """A marker timestamp matching the source pair should be considered fresh."""
    dir_obj = SymbolArchiveDir(tmp_path)
    zip_path = _write_verify_pair(tmp_path, "sample.zip")
    os.utime(zip_path, (1000.0, 1000.0))
    os.utime(tmp_path / "sample.zip.CHECKSUM", (1000.0, 1000.0))

    assert dir_obj.is_marker_fresh("sample.zip", [1000]) is True


def test_is_marker_fresh_returns_true_when_timestamp_is_newer(tmp_path: Path) -> None:
    """A newer marker timestamp should be considered fresh."""
    dir_obj = SymbolArchiveDir(tmp_path)
    zip_path = _write_verify_pair(tmp_path, "sample.zip")
    os.utime(zip_path, (1000.0, 1000.0))
    os.utime(tmp_path / "sample.zip.CHECKSUM", (1000.0, 1000.0))

    assert dir_obj.is_marker_fresh("sample.zip", [999, 1001]) is True


def test_is_marker_fresh_returns_false_when_all_timestamps_are_older(tmp_path: Path) -> None:
    """Older marker timestamps should not be considered fresh."""
    dir_obj = SymbolArchiveDir(tmp_path)
    zip_path = _write_verify_pair(tmp_path, "sample.zip")
    os.utime(zip_path, (1000.9, 1000.9))
    os.utime(tmp_path / "sample.zip.CHECKSUM", (1000.9, 1000.9))

    assert dir_obj.is_marker_fresh("sample.zip", [1000]) is False


def test_is_marker_fresh_returns_false_for_empty_timestamps(tmp_path: Path) -> None:
    """An empty timestamp list should not be considered fresh."""
    dir_obj = SymbolArchiveDir(tmp_path)
    _write_verify_pair(tmp_path, "sample.zip")

    assert dir_obj.is_marker_fresh("sample.zip", []) is False


def test_discard_failed_removes_zip_and_checksum(tmp_path: Path) -> None:
    """Failed zip/checksum pairs should be deleted together."""
    dir_obj = SymbolArchiveDir(tmp_path)
    zip_path = _write_verify_pair(tmp_path, "failed.zip")
    checksum_path = tmp_path / "failed.zip.CHECKSUM"

    dir_obj.discard_failed("failed.zip")

    assert not zip_path.exists()
    assert not checksum_path.exists()


def test_remove_orphan_checksum_deletes_only_target_checksum(tmp_path: Path) -> None:
    """Removing an orphan checksum should not affect other files."""
    dir_obj = SymbolArchiveDir(tmp_path)
    target = tmp_path / "missing.zip.CHECKSUM"
    other = tmp_path / "keep.zip.CHECKSUM"
    target.write_text("checksum", encoding="utf-8")
    other.write_text("checksum", encoding="utf-8")

    dir_obj.remove_orphan_checksum("missing.zip.CHECKSUM")

    assert not target.exists()
    assert other.exists()


def test_scan_classifies_fresh_stale_legacy_and_plain_files(tmp_path: Path) -> None:
    """Scan should skip fresh markers and re-verify stale, legacy, and plain files."""
    dir_obj = SymbolArchiveDir(tmp_path)
    fresh = _write_verify_pair(tmp_path, "fresh.zip")
    stale = _write_verify_pair(tmp_path, "stale.zip")
    legacy = _write_verify_pair(tmp_path, "legacy.zip")
    plain = _write_verify_pair(tmp_path, "plain.zip")

    fresh_marker = tmp_path / f"fresh.zip.{int(fresh.stat().st_mtime) + 10}.verified"
    stale_marker = tmp_path / f"stale.zip.{int(stale.stat().st_mtime) - 10}.verified"
    legacy_marker = tmp_path / "legacy.zip.verified"
    fresh_marker.write_text("", encoding="utf-8")
    stale_marker.write_text("", encoding="utf-8")
    legacy_marker.write_text("", encoding="utf-8")

    result = dir_obj.scan()

    assert result.skipped == 1
    assert result.to_verify == [legacy, plain, stale]
    assert result.orphan_zips == []
    assert result.orphan_checksums == []


def test_scan_detects_orphan_zip_and_checksum(tmp_path: Path) -> None:
    """Scan should classify orphan zip and checksum files separately."""
    dir_obj = SymbolArchiveDir(tmp_path)
    orphan_zip = tmp_path / "orphan.zip"
    orphan_zip.write_bytes(b"zip-only")
    orphan_checksum = tmp_path / "missing.zip.CHECKSUM"
    orphan_checksum.write_text("checksum", encoding="utf-8")

    result = dir_obj.scan()

    assert result.to_verify == []
    assert result.skipped == 0
    assert result.orphan_zips == [orphan_zip]
    assert result.orphan_checksums == [orphan_checksum]


@pytest.mark.parametrize(
    ("zip_mtime", "checksum_mtime", "timestamps", "skipped"),
    [
        (1000.1, 1000.9, [1000], 0),
        (1000.9, 1000.1, [1000], 0),
        (1000.1, 1000.9, [999, 1001], 1),
        (1000.9, 1000.1, [1001], 1),
        (1001.0, 1001.0, [1001], 1),
    ],
)
def test_scan_preserves_marker_freshness_boundary(
    tmp_path: Path,
    zip_mtime: float,
    checksum_mtime: float,
    timestamps: list[int],
    skipped: int,
) -> None:
    """Scan uses the newest marker and rounds the newest source mtime upward."""
    zip_path = _write_verify_pair(tmp_path, "sample.zip")
    os.utime(zip_path, (zip_mtime, zip_mtime))
    os.utime(tmp_path / "sample.zip.CHECKSUM", (checksum_mtime, checksum_mtime))
    for timestamp in timestamps:
        (tmp_path / f"sample.zip.{timestamp}.verified").touch()

    result = SymbolArchiveDir(tmp_path).scan()

    assert result.skipped == skipped
    assert result.to_verify == ([] if skipped else [zip_path])


def test_scan_missing_directory_returns_empty_result(tmp_path: Path) -> None:
    """A symbol absent from local storage contributes no files or skipped work."""
    result = SymbolArchiveDir(tmp_path / "missing").scan()

    assert result.to_verify == []
    assert result.skipped == 0
    assert result.orphan_zips == []
    assert result.orphan_checksums == []


def test_collect_markers_by_zip_returns_empty_for_no_markers(tmp_path: Path) -> None:
    """Marker collection should return an empty mapping when no markers exist."""
    zip_path = _write_verify_pair(tmp_path, "a.zip")

    assert collect_markers_by_zip([zip_path]) == {}


def test_collect_markers_by_zip_collects_legacy_timestamped_and_malformed_markers(
    tmp_path: Path,
) -> None:
    """Marker collection should keep every marker matched to the target zip."""
    zip_path = _write_verify_pair(tmp_path, "a.zip")
    legacy = tmp_path / "a.zip.verified"
    timestamped = tmp_path / "a.zip.100.verified"
    malformed = tmp_path / "a.zip.bad.verified"
    legacy.touch()
    timestamped.touch()
    malformed.touch()

    result = collect_markers_by_zip([zip_path])

    assert zip_path in result
    assert set(result[zip_path]) == {legacy, timestamped, malformed}


def test_collect_markers_by_zip_handles_multiple_directories(tmp_path: Path) -> None:
    """Marker collection should scan each directory independently."""
    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    zip_a = _write_verify_pair(dir_a, "a.zip")
    zip_b = _write_verify_pair(dir_b, "b.zip")
    marker_a = dir_a / "a.zip.100.verified"
    marker_b = dir_b / "b.zip.200.verified"
    marker_a.touch()
    marker_b.touch()

    result = collect_markers_by_zip([zip_a, zip_b])

    assert result == {zip_a: [marker_a], zip_b: [marker_b]}
