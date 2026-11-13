# binance_datatool.common.path

Archive layout, interval validation, and local archive-home resolution.

## `archive_path_parts()`

```python
from pathlib import Path

from binance_datatool.common import DataFrequency, DataType, TradeType
from binance_datatool.common.path import archive_path_parts

archive_home = Path("/data/binance_archive")
parts = archive_path_parts(
    TradeType.um, DataFrequency.daily, DataType.klines, "BTCUSDT", "1m"
)
# ("data", "futures/um", "daily", "klines", "BTCUSDT", "1m")
remote_prefix = "/".join(parts) + "/"
local_directory = archive_home.joinpath(*parts)
```

Owns the archive directory layout used by remote listings, local symbol directories,
and CLI relative-path formatting. Omit `symbol` and `interval` to obtain the dataset
prefix. It constructs components without validating interval compatibility or performing I/O.

## `validate_interval()`

```python
from binance_datatool.common import DataType
from binance_datatool.common.path import validate_interval

validate_interval(DataType.klines, "1m")
validate_interval(DataType.funding_rate, None)
```

Raises `ValueError` when a kline-class dataset lacks an interval or a non-kline dataset
receives one. This is the shared implementation used at the existing CLI, workflow,
and archive-client validation boundaries before I/O. The CLI converts the error to an
`--interval` usage error with exit status 2. This rule checks presence, not interval values.

Both helpers are imported from this module rather than re-exported from
`binance_datatool.common`.

## `resolve_archive_home()`

```python
from binance_datatool.common import resolve_archive_home

home = resolve_archive_home()                     # from $BINANCE_DATATOOL_ARCHIVE_HOME
home = resolve_archive_home("/custom/path")      # explicit override
```

Resolves the archive home directory using the following priority:

| Priority | Source | Description |
|----------|--------|-------------|
| 1 | `override` argument | CLI-provided `--archive-home` value. |
| 2 | `$BINANCE_DATATOOL_ARCHIVE_HOME` env var | Environment variable fallback. |
| 3 | *(none)* | Raises `ArchiveHomeNotConfiguredError`. |

Both the override and the env-var value are expanded via `Path.expanduser()`.

`archive_home` is the local Binance archive root itself, so local paths resolve
directly under `archive_home / "data" / ...`.

## `ArchiveHomeNotConfiguredError`

Custom `ValueError` subclass raised when neither a CLI override nor the
`BINANCE_DATATOOL_ARCHIVE_HOME` environment variable is set. The error message
includes remediation advice pointing to `--archive-home` and the environment
variable.

## `ARCHIVE_HOME_ENV_VAR`

String constant `"BINANCE_DATATOOL_ARCHIVE_HOME"` — the environment variable
name used by `resolve_archive_home()`.

```python
from binance_datatool.common.path import ARCHIVE_HOME_ENV_VAR
```

This constant is documented here but is not re-exported from
`binance_datatool.common`.

---

See also: [constants](constants.md) | [CLI overview](../cli/) | [Architecture](../../architecture.md)
