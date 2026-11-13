"""Tests for shared progress reporters."""

from __future__ import annotations

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
