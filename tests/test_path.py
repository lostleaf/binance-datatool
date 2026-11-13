"""Tests for archive path resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from binance_datatool.common.path import ArchiveHomeNotConfiguredError, resolve_archive_home


def test_resolve_archive_home_prefers_cli_override(monkeypatch) -> None:
    """CLI overrides should win over the environment."""
    monkeypatch.setenv("BINANCE_DATATOOL_ARCHIVE_HOME", "/env/home")

    result = resolve_archive_home(Path("~/cli-home"))

    assert result == Path("~/cli-home").expanduser()


def test_resolve_archive_home_falls_back_to_environment(monkeypatch) -> None:
    """The environment should be used when no override is supplied."""
    monkeypatch.setenv("BINANCE_DATATOOL_ARCHIVE_HOME", "~/env-home")

    result = resolve_archive_home()

    assert result == Path("~/env-home").expanduser()


def test_resolve_archive_home_raises_when_unconfigured(monkeypatch) -> None:
    """A descriptive error should be raised when the archive home is missing."""
    monkeypatch.delenv("BINANCE_DATATOOL_ARCHIVE_HOME", raising=False)

    with pytest.raises(ArchiveHomeNotConfiguredError):
        resolve_archive_home()
