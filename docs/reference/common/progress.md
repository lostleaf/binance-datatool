# binance_datatool.common.progress

Shared progress-reporting helpers used by archive workflows and the downloader.

```python
from binance_datatool.common.progress import make_reporter, ProgressEvent
```

This module is **not** re-exported from `binance_datatool.common` — import directly
from the defining module.

## `ProgressEvent`

Immutable payload for a single progress tick.

```python
from binance_datatool.common.progress import ProgressEvent

event = ProgressEvent(name="BTCUSDT", ok=True, count=1)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | *(required)* | Short label for the item that just completed (e.g. a symbol name or batch label). |
| `ok` | `bool` | *(required)* | Whether the item succeeded. |
| `count` | `int` | `1` | Number of logical units this event represents. |

Declared as `@dataclass(slots=True, frozen=True)`.

## `ProgressReporter` (Protocol)

Context-managed interface that all reporter implementations satisfy.

```python
class ProgressReporter(Protocol):
    def __enter__(self) -> ProgressReporter: ...
    def __exit__(self, exc_type, exc, tb) -> None: ...
    def tick(self, event: ProgressEvent) -> None: ...
```

Callers should use `make_reporter()` to obtain a concrete implementation rather
than constructing reporters directly.

## `LogReporter`

Emits sampled progress lines to loguru's `INFO` channel. Progress lines are
rate-limited to ~20 steps by default. An explicit `log_interval` overrides the
number of units between sampled updates; `1` emits every tick. Downloads use
`1` with batches of at most 512 files, while listing and scanning retain the default.

On context exit the reporter emits a final summary line
(`complete` or `aborted`) with cumulative ok/fail counts.

| Parameter | Description |
|-----------|-------------|
| `total` | Expected number of units. |
| `description` | Human-readable label (e.g. `"download"`, `"verify"`). |
| `log_interval` | Optional interval in progress units, clamped to at least 1. `None` uses `max(1, total // 20)`. |

## `TqdmReporter`

Interactive `tqdm`-based progress bar on stderr. The reporter manages the bar,
counters, and `complete` / `aborted` summary. CLI logging writes through
`tqdm.write()` so log lines appear above the active bar.

Library callers retain ownership of their log sinks: the reporter leaves those
sinks and their filtering, formatting, and destinations unchanged. Automatic
redirection of library callers' stderr sinks has been removed. To coordinate
library logs with a bar, configure a sink that writes through `tqdm.write()` or
use `configure_cli_logging()` if replacing the current loguru configuration is
appropriate. Otherwise, logs written directly to the same terminal can overlap
the bar.

| Parameter | Description |
|-----------|-------------|
| `total` | Expected number of units. |
| `description` | Human-readable label shown in the progress bar prefix. |

`TqdmReporter` is **not re-entrant** — nesting two reporters in the same
process raises `RuntimeError`.

## `make_reporter()`

Factory function that selects the appropriate reporter implementation.

```python
from binance_datatool.common.progress import make_reporter

with make_reporter(progress_bar=True, total=100, description="download") as reporter:
    for item in items:
        process(item)
        reporter.tick(ProgressEvent(name=item.name, ok=True))
```

| Parameter | Type | Description |
|-----------|------|-------------|
| `progress_bar` | `bool` | `True` → `TqdmReporter`; `False` → `LogReporter`. |
| `total` | `int` | Expected number of progress units. |
| `description` | `str` | Human-readable label for the operation. |
| `log_interval` | `int \| None` | Log sampling interval; `None` preserves proportional sampling, `1` logs every tick. Ignored when `progress_bar=True`. |

Returns a `ProgressReporter`-compatible context manager.

---

See also: [Downloader](../archive/downloader.md) | [Archive client](../archive/client.md) | [Architecture](../../architecture.md)
