"""CLI smoke tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
import typer
from typer.testing import CliRunner

from binance_datatool.archive import ArchiveFile
from binance_datatool.cli import app
from binance_datatool.common import (
    CmSymbolFilter,
    CmSymbolInfo,
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


@pytest.mark.parametrize(
    "command", [[], ["list-symbols"], ["list-files"], ["download"], ["verify"]]
)
def test_cli_help_is_available(command: list[str]) -> None:
    """Root and command help should be available without running workflows."""
    result = runner.invoke(app, [*command, "--help"])

    assert result.exit_code == 0
    assert result.stdout.strip()
    assert result.stderr == ""


@pytest.fixture
def no_workflow_execution(monkeypatch):
    """Reject workflow execution when testing invalid command inputs."""
    executed = []

    def unexpected_run(self):
        executed.append(self)
        pytest.fail("Invalid input must be rejected before workflow execution.")

    for name in ("ArchiveListFilesWorkflow", "ArchiveDownloadWorkflow", "ArchiveVerifyWorkflow"):
        monkeypatch.setattr(f"binance_datatool.workflow.{name}.run", unexpected_run)
    yield
    assert executed == []


@pytest.fixture
def stderr_messages(monkeypatch) -> list[str]:
    """Observe CLI diagnostic emissions while preserving actual stream output."""
    messages: list[str] = []
    original_echo = typer.echo

    def capture_echo(message=None, *args, **kwargs):
        if kwargs.get("err"):
            messages.append(str(message))
        return original_echo(message, *args, **kwargs)

    monkeypatch.setattr(typer, "echo", capture_echo)
    return messages


def test_cli_list_symbols_outputs_all_raw_symbols_without_filters(monkeypatch) -> None:
    """Unfiltered output should retain unknown symbols in archive listing order."""

    async def fake_run(self) -> ListSymbolsResult:
        return ListSymbolsResult(
            matched=[
                SpotSymbolInfo(symbol, base, "USDT", False, False)
                for symbol, base in [("BTCUSDT", "BTC"), ("ETHUSDT", "ETH")]
            ],
            unmatched=["BTCZZZUNKNOWN"],
            filtered_out=[],
            raw_symbols=["BTCUSDT", "BTCZZZUNKNOWN", "ETHUSDT"],
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListSymbolsWorkflow.run",
        fake_run,
    )

    result = runner.invoke(app, ["list-symbols", "spot"])

    assert result.exit_code == 0
    assert result.stdout == "BTCUSDT\nBTCZZZUNKNOWN\nETHUSDT\n"
    assert result.stderr == ""


@pytest.mark.parametrize("flags", [[], ["--quote", "USDT"]])
def test_cli_list_symbols_does_not_warn_when_all_symbols_are_inferable(
    monkeypatch, flags: list[str]
) -> None:
    """Successful inference should keep stderr empty in both listing modes."""

    async def fake_run(self) -> ListSymbolsResult:
        return ListSymbolsResult(
            matched=[
                SpotSymbolInfo(symbol, base, "USDT", False, False)
                for symbol, base in [("BTCUSDT", "BTC"), ("ETHUSDT", "ETH")]
            ],
            unmatched=[],
            filtered_out=[],
            raw_symbols=["BTCUSDT", "ETHUSDT"],
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListSymbolsWorkflow.run",
        fake_run,
    )

    result = runner.invoke(app, ["list-symbols", "spot", *flags])

    assert result.exit_code == 0
    assert result.stdout == "BTCUSDT\nETHUSDT\n"
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("trade_type", "flags", "known_symbol"),
    [
        ("spot", ["--quote", "USDT"], "BTCUSDT"),
        ("spot", ["--exclude-leverage"], "BTCUSDT"),
        ("spot", ["--exclude-stables"], "BTCUSDT"),
        ("spot", ["--contract-type", "perpetual"], "BTCUSDT"),
        ("um", ["--contract-type", "perpetual"], "BTCUSDT"),
        ("um", ["--exclude-leverage"], "BTCUSDT"),
        ("cm", ["--quote", "USDT"], "BTCUSD_PERP"),
        ("cm", ["--exclude-leverage"], "BTCUSD_PERP"),
        ("cm", ["--exclude-stables"], "BTCUSD_PERP"),
    ],
)
def test_cli_list_symbols_warns_about_unknown_symbols_with_any_filter_flag(
    monkeypatch, stderr_messages, trade_type: str, flags: list[str], known_symbol: str
) -> None:
    """Filter flags should skip unknown symbols with one visible warning carrying their data."""

    async def fake_run(self) -> ListSymbolsResult:
        known_info = {
            "spot": SpotSymbolInfo("BTCUSDT", "BTC", "USDT", False, False),
            "um": UmSymbolInfo("BTCUSDT", "BTC", "USDT", ContractType.perpetual, False),
            "cm": CmSymbolInfo("BTCUSD_PERP", "BTC", "USD", ContractType.perpetual),
        }[trade_type]
        return ListSymbolsResult(
            matched=[known_info],
            unmatched=["BTCZZZUNKNOWN", "ETHZZZUNKNOWN"],
            filtered_out=[],
            raw_symbols=[known_symbol, "BTCZZZUNKNOWN", "ETHZZZUNKNOWN"],
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListSymbolsWorkflow.run",
        fake_run,
    )

    result = runner.invoke(app, ["list-symbols", trade_type, *flags])

    assert result.exit_code == 0
    assert result.stdout == f"{known_symbol}\n"
    assert len(stderr_messages) == 1
    assert stderr_messages[0] in result.stderr
    assert "2" in stderr_messages[0]
    assert "BTCZZZUNKNOWN" in stderr_messages[0]
    assert "ETHZZZUNKNOWN" in stderr_messages[0]


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


def test_cli_list_files_rejects_mutually_exclusive_flags(no_workflow_execution) -> None:
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
    assert result.stdout == ""
    assert result.stderr.strip()


def test_cli_list_files_requires_interval_for_kline_types(no_workflow_execution) -> None:
    """Kline-class data types should require an interval."""
    result = runner.invoke(app, ["list-files", "um", "BTCUSDT"])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.strip()


def test_cli_list_files_rejects_interval_for_non_kline_types(no_workflow_execution) -> None:
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
    assert result.stdout == ""
    assert result.stderr.strip()


def test_cli_list_files_requires_symbols(no_workflow_execution) -> None:
    """The CLI should reject calls without symbols from args or stdin."""
    result = runner.invoke(app, ["list-files", "um", "--type", "fundingRate"])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.strip()


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
                    error="remote-listing-sentinel-37",
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
    assert result.stdout == ""
    assert "BTCUSDT" in result.stderr
    assert "remote-listing-sentinel-37" in result.stderr


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


@pytest.mark.parametrize("outcome", ["empty", "nonempty", "failed"])
def test_cli_list_files_warns_only_on_empty_success(
    monkeypatch, sample_archive_files, stderr_messages, outcome: str
) -> None:
    """An empty successful listing should emit a warning hint."""

    async def fake_run(self) -> ListFilesResult:
        return ListFilesResult(
            per_symbol=[
                SymbolListFilesResult(
                    symbol="BTCUSDT",
                    files=sample_archive_files if outcome == "nonempty" else [],
                    error="empty-listing-sentinel-37" if outcome == "failed" else None,
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

    assert result.exit_code == (2 if outcome == "failed" else 0)
    assert len(stderr_messages) == (1 if outcome == "empty" else 0)
    if outcome == "nonempty":
        assert result.stdout
        assert result.stderr == ""
    else:
        assert result.stdout == ""
        assert result.stderr.strip()
    if outcome == "failed":
        assert "BTCUSDT" in result.stderr
        assert "empty-listing-sentinel-37" in result.stderr


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


def test_cli_download_requires_symbols(no_workflow_execution) -> None:
    """Download should reject calls without symbols from args or stdin."""
    result = runner.invoke(
        app, ["--archive-home", "/tmp/archive-home", "download", "um", "--type", "fundingRate"]
    )

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.strip()


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
    assert result.stderr.strip()


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
    assert result.stderr.strip()


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
            listing_errors=[
                SymbolListingError(symbol="ETHUSDT", error="download-listing-sentinel-37")
            ],
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
    assert result.stdout == ""
    assert "ETHUSDT" in result.stderr
    assert "download-listing-sentinel-37" in result.stderr


def test_cli_verify_requires_symbols(no_workflow_execution) -> None:
    """Verify should reject calls without symbols from args or stdin."""
    result = runner.invoke(
        app, ["--archive-home", "/tmp/archive-home", "verify", "um", "--type", "fundingRate"]
    )

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.strip()


def test_cli_verify_validates_interval(no_workflow_execution) -> None:
    """Verify should enforce the same interval validation as list-files/download."""
    missing_interval = runner.invoke(
        app, ["--archive-home", "/tmp/archive-home", "verify", "um", "BTCUSDT"]
    )
    extra_interval = runner.invoke(
        app,
        [
            "--archive-home",
            "/tmp/archive-home",
            "verify",
            "um",
            "--type",
            "fundingRate",
            "--interval",
            "1m",
            "BTCUSDT",
        ],
    )

    assert missing_interval.exit_code == 2
    assert missing_interval.stdout == ""
    assert missing_interval.stderr.strip()
    assert extra_interval.exit_code == 2
    assert extra_interval.stdout == ""
    assert extra_interval.stderr.strip()


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
    assert result.stdout == ""
    assert result.stderr.strip()


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
    assert result.stderr.strip()


@pytest.mark.parametrize("keep_failed", [False, True])
def test_cli_verify_returns_two_with_failures(
    monkeypatch, stderr_messages, keep_failed: bool
) -> None:
    """Verify failures exit two regardless of failed-file retention."""

    def fake_run(self) -> VerifyResult:
        return VerifyResult(
            skipped=50,
            verified=120,
            orphan_zips=1,
            orphan_checksums=2,
            failed_details={Path("/tmp/archive-home/file.zip"): "verify-failure-sentinel-37"},
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
            *(["--keep-failed"] if keep_failed else []),
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 2
    assert result.stdout == ""
    assert "file.zip" in result.stderr
    assert "verify-failure-sentinel-37" in result.stderr
    assert len(stderr_messages) == (3 if keep_failed else 2)
    assert all(message.strip() for message in stderr_messages)


@pytest.mark.parametrize("verified", [0, 1])
@pytest.mark.parametrize("orphans", [0, 1])
def test_cli_verify_returns_zero_without_failures(monkeypatch, verified: int, orphans: int) -> None:
    """Passing, empty, and orphan-only results all exit successfully."""

    def fake_run(self) -> VerifyResult:
        return VerifyResult(
            skipped=0,
            verified=verified,
            orphan_zips=orphans,
            orphan_checksums=orphans,
            failed_details={},
        )

    monkeypatch.setattr("binance_datatool.workflow.ArchiveVerifyWorkflow.run", fake_run)

    result = runner.invoke(
        app,
        ["--archive-home", "/tmp/archive-home", "verify", "um", "--type", "fundingRate", "BTCUSDT"],
    )

    assert result.exit_code == 0
    assert result.stdout == ""
    assert result.stderr.strip()


@pytest.mark.parametrize("skipped", [0, 1])
def test_cli_verify_warns_only_on_empty_local_scan(monkeypatch, stderr_messages, skipped) -> None:
    """Empty verify scans should warn instead of pretending everything is current."""

    def fake_run(self) -> VerifyDiffResult:
        return VerifyDiffResult(
            to_verify=[],
            skipped=skipped,
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
    assert result.stdout == ""
    assert result.stderr.strip()
    assert len(stderr_messages) == (2 if skipped == 0 else 1)


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("outcome", ["empty", "nonempty", "failed"])
def test_cli_download_warns_only_on_empty_success(
    monkeypatch, stderr_messages, dry_run: bool, outcome: str
) -> None:
    """Empty listings warn; nonempty listings and listing failures suppress the warning."""

    async def fake_run(self) -> DiffResult | DownloadResult:
        errors = (
            [SymbolListingError(symbol="BTCUSDT", error="download-warning-sentinel-37")]
            if outcome == "failed"
            else []
        )
        total = 1 if outcome == "nonempty" else 0
        if dry_run:
            return DiffResult(
                to_download=[], skipped=total, total_remote=total, listing_errors=errors
            )
        return DownloadResult(
            total_remote=total, skipped=total, downloaded=0, failed=0, listing_errors=errors
        )

    monkeypatch.setattr("binance_datatool.workflow.ArchiveDownloadWorkflow.run", fake_run)
    args = ["--archive-home", "/tmp/archive-home", "download", "um", "--type", "fundingRate"]
    if dry_run:
        args.append("--dry-run")
    result = runner.invoke(app, [*args, "BTCUSDT"])

    assert result.exit_code == (2 if outcome == "failed" else 0)
    assert result.stdout == ""
    assert result.stderr.strip()
    assert len(stderr_messages) == (2 if outcome == "empty" else 1)
    if outcome == "failed":
        assert "BTCUSDT" in result.stderr
        assert "download-warning-sentinel-37" in result.stderr


@pytest.mark.parametrize(
    "arguments",
    [
        ["--archive-home", "/tmp/archive-home", "download", "um", "BTCUSDT"],
        [
            "--archive-home",
            "/tmp/archive-home",
            "download",
            "um",
            "--type",
            "fundingRate",
            "--interval",
            "1m",
            "BTCUSDT",
        ],
        ["download", "um", "--type", "fundingRate", "BTCUSDT"],
        ["verify", "um", "--type", "fundingRate", "BTCUSDT"],
    ],
)
def test_cli_rejects_invalid_local_command_input(
    monkeypatch, no_workflow_execution, arguments: list[str]
) -> None:
    """Invalid intervals and missing archive home fail before any workflow work."""
    monkeypatch.delenv("BINANCE_DATATOOL_ARCHIVE_HOME", raising=False)

    result = runner.invoke(app, arguments)

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.strip()


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
