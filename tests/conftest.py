"""Shared test fixtures and pytest configuration."""

from __future__ import annotations

from datetime import UTC, datetime
from urllib.parse import parse_qs, urlsplit

import aiohttp
import pytest
from tenacity import wait_none

from binance_datatool.archive import ArchiveFile


class FakeArchiveClient:
    """Programmable stub for ArchiveClient-based tests."""

    def __init__(
        self,
        *,
        symbols: list[str] | None = None,
        files_by_symbol: dict[str, list[ArchiveFile]] | None = None,
        errors_by_symbol: dict[str, Exception] | None = None,
    ) -> None:
        self._symbols = symbols or []
        self._files = files_by_symbol or {}
        self._errors = errors_by_symbol or {}
        self.last_list_symbol_files_batch_progress_bar: bool | None = None

    async def list_symbols(self, trade_type, data_freq, data_type) -> list[str]:
        return list(self._symbols)

    async def list_symbol_files(
        self,
        trade_type,
        data_freq,
        data_type,
        symbol,
        interval=None,
        *,
        session=None,
    ) -> list[ArchiveFile]:
        del trade_type, data_freq, data_type, interval, session
        if symbol in self._errors:
            raise self._errors[symbol]
        return list(self._files.get(symbol, []))

    async def list_symbol_files_batch(
        self,
        trade_type,
        data_freq,
        data_type,
        symbols,
        interval=None,
        *,
        progress_bar: bool = False,
    ) -> dict[str, tuple[list[ArchiveFile], str | None]]:
        del trade_type, data_freq, data_type, interval
        self.last_list_symbol_files_batch_progress_bar = progress_bar
        return {
            symbol: (
                [],
                str(self._errors[symbol]),
            )
            if symbol in self._errors
            else (
                list(self._files.get(symbol, [])),
                None,
            )
            for symbol in symbols
        }


@pytest.fixture
def sample_archive_files() -> list[ArchiveFile]:
    """Return representative archive files for list-files tests."""
    return [
        ArchiveFile(
            key="data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-03.zip",
            size=1048,
            last_modified=datetime(2026, 4, 1, 8, 6, 34, tzinfo=UTC),
        ),
        ArchiveFile(
            key=(
                "data/futures/um/monthly/fundingRate/BTCUSDT/"
                "BTCUSDT-fundingRate-2026-03.zip.CHECKSUM"
            ),
            size=105,
            last_modified=datetime(2026, 4, 1, 8, 6, 34, tzinfo=UTC),
        ),
    ]


@pytest.fixture
def listing_timeout_http(monkeypatch, sample_archive_files) -> dict[str, int]:
    """Serve failed, empty, and nonempty listings without network or retry delays."""
    attempts: dict[str, int] = {}

    class Response:
        def __init__(self, symbol: str) -> None:
            self.symbol = symbol

        async def __aenter__(self) -> Response:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        async def text(self) -> str:
            files = sample_archive_files if self.symbol == "BTCUSDT" else []
            entries = "".join(
                f"<Contents><Key>{file.key}</Key><Size>{file.size}</Size>"
                f"<LastModified>{file.last_modified.isoformat()}</LastModified></Contents>"
                for file in files
            )
            return f"<ListBucketResult>{entries}</ListBucketResult>"

    def get(session: aiohttp.ClientSession, url: str) -> Response:
        prefix = parse_qs(urlsplit(url).query)["prefix"][0]
        symbol = prefix.rstrip("/").rsplit("/", maxsplit=1)[-1]
        attempts[symbol] = attempts.get(symbol, 0) + 1
        if symbol == "ETHUSDT":
            raise TimeoutError
        return Response(symbol)

    monkeypatch.setattr(aiohttp.ClientSession, "get", get)
    monkeypatch.setattr(
        "binance_datatool.archive.client.wait_exponential", lambda **kw: wait_none()
    )
    return attempts


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register local pytest options."""
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run tests that make real network requests to data.binance.vision.",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip integration tests unless explicitly requested."""
    if config.getoption("--run-integration"):
        return

    skip_integration = pytest.mark.skip(
        reason="use --run-integration to run network integration tests"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)
