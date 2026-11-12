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

    def __init__(self, *, total: int, description: str) -> None:
        super().__init__(total=total, description=description)
        self._step = max(1, total // 20)

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


@dataclass(slots=True, frozen=True)
class _StderrSinkSnapshot:
    """Minimal state needed to restore a stderr-bound loguru sink."""

    stream: Any
    level: int
    decolorized_format: str | None
    precolorized_formats: dict[str | None, str] | None
    filter_value: Any
    colorize: bool
    serialize: bool
    enqueue: bool


def _resolve_restore_format(
    snapshot: _StderrSinkSnapshot,
) -> tuple[Any, bool]:
    """Choose the format value and colorize flag for restoring a snapshotted sink.

    When the original handler was colorized, loguru stores per-level ANSI
    format strings in ``_precolorized_formats`` but leaves
    ``_decolorized_format`` as ``None``.  We restore such handlers by
    returning a dynamic format function that picks the right pre-colored
    template for the log level, with ``colorize=False`` so loguru does not
    double-apply ANSI escapes.

    For non-colorized handlers, ``_decolorized_format`` is usable directly
    after stripping the ``\\n{exception}`` suffix that loguru appends
    internally (``logger.add`` will re-append it).

    Returns:
        ``(format, colorize)`` pair suitable for ``logger.add()``.
    """
    if snapshot.precolorized_formats is not None:
        pcf = snapshot.precolorized_formats
        fallback = pcf.get(None, "{message}\n{exception}")

        def _make_dynamic(formats: dict[str | None, str], fb: str) -> Any:
            def _format(record: dict[str, Any]) -> str:
                return formats.get(record["level"].name, fb)

            return _format

        return _make_dynamic(pcf, fallback), False

    fmt = snapshot.decolorized_format
    if isinstance(fmt, str):
        if fmt.endswith("\n{exception}"):
            fmt = fmt[: -len("\n{exception}")]
        return fmt, snapshot.colorize

    return "{message}", snapshot.colorize


class TqdmReporter(_ReporterState):
    """Interactive tqdm-based reporter with stderr-safe log redirection."""

    _active_lock = threading.Lock()
    _active = False

    def __init__(self, *, total: int, description: str) -> None:
        super().__init__(total=total, description=description)
        self._stderr = sys.stderr
        self._bar: Any | None = None
        self._stderr_snapshots: list[_StderrSinkSnapshot] = []
        self._redirect_sink_id: int | None = None

    def __enter__(self) -> TqdmReporter:
        """Set up the tqdm bar and redirect stderr-bound loguru sinks.

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
            self._stderr_snapshots = self._remove_stderr_sinks()
            if self._stderr_snapshots:
                redirect_level = min(s.level for s in self._stderr_snapshots)
                self._redirect_sink_id = logger.add(
                    self._write_log_line, level=redirect_level, format="{message}"
                )
            return self
        except Exception:
            if self._bar is not None:
                self._bar.close()
            self._restore_stderr_sinks()
            with self._active_lock:
                type(self)._active = False
            raise

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close the tqdm bar and restore the original stderr loguru sinks."""
        del exc, tb
        status = "complete" if exc_type is None else "aborted"
        try:
            self._write_terminal_line(self._summary_line(status))
        finally:
            if self._bar is not None:
                self._bar.close()
            if self._redirect_sink_id is not None:
                logger.remove(self._redirect_sink_id)
                self._redirect_sink_id = None
            self._restore_stderr_sinks()
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

    def _write_log_line(self, message: str) -> None:
        """Send one formatted log line through tqdm's write helper."""
        self._write_terminal_line(str(message).rstrip("\n"))

    def _write_terminal_line(self, line: str) -> None:
        """Write one terminal-safe line while the progress bar is active."""
        tqdm.write(line, file=self._stderr)

    def _remove_stderr_sinks(self) -> list[_StderrSinkSnapshot]:
        """Remove and snapshot every loguru sink currently bound to stderr."""
        snapshots: list[_StderrSinkSnapshot] = []
        for handler_id, handler in list(logger._core.handlers.items()):
            stream = getattr(getattr(handler, "_sink", None), "_stream", None)
            if stream is not self._stderr:
                continue
            snapshots.append(
                _StderrSinkSnapshot(
                    stream=stream,
                    level=handler._levelno,
                    decolorized_format=getattr(handler, "_decolorized_format", None),
                    precolorized_formats=(
                        dict(handler._precolorized_formats)
                        if handler._colorize
                        and isinstance(getattr(handler, "_precolorized_formats", None), dict)
                        else None
                    ),
                    filter_value=handler._filter,
                    colorize=handler._colorize,
                    serialize=handler._serialize,
                    enqueue=handler._enqueue,
                )
            )
            logger.remove(handler_id)
        return snapshots

    def _restore_stderr_sinks(self) -> None:
        """Restore stderr-bound sinks removed during reporter entry."""
        while self._stderr_snapshots:
            snapshot = self._stderr_snapshots.pop(0)
            fmt, colorize = _resolve_restore_format(snapshot)
            logger.add(
                snapshot.stream,
                level=snapshot.level,
                format=fmt,
                filter=snapshot.filter_value,
                colorize=colorize,
                serialize=snapshot.serialize,
                enqueue=snapshot.enqueue,
            )


def make_reporter(
    progress_bar: bool,
    *,
    total: int,
    description: str,
) -> ProgressReporter:
    """Create the configured reporter implementation.

    Args:
        progress_bar: When ``True``, return a :class:`TqdmReporter` with an
            interactive progress bar; otherwise return a :class:`LogReporter`
            that emits sampled log lines.
        total: Total number of expected progress units.
        description: Human-readable label shown in progress output.

    Returns:
        A :class:`ProgressReporter` ready for use as a context manager.
    """
    if progress_bar:
        return TqdmReporter(total=total, description=description)
    return LogReporter(total=total, description=description)


__all__ = [
    "LogReporter",
    "ProgressEvent",
    "ProgressReporter",
    "TqdmReporter",
    "make_reporter",
]
