"""Tests for archive checksum helpers."""

from __future__ import annotations

from pathlib import Path

from binance_datatool.archive import calc_sha256, read_expected_checksum, verify_single_file


def test_calc_sha256() -> None:
    """SHA256 calculation should match the known sample archive digest."""
    zip_path = Path("tests/data/BTCUSDT-1m-2020-01-01.zip")

    assert (
        calc_sha256(zip_path) == "dd579c62368ded93d3f01a1904575b932279e32936e181c062763e605793c1c2"
    )


def test_read_expected_checksum() -> None:
    """Checksum files should expose the first token as the expected digest."""
    zip_path = Path("tests/data/BTCUSDT-1m-2020-01-01.zip")

    assert (
        read_expected_checksum(zip_path)
        == "dd579c62368ded93d3f01a1904575b932279e32936e181c062763e605793c1c2"
    )


def test_verify_single_file_passes() -> None:
    """Matching sample files should verify successfully."""
    zip_path = Path("tests/data/BTCUSDT-1m-2020-01-01.zip")

    result = verify_single_file(zip_path)

    assert result.zip_path == zip_path
    assert result.passed is True
    assert result.detail == ""


def test_verify_single_file_fails(tmp_path) -> None:
    """Checksum mismatches should be reported without raising."""
    zip_path = tmp_path / "BTCUSDT-1m-2020-01-01.zip"
    zip_path.write_bytes(b"not the sample payload")
    (tmp_path / "BTCUSDT-1m-2020-01-01.zip.CHECKSUM").write_text(
        "dd579c62368ded93d3f01a1904575b932279e32936e181c062763e605793c1c2  "
        "BTCUSDT-1m-2020-01-01.zip\n",
        encoding="utf-8",
    )

    result = verify_single_file(zip_path)

    assert result.zip_path == zip_path
    assert result.passed is False
    assert result.detail
    assert zip_path.exists()
    assert zip_path.with_suffix(".zip.CHECKSUM").exists()
