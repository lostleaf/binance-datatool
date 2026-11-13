# binance_datatool.archive.client

S3 listing client for data.binance.vision.

The package-level `binance_datatool.archive` re-exports `ArchiveClient`,
`ArchiveFile`, `SymbolListingResult`, and `list_symbols`, so most imports can use the package surface:

```python
from binance_datatool.archive import ArchiveClient, SymbolListingResult, list_symbols
```

## `ArchiveClient`

The main class for communicating with the Binance public data archive.

```python
from binance_datatool.archive import ArchiveClient

client = ArchiveClient(timeout_seconds=15, trust_env=True)
```

| Parameter | Default | Description |
|-----------|---------|-------------|
| `timeout_seconds` | `15` | Total timeout in seconds per HTTP request. |
| `trust_env` | `True` | Read proxy settings from environment variables (`http_proxy`, etc.). |

**Public methods:**

| Method | Signature | Description |
|--------|-----------|-------------|
| `list_dir` | `async (session, prefix) -> list[str]` | List child prefixes under an S3 prefix, handling pagination automatically. |
| `list_files_in_dir` | `async (session, prefix) -> list[ArchiveFile]` | List files directly under an S3 prefix without recursion, handling pagination automatically. |
| `list_symbols` | `async (trade_type, data_freq, data_type) -> list[str]` | List sorted symbol names for a given archive path. Creates its own session internally. |
| `list_symbol_files` | `async (trade_type, data_freq, data_type, symbol, interval=None, *, session=None) -> list[ArchiveFile]` | Build the S3 prefix and list every file for one symbol. Reuses a caller-supplied session when provided; otherwise creates and closes a short-lived one internally. Raises `ValueError` when `interval` does not match `data_type.has_interval_layer`. |
| `list_symbol_files_batch` | `async (trade_type, data_freq, data_type, symbols, interval=None, *, progress_bar=False) -> dict[str, SymbolListingResult]` | List files for multiple symbols concurrently via a shared session. Returns an ordered mapping from each symbol to `(files, error)`. |

`list_dir()` and `list_files_in_dir()` share one pagination implementation.
The higher-level methods build archive prefixes for you. Listing pages are parsed
with the standard-library `xml.etree.ElementTree` module, accepting the S3 XML
namespace and unqualified XML. Empty pages return empty lists; single and repeated
entries preserve response order before `list_symbols()` sorts the symbol names.

## `ArchiveFile`

Immutable metadata record for a single file on the Binance public data archive.
Returned by `ArchiveClient.list_files_in_dir()` and
`ArchiveClient.list_symbol_files()`.

```python
from binance_datatool.archive import ArchiveFile
```

| Field | Type | Description |
|-------|------|-------------|
| `key` | `str` | Full S3 object key, e.g. `data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-03.zip`. |
| `size` | `int` | File size in bytes, parsed from the S3 `Size` field. |
| `last_modified` | `datetime` | Last-modified timestamp, always tz-aware in UTC. Parsed from the S3 `LastModified` ISO 8601 value. |

Declared as `@dataclass(slots=True, frozen=True)`, so instances are hashable and
immutable.

## `list_symbols()` (module-level convenience function)

```python
from binance_datatool.archive import list_symbols

symbols = await list_symbols(TradeType.spot, DataFrequency.daily, DataType.klines)
```

Creates a temporary `ArchiveClient` and delegates to `ArchiveClient.list_symbols()`.

## `SymbolListingResult` (type alias)

```python
SymbolListingResult: TypeAlias = tuple[list[ArchiveFile], str | None]
```

Per-symbol outcome from `ArchiveClient.list_symbol_files_batch()`. The first
element is the file list (empty on both success-with-empty-directory and
failure); the second is `None` on success or a text error description on
failure.

For S3 XML protocol details such as request format, pagination, retry, and proxy
behavior, see [S3 Listing Protocol](s3-protocol.md).

---

See also: [Archive package](README.md) | [Workflow](../workflow/) | [Architecture](../../architecture.md)
