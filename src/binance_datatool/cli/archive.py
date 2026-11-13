"""Archive CLI commands."""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC
from typing import TYPE_CHECKING, Annotated

import typer
from loguru import logger

from binance_datatool.cli import app
from binance_datatool.common import (
    ArchiveHomeNotConfiguredError,
    ContractType,
    DataFrequency,
    DataType,
    TradeType,
    build_symbol_filter,
    resolve_archive_home,
)
from binance_datatool.workflow import (
    ArchiveDownloadWorkflow,
    ArchiveListFilesWorkflow,
    ArchiveListSymbolsWorkflow,
    ArchiveVerifyWorkflow,
    DiffResult,
    DownloadResult,
    SymbolListingError,
    VerifyDiffResult,
    VerifyResult,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


@app.command("list-symbols")
def list_symbols_command(
    trade_type: Annotated[TradeType, typer.Argument(help="Market segment.")],
    data_freq: Annotated[
        DataFrequency,
        typer.Option("--freq", help="Partition frequency."),
    ] = DataFrequency.daily,
    data_type: Annotated[
        DataType,
        typer.Option("--type", help="Dataset type."),
    ] = DataType.klines,
    quotes: Annotated[
        list[str] | None,
        typer.Option("--quote", help="Filter by quote asset. Repeat to allow multiple values."),
    ] = None,
    exclude_leverage: Annotated[
        bool,
        typer.Option("--exclude-leverage", help="Exclude leveraged spot tokens."),
    ] = False,
    exclude_stables: Annotated[
        bool,
        typer.Option("--exclude-stables", help="Exclude stablecoin pairs."),
    ] = False,
    contract_type: Annotated[
        ContractType | None,
        typer.Option("--contract-type", help="Filter futures symbols by contract type."),
    ] = None,
) -> None:
    """List symbol directories under a Binance archive prefix.

    Prints one symbol per line to stdout.
    """
    symbol_filter = build_symbol_filter(
        trade_type=trade_type,
        quote_assets=frozenset(quote.upper() for quote in quotes) if quotes else None,
        exclude_leverage=exclude_leverage,
        exclude_stable_pairs=exclude_stables,
        contract_type=contract_type,
    )
    workflow = ArchiveListSymbolsWorkflow(
        trade_type=trade_type,
        data_freq=data_freq,
        data_type=data_type,
        symbol_filter=symbol_filter,
    )
    for info in asyncio.run(workflow.run()).matched:
        typer.echo(info.symbol)


def _resolve_symbols(symbols: list[str] | None) -> list[str]:
    """Resolve symbol inputs from CLI arguments or piped stdin."""
    if symbols:
        return [symbol.strip().upper() for symbol in symbols if symbol.strip()]

    if not sys.stdin.isatty():
        return [line.strip().upper() for line in sys.stdin.read().splitlines() if line.strip()]

    return []


def _validate_interval(data_type: DataType, interval: str | None) -> None:
    """Validate whether an interval matches the selected data type."""
    if data_type.has_interval_layer and interval is None:
        raise typer.BadParameter(
            "Option '--interval' is required for kline-class data types.",
            param_hint="--interval",
        )
    if not data_type.has_interval_layer and interval is not None:
        raise typer.BadParameter(
            "Option '--interval' is only valid for kline-class data types.",
            param_hint="--interval",
        )


def _matches_output_filter(
    key: str,
    *,
    only_zip: bool,
    only_checksum: bool,
) -> bool:
    """Return whether a listed file should be printed."""
    if only_zip:
        return not key.endswith(".CHECKSUM")
    if only_checksum:
        return key.endswith(".CHECKSUM")
    return True


def _format_relative_path(
    key: str,
    trade_type: TradeType,
    data_freq: DataFrequency,
    data_type: DataType,
) -> str:
    """Format a key relative to the shared archive prefix."""
    prefix = f"data/{trade_type.s3_path}/{data_freq.value}/{data_type.value}/"
    return key.removeprefix(prefix)


def _format_local_relative_path(
    path: Path,
    *,
    archive_home: Path,
    trade_type: TradeType,
    data_freq: DataFrequency,
    data_type: DataType,
) -> str:
    """Format a local archive path relative to the shared archive prefix."""
    prefix = archive_home / "data" / trade_type.s3_path / data_freq.value / data_type.value
    return str(path.relative_to(prefix))


def _warn_if_empty_remote(*, total_remote: int, has_failures: bool) -> None:
    """Print a heuristic warning for empty remote results."""
    if total_remote != 0 or has_failures:
        return

    typer.echo(
        (
            "Warning: no archive files found; check --freq, --type, and trade_type "
            "(for example, futures fundingRate requires --freq monthly)."
        ),
        err=True,
    )


def _warn_if_empty_local_scan(*, total_zips: int) -> None:
    """Print a warning when verify did not find any local zip files."""
    if total_zips != 0:
        return

    typer.echo(
        (
            "Warning: no local zip files found; check --archive-home, --freq, --type, "
            "--interval, and symbols."
        ),
        err=True,
    )


def _resolve_archive_home(ctx: typer.Context) -> Path:
    """Resolve the archive home directory for commands that use local files."""
    override = ctx.obj.get("archive_home_override")

    try:
        return resolve_archive_home(override)
    except ArchiveHomeNotConfiguredError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=2) from exc


