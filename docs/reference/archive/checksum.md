# binance_datatool.archive.checksum

SHA256 verification helpers for local archive files.

The package-level `binance_datatool.archive` re-exports every public
checksum helper, so most imports can use:

```python
from binance_datatool.archive import calc_sha256, verify_single_file
```

## `VerifyFileResult`

Mutable `@dataclass(slots=True)` describing the verification outcome for a
single zip file.

| Field | Type | Description |
|-------|------|-------------|
| `zip_path` | `Path` | Path to the zip file that was verified. |
| `passed` | `bool` | `True` when the computed SHA256 matches the expected checksum. |
| `detail` | `str` | Empty on success; describes the failure otherwise, such as `"checksum mismatch"` or an exception message for I/O errors. |

## `calc_sha256()`

```python
from binance_datatool.archive import calc_sha256

hex_digest = calc_sha256(file_path)
```

Computes the SHA256 hex digest of a file using `hashlib.file_digest()`.

## `read_expected_checksum()`

```python
from binance_datatool.archive import read_expected_checksum

expected = read_expected_checksum(zip_path)
```

Reads the first whitespace-delimited token from the sibling `.CHECKSUM` file
(`{zip_path}.CHECKSUM`). The token must contain exactly 64 hexadecimal characters.
Raises `FileNotFoundError` when the checksum file does not exist and `ValueError`
identifying the invalid checksum file when its contents are empty, contain an
invalid SHA256 token, or cannot be decoded as UTF-8.

## `verify_single_file()`

```python
from binance_datatool.archive import verify_single_file

result = verify_single_file(zip_path)
```

Verifies a single zip file against its sibling checksum file. Returns a
`VerifyFileResult` and never raises. Exceptions during checksum reading or
SHA256 computation are caught and reported via `result.detail`.

This function is the unit of work submitted to `ProcessPoolExecutor` by
`ArchiveVerifyWorkflow`.

---

See also: [Archive package](README.md) | [Downloader helpers](downloader.md) | [Workflow](../workflow/)
