# binance_datatool.workflow

Business logic orchestration between the CLI and remote/local archive helpers.
Verification is local-only. Domain meanings live in the [glossary](../../../GLOSSARY.md).

## `ArchiveListSymbolsWorkflow`

Fetches raw symbols via `ArchiveClient`, infers typed metadata per market segment, and
optionally applies a typed symbol filter.

```python
from binance_datatool.workflow import ArchiveListSymbolsWorkflow, ListSymbolsResult
from binance_datatool.common import DataFrequency, DataType, SpotSymbolFilter, TradeType

workflow = ArchiveListSymbolsWorkflow(
    trade_type=TradeType.spot,
    data_freq=DataFrequency.daily,
    data_type=DataType.klines,
    symbol_filter=SpotSymbolFilter(
        quote_assets=frozenset({"USDT"}),
        exclude_leverage=True,
    ),
)
result: ListSymbolsResult = await workflow.run()
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `trade_type` | *(required)* | Market segment to query. |
| `data_freq` | *(required)* | Partition frequency. |
| `data_type` | *(required)* | Dataset type. |
| `symbol_filter` | `None` | Optional typed filter applied to inferred metadata. `None` disables filtering. |
| `client` | `None` | Optional pre-configured `ArchiveClient`. A default client is created when omitted. |

### `run()`

```python
async def run(self) -> ListSymbolsResult
```

1. Calls `client.list_symbols()` for the configured market and retains the returned order
   in `raw_symbols`.
2. Dispatches each raw symbol through `infer_spot_info` / `infer_um_info` / `infer_cm_info`
   according to `trade_type`.
3. Splits the results into `inferred` and `unmatched` (raw strings that failed inference).
4. If `symbol_filter` is set, further splits `inferred` into `matched` and `filtered_out`
   via `symbol_filter.matches()`. Otherwise `matched == inferred` and `filtered_out` is empty.

## `ListSymbolsResult`

Structured return type for `ArchiveListSymbolsWorkflow.run()`. Declared as a `slots=True`
dataclass in the workflow module because it is the workflow's result shape, not a general
shared type.

| Field | Type | Description |
|-------|------|-------------|
| `matched` | `list[SymbolInfo]` | Inferred symbols that passed the filter (or all inferred symbols when no filter is set). |
| `unmatched` | `list[str]` | Raw symbols that could not be parsed by the per-market inference function. |
| `filtered_out` | `list[SymbolInfo]` | Inferred symbols rejected by the filter. Always empty when no filter is set. |
| `raw_symbols` | `list[str]` | Every symbol returned by the archive in listing order, including uninferable and filtered-out symbols. Defaults to an empty list when constructing results manually. |

Input order is preserved within each bucket. `raw_symbols` preserves the full interleaving
across buckets so unfiltered CLI output can print every directory in archive order.

## `ArchiveListFilesWorkflow`

Lists archive files for one or more symbols concurrently while preserving caller
input order and isolating per-symbol failures so that one bad symbol does not abort
the entire batch.

```python
from binance_datatool.workflow import (
    ArchiveListFilesWorkflow,
    ListFilesResult,
)
from binance_datatool.common import DataFrequency, DataType, TradeType

workflow = ArchiveListFilesWorkflow(
    trade_type=TradeType.um,
    data_freq=DataFrequency.daily,
    data_type=DataType.klines,
    symbols=["BTCUSDT", "ETHUSDT"],
    interval="1m",
)
result: ListFilesResult = await workflow.run()
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `trade_type` | *(required)* | Market segment to query. |
| `data_freq` | *(required)* | Partition frequency. |
| `data_type` | *(required)* | Dataset type. |
| `symbols` | *(required)* | Sequence of symbols to list. Caller order is preserved. |
| `interval` | `None` | Kline interval directory. Required when `data_type.has_interval_layer` is `True`; must be `None` otherwise. |
| `progress_bar` | `False` | When `True`, display an interactive tqdm progress bar on stderr via the shared progress-reporting framework. When `False`, emit sampled log lines at INFO level. See [`common.progress`](../common/progress.md). |
| `client` | `None` | Optional pre-configured `ArchiveClient`. A default client is created when omitted. |

