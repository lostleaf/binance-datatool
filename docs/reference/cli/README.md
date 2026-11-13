# binance_datatool.cli

Typer CLI application. The entry point is `binance_datatool.cli:app`, exposed as the `binance-datatool`
console script via `pyproject.toml`.

## App Structure

```
binance-datatool [-v | -vv] [--archive-home PATH]   # Root Typer app with shared options
├── list-symbols                     # Command
├── list-files                       # Command
├── download                         # Command
└── verify                           # Command
```

## Root Callback

The root `binance-datatool` app defines a callback that runs before any sub-command:

| Flag | Effect |
|------|--------|
| *(default)* | `loguru` level `WARNING`, unified `date \| level \| module - message` format |
| `-v` | `loguru` level `INFO`, same unified format |
| `-vv` | `loguru` level `DEBUG`, same unified format |
| `--archive-home` | Override the archive data directory. Stored in `ctx.obj["archive_home_override"]` and consumed by commands that need local archive storage (`download`, `verify`). See [`common.path`](../common/path.md) for resolution priority. |

`-v` is `count`-based — pass `-v -v` or `-vv` for DEBUG. All CLI logging is written
to `stderr` via `configure_cli_logging()` from [`common.logging`](../common/logging.md),
so sub-command stdout remains safe to pipe.

## Root Commands

| Command Set | Description | Reference |
|-------------|-------------|-----------|
| Root data commands | Remote archive listing and download, local-only verification | [command reference](archive.md) |

---

See also: [Architecture](../../architecture.md) |
[Extending the Project — Adding a New CLI Command](../../extending.md#adding-a-new-cli-command)