def _print_listing_errors(listing_errors: Sequence[SymbolListingError]) -> None:
    """Print per-symbol listing errors to stderr."""
    for entry in listing_errors:
        logger.error("{}: {}", entry.symbol, entry.error)


def _finalize_download_result(result: DiffResult | DownloadResult) -> None:
    """Emit shared warnings and exit status for download-style commands."""
    _print_listing_errors(result.listing_errors)
    _warn_if_empty_remote(
        total_remote=result.total_remote,
        has_failures=result.listing_failed_symbols > 0,
    )

    if result.listing_failed_symbols > 0:
        raise typer.Exit(code=2)


@app.command("list-files")
def list_files_command(
    trade_type: Annotated[TradeType, typer.Argument(help="Market segment.")],
    symbols: Annotated[list[str] | None, typer.Argument(help="Symbols to list files for.")] = None,
    data_freq: Annotated[
        DataFrequency,
        typer.Option("--freq", help="Partition frequency."),
    ] = DataFrequency.daily,
    data_type: Annotated[
        DataType,
        typer.Option("--type", help="Dataset type."),
    ] = DataType.klines,
    interval: Annotated[
        str | None,
        typer.Option("--interval", help="Interval for kline-class data types."),
    ] = None,
    long_format: Annotated[
        bool,
        typer.Option("-l", "--long", help="Print three-column TSV output."),
    ] = False,
    only_zip: Annotated[
        bool,
        typer.Option("--only-zip", help="Print only .zip files."),
    ] = False,
    only_checksum: Annotated[
        bool,
        typer.Option("--only-checksum", help="Print only .zip.CHECKSUM files."),
    ] = False,
    progress_bar: Annotated[
        bool,
        typer.Option(
            "--progress-bar",
            help=(
                "Show interactive tqdm progress bar. By default no interactive progress is shown."
            ),
        ),
    ] = False,
) -> None:
    """List archive files under one or more symbol directories."""
    if only_zip and only_checksum:
        raise typer.BadParameter(
            "Options '--only-zip' and '--only-checksum' are mutually exclusive.",
            param_hint="--only-zip",
        )

    _validate_interval(data_type, interval)

    resolved_symbols = _resolve_symbols(symbols)
    if not resolved_symbols:
        raise typer.BadParameter("No symbols given.", param_hint="SYMBOLS")

    workflow = ArchiveListFilesWorkflow(
        trade_type=trade_type,
        data_freq=data_freq,
        data_type=data_type,
        symbols=resolved_symbols,
        interval=interval,
        progress_bar=progress_bar,
    )
    result = asyncio.run(workflow.run())

    for entry in result.per_symbol:
        if entry.error is not None:
            logger.error("{}: {}", entry.symbol, entry.error)
            continue

        for archive_file in entry.files:
            if not _matches_output_filter(
                archive_file.key,
                only_zip=only_zip,
                only_checksum=only_checksum,
            ):
                continue

            relative_path = _format_relative_path(
                archive_file.key,
                trade_type=trade_type,
                data_freq=data_freq,
                data_type=data_type,
            )
            if long_format:
                timestamp = archive_file.last_modified.astimezone(UTC).strftime(
                    "%Y-%m-%dT%H:%M:%SZ"
                )
                typer.echo(f"{archive_file.size}\t{timestamp}\t{relative_path}")
            else:
                typer.echo(relative_path)

    _warn_if_empty_remote(
        total_remote=result.total_remote_files,
        has_failures=result.has_failures,
    )

    if result.has_failures:
        raise typer.Exit(code=2)


