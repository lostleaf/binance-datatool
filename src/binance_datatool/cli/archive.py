"""Archive CLI commands."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import asdict
from datetime import UTC
from typing import TYPE_CHECKING, Annotated, TypeAlias

import typer
from loguru import logger

from binance_datatool.archive import Aria2NotFoundError
from binance_datatool.cli import app
from binance_datatool.cli.output import JsonOutputOption, absolute_path, emit_json
from binance_datatool.common import (
    ArchiveHomeNotConfiguredError,
    ContractType,
    DataFrequency,
    DataType,
    TradeType,
    build_symbol_filter,
    resolve_archive_home,
)
from binance_datatool.common.constants import S3_DOWNLOAD_PREFIX
from binance_datatool.common.path import archive_path_parts, validate_interval
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


DataFrequencyOption: TypeAlias = Annotated[
    DataFrequency,
    typer.Option("--freq", help="Partition frequency."),
]
DataTypeOption: TypeAlias = Annotated[
    DataType,
    typer.Option("--type", help="Dataset type."),
]
IntervalOption: TypeAlias = Annotated[
    str | None,
    typer.Option("--interval", help="Interval for kline-class data types."),
]
ProgressBarOption: TypeAlias = Annotated[
    bool,
    typer.Option(
        "--progress-bar",
        help=("Show interactive tqdm progress bar. By default no interactive progress is shown."),
    ),
]


@app.command("list-symbols")
def list_symbols_command(
    trade_type: Annotated[TradeType, typer.Argument(help="Market segment.")],
    data_freq: DataFrequencyOption = DataFrequency.daily,
    data_type: DataTypeOption = DataType.klines,
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
    json_output: JsonOutputOption = False,
) -> None:
    """List symbol directories under a Binance archive prefix.

    Prints one symbol per line or a structured JSON classification result.
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
    result = asyncio.run(workflow.run())
    filtering = bool(quotes or exclude_leverage or exclude_stables or contract_type)
    symbols = [info.symbol for info in result.matched] if filtering else result.raw_symbols
    if json_output:
        emit_json(
            "list-symbols",
            dry_run=False,
            summary={
                "total_raw_symbols": result.total_raw_symbols,
                "returned_symbols": len(symbols),
                "matched_symbols": result.matched_symbols,
                "filtered_out_symbols": result.filtered_out_symbols,
                "uninferable_symbols": result.inference_failed_symbols,
            },
            symbols=symbols,
            matched=[asdict(info) for info in result.matched],
            filtered_out=[asdict(info) for info in result.filtered_out],
            uninferable=result.unmatched,
        )
    else:
        for symbol in symbols:
            typer.echo(symbol)
    if filtering and result.unmatched:
        typer.echo(
            f"Warning: skipped {result.inference_failed_symbols} symbols whose metadata "
            f"could not be inferred for filtering: {', '.join(result.unmatched)}",
            err=True,
        )


def _resolve_symbols(symbols: list[str] | None) -> list[str]:
    """Resolve symbol inputs from CLI arguments or piped stdin."""
    if symbols:
        return [symbol.strip().upper() for symbol in symbols if symbol.strip()]

    if not sys.stdin.isatty():
        return [line.strip().upper() for line in sys.stdin.read().splitlines() if line.strip()]

    return []


