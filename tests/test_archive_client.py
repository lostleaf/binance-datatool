"""Tests for the archive listing client."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import aiohttp
import pytest

from binance_datatool.archive.client import (
    ArchiveClient,
    ArchiveFile,
    _extract_files_from_payload,
)
from binance_datatool.common import S3_HTTP_TIMEOUT_SECONDS, DataFrequency, DataType, TradeType

if TYPE_CHECKING:
    from binance_datatool.archive.client import SymbolListingResult


@pytest.mark.asyncio
async def test_archive_client_list_dir_handles_pagination_and_single_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """S3 pagination should aggregate prefixes, including single-item pages."""
    responses = [
        {
            "ListBucketResult": {
                "IsTruncated": "true",
                "CommonPrefixes": [
                    {"Prefix": "data/spot/daily/klines/BTCUSDT/"},
                    {"Prefix": "data/spot/daily/klines/ETHUSDT/"},
                ],
            }
        },
        {
            "ListBucketResult": {
                "IsTruncated": "false",
                "CommonPrefixes": {"Prefix": "data/spot/daily/klines/BNBUSDT/"},
            }
        },
    ]
    client = ArchiveClient()

    async def fake_fetch_xml(session: aiohttp.ClientSession, url: str) -> dict[str, Any]:
        assert "prefix=data%2Fspot%2Fdaily%2Fklines%2F" in url
        return responses.pop(0)

    monkeypatch.setattr(client, "_fetch_xml", fake_fetch_xml)

    async with aiohttp.ClientSession() as session:
        result = await client.list_dir(session, "data/spot/daily/klines/")

    assert result == [
        "data/spot/daily/klines/BTCUSDT/",
        "data/spot/daily/klines/ETHUSDT/",
        "data/spot/daily/klines/BNBUSDT/",
    ]


@pytest.mark.asyncio
async def test_archive_client_list_symbols_uses_trust_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Archive client sessions should trust standard proxy environment variables."""
    captured: dict[str, Any] = {}

    class FakeSession:
        """Minimal async context manager used to capture session kwargs."""

        def __init__(self, **kwargs: Any) -> None:
            captured.update(kwargs)

        async def __aenter__(self) -> FakeSession:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    async def fake_list_dir(self, session: FakeSession, prefix: str) -> list[str]:
        assert prefix == "data/spot/daily/klines/"
        return ["data/spot/daily/klines/ETHUSDT/", "data/spot/daily/klines/BTCUSDT/"]

    monkeypatch.setattr("binance_datatool.archive.client.aiohttp.ClientSession", FakeSession)
    monkeypatch.setattr(ArchiveClient, "list_dir", fake_list_dir)

    client = ArchiveClient()
    symbols = await client.list_symbols(TradeType.spot, DataFrequency.daily, DataType.klines)

    assert symbols == ["BTCUSDT", "ETHUSDT"]
    assert captured["trust_env"] is True
    assert captured["timeout"].total == S3_HTTP_TIMEOUT_SECONDS


def test_extract_files_from_payload_handles_empty_contents() -> None:
    """Missing S3 contents should produce an empty file list."""
    payload = {"ListBucketResult": {"IsTruncated": "false"}}

    assert _extract_files_from_payload(payload) == []


def test_extract_files_from_payload_parses_single_entry() -> None:
    """A single S3 content dict should become one ArchiveFile."""
    payload = {
        "ListBucketResult": {
            "Contents": {
                "Key": "data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-03.zip",
                "LastModified": "2026-04-01T08:06:34.000Z",
                "Size": "1048",
            }
        }
    }

    assert _extract_files_from_payload(payload) == [
        ArchiveFile(
            key="data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-03.zip",
            size=1048,
            last_modified=datetime(2026, 4, 1, 8, 6, 34, tzinfo=UTC),
        )
    ]