The constructor validates the `interval` vs `data_type.has_interval_layer` invariant
and raises `ValueError` on mismatch. This is the workflow-layer line of defense in
the three-layer interval consistency check (CLI / Workflow / Client).

### `run()`

```python
async def run(self) -> ListFilesResult
```

1. Delegates to `ArchiveClient.list_symbol_files_batch()` with the configured
   market, symbols, interval, and progress bar settings. The batch method
   opens a single shared `aiohttp.ClientSession` and concurrently lists every
   symbol via `asyncio.as_completed`.
2. Wraps each `(files, error)` tuple from the batch result into a
   `SymbolListFilesResult`, preserving caller input order.

Returns a `ListFilesResult` that always covers every requested symbol.

## `SymbolListFilesResult`

Per-symbol entry inside `ListFilesResult.per_symbol`. A successful listing of an
empty directory is represented by `files == []` with `error is None`; this is
**distinct** from a failed listing, which also carries an empty `files` list but sets
`error` to a non-empty description of the failure.

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | `str` | The symbol this entry describes, normalized to uppercase by the CLI. |
| `files` | `list[ArchiveFile]` | Files found under the symbol directory. Empty on both success-with-empty-directory and failure. |
| `error` | `str \| None` | `None` on success; a text description of the failure otherwise. |

## `ListFilesResult`

Aggregate result for `ArchiveListFilesWorkflow.run()`.

| Field / Property | Type | Description |
|------------------|------|-------------|
| `per_symbol` | `list[SymbolListFilesResult]` | One entry per requested symbol, in caller-provided input order. |
| `requested_symbols` | `int` *(property)* | Number of requested symbols. |
| `has_failures` | `bool` *(property)* | `True` when any `per_symbol` entry has a non-`None` `error`. Used by the CLI to set exit code 2. |
| `failed_symbols` | `int` *(property)* | Number of symbols whose listing failed. |
| `successful_symbols` | `int` *(property)* | Number of symbols that listed successfully. |
| `total_remote_files` | `int` *(property)* | Total number of successfully listed remote files across all symbols. |

## `ArchiveDownloadWorkflow`

Diffs remote archive listings against local files and optionally downloads new or
updated files via aria2c.

