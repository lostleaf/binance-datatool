"""CLI smoke tests."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest
import typer
from loguru import logger
from typer.main import get_command
from typer.testing import CliRunner

from binance_datatool.archive import ArchiveFile, Aria2NotFoundError
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
from binance_datatool.common.progress import ProgressEvent, make_reporter
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


def test_cli_list_files_json_metadata_without_archive_home(
    monkeypatch, sample_archive_files
) -> None:
    """Remote JSON metadata remains usable without local archive configuration."""
    monkeypatch.delenv("BINANCE_DATATOOL_ARCHIVE_HOME", raising=False)

    async def fake_run(self) -> ListFilesResult:
        return ListFilesResult(
            per_symbol=[
                SymbolListFilesResult(
                    "BTCUSDT",
                    [
                        ArchiveFile(
                            sample_archive_files[0].key,
                            1048,
                            datetime(2026, 4, 1, 16, 6, 34, tzinfo=timezone(timedelta(hours=8))),
                        ),
                        sample_archive_files[1],
                    ],
                    None,
                )
            ]
        )

    monkeypatch.setattr("binance_datatool.workflow.ArchiveListFilesWorkflow.run", fake_run)
    result = runner.invoke(
        app,
        ["list-files", "um", "BTCUSDT", "--type", "fundingRate", "--freq", "monthly", "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "command": "list-files",
        "dry_run": False,
        "summary": {
            "requested_symbols": 1,
            "successful_symbols": 1,
            "failed_symbols": 0,
            "total_remote_files": 2,
            "returned_files": 2,
        },
        "per_symbol": [
            {
                "symbol": "BTCUSDT",
                "error": None,
                "files": [
                    {
                        "url": "https://data.binance.vision/data/futures/um/monthly/fundingRate/"
                        "BTCUSDT/BTCUSDT-fundingRate-2026-03.zip",
                        "size": 1048,
                        "last_modified": "2026-04-01T08:06:34Z",
                    },
                    {
                        "url": "https://data.binance.vision/data/futures/um/monthly/fundingRate/"
                        "BTCUSDT/BTCUSDT-fundingRate-2026-03.zip.CHECKSUM",
                        "size": 105,
                        "last_modified": "2026-04-01T08:06:34Z",
                    },
                ],
            }
        ],
    }
    assert result.stderr == ""


@pytest.mark.parametrize(
    "command", [[], ["list-symbols"], ["list-files"], ["download"], ["verify"]]
)
def test_cli_help_is_available(command: list[str]) -> None:
    """Root and command help should be available without running workflows."""
    result = runner.invoke(app, [*command, "--help"])

    assert result.exit_code == 0
    assert result.stdout.strip()
    assert result.stderr == ""


@pytest.mark.parametrize("command", ["list-symbols", "list-files", "download", "verify"])
def test_cli_shared_parameters_keep_labels_and_defaults(command: str) -> None:
    """Shared parameters retain their labels, availability, and defaults."""
    registered = get_command(app).commands[command]
    market_argument = next(
        parameter for parameter in registered.params if parameter.name == "market_type"
    )
    assert market_argument.human_readable_name == "MARKET_TYPE"

    options = {
        option: parameter.default
        for parameter in registered.params
        for option in getattr(parameter, "opts", [])
    }

    assert options["--freq"] == "daily"
    assert options["--type"] == "klines"
    if command == "list-symbols":
        assert "--interval" not in options
        assert "--progress-bar" not in options
    else:
        assert options["--interval"] is None
        assert options["--progress-bar"] is False
    if command == "download":
        assert options["--concurrency"] == 64


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
            inference_failures=["BTCZZZUNKNOWN"],
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


def test_cli_list_symbols_json_preserves_unfiltered_archive_order(monkeypatch) -> None:
    """JSON retains unknown names and reports inferred spot attributes."""

    async def fake_run(self) -> ListSymbolsResult:
        assert self.symbol_filter is None
        return ListSymbolsResult(
            matched=[SpotSymbolInfo("BTCUPUSDT", "BTCUP", "USDT", True, False)],
            inference_failures=["UNKNOWN"],
            filtered_out=[],
            raw_symbols=["UNKNOWN", "BTCUPUSDT"],
        )

    monkeypatch.setattr("binance_datatool.workflow.ArchiveListSymbolsWorkflow.run", fake_run)

    result = runner.invoke(app, ["list-symbols", "spot", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "command": "list-symbols",
        "dry_run": False,
        "summary": {
            "total_raw_symbols": 2,
            "returned_symbols": 2,
            "matched_symbols": 1,
            "filtered_out_symbols": 0,
            "inference_failure_count": 1,
        },
        "symbols": ["UNKNOWN", "BTCUPUSDT"],
        "matched": [
            {
                "symbol": "BTCUPUSDT",
                "base_asset": "BTCUP",
                "quote_asset": "USDT",
                "is_leverage": True,
                "is_stable_pair": False,
            }
        ],
        "filtered_out": [],
        "inference_failures": ["UNKNOWN"],
    }
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("market", "matched", "filtered_out", "attributes", "excluded_attributes"),
    [
        (
            "spot",
            SpotSymbolInfo("USDCUSDT", "USDC", "USDT", False, True),
            SpotSymbolInfo("BTCUPUSDT", "BTCUP", "USDT", True, False),
            {"is_leverage": False, "is_stable_pair": True},
            {"is_leverage": True, "is_stable_pair": False},
        ),
        (
            "um",
            UmSymbolInfo("USDCUSDT", "USDC", "USDT", ContractType.perpetual, True),
            UmSymbolInfo("BTCUSDT_240927", "BTC", "USDT", ContractType.delivery, False),
            {"contract_type": "perpetual", "is_stable_pair": True},
            {"contract_type": "delivery", "is_stable_pair": False},
        ),
        (
            "cm",
            CmSymbolInfo("BTCUSD_PERP", "BTC", "USD", ContractType.perpetual),
            CmSymbolInfo("ETHUSD_240927", "ETH", "USD", ContractType.delivery),
            {"contract_type": "perpetual"},
            {"contract_type": "delivery"},
        ),
    ],
)
def test_cli_list_symbols_json_classifies_market_records(
    monkeypatch, market, matched, filtered_out, attributes, excluded_attributes
) -> None:
    """Filtered JSON separates filter exclusions from inference failures in every market."""

    async def fake_run(self) -> ListSymbolsResult:
        return ListSymbolsResult(
            matched=[matched],
            inference_failures=["UNKNOWN"],
            filtered_out=[filtered_out],
            raw_symbols=[filtered_out.symbol, "UNKNOWN", matched.symbol],
        )

    monkeypatch.setattr("binance_datatool.workflow.ArchiveListSymbolsWorkflow.run", fake_run)

    result = runner.invoke(app, ["list-symbols", market, "--quote", "USDT", "--json"])

    assert result.exit_code == 0
    document = json.loads(result.stdout)
    assert document == {
        "command": "list-symbols",
        "dry_run": False,
        "summary": {
            "total_raw_symbols": 3,
            "returned_symbols": 1,
            "matched_symbols": 1,
            "filtered_out_symbols": 1,
            "inference_failure_count": 1,
        },
        "symbols": [matched.symbol],
        "matched": [
            {
                "symbol": matched.symbol,
                "base_asset": matched.base_asset,
                "quote_asset": matched.quote_asset,
                **attributes,
            }
        ],
        "filtered_out": [
            {
                "symbol": filtered_out.symbol,
                "base_asset": filtered_out.base_asset,
                "quote_asset": filtered_out.quote_asset,
                **excluded_attributes,
            }
        ],
        "inference_failures": ["UNKNOWN"],
    }
    assert document["dry_run"] is False
    assert all(type(count) is int for count in document["summary"].values())
    assert "UNKNOWN" in result.stderr


@pytest.mark.parametrize("verbosity", [[], ["-v"], ["-vv"]])
@pytest.mark.parametrize("flags", [[], ["--quote", "USDT"]])
def test_cli_list_symbols_json_empty_and_verbose_results(monkeypatch, verbosity, flags) -> None:
    """Empty results are explicit and verbosity sends diagnostics only to stderr."""

    async def fake_run(self) -> ListSymbolsResult:
        logger.info("listing diagnostic payload")
        return ListSymbolsResult(matched=[], inference_failures=[], filtered_out=[])

    monkeypatch.setattr("binance_datatool.workflow.ArchiveListSymbolsWorkflow.run", fake_run)

    result = runner.invoke(app, [*verbosity, "list-symbols", "spot", *flags, "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {
        "command": "list-symbols",
        "dry_run": False,
        "summary": {
            "total_raw_symbols": 0,
            "returned_symbols": 0,
            "matched_symbols": 0,
            "filtered_out_symbols": 0,
            "inference_failure_count": 0,
        },
        "symbols": [],
        "matched": [],
        "filtered_out": [],
        "inference_failures": [],
    }
    if verbosity:
        assert "listing diagnostic payload" in result.stderr
    else:
        assert result.stderr == ""


def test_cli_list_symbols_json_prefix_selectors_do_not_enable_filtering(monkeypatch) -> None:
    """Frequency and dataset selection retain names with inference failures without warnings."""

    async def fake_run(self) -> ListSymbolsResult:
        assert self.data_freq.value == "monthly"
        assert self.data_type.value == "fundingRate"
        assert self.symbol_filter is None
        return ListSymbolsResult(
            matched=[], inference_failures=["UNKNOWN"], filtered_out=[], raw_symbols=["UNKNOWN"]
        )

    monkeypatch.setattr("binance_datatool.workflow.ArchiveListSymbolsWorkflow.run", fake_run)
    result = runner.invoke(
        app, ["list-symbols", "um", "--freq", "monthly", "--type", "fundingRate", "--json"]
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["symbols"] == ["UNKNOWN"]
    assert result.stderr == ""


@pytest.mark.parametrize("arguments", [["invalid", "--json"], ["spot", "--dry-run", "--json"]])
def test_cli_list_symbols_json_argument_errors_have_no_result(monkeypatch, arguments) -> None:
    """Invalid arguments retain their failure without manufacturing a result."""

    async def unexpected_run(self):
        pytest.fail("Invalid input must be rejected before workflow execution.")

    monkeypatch.setattr("binance_datatool.workflow.ArchiveListSymbolsWorkflow.run", unexpected_run)
    result = runner.invoke(app, ["list-symbols", *arguments])

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr


def test_cli_list_symbols_json_unhandled_error_has_no_result(monkeypatch) -> None:
    """A workflow exception remains an exception and emits no JSON."""

    async def fake_run(self):
        raise RuntimeError("symbol listing unavailable")

    monkeypatch.setattr("binance_datatool.workflow.ArchiveListSymbolsWorkflow.run", fake_run)
    result = runner.invoke(app, ["list-symbols", "spot", "--json"])

    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)
    assert str(result.exception) == "symbol listing unavailable"
    assert result.stdout == ""


@pytest.mark.parametrize("flags", [[], ["--quote", "USDT"]])
@pytest.mark.parametrize("json_output", [False, True])
def test_cli_list_symbols_does_not_warn_when_all_symbols_are_inferable(
    monkeypatch, flags: list[str], json_output: bool
) -> None:
    """Successful inference should keep stderr empty in both listing modes."""

    async def fake_run(self) -> ListSymbolsResult:
        return ListSymbolsResult(
            matched=[
                SpotSymbolInfo(symbol, base, "USDT", False, False)
                for symbol, base in [("BTCUSDT", "BTC"), ("ETHUSDT", "ETH")]
            ],
            inference_failures=[],
            filtered_out=[],
            raw_symbols=["BTCUSDT", "ETHUSDT"],
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListSymbolsWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app, ["list-symbols", "spot", *flags, *(["--json"] if json_output else [])]
    )

    assert result.exit_code == 0
    if json_output:
        assert json.loads(result.stdout)["symbols"] == ["BTCUSDT", "ETHUSDT"]
    else:
        assert result.stdout == "BTCUSDT\nETHUSDT\n"
    assert result.stderr == ""


@pytest.mark.parametrize(
    ("market_type", "flags", "known_symbol"),
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
@pytest.mark.parametrize("json_output", [False, True])
def test_cli_list_symbols_warns_about_unknown_symbols_with_any_filter_flag(
    monkeypatch,
    stderr_messages,
    market_type: str,
    flags: list[str],
    known_symbol: str,
    json_output: bool,
) -> None:
    """Filter flags should skip unknown symbols with one visible warning carrying their data."""

    async def fake_run(self) -> ListSymbolsResult:
        known_info = {
            "spot": SpotSymbolInfo("BTCUSDT", "BTC", "USDT", False, False),
            "um": UmSymbolInfo("BTCUSDT", "BTC", "USDT", ContractType.perpetual, False),
            "cm": CmSymbolInfo("BTCUSD_PERP", "BTC", "USD", ContractType.perpetual),
        }[market_type]
        return ListSymbolsResult(
            matched=[known_info],
            inference_failures=["BTCZZZUNKNOWN", "ETHZZZUNKNOWN"],
            filtered_out=[],
            raw_symbols=[known_symbol, "BTCZZZUNKNOWN", "ETHZZZUNKNOWN"],
        )

    monkeypatch.setattr(
        "binance_datatool.workflow.ArchiveListSymbolsWorkflow.run",
        fake_run,
    )

    result = runner.invoke(
        app, ["list-symbols", market_type, *flags, *(["--json"] if json_output else [])]
    )

    assert result.exit_code == 0
    if json_output:
        document = json.loads(result.stdout)
        assert document["symbols"] == [known_symbol]
        assert document["inference_failures"] == ["BTCZZZUNKNOWN", "ETHZZZUNKNOWN"]
        assert document["summary"]["returned_symbols"] == 1
        assert document["summary"]["inference_failure_count"] == 2
    else:
        assert result.stdout == f"{known_symbol}\n"
    assert len(stderr_messages) == 1
    assert stderr_messages[0] in result.stderr
    assert "2" in stderr_messages[0]
    assert "BTCZZZUNKNOWN" in stderr_messages[0]
    assert "ETHZZZUNKNOWN" in stderr_messages[0]


def test_cli_list_symbols_builds_um_filter_from_flags(monkeypatch) -> None:
    """The CLI should normalize repeated quote filters for USDⓈ-M."""

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
            inference_failures=[],
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
        return ListSymbolsResult(matched=[], inference_failures=["BTCUSDT"], filtered_out=[])

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
            inference_failures=[],
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
        return ListSymbolsResult(matched=[], inference_failures=[], filtered_out=[])

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


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize("mixed", [False, True])
def test_cli_list_files_retains_timeout_diagnostics(
    monkeypatch, sample_archive_files, stderr_messages, json_output, mixed
) -> None:
    """Timeouts remain Symbol-associated errors in text and JSON CLI output."""
    symbols = ["ETHUSDT", "BNBUSDT", "BTCUSDT"] if mixed else ["ETHUSDT"]

    async def fake_run(self) -> ListFilesResult:
        assert self.symbols == symbols
        per_symbol = [SymbolListFilesResult(symbol="ETHUSDT", files=[], error="TimeoutError")]
        if mixed:
            per_symbol.extend(
                [
                    SymbolListFilesResult(symbol="BNBUSDT", files=[], error=None),
                    SymbolListFilesResult(symbol="BTCUSDT", files=sample_archive_files, error=None),
                ]
            )
        return ListFilesResult(per_symbol=per_symbol)

    monkeypatch.setattr("binance_datatool.workflow.ArchiveListFilesWorkflow.run", fake_run)
    result = runner.invoke(
        app,
        [
            "list-files",
            "um",
            "--freq",
            "monthly",
            "--type",
            "fundingRate",
            *symbols,
            *(["--json"] if json_output else []),
        ],
    )

    assert result.exit_code == 2, result.exception
    assert any("ETHUSDT" in line and "TimeoutError" in line for line in result.stderr.splitlines())
    assert stderr_messages == []
    if json_output:
        document = json.loads(result.stdout)
        assert set(document) == {"command", "dry_run", "summary", "per_symbol"}
        assert document["command"] == "list-files"
        assert document["dry_run"] is False
        assert document["summary"] == {
            "requested_symbols": 3 if mixed else 1,
            "successful_symbols": 2 if mixed else 0,
            "failed_symbols": 1,
            "total_remote_files": 2 if mixed else 0,
            "returned_files": 2 if mixed else 0,
        }
        assert [entry["symbol"] for entry in document["per_symbol"]] == symbols
        assert document["per_symbol"][0] == {
            "symbol": "ETHUSDT",
            "files": [],
            "error": "TimeoutError",
        }
        if mixed:
            assert document["per_symbol"][1] == {"symbol": "BNBUSDT", "files": [], "error": None}
            assert document["per_symbol"][2]["error"] is None
            assert len(document["per_symbol"][2]["files"]) == 2
    else:
        assert result.stdout.splitlines() == (
            [
                "BTCUSDT/BTCUSDT-fundingRate-2026-03.zip",
                "BTCUSDT/BTCUSDT-fundingRate-2026-03.zip.CHECKSUM",
            ]
            if mixed
            else []
        )


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


@pytest.mark.parametrize("only_flag", ["--only-zip", "--only-checksum"])
@pytest.mark.parametrize("long_format", [False, True])
def test_cli_list_files_json_filters_keep_remote_counts(
    monkeypatch, sample_archive_files, only_flag, long_format
) -> None:
    """Filtering changes returned counts, while long mode leaves JSON fields intact."""

    async def fake_run(self) -> ListFilesResult:
        return ListFilesResult([SymbolListFilesResult("BTCUSDT", sample_archive_files)])

    monkeypatch.setattr("binance_datatool.workflow.ArchiveListFilesWorkflow.run", fake_run)
    result = runner.invoke(
        app,
        [
            "list-files",
            "um",
            "BTCUSDT",
            "--type",
            "fundingRate",
            "--json",
            only_flag,
            *(["--long"] if long_format else []),
        ],
    )

    assert result.exit_code == 0
    document = json.loads(result.stdout)
    assert document["summary"] == {
        "requested_symbols": 1,
        "successful_symbols": 1,
        "failed_symbols": 0,
        "total_remote_files": 2,
        "returned_files": 1,
    }
    assert document["per_symbol"] == [
        {
            "symbol": "BTCUSDT",
            "error": None,
            "files": [
                {
                    "url": "https://data.binance.vision/data/futures/um/monthly/fundingRate/"
                    "BTCUSDT/BTCUSDT-fundingRate-2026-03.zip"
                    + (".CHECKSUM" if only_flag == "--only-checksum" else ""),
                    "size": 105 if only_flag == "--only-checksum" else 1048,
                    "last_modified": "2026-04-01T08:06:34Z",
                }
            ],
        }
    ]
    assert result.stderr == ""


@pytest.mark.parametrize("outcome", ["empty-result", "empty-symbol", "filtered-symbol"])
def test_cli_list_files_json_retains_empty_records_and_warning_conditions(
    monkeypatch, sample_archive_files, stderr_messages, outcome
) -> None:
    """An output filter cannot discard symbol records or create an empty-inventory warning."""

    async def fake_run(self) -> ListFilesResult:
        if outcome == "empty-result":
            return ListFilesResult([])
        return ListFilesResult(
            [
                SymbolListFilesResult(
                    "BTCUSDT", sample_archive_files[1:] if outcome == "filtered-symbol" else []
                )
            ]
        )

    monkeypatch.setattr("binance_datatool.workflow.ArchiveListFilesWorkflow.run", fake_run)
    result = runner.invoke(
        app,
        ["list-files", "um", "BTCUSDT", "--type", "fundingRate", "--json", "--only-zip"],
    )

    assert result.exit_code == 0
    document = json.loads(result.stdout)
    assert document["per_symbol"] == (
        [] if outcome == "empty-result" else [{"symbol": "BTCUSDT", "files": [], "error": None}]
    )
    assert document["summary"] == {
        "requested_symbols": 0 if outcome == "empty-result" else 1,
        "successful_symbols": 0 if outcome == "empty-result" else 1,
        "failed_symbols": 0,
        "total_remote_files": 1 if outcome == "filtered-symbol" else 0,
        "returned_files": 0,
    }
    if outcome == "filtered-symbol":
        assert result.stderr == ""
        assert stderr_messages == []
    else:
        assert len(stderr_messages) == 1
        assert stderr_messages[0] in result.stderr


@pytest.mark.parametrize("all_failed", [False, True])
@pytest.mark.parametrize("verbosity", [0, 1, 2])
@pytest.mark.parametrize("progress_bar", [False, True])
def test_cli_list_files_json_listing_failures_keep_stdout_clean(
    monkeypatch, sample_archive_files, stderr_messages, all_failed, verbosity, progress_bar
) -> None:
    """Partial and all-symbol failures serialize before exit, with diagnostics on stderr."""

    async def fake_run(self) -> ListFilesResult:
        entries = [
            SymbolListFilesResult("ETHUSDT", [], "listing-error-eth-41"),
            SymbolListFilesResult("BNBUSDT", [], "listing-error-bnb-41"),
        ]
        if not all_failed:
            entries.insert(1, SymbolListFilesResult("BTCUSDT", sample_archive_files))
        logger.info("listing-log-41")
        with make_reporter(
            self.progress_bar, total=len(entries), description="listing-progress-41"
        ) as reporter:
            for entry in entries:
                reporter.tick(ProgressEvent(name=entry.symbol, ok=entry.error is None))
        return ListFilesResult(entries)

    monkeypatch.setattr("binance_datatool.workflow.ArchiveListFilesWorkflow.run", fake_run)
    result = runner.invoke(
        app,
        [
            *(["-v"] * verbosity),
            "list-files",
            "um",
            "ETHUSDT",
            "BTCUSDT",
            "BNBUSDT",
            "--type",
            "fundingRate",
            "--json",
            *(["--progress-bar"] if progress_bar else []),
        ],
    )

    assert result.exit_code == 2
    document = json.loads(result.stdout)
    assert document["command"] == "list-files"
    assert document["dry_run"] is False
    assert document["summary"] == {
        "requested_symbols": 2 if all_failed else 3,
        "successful_symbols": 0 if all_failed else 1,
        "failed_symbols": 2,
        "total_remote_files": 0 if all_failed else 2,
        "returned_files": 0 if all_failed else 2,
    }
    assert [entry["symbol"] for entry in document["per_symbol"]] == (
        ["ETHUSDT", "BNBUSDT"] if all_failed else ["ETHUSDT", "BTCUSDT", "BNBUSDT"]
    )
    assert document["per_symbol"][0] == {
        "symbol": "ETHUSDT",
        "files": [],
        "error": "listing-error-eth-41",
    }
    assert document["per_symbol"][-1] == {
        "symbol": "BNBUSDT",
        "files": [],
        "error": "listing-error-bnb-41",
    }
    for symbol, error in [("ETHUSDT", "listing-error-eth-41"), ("BNBUSDT", "listing-error-bnb-41")]:
        assert any(symbol in line and error in line for line in result.stderr.splitlines())
    assert ("listing-log-41" in result.stderr) is (verbosity > 0)
    if progress_bar or verbosity:
        assert "listing-progress-41" in result.stderr
    assert stderr_messages == []


@pytest.mark.parametrize("piped", [False, True])
def test_cli_list_files_json_preserves_normalized_duplicate_and_file_order(
    monkeypatch, sample_archive_files, piped
) -> None:
    """The real listing workflow collapses uppercase duplicate inputs in first-seen order."""

    async def fake_list_symbol_files(
        self, market_type, data_freq, data_type, symbol, interval=None, *, session=None
    ):
        return list(reversed(sample_archive_files)) if symbol == "BTCUSDT" else []

    monkeypatch.setattr(
        "binance_datatool.archive.ArchiveClient.list_symbol_files", fake_list_symbol_files
    )
    result = runner.invoke(
        app,
        [
            "list-files",
            "um",
            "--type",
            "fundingRate",
            "--json",
            *([] if piped else ["ethusdt", "btcusdt", "ETHUSDT", "BTCUSDT"]),
        ],
        input="ethusdt\nbtcusdt\nETHUSDT\nBTCUSDT\n" if piped else None,
    )

    assert result.exit_code == 0
    document = json.loads(result.stdout)
    assert document["per_symbol"][0] == {"symbol": "ETHUSDT", "files": [], "error": None}
    assert [entry["symbol"] for entry in document["per_symbol"]] == ["ETHUSDT", "BTCUSDT"]
    assert [file["size"] for file in document["per_symbol"][1]["files"]] == [105, 1048]
    assert document["summary"] == {
        "requested_symbols": 2,
        "successful_symbols": 2,
        "failed_symbols": 0,
        "total_remote_files": 2,
        "returned_files": 2,
    }
    assert result.stderr == ""


@pytest.mark.parametrize(
    "arguments",
    [
        ["um", "BTCUSDT", "--type", "fundingRate", "--only-zip", "--only-checksum"],
        ["um", "BTCUSDT"],
        ["um", "BTCUSDT", "--type", "fundingRate", "--interval", "1m"],
        ["um", "--type", "fundingRate"],
        ["um", "BTCUSDT", "--type", "fundingRate", "--dry-run"],
    ],
)
def test_cli_list_files_json_argument_errors_have_no_document(
    no_workflow_execution, arguments
) -> None:
    """Invalid JSON invocations retain validation exits without a result envelope."""
    result = runner.invoke(app, ["list-files", *arguments, "--json"], input="")

    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.strip()


def test_cli_list_files_json_unhandled_error_has_no_result(monkeypatch) -> None:
    """An exception before a workflow result does not invent a completed listing."""

    async def fake_run(self) -> ListFilesResult:
        raise RuntimeError("listing-exception-41")

    monkeypatch.setattr("binance_datatool.workflow.ArchiveListFilesWorkflow.run", fake_run)
    result = runner.invoke(app, ["list-files", "um", "BTCUSDT", "--type", "fundingRate", "--json"])

    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)
    assert str(result.exception) == "listing-exception-41"
    assert result.stdout == ""


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
    assert "already verified" in result.stderr


def test_cli_verify_dry_run_preserves_workflow_path_order(monkeypatch, tmp_path: Path) -> None:
    """Dry-run stdout preserves the workflow plan's order and relative paths."""

    def fake_run(self) -> VerifyDiffResult:
        assert self.symbols == ["ETHUSDT", "MISSING", "BTCUSDT"]
        assert self.dry_run is True
        return VerifyDiffResult(
            to_verify=[
                tmp_path / f"data/spot/daily/klines/{symbol}/1m/{name}"
                for symbol in ("ETHUSDT", "BTCUSDT")
                for name in ("a.zip", "z.zip")
            ],
            skipped=0,
            orphan_zips=[],
            orphan_checksums=[],
        )

    monkeypatch.setattr("binance_datatool.workflow.ArchiveVerifyWorkflow.run", fake_run)

    result = runner.invoke(
        app,
        [
            "--archive-home",
            str(tmp_path),
            "verify",
            "spot",
            "--dry-run",
            "--interval",
            "1m",
            "ETHUSDT",
            "MISSING",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == (
        "ETHUSDT/1m/a.zip\nETHUSDT/1m/z.zip\nBTCUSDT/1m/a.zip\nBTCUSDT/1m/z.zip\n"
    )


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


@pytest.mark.parametrize(("options", "expected"), [([], 64), (["--concurrency", "128"], 128)])
def test_cli_download_passes_concurrency(monkeypatch, options, expected) -> None:
    """Download concurrency should reach the workflow, including its default."""

    async def fake_run(self) -> DownloadResult:
        assert self.concurrency == expected
        return DownloadResult(total_remote=0, skipped=0, downloaded=0, failed=0, listing_errors=[])

    monkeypatch.setattr("binance_datatool.workflow.ArchiveDownloadWorkflow.run", fake_run)
    result = runner.invoke(
        app,
        [
            "--archive-home",
            "/tmp/archive-home",
            "download",
            "um",
            "--type",
            "fundingRate",
            *options,
            "BTCUSDT",
        ],
    )
    assert result.exit_code == 0


@pytest.mark.parametrize("concurrency", ["0", "-1"])
def test_cli_download_rejects_invalid_concurrency(no_workflow_execution, concurrency) -> None:
    """Nonpositive concurrency should be rejected before workflow execution."""
    result = runner.invoke(
        app,
        [
            "--archive-home",
            "/tmp/archive-home",
            "download",
            "um",
            "--type",
            "fundingRate",
            "--concurrency",
            concurrency,
            "BTCUSDT",
        ],
    )
    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.strip()


@pytest.mark.parametrize("progress_bar", [False, True])
@pytest.mark.parametrize("verbosity", [0, 1, 2])
def test_cli_routes_progress_and_filtered_diagnostics_to_stderr(
    monkeypatch, progress_bar: bool, verbosity: int
) -> None:
    """CLI verbosity preserves diagnostic payloads with and without a progress bar."""

    async def fake_run(self) -> ListFilesResult:
        with make_reporter(self.progress_bar, total=1, description="listing") as reporter:
            logger.warning("warning-payload-32 BTCUSDT")
            logger.info("info-payload-32 ETHUSDT")
            logger.debug("debug-payload-32 BNBUSDT")
            reporter.tick(ProgressEvent(name="BTCUSDT", ok=True))
        return ListFilesResult(per_symbol=[])

    monkeypatch.setattr("binance_datatool.workflow.ArchiveListFilesWorkflow.run", fake_run)
    result = runner.invoke(
        app,
        [
            *(["-" + "v" * verbosity] if verbosity else []),
            "list-files",
            "um",
            "--type",
            "fundingRate",
            *(["--progress-bar"] if progress_bar else []),
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 0
    assert result.stdout == ""
    assert "\x1b[" not in result.stderr
    assert result.stderr.count("warning-payload-32 BTCUSDT") == 1
    assert result.stderr.count("info-payload-32 ETHUSDT") == (1 if verbosity >= 1 else 0)
    assert result.stderr.count("debug-payload-32 BNBUSDT") == (1 if verbosity >= 2 else 0)


def test_cli_download_json_dry_run_plan(monkeypatch, tmp_path, sample_archive_files) -> None:
    """JSON plans retain reasons and sizes with absolute, possibly absent targets."""
    monkeypatch.chdir(tmp_path)

    async def fake_run(self) -> DiffResult:
        assert self.archive_home == Path("relative-home")
        assert self.dry_run is True
        return DiffResult(
            to_download=[
                DiffEntry(sample_archive_files[0], Path("relative-home/new.zip"), "new"),
                DiffEntry(
                    sample_archive_files[1], Path("relative-home/old.zip.CHECKSUM"), "updated"
                ),
            ],
            skipped=1,
            total_remote=3,
            listing_errors=[],
        )

    monkeypatch.setattr("binance_datatool.workflow.ArchiveDownloadWorkflow.run", fake_run)
    result = runner.invoke(
        app,
        [
            "--archive-home",
            "relative-home",
            "download",
            "um",
            "--type",
            "fundingRate",
            "--dry-run",
            "--json",
            "BTCUSDT",
        ],
    )
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == {
        "command": "download",
        "dry_run": True,
        "summary": {"total_remote": 3, "skipped": 1, "to_download": 2, "listing_failed_symbols": 0},
        "to_download": [
            {"path": str(tmp_path / "relative-home/new.zip"), "size": 1048, "reason": "new"},
            {
                "path": str(tmp_path / "relative-home/old.zip.CHECKSUM"),
                "size": 105,
                "reason": "updated",
            },
        ],
        "listing_errors": [],
    }
    assert result.stderr.strip()
    assert not (tmp_path / "relative-home").exists()


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize(
    "scenario",
    ["success", "empty", "partial", "all-listings-failed", "transfer-failed", "mixed-failures"],
)
def test_cli_download_json_results(monkeypatch, tmp_path, dry_run, scenario) -> None:
    """Returned results always emit one document before result-based exits."""
    errors = (
        [SymbolListingError("ETHUSDT", "listing-payload-39")]
        if scenario in {"partial", "all-listings-failed", "mixed-failures"}
        else []
    )
    if scenario == "all-listings-failed":
        errors.insert(0, SymbolListingError("BTCUSDT", "all-listing-payload-39"))
    skipped = 1 if scenario in {"success", "partial"} else 0
    failed = 1 if scenario in {"transfer-failed", "mixed-failures"} and not dry_run else 0
    downloaded = 1 if scenario in {"success", "partial", "mixed-failures"} and not dry_run else 0

    async def fake_run(self):
        assert self.progress_bar is True
        logger.info("download-log-payload-39")
        with make_reporter(True, total=1, description="download-progress-39") as reporter:
            reporter.tick(ProgressEvent(name="BTCUSDT", ok=True))
        if dry_run:
            return DiffResult([], skipped, skipped, errors)
        return DownloadResult(
            total_remote=skipped + downloaded + failed,
            skipped=skipped,
            downloaded=downloaded,
            failed=failed,
            listing_errors=errors,
            failed_paths=[Path("relative-home/failed.zip")] if failed else [],
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("binance_datatool.workflow.ArchiveDownloadWorkflow.run", fake_run)
    result = runner.invoke(
        app,
        [
            "-vv",
            "--archive-home",
            "relative-home",
            "download",
            "um",
            "--type",
            "fundingRate",
            "--json",
            "--progress-bar",
            *(["--dry-run"] if dry_run else []),
            "BTCUSDT",
            "ETHUSDT",
        ],
    )
    assert result.exit_code == (2 if errors or failed else 0), result.exception
    document = json.loads(result.stdout)
    assert document["command"] == "download"
    assert document["dry_run"] is dry_run
    summary = document["summary"]
    assert all(type(value) is int and value >= 0 for value in summary.values())
    assert summary["listing_failed_symbols"] == len(errors)
    expected_errors = [{"symbol": "ETHUSDT", "error": "listing-payload-39"}] if errors else []
    if scenario == "all-listings-failed":
        expected_errors.insert(0, {"symbol": "BTCUSDT", "error": "all-listing-payload-39"})
    assert document["listing_errors"] == expected_errors
    if dry_run:
        assert document == {
            "command": "download",
            "dry_run": True,
            "summary": {
                "total_remote": skipped,
                "skipped": skipped,
                "to_download": 0,
                "listing_failed_symbols": len(errors),
            },
            "to_download": [],
            "listing_errors": document["listing_errors"],
        }
    else:
        assert document == {
            "command": "download",
            "dry_run": False,
            "summary": {
                "total_remote": skipped + downloaded + failed,
                "skipped": skipped,
                "downloaded": downloaded,
                "failed": failed,
                "listing_failed_symbols": len(errors),
            },
            "failed_paths": [str(tmp_path / "relative-home/failed.zip")] if failed else [],
            "listing_errors": document["listing_errors"],
        }
    assert "download-log-payload-39" in result.stderr
    assert "download-progress-39" in result.stderr
    for entry in expected_errors:
        assert entry["symbol"] in result.stderr
        assert entry["error"] in result.stderr


@pytest.mark.parametrize("json_output", [True, False])
def test_cli_download_child_output_routing(
    monkeypatch, tmp_path, sample_archive_files, capfd, json_output
) -> None:
    """A real controlled child cannot contaminate JSON stdout, even with progress."""
    executable = tmp_path / "aria2c"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "from pathlib import Path\n"
        "print('child-stdout-payload-39', flush=True)\n"
        "print('child-stderr-payload-39', file=sys.stderr, flush=True)\n"
        "lines = Path(sys.argv[sys.argv.index('-i') + 1]).read_text().splitlines()\n"
        "for url, directory in zip(lines[::2], lines[1::2]):\n"
        "    (Path(directory.strip().removeprefix('dir=')) / url.rsplit('/', 1)[1]).write_bytes(b'data')\n",
        encoding="utf-8",
    )
    executable.chmod(0o755)
    monkeypatch.setattr("shutil.which", lambda name: str(executable))

    async def fake_listing(self, *args, **kwargs):
        return {"BTCUSDT": (sample_archive_files, None)}

    monkeypatch.setattr(
        "binance_datatool.archive.ArchiveClient.list_symbol_files_batch", fake_listing
    )
    result = runner.invoke(
        app,
        [
            "-vv",
            "--archive-home",
            str(tmp_path / "home"),
            "download",
            "um",
            "--freq",
            "monthly",
            "--type",
            "fundingRate",
            "--progress-bar",
            *(["--json"] if json_output else []),
            "BTCUSDT",
        ],
    )
    child_output = capfd.readouterr()
    assert result.exit_code == 0, result.exception
    if json_output:
        document = json.loads(result.stdout)
        assert document["summary"] == {
            "total_remote": 2,
            "skipped": 0,
            "downloaded": 2,
            "failed": 0,
            "listing_failed_symbols": 0,
        }
        assert document["failed_paths"] == []
        assert child_output.out == ""
        assert "child-stdout-payload-39" in result.stderr
    else:
        assert result.stdout == ""
        assert "child-stdout-payload-39" in child_output.out
    assert "child-stderr-payload-39" in child_output.err
    assert result.stderr.strip()


@pytest.mark.parametrize(
    "arguments",
    [
        ["--archive-home", "/tmp/home", "download", "um", "BTCUSDT", "--json"],
        ["download", "um", "--type", "fundingRate", "BTCUSDT", "--json"],
        ["--archive-home", "/tmp/home", "download", "um", "--type", "fundingRate", "--json"],
    ],
)
def test_cli_download_json_pre_result_errors(monkeypatch, no_workflow_execution, arguments) -> None:
    """Invalid arguments and missing configuration have no JSON result envelope."""
    monkeypatch.delenv("BINANCE_DATATOOL_ARCHIVE_HOME", raising=False)
    result = runner.invoke(app, arguments)
    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.strip()


def test_cli_download_json_unhandled_error_has_no_result(monkeypatch) -> None:
    """Exceptions without a workflow result retain their existing failure boundary."""

    async def fake_run(self):
        raise RuntimeError("workflow-exception-payload-39")

    monkeypatch.setattr("binance_datatool.workflow.ArchiveDownloadWorkflow.run", fake_run)
    result = runner.invoke(
        app,
        [
            "--archive-home",
            "/tmp/home",
            "download",
            "um",
            "--type",
            "fundingRate",
            "--json",
            "BTCUSDT",
        ],
    )
    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)
    assert str(result.exception) == "workflow-exception-payload-39"
    assert result.stdout == ""


def test_cli_verify_json_dry_run_plan(monkeypatch, tmp_path) -> None:
    """JSON scan plans retain path order and orphan counts with a relative Archive home."""
    monkeypatch.chdir(tmp_path)

    def fake_run(self) -> VerifyDiffResult:
        assert self.archive_home == Path("relative-home")
        assert self.dry_run is True
        return VerifyDiffResult(
            to_verify=[Path("relative-home/z.zip"), Path("relative-home/a.zip")],
            skipped=3,
            orphan_zips=[Path("relative-home/orphan.zip")],
            orphan_checksums=[Path("relative-home/missing.zip.CHECKSUM")],
        )

    monkeypatch.setattr("binance_datatool.workflow.ArchiveVerifyWorkflow.run", fake_run)
    result = runner.invoke(
        app,
        [
            "--archive-home",
            "relative-home",
            "verify",
            "um",
            "--type",
            "fundingRate",
            "--dry-run",
            "--json",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == {
        "command": "verify",
        "dry_run": True,
        "summary": {
            "total_zips": 6,
            "to_verify": 2,
            "already_verified": 3,
            "orphan_zips": 1,
            "orphan_checksums": 1,
        },
        "to_verify": [str(tmp_path / "relative-home/z.zip"), str(tmp_path / "relative-home/a.zip")],
    }
    assert result.stderr.strip()
    assert not (tmp_path / "relative-home").exists()


@pytest.mark.parametrize("keep_failed", [False, True])
def test_cli_verify_json_failed_pair_cleanup(monkeypatch, tmp_path, keep_failed) -> None:
    """Failed paths survive cleanup in JSON while keep-failed controls actual file retention."""
    monkeypatch.chdir(tmp_path)
    base_dir = tmp_path / "relative-home/data/futures/um/daily/fundingRate/BTCUSDT"
    base_dir.mkdir(parents=True)
    zip_path = base_dir / "failed.zip"
    zip_path.write_bytes(b"bad archive")
    checksum_path = base_dir / "failed.zip.CHECKSUM"
    checksum_path.write_text(f"{'0' * 64}  failed.zip\n", encoding="utf-8")
    marker_path = base_dir / "failed.zip.100.verified"
    marker_path.touch()

    result = runner.invoke(
        app,
        [
            "--archive-home",
            "relative-home",
            "verify",
            "um",
            "--type",
            "fundingRate",
            "--json",
            *(["--keep-failed"] if keep_failed else []),
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 2, result.exception
    assert json.loads(result.stdout) == {
        "command": "verify",
        "dry_run": False,
        "summary": {
            "total_zips": 1,
            "verified": 0,
            "failed": 1,
            "skipped": 0,
            "orphan_zips": 0,
            "orphan_checksums": 0,
        },
        "failed_details": [{"path": str(zip_path), "detail": "checksum mismatch"}],
    }
    assert zip_path.exists() is keep_failed
    assert checksum_path.exists() is keep_failed
    assert not marker_path.exists()
    assert "failed.zip" in result.stderr
    assert "checksum mismatch" in result.stderr


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize(
    "scenario", ["success", "empty", "orphan-zip", "orphan-checksum", "failed"]
)
def test_cli_verify_json_results(monkeypatch, tmp_path, dry_run, scenario) -> None:
    """Returned verification results always emit their mode's document with clean stdout."""
    skipped = 1 if scenario == "success" else 0
    verified = 2 if scenario == "success" and not dry_run else 0
    pending = [Path("relative-home/pending.zip")] if scenario == "success" and dry_run else []
    orphan_zips = [Path("relative-home/orphan.zip")] if scenario == "orphan-zip" else []
    orphan_checksums = (
        [Path("relative-home/missing.zip.CHECKSUM")] if scenario == "orphan-checksum" else []
    )
    failed_details = (
        {
            Path("relative-home/z.zip"): "verify-detail-payload-42-z",
            Path("relative-home/a.zip"): "verify-detail-payload-42-a",
        }
        if scenario == "failed" and not dry_run
        else {}
    )

    def fake_run(self):
        assert self.progress_bar is True
        logger.info("verify-log-payload-42")
        with make_reporter(True, total=1, description="verify-progress-42") as reporter:
            reporter.tick(ProgressEvent(name="BTCUSDT", ok=True))
        if dry_run:
            return VerifyDiffResult(pending, skipped, orphan_zips, orphan_checksums)
        return VerifyResult(
            skipped, verified, len(orphan_zips), len(orphan_checksums), failed_details
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("binance_datatool.workflow.ArchiveVerifyWorkflow.run", fake_run)
    result = runner.invoke(
        app,
        [
            "-vv",
            "--archive-home",
            "relative-home",
            "verify",
            "um",
            "--type",
            "fundingRate",
            "--json",
            "--progress-bar",
            *(["--dry-run"] if dry_run else []),
            "BTCUSDT",
        ],
    )

    assert result.exit_code == (2 if failed_details else 0), result.exception
    document = json.loads(result.stdout)
    assert document["command"] == "verify"
    assert document["dry_run"] is dry_run
    assert all(type(value) is int and value >= 0 for value in document["summary"].values())
    if dry_run:
        assert document == {
            "command": "verify",
            "dry_run": True,
            "summary": {
                "total_zips": len(pending) + skipped + len(orphan_zips),
                "to_verify": len(pending),
                "already_verified": skipped,
                "orphan_zips": len(orphan_zips),
                "orphan_checksums": len(orphan_checksums),
            },
            "to_verify": [str(tmp_path / "relative-home/pending.zip")] if pending else [],
        }
    else:
        assert document == {
            "command": "verify",
            "dry_run": False,
            "summary": {
                "total_zips": verified + len(failed_details) + skipped + len(orphan_zips),
                "verified": verified,
                "failed": len(failed_details),
                "skipped": skipped,
                "orphan_zips": len(orphan_zips),
                "orphan_checksums": len(orphan_checksums),
            },
            "failed_details": [
                {
                    "path": str(tmp_path / "relative-home/z.zip"),
                    "detail": "verify-detail-payload-42-z",
                },
                {
                    "path": str(tmp_path / "relative-home/a.zip"),
                    "detail": "verify-detail-payload-42-a",
                },
            ]
            if failed_details
            else [],
        }
    assert "verify-log-payload-42" in result.stderr
    assert "verify-progress-42" in result.stderr
    for detail in failed_details.values():
        assert detail in result.stderr


@pytest.mark.parametrize("dry_run", [False, True])
def test_cli_verify_json_orphan_cleanup(monkeypatch, tmp_path, dry_run) -> None:
    """Orphan counts describe artifacts even when an orphan ZIP has no existing marker."""
    base_dir = tmp_path / "data/futures/um/daily/fundingRate/BTCUSDT"
    base_dir.mkdir(parents=True)
    orphan_zip = base_dir / "orphan.zip"
    orphan_zip.write_bytes(b"orphan")
    unmarked_zip = base_dir / "unmarked.zip"
    unmarked_zip.write_bytes(b"orphan without marker")
    checksum_path = base_dir / "missing.zip.CHECKSUM"
    checksum_path.write_text("orphan checksum", encoding="utf-8")
    markers = [base_dir / "orphan.zip.100.verified", base_dir / "missing.zip.100.verified"]
    for marker in markers:
        marker.touch()

    result = runner.invoke(
        app,
        [
            "--archive-home",
            str(tmp_path),
            "verify",
            "um",
            "--type",
            "fundingRate",
            "--json",
            *(["--dry-run"] if dry_run else []),
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 0, result.exception
    assert json.loads(result.stdout) == {
        "command": "verify",
        "dry_run": dry_run,
        "summary": {
            "total_zips": 2,
            **(
                {"to_verify": 0, "already_verified": 0}
                if dry_run
                else {"verified": 0, "failed": 0, "skipped": 0}
            ),
            "orphan_zips": 2,
            "orphan_checksums": 1,
        },
        "to_verify" if dry_run else "failed_details": [],
    }
    assert orphan_zip.exists()
    assert unmarked_zip.exists()
    assert checksum_path.exists() is dry_run
    assert all(marker.exists() is dry_run for marker in markers)


def test_cli_verify_json_dry_run_preserves_pending_pair(monkeypatch, tmp_path) -> None:
    """Dry-run scans pending ZIPs without hashing, deleting artifacts, or changing markers."""
    base_dir = tmp_path / "data/futures/um/daily/fundingRate/BTCUSDT"
    base_dir.mkdir(parents=True)
    zip_path = base_dir / "pending.zip"
    zip_path.write_bytes(b"pending")
    checksum_path = base_dir / "pending.zip.CHECKSUM"
    checksum_path.write_text("invalid checksum", encoding="utf-8")
    legacy_marker = base_dir / "pending.zip.verified"
    legacy_marker.touch()
    contents_before = {path: path.read_bytes() for path in base_dir.iterdir()}

    def unexpected_verification(zip_path):
        pytest.fail("Dry-run must not hash pending files.")

    monkeypatch.setattr(
        "binance_datatool.workflow.verify.verify_single_file", unexpected_verification
    )
    result = runner.invoke(
        app,
        [
            "--archive-home",
            str(tmp_path),
            "verify",
            "um",
            "--type",
            "fundingRate",
            "--json",
            "--dry-run",
            "BTCUSDT",
        ],
    )

    assert result.exit_code == 0, result.exception
    assert json.loads(result.stdout) == {
        "command": "verify",
        "dry_run": True,
        "summary": {
            "total_zips": 1,
            "to_verify": 1,
            "already_verified": 0,
            "orphan_zips": 0,
            "orphan_checksums": 0,
        },
        "to_verify": [str(zip_path)],
    }
    assert {path: path.read_bytes() for path in base_dir.iterdir()} == contents_before


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize(
    "arguments",
    [
        ["--archive-home", "/tmp/home", "verify", "um", "BTCUSDT"],
        ["verify", "um", "--type", "fundingRate", "BTCUSDT"],
        ["--archive-home", "/tmp/home", "verify", "um", "--type", "fundingRate"],
    ],
)
def test_cli_verify_json_pre_result_errors(
    monkeypatch, no_workflow_execution, arguments, dry_run
) -> None:
    """Invalid arguments and missing configuration retain an empty stdout before any result."""
    monkeypatch.delenv("BINANCE_DATATOOL_ARCHIVE_HOME", raising=False)
    result = runner.invoke(app, [*arguments, "--json", *(["--dry-run"] if dry_run else [])])
    assert result.exit_code == 2
    assert result.stdout == ""
    assert result.stderr.strip()


def test_cli_verify_json_unhandled_error_has_no_result(monkeypatch) -> None:
    """Workflow exceptions retain their existing failure boundary without a JSON result."""

    def fake_run(self):
        raise RuntimeError("verify-exception-payload-42")

    monkeypatch.setattr("binance_datatool.workflow.ArchiveVerifyWorkflow.run", fake_run)
    result = runner.invoke(
        app,
        [
            "--archive-home",
            "/tmp/home",
            "verify",
            "um",
            "--type",
            "fundingRate",
            "--json",
            "BTCUSDT",
        ],
    )
    assert result.exit_code == 1
    assert isinstance(result.exception, RuntimeError)
    assert str(result.exception) == "verify-exception-payload-42"
    assert result.stdout == ""


@pytest.mark.parametrize("json_output", [False, True])
def test_cli_download_missing_aria2_reports_clean_error(monkeypatch, json_output) -> None:
    """Missing tooling reports cleanly in both output modes."""

    async def fake_run(self):
        raise Aria2NotFoundError("aria2c executable not found in PATH.")

    monkeypatch.setattr("binance_datatool.workflow.ArchiveDownloadWorkflow.run", fake_run)
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
            *(["--json"] if json_output else []),
            "BTCUSDT",
        ],
    )
    assert result.exit_code == 2
    assert result.stdout == ""
    assert "aria2c" in result.stderr
    assert "PATH" in result.stderr
    assert "Traceback" not in result.output
