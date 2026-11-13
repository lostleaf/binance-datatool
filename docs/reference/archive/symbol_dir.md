# binance_datatool.archive.symbol_dir

Local symbol archive directory helpers. Used internally by the download and
verify workflows to manage on-disk layout, verification markers, and orphan
cleanup.

The package-level `binance_datatool.archive` re-exports
`SymbolArchiveDir` and `create_symbol_archive_dir`:

```python
from binance_datatool.archive import SymbolArchiveDir, create_symbol_archive_dir
```

## `SymbolArchiveDir`

Represents one local symbol archive directory and provides methods for
marker management, scanning, and cleanup.

```python
from binance_datatool.archive import create_symbol_archive_dir
from binance_datatool.common import DataFrequency, DataType, TradeType

symbol_dir = create_symbol_archive_dir(
    archive_home=Path("/data/binance_archive"),
    trade_type=TradeType.um,
    data_freq=DataFrequency.daily,
    data_type=DataType.klines,
    symbol="BTCUSDT",
    interval="1m",
)
```

**Attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `path` | `Path` | Absolute path to the symbol directory on disk. |

**Public methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `zip_path` | `(zip_name) -> Path` | Return the local path for a zip file. |
| `checksum_path` | `(zip_name) -> Path` | Return the local checksum path for a zip file. |
| `clear_markers` | `(zip_name) -> None` | Delete all verification markers for one zip file. |
| `clear_markers_many` | `(zip_names: Collection[str]) -> None` | Delete verification markers for multiple zip files. |
| `max_source_mtime` | `(zip_name) -> int` | Return the normalized freshness timestamp (`ceil(max(zip_mtime, checksum_mtime))`). |
| `is_marker_fresh` | `(zip_name, timestamps: list[int]) -> bool` | Return `True` when any marker timestamp is fresh relative to the source files. |
| `write_marker` | `(zip_name) -> None` | Create a fresh timestamped `.verified` marker. |
| `discard_failed` | `(zip_name) -> None` | Delete a failed zip and its sibling checksum file. |
| `remove_orphan_checksum` | `(checksum_name) -> None` | Delete an orphan checksum file. |
| `scan` | `() -> SymbolScanResult` | Scan the directory and classify local verify work (see below). |

### `scan()`

Reads the symbol directory once with `os.scandir`, classifying entry names and
using directory-entry metadata for marker freshness checks. Path lists are sorted
by filename, and a missing directory returns an empty result. Classifies local
files into these buckets:

| Bucket | Description |
|--------|-------------|
| `to_verify` | Zip files that need SHA256 verification (no fresh marker). |
| `skipped` | Zip files with a fresh timestamped marker. |
| `orphan_zips` | Zip files with no sibling `.CHECKSUM`. |
| `orphan_checksums` | `.CHECKSUM` files with no sibling `.zip`. |

Returns a `SymbolScanResult` dataclass (module-internal — not re-exported
from the package surface).

## `create_symbol_archive_dir()`

Factory function that builds the local directory path for one symbol and
returns a `SymbolArchiveDir` wrapping it.

```python
create_symbol_archive_dir(
    archive_home: Path,
    trade_type: TradeType,
    data_freq: DataFrequency,
    data_type: DataType,
    symbol: str,
    interval: str | None = None,
) -> SymbolArchiveDir
```

The resolved path follows the pattern:

```
archive_home/data/{trade_type.s3_path}/{data_freq}/{data_type}/{symbol}[/{interval}]
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `archive_home` | *(required)* | Root directory for local archive data storage. |
| `trade_type` | *(required)* | Market segment. |
| `data_freq` | *(required)* | Partition frequency. |
| `data_type` | *(required)* | Dataset type. |
| `symbol` | *(required)* | Symbol name. |
| `interval` | `None` | Kline interval directory. Appended when not `None`. |

## `collect_markers_by_zip()`

Module-level helper that collects all verification marker files for a list
of zip paths, grouped by their parent zip. Used by the verify workflow to
pre-collect markers and avoid per-file glob calls when applying verify results.

```python
from binance_datatool.archive.symbol_dir import collect_markers_by_zip

markers_by_zip = collect_markers_by_zip(zip_paths)
# {Path(".../BTCUSDT-1m-2024-01-01.zip"): [Path(".../BTCUSDT-1m-2024-01-01.zip.1234.verified")]}
```

---

See also: [Workflow](../workflow/) | [Archive package](README.md) | [Architecture](../../architecture.md)
