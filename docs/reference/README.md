# Module Reference

Reference documentation for the importable modules and CLI packages in
`binance_datatool`.

## Common

Most user-facing imports should prefer the package-level
`binance_datatool.common` re-export surface when it exposes the name you need:

```python
from binance_datatool.common import DataFrequency, DataType, TradeType, resolve_archive_home
```

That package currently re-exports the shared enums, symbol-info dataclasses,
symbol filters, symbol inference helpers, CLI logging helper, archive-home
resolver, and the main S3 / leverage / stablecoin constants. Names that are documented but not
re-exported from `binance_datatool.common` should be imported from their
defining module, for example:

```python
from binance_datatool.common.constants import QUOTE_BASE_EXCLUDES
from binance_datatool.common.path import ARCHIVE_HOME_ENV_VAR
```

| Module | Description |
|--------|-------------|
| [common.constants](common/constants.md) | S3 settings, quote assets, stablecoins, leverage rules. |
| [common.enums](common/enums.md) | TradeType, DataFrequency, DataType, ContractType. |
| [common.filter](common/filter.md) | Typed symbol filters and `build_symbol_filter()`. |
| [common.types](common/types.md) | SymbolInfoBase and per-market symbol info dataclasses. |
| [common.logging](common/logging.md) | `configure_cli_logging` helper for CLI entry points. |
| [common.path](common/path.md) | Archive layout, interval validation, and archive-home resolution. |
| [common.symbols](common/symbols.md) | Symbol inference functions and quote parsing rules. |
| [common.progress](common/progress.md) | Progress-reporting framework (`ProgressEvent`, `ProgressReporter`, `make_reporter`). |

## Archive

| Module | Description |
|--------|-------------|
| [archive](archive/) | Package index and re-export surface for archive access helpers. |
| [archive.client](archive/client.md) | S3 listing client, `ArchiveFile`, and `list_symbols()`. |
| [archive.downloader](archive/downloader.md) | Aria2-backed batch download helpers and result types. |
| [archive.checksum](archive/checksum.md) | SHA256 verification helpers and `VerifyFileResult`. |
| [archive.symbol_dir](archive/symbol_dir.md) | Local symbol archive directory helpers and marker management. |
| [archive.s3-protocol](archive/s3-protocol.md) | S3 XML listing protocol, pagination, retry, and proxy. |
| [workflow](workflow/README.md) | Business logic orchestration for archive workflows. |
| [cli](cli/) | Typer CLI overview, verbosity, and sub-command index. |
| [cli commands](cli/archive.md) | Archive commands (`list-symbols`, `list-files`, `download`, `verify`). |

---

See also: [Architecture](../architecture.md) | [Extending the Project](../extending.md)
