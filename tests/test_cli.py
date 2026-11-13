"""CLI smoke tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from binance_datatool.archive import ArchiveFile
from binance_datatool.cli import app
from binance_datatool.common import (
    CmSymbolFilter,
    ContractType,
    SpotSymbolFilter,
    SpotSymbolInfo,
    UmSymbolFilter,
    UmSymbolInfo,
)
from binance_datatool.workflow import (
    ArchiveVerifyWorkflow,
    DiffEntry,
    DiffResult,
    DownloadResult,
    ListFilesResult,
    ListSymbolsResult,
    SymbolListFilesResult,
    SymbolListingError,
    VerifyDiffResult,
    VerifyResult,
)

runner = CliRunner(env={"TERM": "dumb"})


def test_cli_root_help_uses_new_app_name() -> None:
    """Root help should expose root commands without an archive namespace."""
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "binance-datatool" in result.stdout
    assert "Binance DataTool CLI." in result.stdout
    assert "--archive-home" in result.stdout
    assert "list-symbols" in result.stdout
    assert "list-files" in result.stdout
    assert "download" in result.stdout
    assert "verify" in result.stdout
    assert "\n  archive" not in result.stdout


def test_cli_list_symbols_outputs_only_matched_symbols(monkeypatch) -> None:
    """The CLI should print only matched symbol names."""

    async def fake_run(self) -> ListSymbolsResult:
        assert self.symbol_filter is None
        return ListSymbolsResult(
            matched=[
                SpotSymbolInfo(
                    symbol="BTCUSDT",
                    base_asset="BTC",
                    quote_asset="USDT",
                    is_leverage=False,
                    is_stable_pair=False,
                ),
                SpotSymbolInfo(
                    symbol="ETHUSDT",
                    base_asset="ETH",
                    quote_asset="USDT",
                    is_leverage=False,
                    is_stable_pair=False,
                ),
            ],
            unmatched=["RAWBAD"],
            filtered_out=[
                SpotSymbolInfo(
                    symbol="BNBUPUSDT",
                    base_asset="BNBUP",
                    quote_asset="USDT",
                    is_leverage=True,
                    is_stable_pair=False,
                )
            ],
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListSymbolsWorkflow.run",
        fake_run,
    )

    result = runner.invoke(app, ["list-symbols", "spot"])

    assert result.exit_code == 0
    assert result.stdout == "BTCUSDT\nETHUSDT\n"


def test_cli_list_symbols_builds_um_filter_from_flags(monkeypatch) -> None:
    """The CLI should normalize repeated quote filters for USD-M."""

    async def fake_run(self) -> ListSymbolsResult:
        assert self.data_freq.value == "monthly"
        assert self.data_type.value == "fundingRate"
        assert isinstance(self.symbol_filter, UmSymbolFilter)
        assert self.symbol_filter.quote_assets == frozenset({"USDT", "USDC"})
        assert self.symbol_filter.exclude_stable_pairs is True
        assert self.symbol_filter.contract_type is ContractType.perpetual
        return ListSymbolsResult(
            matched=[
                UmSymbolInfo(
                    symbol="BTCUSDT",
                    base_asset="BTC",
                    quote_asset="USDT",
                    contract_type=ContractType.perpetual,
                    is_stable_pair=False,
                )
            ],
            unmatched=[],
            filtered_out=[],
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListSymbolsWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        [
            "list-symbols",
            "um",
            "--freq",
            "monthly",
            "--type",
            "fundingRate",
            "--quote",
            "usdt",
            "--quote",
            "usdc",
            "--exclude-leverage",
            "--exclude-stables",
            "--contract-type",
            "perpetual",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == "BTCUSDT\n"


def test_cli_list_symbols_ignores_inapplicable_flags(monkeypatch) -> None:
    """Flags that do not apply to the chosen market should be silently ignored."""

    async def fake_run(self) -> ListSymbolsResult:
        assert self.symbol_filter is None
        return ListSymbolsResult(matched=[], unmatched=["BTCUSDT"], filtered_out=[])

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListSymbolsWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        [
            "list-symbols",
            "cm",
            "--quote",
            "usdt",
            "--exclude-leverage",
            "--exclude-stables",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == ""


def test_cli_list_symbols_builds_spot_filter(monkeypatch) -> None:
    """Spot-specific flags should produce a spot filter."""

    async def fake_run(self) -> ListSymbolsResult:
        assert isinstance(self.symbol_filter, SpotSymbolFilter)
        assert self.symbol_filter.quote_assets == frozenset({"USDT"})
        assert self.symbol_filter.exclude_leverage is True
        assert self.symbol_filter.exclude_stable_pairs is True
        return ListSymbolsResult(
            matched=[
                SpotSymbolInfo(
                    symbol="BTCUSDT",
                    base_asset="BTC",
                    quote_asset="USDT",
                    is_leverage=False,
                    is_stable_pair=False,
                )
            ],
            unmatched=[],
            filtered_out=[],
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListSymbolsWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        [
            "list-symbols",
            "spot",
            "--quote",
            "usdt",
            "--exclude-leverage",
            "--exclude-stables",
            "--contract-type",
            "delivery",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == "BTCUSDT\n"


def test_cli_list_symbols_builds_cm_filter(monkeypatch) -> None:
    """COIN-M should only honor the contract-type filter."""

    async def fake_run(self) -> ListSymbolsResult:
        assert isinstance(self.symbol_filter, CmSymbolFilter)
        assert self.symbol_filter.contract_type is ContractType.delivery
        return ListSymbolsResult(matched=[], unmatched=[], filtered_out=[])

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListSymbolsWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        ["list-symbols", "cm", "--quote", "usdt", "--contract-type", "delivery"],
    )

    assert result.exit_code == 0
    assert result.stdout == ""


def test_cli_list_files_rejects_mutually_exclusive_flags() -> None:
    """The CLI should reject incompatible output filters."""
    result = runner.invoke(
        app,
        [
            "list-files",
            "um",
            "--type",
            "fundingRate",
            "--only-zip",
            "--only-checksum",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 2
    assert "mutually exclusive" in result.stderr


def test_cli_list_files_requires_interval_for_kline_types() -> None:
    """Kline-class data types should require an interval."""
    result = runner.invoke(app, ["list-files", "um", "BTCUSDT"])

    assert result.exit_code == 2
    assert "--interval" in result.stderr


def test_cli_list_files_rejects_interval_for_non_kline_types() -> None:
    """Non-kline data types should reject interval arguments."""
    result = runner.invoke(
        app,
        [
            "list-files",
            "um",
            "--type",
            "fundingRate",
            "--interval",
            "1m",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 2
    assert "--interval" in result.stderr


def test_cli_list_files_requires_symbols() -> None:
    """The CLI should reject calls without symbols from args or stdin."""
    result = runner.invoke(app, ["list-files", "um", "--type", "fundingRate"])

    assert result.exit_code == 2
    assert "No symbols given" in result.stderr


def test_cli_list_files_argument_symbols_override_stdin(monkeypatch) -> None:
    """Positional symbols should win when stdin is also present."""

    async def fake_run(self) -> ListFilesResult:
        assert self.symbols == ["BTCUSDT"]
        return ListFilesResult(per_symbol=[])

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListFilesWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        ["list-files", "um", "--type", "fundingRate", "btcusdt"],
        input="ethusdt\n",
    )

    assert result.exit_code == 0


def test_cli_list_files_reads_symbols_from_stdin(monkeypatch) -> None:
    """Piped stdin should be used when no positional symbols are provided."""

    async def fake_run(self) -> ListFilesResult:
        assert self.symbols == ["BTCUSDT", "ETHUSDT"]
        return ListFilesResult(per_symbol=[])

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListFilesWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        ["list-files", "um", "--type", "fundingRate"],
        input="btcusdt\n\nethusdt\n",
    )

    assert result.exit_code == 0


def test_cli_list_files_short_output(monkeypatch) -> None:
    """Short output should print one relative path per line."""

    async def fake_run(self) -> ListFilesResult:
        assert self.symbols == ["BTCUSDT"]
        return ListFilesResult(
            per_symbol=[
                SymbolListFilesResult(
                    symbol="BTCUSDT",
                    files=[
                        ArchiveFile(
                            key=(
                                "data/futures/um/monthly/fundingRate/BTCUSDT/"
                                "BTCUSDT-fundingRate-2026-03.zip"
                            ),
                            size=1048,
                            last_modified=datetime(2026, 4, 1, 8, 6, 34, tzinfo=UTC),
                        ),
                        ArchiveFile(
                            key=(
                                "data/futures/um/monthly/fundingRate/BTCUSDT/"
                                "BTCUSDT-fundingRate-2026-03.zip.CHECKSUM"
                            ),
                            size=105,
                            last_modified=datetime(2026, 4, 1, 8, 6, 34, tzinfo=UTC),
                        ),
                    ],
                )
            ]
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListFilesWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        ["list-files", "um", "--freq", "monthly", "--type", "fundingRate", "btcusdt"],
    )

    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        "BTCUSDT/BTCUSDT-fundingRate-2026-03.zip",
        "BTCUSDT/BTCUSDT-fundingRate-2026-03.zip.CHECKSUM",
    ]


def test_cli_list_files_long_output_and_only_zip(monkeypatch) -> None:
    """Long output should emit TSV rows and respect zip-only filtering."""

    async def fake_run(self) -> ListFilesResult:
        return ListFilesResult(
            per_symbol=[
                SymbolListFilesResult(
                    symbol="BTCUSDT",
                    files=[
                        ArchiveFile(
                            key=(
                                "data/futures/um/monthly/fundingRate/BTCUSDT/"
                                "BTCUSDT-fundingRate-2026-03.zip"
                            ),
                            size=1048,
                            last_modified=datetime(2026, 4, 1, 8, 6, 34, tzinfo=UTC),
                        ),
                        ArchiveFile(
                            key=(
                                "data/futures/um/monthly/fundingRate/BTCUSDT/"
                                "BTCUSDT-fundingRate-2026-03.zip.CHECKSUM"
                            ),
                            size=105,
                            last_modified=datetime(2026, 4, 1, 8, 6, 34, tzinfo=UTC),
                        ),
                    ],
                )
            ]
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListFilesWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        [
            "list-files",
            "um",
            "--freq",
            "monthly",
            "--type",
            "fundingRate",
            "-l",
            "--only-zip",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines == ["1048\t2026-04-01T08:06:34Z\tBTCUSDT/BTCUSDT-fundingRate-2026-03.zip"]


def test_cli_list_files_logs_errors_and_exits_2(monkeypatch) -> None:
    """Per-symbol failures should log to stderr and exit with code 2."""

    async def fake_run(self) -> ListFilesResult:
        return ListFilesResult(
            per_symbol=[
                SymbolListFilesResult(
                    symbol="BTCUSDT",
                    files=[],
                    error="Connection reset by peer",
                )
            ]
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListFilesWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        ["list-files", "um", "--type", "fundingRate", "BTCUSDT"],
    )

    assert result.exit_code == 2
    assert "BTCUSDT: Connection reset by peer" in result.stderr


def test_cli_list_files_kline_relative_path_contains_interval(monkeypatch) -> None:
    """Kline paths should include the interval directory in short output."""

    async def fake_run(self) -> ListFilesResult:
        return ListFilesResult(
            per_symbol=[
                SymbolListFilesResult(
                    symbol="BTCUSDT",
                    files=[
                        ArchiveFile(
                            key="data/futures/um/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01-01.zip",
                            size=100,
                            last_modified=datetime(2026, 4, 1, 8, 6, 34, tzinfo=UTC),
                        )
                    ],
                )
            ]
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListFilesWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        ["list-files", "um", "--interval", "1m", "btcusdt"],
    )

    assert result.exit_code == 0
    assert result.stdout == "BTCUSDT/1m/BTCUSDT-1m-2024-01-01.zip\n"


def test_cli_list_files_only_checksum(monkeypatch) -> None:
    """Checksum-only mode should print only checksum entries."""

    async def fake_run(self) -> ListFilesResult:
        return ListFilesResult(
            per_symbol=[
                SymbolListFilesResult(
                    symbol="BTCUSDT",
                    files=[
                        ArchiveFile(
                            key=(
                                "data/futures/um/monthly/fundingRate/BTCUSDT/"
                                "BTCUSDT-fundingRate-2026-03.zip"
                            ),
                            size=1048,
                            last_modified=datetime(2026, 4, 1, 8, 6, 34, tzinfo=UTC),
                        ),
                        ArchiveFile(
                            key=(
                                "data/futures/um/monthly/fundingRate/BTCUSDT/"
                                "BTCUSDT-fundingRate-2026-03.zip.CHECKSUM"
                            ),
                            size=105,
                            last_modified=datetime(2026, 4, 1, 8, 6, 34, tzinfo=UTC),
                        ),
                    ],
                )
            ]
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListFilesWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        [
            "list-files",
            "um",
            "--freq",
            "monthly",
            "--type",
            "fundingRate",
            "--only-checksum",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == "BTCUSDT/BTCUSDT-fundingRate-2026-03.zip.CHECKSUM\n"


def test_cli_list_files_warns_on_empty_remote_without_failures(monkeypatch) -> None:
    """An empty successful listing should emit a warning hint."""

    async def fake_run(self) -> ListFilesResult:
        return ListFilesResult(per_symbol=[SymbolListFilesResult(symbol="BTCUSDT", files=[])])

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListFilesWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        ["list-files", "um", "--type", "fundingRate", "BTCUSDT"],
    )

    assert result.exit_code == 0
    assert "Warning: no archive files found" in result.stderr


def test_cli_list_files_passes_progress_bar_flag(monkeypatch) -> None:
    """The list-files progress-bar flag should reach the workflow."""

    async def fake_run(self) -> ListFilesResult:
        assert self.progress_bar is True
        return ListFilesResult(per_symbol=[])

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListFilesWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        [
            "list-files",
            "um",
            "--type",
            "fundingRate",
            "--progress-bar",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 0


def test_cli_download_requires_symbols() -> None:
    """Download should reject calls without symbols from args or stdin."""
    result = runner.invoke(app, ["download", "um", "--type", "fundingRate"])

    assert result.exit_code == 2
    assert "No symbols given" in result.stderr


def test_cli_download_dry_run_outputs_tsv(monkeypatch) -> None:
    """Dry-run output should keep the planned downloads on stdout."""

    async def fake_run(self) -> DiffResult:
        assert self.dry_run is True
        return DiffResult(
            to_download=[
                DiffEntry(
                    remote=ArchiveFile(
                        key=(
                            "data/futures/um/monthly/fundingRate/BTCUSDT/"
                            "BTCUSDT-fundingRate-2026-03.zip"
                        ),
                        size=1048,
                        last_modified=datetime(2026, 4, 1, 8, 6, 34, tzinfo=UTC),
                    ),
                    local_path=Path(
                        "/tmp/archive-home/data/futures/um/monthly/fundingRate/BTCUSDT/"
                        "BTCUSDT-fundingRate-2026-03.zip"
                    ),
                    reason="new",
                )
            ],
            skipped=12,
            total_remote=13,
            listing_errors=[],
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveDownloadWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        [
            "--archive-home",
            "/tmp/archive-home",
            "download",
            "um",
            "--freq",
            "monthly",
            "--type",
            "fundingRate",
            "--dry-run",
            "btcusdt",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == "new\t1048\tBTCUSDT/BTCUSDT-fundingRate-2026-03.zip\n"
    assert result.stderr == "1 files to download, 12 up to date\n"


@pytest.mark.parametrize(
    ("downloaded", "failed", "skipped", "expected_exit_code"),
    [
        (1, 0, 2, 0),
        (0, 0, 12, 0),
        (1, 2, 3, 2),
    ],
)
def test_cli_download_prints_summary(
    monkeypatch,
    downloaded: int,
    failed: int,
    skipped: int,
    expected_exit_code: int,
) -> None:
    """Download should print final counts at default verbosity."""

    async def fake_run(self) -> DownloadResult:
        assert self.dry_run is False
        return DownloadResult(
            total_remote=downloaded + failed + skipped,
            skipped=skipped,
            downloaded=downloaded,
            failed=failed,
            listing_errors=[],
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveDownloadWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        [
            "--archive-home",
            "/tmp/archive-home",
            "download",
            "um",
            "--type",
            "fundingRate",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == expected_exit_code
    assert result.stdout == ""
    assert result.stderr == (f"Done: {downloaded} downloaded, {failed} failed, {skipped} skipped\n")


def test_cli_download_passes_archive_home_and_proxy_flag(monkeypatch) -> None:
    """Global archive home and aria2 proxy flags should reach the workflow."""

    async def fake_run(self) -> DownloadResult:
        assert self.archive_home == Path("/tmp/archive-home")
        assert self.inherit_aria2_proxy is True
        return DownloadResult(
            total_remote=1,
            skipped=0,
            downloaded=1,
            failed=0,
            listing_errors=[],
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveDownloadWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        [
            "--archive-home",
            "/tmp/archive-home",
            "download",
            "um",
            "--type",
            "fundingRate",
            "--aria2-proxy",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 0


def test_cli_download_passes_progress_bar_flag(monkeypatch) -> None:
    """The download progress-bar flag should reach the workflow."""

    async def fake_run(self) -> DownloadResult:
        assert self.progress_bar is True
        return DownloadResult(
            total_remote=1,
            skipped=0,
            downloaded=1,
            failed=0,
            listing_errors=[],
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveDownloadWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        [
            "--archive-home",
            "/tmp/archive-home",
            "download",
            "um",
            "--type",
            "fundingRate",
            "--progress-bar",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 0


def test_cli_download_logs_listing_errors_and_exits_2(monkeypatch) -> None:
    """Listing failures should still print results for good symbols and exit 2."""

    async def fake_run(self) -> DiffResult:
        return DiffResult(
            to_download=[],
            skipped=0,
            total_remote=0,
            listing_errors=[SymbolListingError(symbol="ETHUSDT", error="boom")],
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveDownloadWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        [
            "--archive-home",
            "/tmp/archive-home",
            "download",
            "um",
            "--type",
            "fundingRate",
            "--dry-run",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 2
    assert "ETHUSDT: boom" in result.stderr


def test_cli_verify_requires_symbols() -> None:
    """Verify should reject calls without symbols from args or stdin."""
    result = runner.invoke(app, ["verify", "um", "--type", "fundingRate"])

    assert result.exit_code == 2
    assert "No symbols given" in result.stderr


def test_cli_verify_validates_interval() -> None:
    """Verify should enforce the same interval validation as list-files/download."""
    missing_interval = runner.invoke(app, ["verify", "um", "BTCUSDT"])
    extra_interval = runner.invoke(
        app,
        ["verify", "um", "--type", "fundingRate", "--interval", "1m", "BTCUSDT"],
    )

    assert missing_interval.exit_code == 2
    assert "--interval" in missing_interval.stderr
    assert extra_interval.exit_code == 2
    assert "--interval" in extra_interval.stderr


def test_cli_verify_passes_archive_home_and_keep_failed(monkeypatch) -> None:
    """Global archive home and keep-failed should reach the verify workflow."""

    def fake_run(self) -> VerifyResult:
        assert isinstance(self, ArchiveVerifyWorkflow)
        assert self.archive_home == Path("/tmp/archive-home")
        assert self.keep_failed is True
        return VerifyResult(
            skipped=0,
            verified=1,
            orphan_zips=0,
            orphan_checksums=0,
            failed_details={},
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveVerifyWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        [
            "--archive-home",
            "/tmp/archive-home",
            "verify",
            "um",
            "--type",
            "fundingRate",
            "--keep-failed",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 0
    assert "Done: 1 verified, 0 failed, 0 skipped" in result.stderr


def test_cli_verify_passes_progress_bar_flag(monkeypatch) -> None:
    """The verify progress-bar flag should reach the workflow."""

    def fake_run(self) -> VerifyResult:
        assert self.progress_bar is True
        return VerifyResult(
            skipped=0,
            verified=1,
            orphan_zips=0,
            orphan_checksums=0,
            failed_details={},
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveVerifyWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        [
            "--archive-home",
            "/tmp/archive-home",
            "verify",
            "um",
            "--type",
            "fundingRate",
            "--progress-bar",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 0


def test_cli_verify_dry_run_outputs_paths_and_summary(monkeypatch) -> None:
    """Dry-run verify should print relative paths and a local scan summary."""

    def fake_run(self) -> VerifyDiffResult:
        return VerifyDiffResult(
            to_verify=[
                Path(
                    "/tmp/archive-home/data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2020-01-01.zip"
                ),
                Path(
                    "/tmp/archive-home/data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2020-01-02.zip"
                ),
            ],
            skipped=120,
            orphan_zips=[],
            orphan_checksums=[
                Path("/tmp/archive-home/data/spot/daily/klines/BTCUSDT/1m/missing.zip.CHECKSUM")
            ],
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveVerifyWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        [
            "--archive-home",
            "/tmp/archive-home",
            "verify",
            "spot",
            "--dry-run",
            "--interval",
            "1m",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == (
        "BTCUSDT/1m/BTCUSDT-1m-2020-01-01.zip\nBTCUSDT/1m/BTCUSDT-1m-2020-01-02.zip\n"
    )
    assert "2 to verify, 120 up to date, 0 orphan zip, 1 orphan checksum" in result.stderr


def test_cli_verify_returns_zero_with_failures_or_orphans(monkeypatch) -> None:
    """Verify failures and orphan cleanup should still exit successfully."""

    def fake_run(self) -> VerifyResult:
        return VerifyResult(
            skipped=50,
            verified=120,
            orphan_zips=1,
            orphan_checksums=2,
            failed_details={Path("/tmp/archive-home/file.zip"): "checksum mismatch"},
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveVerifyWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        [
            "--archive-home",
            "/tmp/archive-home",
            "verify",
            "um",
            "--type",
            "fundingRate",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 0
    assert "Done: 120 verified, 1 failed, 50 skipped" in result.stderr
    assert "Cleaned 1 orphan zip markers, deleted 2 orphan checksums" in result.stderr
    assert "file.zip: checksum mismatch" in result.stderr


def test_cli_verify_warns_on_empty_local_scan(monkeypatch) -> None:
    """Empty verify scans should warn instead of pretending everything is current."""

    def fake_run(self) -> VerifyDiffResult:
        return VerifyDiffResult(
            to_verify=[],
            skipped=0,
            orphan_zips=[],
            orphan_checksums=[],
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveVerifyWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app,
        [
            "--archive-home",
            "/tmp/archive-home",
            "verify",
            "spot",
            "--dry-run",
            "--interval",
            "1m",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 0
    assert "Warning: no local zip files found" in result.stderr


@pytest.mark.integration
def test_cli_list_files_integration() -> None:
    """The real CLI should list funding-rate archive files for BTCUSDT."""
    result = runner.invoke(
        app,
        [
            "list-files",
            "um",
            "--freq",
            "monthly",
            "--type",
            "fundingRate",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines
    assert any(line.startswith("BTCUSDT/BTCUSDT-fundingRate-") for line in lines)


@pytest.mark.integration
def test_cli_list_files_long_output_integration() -> None:
    """The real CLI should support long and filtered archive output."""
    result = runner.invoke(
        app,
        [
            "list-files",
            "um",
            "--freq",
            "monthly",
            "--type",
            "fundingRate",
            "-l",
            "--only-zip",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 0
    lines = result.stdout.splitlines()
    assert lines
    assert all(line.count("\t") == 2 for line in lines)
    assert all(".CHECKSUM" not in line for line in lines)