```python
from pathlib import Path

from binance_datatool.workflow import (
    ArchiveDownloadWorkflow,
    DiffResult,
    DownloadResult,
)
from binance_datatool.common import DataFrequency, DataType, TradeType

workflow = ArchiveDownloadWorkflow(
    trade_type=TradeType.um,
    data_freq=DataFrequency.monthly,
    data_type=DataType.funding_rate,
    symbols=["BTCUSDT"],
    archive_home=Path("/data/binance_archive"),
)
result = await workflow.run()
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `trade_type` | *(required)* | Market segment to query. |
| `data_freq` | *(required)* | Partition frequency. |
| `data_type` | *(required)* | Dataset type. |
| `symbols` | *(required)* | Symbols to download, preserving caller order. |
| `archive_home` | *(required)* | Root directory for local archive data storage. |
| `interval` | `None` | Kline interval directory. Required for kline-class data types. |
| `dry_run` | `False` | When `True`, compute the diff without downloading. |
| `inherit_aria2_proxy` | `False` | Whether aria2c should inherit proxy env vars. |
| `concurrency` | `64` | Concurrent aria2 downloads. Values below 1 raise `ValueError`. |
| `progress_bar` | `False` | When `True`, display an interactive tqdm progress bar on stderr. When `False`, emit sampled log lines at INFO level. See [`common.progress`](../common/progress.md). |
| `client` | `None` | Optional pre-configured `ArchiveClient`. |
| `download_func` | `None` | Optional download callable for dependency injection. Receives `requests`, `inherit_proxy`, `concurrency`, and `progress_bar`. Defaults to `download_archive_files`. |

### Download comparison

```python
async def run(self) -> DiffResult | DownloadResult
```

1. Delegates to `ArchiveListFilesWorkflow` to fetch remote file metadata for all
   requested symbols concurrently.
2. Computes a diff by comparing each remote file against
   `archive_home / Path(remote.key)`. A file is skipped only when its local copy exists,
   its size matches the remote listing, it has no sibling `.aria2` control file, and
   `local_mtime >= remote_last_modified`; otherwise it is classified as `"new"`
   or `"updated"`.
3. In dry-run mode, returns a `DiffResult` immediately.
4. Otherwise, invalidates stale `.verified` markers for updated zip/checksum files,
   deletes stale local copies of updated files, then downloads via
   `download_archive_files` with per-file retry and optional progress reporting.

Returns `DiffResult` when `dry_run=True`, otherwise `DownloadResult`. All file counts
refer to individual archive objects, including ZIP and checksum files. Successful transfer
and download skips do not establish SHA256 verification.

## `DiffEntry`

One file selected for download.

| Field / Property | Type | Description |
|------------------|------|-------------|
| `remote` | `ArchiveFile` | Remote file metadata. |
| `local_path` | `Path` | Target local path at `archive_home / Path(remote.key)`. |
| `reason` | `Literal["new", "updated"]` | Why this file was selected. |
| `url` | `str` *(property)* | Full download URL built from `S3_DOWNLOAD_PREFIX` + key. |

## `DiffResult`

Returned by `ArchiveDownloadWorkflow.run()` in dry-run mode.

| Field / Property | Type | Description |
|------------------|------|-------------|
| `to_download` | `list[DiffEntry]` | Files selected for download. |
| `skipped` | `int` | Files already up to date locally. |
| `total_remote` | `int` | Total remote files listed. |
| `listing_errors` | `list[SymbolListingError]` | Per-symbol listing failures. |
| `listing_failed_symbols` | `int` *(property)* | Count of failed symbol listings. |

## `DownloadResult`

Returned by `ArchiveDownloadWorkflow.run()` after a real download.

| Field / Property | Type | Description |
|------------------|------|-------------|
| `total_remote` | `int` | Total remote files listed. |
| `skipped` | `int` | Files already up to date locally. |
| `downloaded` | `int` | Files successfully downloaded. |
| `failed` | `int` | Files that failed after all retries. |
| `listing_errors` | `list[SymbolListingError]` | Per-symbol listing failures. |
| `listing_failed_symbols` | `int` *(property)* | Count of failed symbol listings. |

## `SymbolListingError`

Structured per-symbol listing error, used by both `DiffResult` and `DownloadResult`.

| Field | Type | Description |
|-------|------|-------------|
| `symbol` | `str` | The symbol whose listing failed. |
| `error` | `str` | Text description of the failure. |

## `ArchiveVerifyWorkflow`

Scans local archive directories, classifies zip files into verify / skip / orphan
buckets, and optionally verifies SHA256 checksums in parallel using a process pool.

```python
from pathlib import Path

from binance_datatool.workflow import (
    ArchiveVerifyWorkflow,
    VerifyDiffResult,
    VerifyResult,
)
from binance_datatool.common import DataFrequency, DataType, TradeType

workflow = ArchiveVerifyWorkflow(
    trade_type=TradeType.um,
    data_freq=DataFrequency.daily,
    data_type=DataType.klines,
    symbols=["BTCUSDT"],
    archive_home=Path("/data/binance_archive"),
    interval="1m",
)
result = workflow.run()
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `trade_type` | *(required)* | Market segment. |
| `data_freq` | *(required)* | Partition frequency. |
| `data_type` | *(required)* | Dataset type. |
| `symbols` | *(required)* | Symbols to verify, preserving caller order. |
| `archive_home` | *(required)* | Root directory for local archive data storage. |
| `interval` | `None` | Kline interval directory. Required for kline-class data types. |
| `keep_failed` | `False` | When `True`, retain failed zip and checksum files instead of deleting them. |
| `dry_run` | `False` | When `True`, scan and classify files without verifying or mutating the filesystem. |
| `n_workers` | `None` | Process pool size. Defaults to `max(1, cpu_count - 2)`. |
| `progress_bar` | `False` | When `True`, display an interactive tqdm progress bar on stderr. When `False`, emit sampled log lines at INFO level. See [`common.progress`](../common/progress.md). |

