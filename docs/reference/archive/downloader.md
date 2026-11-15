# binance_datatool.archive.downloader

Aria2-backed archive download helpers.

The package-level `binance_datatool.archive` re-exports every public
downloader type and function, so most imports can use:

```python
from binance_datatool.archive import DownloadRequest, download_archive_files
```

## `DownloadRequest`

Immutable `@dataclass(slots=True, frozen=True)` describing a single
direct-download task.

| Field | Type | Description |
|-------|------|-------------|
| `url` | `str` | Full download URL built from `S3_DOWNLOAD_PREFIX` plus the archive key. |
| `local_path` | `Path` | Target filesystem path. Parent directories are created automatically. |

## `download_archive_files()`

```python
from binance_datatool.archive import DownloadRequest, download_archive_files

result = download_archive_files(
    requests,
    inherit_proxy=False,
    batch_size=512,
    concurrency=64,
    max_tries=3,
    progress_bar=False,
    stdout_to_stderr=False,
)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `requests` | *(required)* | Sequence of `DownloadRequest` items to download. |
| `inherit_proxy` | *(required)* | When `False`, proxy env vars (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`, etc.) are stripped from the aria2c subprocess environment. When `True`, aria2c inherits the caller's proxy settings. |
| `batch_size` | `512` | Maximum files per aria2c invocation, capped at 512 to bound progress gaps. Must be at least 1. |
| `concurrency` | `64` | Concurrent aria2 downloads (`-j`). Must be at least 1. |
| `max_tries` | `3` | Maximum retry rounds for incomplete files. |
| `progress_bar` | `False` | When `True`, display an interactive tqdm progress bar on stderr via the shared progress-reporting framework. When `False`, emit sampled log lines at INFO level. See [`common.progress`](../common/progress.md). |
| `stdout_to_stderr` | `False` | When `True`, capture child stdout and forward it to stderr after each batch. The JSON CLI selects this through the workflow output-routing option. The default retains inherited subprocess stdout. |

Returns an `Aria2DownloadResult`. Invalid `concurrency` or `batch_size` raises `ValueError`.
A nonempty request sequence resolves `aria2c` before creating directories or input files;
unavailable tooling raises `Aria2NotFoundError`. An empty sequence does not require aria2.

Every completed batch emits progress: one success event, or separate success/failure
events for a partial batch. Download logs use `log_interval=1` so large totals cannot
suppress these updates; the bar advances on the same events.

Aria2 is invoked with `--allow-overwrite=true` and
`--auto-file-renaming=false` so updated files replace existing ones instead of
producing `.1.zip`-style renamed duplicates.

### Per-file retry semantics

Downloads use **per-file retry granularity**. After each aria2 batch
completes, individual files are checked for completeness: a file is
considered complete when it exists on disk and has no leftover `.aria2`
control file (which indicates a partial download). Only files that are
still missing or incomplete are retried in subsequent rounds. This avoids
re-downloading already-completed files within a batch that partially failed.

## `prepare_archive_downloader()`

```python
from binance_datatool.archive import prepare_archive_downloader

# Resolve before making archive changes; execution reuses this executable path.
download = prepare_archive_downloader(stdout_to_stderr=True)
result = download(requests, inherit_proxy=False, concurrency=64)
```

Resolves `aria2c` immediately and returns a callable accepting the same arguments as
`download_archive_files`. `stdout_to_stderr` defaults to `False` and sets the returned
callable's default output routing. Missing tooling raises `Aria2NotFoundError` without
writing to the archive. The workflow prepares only nonempty built-in transfer plans.

Preparation reuses the resolved path during execution. It does not roll back later transfer
failures or prevent an external process from removing the executable after resolution.

## `Aria2DownloadResult`

| Field / Property | Type | Description |
|------------------|------|-------------|
| `requested` | `int` | Total number of files requested. |
| `failed_requests` | `list[DownloadRequest]` | Requests that still failed after all retries. |
| `succeeded` | `int` *(property)* | `requested - len(failed_requests)`. |

## `Aria2NotFoundError`

Custom `FileNotFoundError` subclass raised when `aria2c` is not available in
`PATH`.

---

See also: [Archive package](README.md) | [Workflow](../workflow/) | [S3 protocol](s3-protocol.md) | [Progress reporting](../common/progress.md)
