"""Shared progress-reporting helpers."""

from __future__ import annotations

import sys
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from types import TracebackType

from loguru import logger
from tqdm import tqdm


@dataclass(slots=True, frozen=True)
class ProgressEvent:
    """Single progress tick payload."""

    name: str
    ok: bool
    count: int = 1


class ProgressReporter(Protocol):
    """Context-managed progress reporter."""

    def __enter__(self) -> ProgressReporter: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def tick(self, event: ProgressEvent) -> None: ...


class _ReporterState:
    """Shared counter and formatting state for progress reporters."""

    def __init__(self, *, total: int, description: str) -> None:
        self._total = total
        self._description = description
        self._done = 0
        self._ok = 0
        self._fail = 0

    @property
    def done(self) -> int:
        """Return the number of processed units."""
        return self._done

    @property
    def ok(self) -> int:
        """Return the number of successful units."""
        return self._ok

    @property
    def fail(self) -> int:
        """Return the number of failed units."""
        return self._fail

    def _advance(self, event: ProgressEvent) -> None:
        """Apply one progress event to the internal counters."""
        self._done += event.count
        if event.ok:
            self._ok += event.count
            return
        self._fail += event.count

    def _summary_line(self, status: str) -> str:
        """Build the final summary line."""
        return (
            f"[{self._description}] {status}: "
            f"{self._done}/{self._total} ok={self._ok} fail={self._fail}"
        )


class LogReporter(_ReporterState):
    """Emit sampled progress lines to the shared loguru info channel."""

    def __init__(self, *, total: int, description: str, log_interval: int | None = None) -> None:
        super().__init__(total=total, description=description)
        self._step = max(1, total // 20) if log_interval is None else max(1, log_interval)

    def __enter__(self) -> LogReporter:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        del exc, tb
        status = "complete" if exc_type is None else "aborted"
        self._emit(self._summary_line(status))

    def tick(self, event: ProgressEvent) -> None:
        """Record one progress update and emit a sampled log line."""
        previous_done = self._done
        self._advance(event)
        if self._total <= 0:
            return
        if self._done // self._step <= previous_done // self._step:
            return
        self._emit(self._progress_line(event.name))

    def _emit(self, line: str) -> None:
        """Send one progress line to loguru."""
        logger.info(line)

    def _progress_line(self, name: str) -> str:
        """Build one sampled progress line."""
        pct = min(100, round(100 * self._done / self._total))
        return (
            f"[{self._description}] {pct}% ({self._done}/{self._total}) "
            f"ok={self._ok} fail={self._fail} last={name}"
        )


class TqdmReporter(_ReporterState):
    """Interactive tqdm-based reporter that leaves logging configuration to callers."""

    _active_lock = threading.Lock()
    _active = False

    def __init__(self, *, total: int, description: str) -> None:
        super().__init__(total=total, description=description)
        self._stderr = sys.stderr
        self._bar: Any | None = None

    def __enter__(self) -> TqdmReporter:
        """Set up the tqdm bar.

        Raises:
            RuntimeError: If another ``TqdmReporter`` is already active in
                the same process.
        """
        with self._active_lock:
            if type(self)._active:
                msg = "TqdmReporter does not support nested reporters in the same process."
                raise RuntimeError(msg)
            type(self)._active = True

        try:
            self._bar = tqdm(total=self._total, desc=self._description, file=self._stderr)
            return self
        except Exception:
            if self._bar is not None:
                self._bar.close()
            with self._active_lock:
                type(self)._active = False
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Write the final summary and close the tqdm bar."""
        del exc, tb
        status = "complete" if exc_type is None else "aborted"
        try:
            self._write_terminal_line(self._summary_line(status))
        finally:
            if self._bar is not None:
                self._bar.close()
            with self._active_lock:
                type(self)._active = False

    def tick(self, event: ProgressEvent) -> None:
        """Record one progress update and refresh the tqdm postfix."""
        if self._bar is None:
            msg = "TqdmReporter must be entered before calling tick()."
            raise RuntimeError(msg)

        self._advance(event)
        self._bar.update(event.count)
        self._bar.set_postfix(ok=self._ok, fail=self._fail, last=event.name[:40])

    def _write_terminal_line(self, line: str) -> None:
        """Write one terminal-safe line while the progress bar is active."""
        tqdm.write(line, file=self._stderr)


def make_reporter(
    progress_bar: bool,
    *,
    total: int,
    description: str,
    log_interval: int | None = None,
) -> ProgressReporter:
    """Create the configured reporter implementation.

    Args:
        progress_bar: When ``True``, return a :class:`TqdmReporter` with an
            interactive progress bar; otherwise return a :class:`LogReporter`
            that emits sampled log lines.
        total: Total number of expected progress units.
        description: Human-readable label shown in progress output.
        log_interval: Units between sampled log updates; defaults to about 20
            updates over the run. Use 1 to log each tick. Ignored by the bar.

    Returns:
        A :class:`ProgressReporter` ready for use as a context manager.
    """
    if progress_bar:
        return TqdmReporter(total=total, description=description)
    return LogReporter(total=total, description=description, log_interval=log_interval)


__all__ = [
    "LogReporter",
    "ProgressEvent",
    "ProgressReporter",
    "TqdmReporter",
    "make_reporter",
]
