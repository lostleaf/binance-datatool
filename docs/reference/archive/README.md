# binance_datatool.archive

Remote access to data.binance.vision and local archive storage, checksum, and marker helpers.

Most user-facing imports can prefer the package-level re-export surface:

```python
from binance_datatool.archive import (
    ArchiveClient,
    DownloadRequest,
    SymbolArchiveDir,
    download_archive_files,
    verify_single_file,
)
```

Use the defining submodule only when you want narrower imports or module-specific
details.

## Package Structure

| Module | Description |
|--------|-------------|
| [client](client.md) | `ArchiveClient`, `ArchiveFile`, and `list_symbols()`. |
| [downloader](downloader.md) | Aria2-backed batch download helpers and result types. |
| [checksum](checksum.md) | SHA256 checksum helpers and `VerifyFileResult`. |
| [symbol_dir](symbol_dir.md) | Local symbol archive directory helpers and marker management. |
| [S3 protocol](s3-protocol.md) | XML listing request format, pagination, retry, and proxy behavior. |
| [Path structure](path-structure.md) | S3 directory hierarchy, data type availability, and file naming conventions. |

## Package Re-exports

| Source module | Re-exported names |
|---------------|-------------------|
| [`client`](client.md) | `ArchiveClient`, `ArchiveFile`, `SymbolListingResult`, `list_symbols` |
| [`downloader`](downloader.md) | `DownloadRequest`, `Aria2DownloadResult`, `Aria2NotFoundError`, `download_archive_files` |
| [`checksum`](checksum.md) | `VerifyFileResult`, `calc_sha256`, `read_expected_checksum`, `verify_single_file` |
| [`symbol_dir`](symbol_dir.md) | `SymbolArchiveDir`, `create_symbol_archive_dir` |

Internal helpers such as `_build_prefix()` and `_find_aria2c()` are intentionally
left out of the public reference surface.

---

See also: [Workflow](../workflow/) | [CLI overview](../cli/) | [Architecture](../../architecture.md)