def test_extract_files_from_payload_parses_multiple_entries() -> None:
    """S3 file payloads should preserve order and parse checksum files too."""
    payload = {
        "ListBucketResult": {
            "Contents": [
                {
                    "Key": "data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-03.zip",
                    "LastModified": "2026-04-01T08:06:34.000Z",
                    "Size": "1048",
                },
                {
                    "Key": (
                        "data/futures/um/monthly/fundingRate/BTCUSDT/"
                        "BTCUSDT-fundingRate-2026-03.zip.CHECKSUM"
                    ),
                    "LastModified": "2026-04-01T08:06:34.000Z",
                    "Size": "105",
                },
            ]
        }
    }

    files = _extract_files_from_payload(payload)

    assert [file.size for file in files] == [1048, 105]
    assert files[0].key.endswith(".zip")
    assert files[1].key.endswith(".zip.CHECKSUM")
    assert all(file.last_modified.tzinfo is UTC for file in files)


@pytest.mark.asyncio
async def test_archive_client_list_files_in_dir_handles_pagination(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """File listings should combine multiple S3 pages."""
    responses = [
        {
            "ListBucketResult": {
                "IsTruncated": "true",
                "Contents": {
                    "Key": "data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-03.zip",
                    "LastModified": "2026-04-01T08:06:34.000Z",
                    "Size": "1048",
                },
            }
        },
        {
            "ListBucketResult": {
                "IsTruncated": "false",
                "Contents": {
                    "Key": (
                        "data/futures/um/monthly/fundingRate/BTCUSDT/"
                        "BTCUSDT-fundingRate-2026-03.zip.CHECKSUM"
                    ),
                    "LastModified": "2026-04-01T08:06:34.000Z",
                    "Size": "105",
                },
            }
        },
    ]
    client = ArchiveClient()

    async def fake_fetch_xml(session: aiohttp.ClientSession, url: str) -> dict[str, Any]:
        assert "prefix=data%2Ffutures%2Fum%2Fmonthly%2FfundingRate%2FBTCUSDT%2F" in url
        return responses.pop(0)

    monkeypatch.setattr(client, "_fetch_xml", fake_fetch_xml)

    async with aiohttp.ClientSession() as session:
        result = await client.list_files_in_dir(
            session, "data/futures/um/monthly/fundingRate/BTCUSDT/"
        )

    assert [file.size for file in result] == [1048, 105]


@pytest.mark.asyncio
async def test_archive_client_list_symbol_files_validates_interval(monkeypatch) -> None:
    """High-level symbol file listing should enforce interval compatibility."""
    client = ArchiveClient()

    def unexpected_session(*args, **kwargs):
        pytest.fail("Invalid intervals must be rejected before opening an HTTP session.")

    monkeypatch.setattr("aiohttp.ClientSession", unexpected_session)

    with pytest.raises(ValueError):
        await client.list_symbol_files(
            TradeType.um,
            DataFrequency.daily,
            DataType.klines,
            "BTCUSDT",
        )

    with pytest.raises(ValueError):
        await client.list_symbol_files(
            TradeType.um,
            DataFrequency.monthly,
            DataType.funding_rate,
            "BTCUSDT",
            interval="1m",
        )


@pytest.mark.asyncio
async def test_archive_client_list_symbol_files_batch_preserves_order_and_shares_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Batch listings should preserve symbol order and reuse one shared session."""
    client = ArchiveClient()
    shared_session = object()

    class FakeSession:
        async def __aenter__(self) -> object:
            return shared_session

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    captured_sessions: list[object] = []
    per_symbol_files = {
        "ETHUSDT": [],
        "BTCUSDT": [
            ArchiveFile(
                key="data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-03.zip",
                size=1048,
                last_modified=datetime(2026, 4, 1, 8, 6, 34, tzinfo=UTC),
            )
        ],
    }

    async def fake_list_symbol_files(
        trade_type: TradeType,
        data_freq: DataFrequency,
        data_type: DataType,
        symbol: str,
        interval: str | None = None,
        *,
        session: object | None = None,
    ) -> list[ArchiveFile]:
        del trade_type, data_freq, data_type, interval
        captured_sessions.append(session)
        return per_symbol_files[symbol]

    monkeypatch.setattr(client, "_create_session", lambda: FakeSession())
    monkeypatch.setattr(client, "list_symbol_files", fake_list_symbol_files)

    result: dict[str, SymbolListingResult] = await client.list_symbol_files_batch(
        TradeType.um,
        DataFrequency.monthly,
        DataType.funding_rate,
        ["ETHUSDT", "BTCUSDT"],
    )

    assert isinstance(result["BTCUSDT"], tuple)
    assert list(result) == ["ETHUSDT", "BTCUSDT"]
    assert result == {
        "ETHUSDT": ([], None),
        "BTCUSDT": (per_symbol_files["BTCUSDT"], None),
    }
    assert captured_sessions == [shared_session, shared_session]


@pytest.mark.asyncio
async def test_archive_client_list_symbol_files_batch_isolates_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Batch listings should convert per-symbol exceptions into structured errors."""
    client = ArchiveClient()

    class FakeSession:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    async def fake_list_symbol_files(
        trade_type: TradeType,
        data_freq: DataFrequency,
        data_type: DataType,
        symbol: str,
        interval: str | None = None,
        *,
        session: object | None = None,
    ) -> list[ArchiveFile]:
        del trade_type, data_freq, data_type, interval, session
        if symbol == "ETHUSDT":
            raise aiohttp.ClientError("boom")
        return []

    monkeypatch.setattr(client, "_create_session", lambda: FakeSession())
    monkeypatch.setattr(client, "list_symbol_files", fake_list_symbol_files)

    result: dict[str, SymbolListingResult] = await client.list_symbol_files_batch(
        TradeType.um,
        DataFrequency.monthly,
        DataType.funding_rate,
        ["BTCUSDT", "ETHUSDT"],
    )

    assert result == {
        "BTCUSDT": ([], None),
        "ETHUSDT": ([], "boom"),
    }


@pytest.mark.asyncio
async def test_archive_client_list_symbol_files_batch_propagates_cancelled_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cancellation should abort the batch instead of being converted to an error string."""
    client = ArchiveClient()

    class FakeSession:
        async def __aenter__(self) -> object:
            return object()

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    async def fake_list_symbol_files(
        trade_type: TradeType,
        data_freq: DataFrequency,
        data_type: DataType,
        symbol: str,
        interval: str | None = None,
        *,
        session: object | None = None,
    ) -> list[ArchiveFile]:
        del trade_type, data_freq, data_type, symbol, interval, session
        raise asyncio.CancelledError()

    monkeypatch.setattr(client, "_create_session", lambda: FakeSession())
    monkeypatch.setattr(client, "list_symbol_files", fake_list_symbol_files)

    with pytest.raises(asyncio.CancelledError):
        await client.list_symbol_files_batch(
            TradeType.um,
            DataFrequency.monthly,
            DataType.funding_rate,
            ["BTCUSDT"],
        )


@pytest.mark.asyncio
async def test_archive_client_list_symbol_files_batch_returns_empty_dict_for_no_symbols() -> None:
    """Empty input should short-circuit without creating a session."""
    client = ArchiveClient()

    result = await client.list_symbol_files_batch(
        TradeType.um,
        DataFrequency.monthly,
        DataType.funding_rate,
        [],
    )

    assert result == {}
    assert isinstance(result, dict)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_archive_client_list_symbols_spot_klines_integration() -> None:
    """Spot klines listing should contain common symbols."""
    client = ArchiveClient()
    symbols = await client.list_symbols(TradeType.spot, DataFrequency.daily, DataType.klines)
    assert symbols == sorted(symbols)
    assert "BTCUSDT" in symbols


@pytest.mark.integration
@pytest.mark.asyncio
async def test_archive_client_list_files_in_dir_integration() -> None:
    """Real S3 file listing should return file metadata for a small directory."""
    client = ArchiveClient()
    async with client._create_session() as session:
        files = await client.list_files_in_dir(
            session,
            "data/futures/um/monthly/fundingRate/BTCUSDT/",
        )

    assert files
    assert any(file.key.endswith(".zip") for file in files)
    assert any(file.key.endswith(".zip.CHECKSUM") for file in files)
    assert all(file.size > 0 for file in files)
    assert all(file.last_modified.tzinfo is UTC for file in files)