def _validate_interval(data_type: DataType, interval: str | None) -> None:
    """Validate whether an interval matches the selected data type."""
    try:
        validate_interval(data_type, interval)
    except ValueError as exc:
        messages = {
            "interval is required for kline-class data_type": (
                "Option '--interval' is required for kline-class data types."
            ),
            "interval is not applicable to non-kline data_type": (
                "Option '--interval' is only valid for kline-class data types."
            ),
        }
        raise typer.BadParameter(messages[str(exc)], param_hint="--interval") from exc


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
    prefix = "/".join(archive_path_parts(trade_type, data_freq, data_type)) + "/"
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
    prefix = archive_home.joinpath(*archive_path_parts(trade_type, data_freq, data_type))
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
    data_freq: DataFrequencyOption = DataFrequency.daily,
    data_type: DataTypeOption = DataType.klines,
    interval: IntervalOption = None,
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
    progress_bar: ProgressBarOption = False,
    json_output: JsonOutputOption = False,
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

    per_symbol: list[dict[str, object]] = []
    returned_files = 0
    for entry in result.per_symbol:
        files: list[dict[str, object]] = []
        if json_output:
            per_symbol.append({"symbol": entry.symbol, "files": files, "error": entry.error})
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

            if json_output:
                files.append(
                    {
                        "url": f"{S3_DOWNLOAD_PREFIX}/{archive_file.key}",
                        "size": archive_file.size,
                        "last_modified": archive_file.last_modified.astimezone(UTC).strftime(
                            "%Y-%m-%dT%H:%M:%SZ"
                        ),
                    }
                )
                returned_files += 1
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

    if json_output:
        emit_json(
            "list-files",
            dry_run=False,
            summary={
                "requested_symbols": result.requested_symbols,
                "successful_symbols": result.successful_symbols,
                "failed_symbols": result.failed_symbols,
                "total_remote_files": result.total_remote_files,
                "returned_files": returned_files,
            },
            per_symbol=per_symbol,
        )

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
    data_freq: DataFrequencyOption = DataFrequency.daily,
    data_type: DataTypeOption = DataType.klines,
    interval: IntervalOption = None,
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
    concurrency: Annotated[
        int,
        typer.Option("--concurrency", min=1, help="Number of concurrent aria2 downloads."),
    ] = 64,
    progress_bar: ProgressBarOption = False,
    json_output: JsonOutputOption = False,
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
        concurrency=concurrency,
        progress_bar=progress_bar,
        stdout_to_stderr=json_output,
    )
    try:
        result = asyncio.run(workflow.run())
    except Aria2NotFoundError as exc:
        typer.echo(f"Error: {exc} Install aria2 and ensure aria2c is in PATH.", err=True)
        raise typer.Exit(code=2) from exc

    if json_output:
        listing_errors = [
            {"symbol": entry.symbol, "error": entry.error} for entry in result.listing_errors
        ]

    if isinstance(result, DiffResult):
        if json_output:
            emit_json(
                "download",
                dry_run=True,
                summary={
                    "total_remote": result.total_remote,
                    "skipped": result.skipped,
                    "to_download": len(result.to_download),
                    "listing_failed_symbols": result.listing_failed_symbols,
                },
                to_download=[
                    {
                        "path": absolute_path(entry.local_path),
                        "size": entry.remote.size,
                        "reason": entry.reason,
                    }
                    for entry in result.to_download
                ],
                listing_errors=listing_errors,
            )
        else:
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

    if json_output:
        emit_json(
            "download",
            dry_run=False,
            summary={
                "total_remote": result.total_remote,
                "skipped": result.skipped,
                "downloaded": result.downloaded,
                "failed": result.failed,
                "listing_failed_symbols": result.listing_failed_symbols,
            },
            failed_paths=[absolute_path(path) for path in result.failed_paths],
            listing_errors=listing_errors,
        )

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
    data_freq: DataFrequencyOption = DataFrequency.daily,
    data_type: DataTypeOption = DataType.klines,
    interval: IntervalOption = None,
    keep_failed: Annotated[
        bool,
        typer.Option("--keep-failed", help="Keep failed zip and checksum files."),
    ] = False,
    dry_run: Annotated[
        bool,
        typer.Option("-n", "--dry-run", help="Show what would be verified without writing files."),
    ] = False,
    progress_bar: ProgressBarOption = False,
    json_output: JsonOutputOption = False,
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
        if json_output:
            emit_json(
                "verify",
                dry_run=True,
                summary={
                    "total_zips": result.total_zips,
                    "to_verify": len(result.to_verify),
                    "skipped": result.skipped,
                    "orphan_zips": len(result.orphan_zips),
                    "orphan_checksums": len(result.orphan_checksums),
                },
                to_verify=[absolute_path(path) for path in result.to_verify],
            )
        else:
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
    if json_output:
        emit_json(
            "verify",
            dry_run=False,
            summary={
                "total_zips": result.total_zips,
                "verified": result.verified,
                "failed": result.failed,
                "skipped": result.skipped,
                "orphan_zips": result.orphan_zips,
                "orphan_checksums": result.orphan_checksums,
            },
            failed_details=[
                {"path": absolute_path(path), "detail": detail}
                for path, detail in result.failed_details.items()
            ],
        )

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