@app.command("download")
def download_command(
    ctx: typer.Context,
    trade_type: Annotated[TradeType, typer.Argument(help="Market segment.")],
    symbols: Annotated[list[str] | None, typer.Argument(help="Symbols to download.")] = None,
    data_freq: Annotated[
        DataFrequency,
        typer.Option("--freq", help="Partition frequency."),
    ] = DataFrequency.daily,
    data_type: Annotated[
        DataType,
        typer.Option("--type", help="Dataset type."),
    ] = DataType.klines,
    interval: Annotated[
        str | None,
        typer.Option("--interval", help="Interval for kline-class data types."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option(
            "-n", "--dry-run", help="Show what would be downloaded without writing files."
        ),
    ] = False,
    aria2_proxy: Annotated[
        bool,
        typer.Option(
            "--aria2-proxy",
            help="Allow aria2c to inherit system proxy environment variables.",
        ),
    ] = False,
    progress_bar: Annotated[
        bool,
        typer.Option(
            "--progress-bar",
            help=(
                "Show interactive tqdm progress bar. By default no interactive progress is shown."
            ),
        ),
    ] = False,
) -> None:
    """Download archive files into the local archive directory."""
    _validate_interval(data_type, interval)

    resolved_symbols = _resolve_symbols(symbols)
    if not resolved_symbols:
        raise typer.BadParameter("No symbols given.", param_hint="SYMBOLS")

    archive_home = _resolve_archive_home(ctx)
    workflow = ArchiveDownloadWorkflow(
        trade_type=trade_type,
        data_freq=data_freq,
        data_type=data_type,
        symbols=resolved_symbols,
        archive_home=archive_home,
        interval=interval,
        dry_run=dry_run,
        inherit_aria2_proxy=aria2_proxy,
        progress_bar=progress_bar,
    )
    result = asyncio.run(workflow.run())

    if isinstance(result, DiffResult):
        for entry in result.to_download:
            typer.echo(
                f"{entry.reason}\t{entry.remote.size}\t"
                f"{_format_relative_path(entry.remote.key, trade_type, data_freq, data_type)}"
            )
        typer.echo(
            f"{len(result.to_download)} files to download, {result.skipped} up to date",
            err=True,
        )
        _finalize_download_result(result)
        return

    typer.echo(
        f"Done: {result.downloaded} downloaded, {result.failed} failed, {result.skipped} skipped",
        err=True,
    )
    _finalize_download_result(result)
    if result.failed > 0:
        raise typer.Exit(code=2)


@app.command("verify")
def verify_command(
    ctx: typer.Context,
    trade_type: Annotated[TradeType, typer.Argument(help="Market segment.")],
    symbols: Annotated[list[str] | None, typer.Argument(help="Symbols to verify.")] = None,
    data_freq: Annotated[
        DataFrequency,
        typer.Option("--freq", help="Partition frequency."),
    ] = DataFrequency.daily,
    data_type: Annotated[
        DataType,
        typer.Option("--type", help="Dataset type."),
    ] = DataType.klines,
    interval: Annotated[
        str | None,
        typer.Option("--interval", help="Interval for kline-class data types."),
    ] = None,
    keep_failed: Annotated[
        bool,
        typer.Option("--keep-failed", help="Keep failed zip and checksum files."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("-n", "--dry-run", help="Show what would be verified without writing files."),
    ] = False,
    progress_bar: Annotated[
        bool,
        typer.Option(
            "--progress-bar",
            help=(
                "Show interactive tqdm progress bar. By default no interactive progress is shown."
            ),
        ),
    ] = False,
) -> None:
    """Verify local archive zip files against sibling checksum files."""
    _validate_interval(data_type, interval)

    resolved_symbols = _resolve_symbols(symbols)
    if not resolved_symbols:
        raise typer.BadParameter("No symbols given.", param_hint="SYMBOLS")

    archive_home = _resolve_archive_home(ctx)
    workflow = ArchiveVerifyWorkflow(
        trade_type=trade_type,
        data_freq=data_freq,
        data_type=data_type,
        symbols=resolved_symbols,
        archive_home=archive_home,
        interval=interval,
        keep_failed=keep_failed,
        dry_run=dry_run,
        progress_bar=progress_bar,
    )
    result = workflow.run()

    if isinstance(result, VerifyDiffResult):
        for zip_path in result.to_verify:
            typer.echo(
                _format_local_relative_path(
                    zip_path,
                    archive_home=archive_home,
                    trade_type=trade_type,
                    data_freq=data_freq,
                    data_type=data_type,
                )
            )
        typer.echo(
            (
                f"{len(result.to_verify)} to verify, {result.skipped} up to date, "
                f"{len(result.orphan_zips)} orphan zip, "
                f"{len(result.orphan_checksums)} orphan checksum"
            ),
            err=True,
        )
        _warn_if_empty_local_scan(total_zips=result.total_zips)
        return

    assert isinstance(result, VerifyResult)
    for path, detail in result.failed_details.items():
        logger.error("{}: {}", path.name, detail)

    typer.echo(
        f"Done: {result.verified} verified, {result.failed} failed, {result.skipped} skipped",
        err=True,
    )
    if result.orphan_zips > 0 or result.orphan_checksums > 0:
        typer.echo(
            (
                f"Cleaned {result.orphan_zips} orphan zip markers, "
                f"deleted {result.orphan_checksums} orphan checksums"
            ),
            err=True,
        )
    if keep_failed and result.failed > 0:
        typer.echo("Failed files were kept because --keep-failed is enabled.", err=True)

    _warn_if_empty_local_scan(total_zips=result.total_zips)
    if result.failed > 0:
        raise typer.Exit(code=2)
