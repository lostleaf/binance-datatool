"""Tests for shared progress reporters."""

from __future__ import annotations

import sys

import pytest
from loguru import logger

from binance_datatool.common.progress import (
    LogReporter,
    ProgressEvent,
    TqdmReporter,
    make_reporter,
)


def test_make_reporter_returns_requested_type() -> None:
    """Reporter factory should choose between log and tqdm implementations."""
    assert isinstance(make_reporter(False, total=1, description="x"), LogReporter)
    assert isinstance(make_reporter(True, total=1, description="x"), TqdmReporter)


def test_tqdm_reporter_rejects_nested_instances() -> None:
    """Nested tqdm reporters in one process should fail fast."""
    outer = TqdmReporter(total=1, description="outer")
    inner = TqdmReporter(total=1, description="inner")

    with outer, pytest.raises(RuntimeError), inner:
        pytest.fail("Nested reporters must be rejected before entering the body.")

    with inner:
        pass


def test_default_log_sampling_remains_proportional_to_total() -> None:
    """Listing and scanning callers retain their existing sampled cadence."""
    messages = []
    sink_id = logger.add(messages.append, format="{message}")
    try:
        with make_reporter(False, total=12289, description="listing") as reporter:
            reporter.tick(ProgressEvent(name="first", ok=True, count=512))
            assert messages == []
            reporter.tick(ProgressEvent(name="second", ok=True, count=512))
            assert len(messages) == 1
            assert reporter.done == 1024
    finally:
        logger.remove(sink_id)


def test_tqdm_reporter_preserves_library_sink_diagnostics(capsys) -> None:
    """Library-owned sinks retain diagnostic payloads and filtering during a bar."""
    sink_id = logger.add(
        sys.stderr,
        format="{extra[symbol]} {message}",
        filter=lambda record: record["extra"].get("source") == "library",
    )
    try:
        with TqdmReporter(total=1, description="library") as reporter:
            logger.bind(source="library", symbol="BTCUSDT").warning("checksum-sentinel-32")
            logger.bind(source="excluded", symbol="ETHUSDT").warning("filtered-sentinel-32")
            reporter.tick(ProgressEvent(name="completed-item", ok=True))
        emitted = capsys.readouterr().err
        assert "BTCUSDT" in emitted
        assert "checksum-sentinel-32" in emitted
        assert "ETHUSDT" not in emitted
    finally:
        logger.remove(sink_id)


@pytest.mark.parametrize("reporter_type", [LogReporter, TqdmReporter])
@pytest.mark.parametrize("aborted", [False, True])
def test_reporter_preserves_counters_and_exit_summary(reporter_type, aborted, capsys) -> None:
    """Both reporters retain weighted counters and emit complete or aborted outcomes."""
    messages = []
    sink_id = logger.add(messages.append, format="{message}")
    reporter = reporter_type(total=5, description="archive-work")
    try:
        try:
            with reporter:
                reporter.tick(ProgressEvent(name="BTCUSDT", ok=True, count=3))
                reporter.tick(ProgressEvent(name="ETHUSDT", ok=False, count=2))
                if aborted:
                    raise ValueError("abort-sentinel-32")
        except ValueError as exc:
            assert aborted
            assert str(exc) == "abort-sentinel-32"
        assert (reporter.done, reporter.ok, reporter.fail) == (5, 3, 2)
        emitted = "".join(str(message) for message in messages) + capsys.readouterr().err
        assert "archive-work" in emitted
        assert ("aborted" if aborted else "complete") in emitted
    finally:
        logger.remove(sink_id)
