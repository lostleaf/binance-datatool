# binance_datatool.common.logging

Shared `loguru` configuration helper for CLI entry points.

```python
from binance_datatool.common import configure_cli_logging

configure_cli_logging(verbosity=1)  # 0 = WARNING, 1 = INFO, 2+ = DEBUG
```

`configure_cli_logging(verbosity: int) -> None` resets `loguru` and installs a
single `stderr` sink with a level chosen from the verbosity level. The sink
writes through `tqdm.write()`, which clears and redraws an active progress bar
around each log message and writes normally when no bar is active. All levels
use the same format:

| `verbosity` | `loguru` level |
|-------------|----------------|
| `0` | `WARNING` |
| `1` | `INFO` |
| `2` or more | `DEBUG` |

**Format** (all levels):

```
{time:YYYY-MM-DD HH:mm:ss} | {level} | {module} - {message}
```

The timestamp includes the date, and the module name identifies the source
without cluttering output with file paths or line numbers.

The sink uses `colorize=sys.stderr.isatty()` so ANSI colour escapes appear on
interactive terminals but are stripped from logs redirected to files or pipes.
Level names are emitted in uppercase (`INFO`, `ERROR`, `DEBUG`, `WARNING`),
matching the conventions used by `pip`, the stdlib `logging` module, and the
default `loguru` formatter.

This function is called by the root `binance-datatool` Typer callback before any
sub-command runs; see [CLI — Root Callback](../cli/README.md#root-callback).
It is introduced as a shared helper so future CLI entry points (for example a
planned `bmds`) can reuse the same configuration without duplication.

---

See also: [CLI overview](../cli/) | [Architecture](../../architecture.md)