### `run()`

```python
def run(self) -> VerifyDiffResult | VerifyResult
```

This is a **synchronous** method (no `async`) because the verify workflow is purely
local I/O and CPU work — no network access is needed.

1. **Scan** — walks each symbol's local directory under
   `archive_home/data/{s3_path}/{freq}/{type}/{symbol}[/{interval}]` in caller symbol
   order, using one `os.scandir` pass per directory and directory-entry metadata
   for freshness checks. Classifies each `.zip` file as pending
   verification, already verified (valid timestamped marker), orphan zip (missing
   `.CHECKSUM` sibling), or orphan checksum (missing `.zip` sibling). Each path
   list is sorted within its symbol; missing directories contribute no work.
   Scans run serially and report progress via the shared progress-reporting framework.
   The [scan benchmark](../../../benchmarks/README.md) records classification checks,
   repeated timings, and the serial-versus-threaded comparison.
2. In **dry-run mode**, returns a `VerifyDiffResult` immediately.
3. **Orphan cleanup** — orphan zips have their markers cleared (zip file is kept);
   orphan checksums and their markers are deleted.
4. **Parallel verification** — submits `verify_single_file` tasks to a
   `ProcessPoolExecutor` with `spawn` context. Reports progress via the shared
   progress-reporting framework.
5. **Post-verify** — pre-collects existing markers per directory (via
   `collect_markers_by_zip`) to avoid per-file glob calls, then for each result:
   clears old markers, writes a fresh timestamped marker on pass, or deletes the
   zip + checksum on failure (unless `keep_failed`).

Returns `VerifyDiffResult` when `dry_run=True`, otherwise `VerifyResult`.

### Timestamped marker protocol

Verified files are tracked by marker files named `{zip_name}.{ts}.verified`, where
`ts = max(now, ceil(max(zip_mtime, checksum_mtime)))`. A marker is valid when
`max(ts_markers) >= ceil(max(zip_mtime, checksum_mtime))`. Legacy markers without a
timestamp (`file.zip.verified`) are treated as invalid and force re-verification.

A cached skip performs no new SHA256 comparison. This relies on local ZIP and checksum
modification times: a content change that preserves them is not detected by the cache.
Download updates invalidate the affected ZIP markers before transfer; a failed verification
clears markers even when `keep_failed=True`.

## `VerifyDiffResult`

Returned by `ArchiveVerifyWorkflow.run()` in dry-run mode.

All path lists preserve caller symbol order and sort paths within each symbol.
The CLI prints `to_verify` paths in that same order for `verify --dry-run`.

| Field / Property | Type | Description |
|------------------|------|-------------|
| `to_verify` | `list[Path]` | Zip files pending SHA256 verification. |
| `skipped` | `int` | Zip files with a valid timestamped marker. |
| `orphan_zips` | `list[Path]` | Zip files without a sibling `.CHECKSUM`. |
| `orphan_checksums` | `list[Path]` | `.CHECKSUM` files without a sibling `.zip`. |
| `total_zips` | `int` *(property)* | `len(to_verify) + skipped + len(orphan_zips)`. |

## `VerifyResult`

Returned by `ArchiveVerifyWorkflow.run()` after a real verify run.

| Field / Property | Type | Description |
|------------------|------|-------------|
| `skipped` | `int` | Zip files accepted through cached verification (not hashed in this run). |
| `verified` | `int` | Zip files that passed SHA256 comparison in this run. |
| `orphan_zips` | `int` | Orphan zips whose markers were cleared. |
| `orphan_checksums` | `int` | Orphan checksums that were deleted. |
| `failed_details` | `dict[Path, str]` | Failed zip paths mapped to failure descriptions. |
| `failed` | `int` *(property)* | `len(failed_details)`. |
| `total_zips` | `int` *(property)* | `skipped + verified + failed + orphan_zips`. |

---

See also: [Archive package](../archive/) | [Archive client module](../archive/client.md) | [CLI commands](../cli/archive.md) | [Architecture](../../architecture.md)
