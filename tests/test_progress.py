"""Tests for shared progress reporters."""

from __future__ import annotations

import pytest

from binance_datatool.common.progress import (
    LogReporter,
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
