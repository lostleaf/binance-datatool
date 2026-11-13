"""Tests for the archive listing client."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypeAlias
from urllib.parse import parse_qs, urlsplit

import aiohttp
import pytest

from binance_datatool.archive.client import (
    ArchiveClient,
    ArchiveFile,
)
from binance_datatool.common import S3_HTTP_TIMEOUT_SECONDS, DataFrequency, DataType, TradeType

if TYPE_CHECKING:
    from binance_datatool.archive.client import SymbolListingResult


XmlResponses: TypeAlias = tuple[list[str], list[dict[str, list[str]]]]


@pytest.fixture
def xml_responses(monkeypatch: pytest.MonkeyPatch) -> XmlResponses:
    """Serve XML pages at the HTTP boundary and record their request queries."""
    pages: list[str] = []
    queries: list[dict[str, list[str]]] = []

    class Response:
        async def __aenter__(self) -> Response:
            return self

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

        def raise_for_status(self) -> None:
            return None

        async def text(self) -> str:
            return pages.pop(0)

    def get(session: aiohttp.ClientSession, url: str) -> Response:
        queries.append(parse_qs(urlsplit(url).query))
        return Response()

    monkeypatch.setattr(aiohttp.ClientSession, "get", get)
    return pages, queries


@pytest.mark.asyncio
async def test_archive_client_list_symbols_handles_namespaced_pages(
    xml_responses: XmlResponses,
) -> None:
    """Symbol listings accept namespace prefixes and follow the last child prefix."""
    pages, queries = xml_responses
    pages.extend(
        [
            '<s3:ListBucketResult xmlns:s3="http://s3.amazonaws.com/doc/2006-03-01/">'
            "<s3:IsTruncated>true</s3:IsTruncated>"
            "<s3:CommonPrefixes><s3:Prefix>data/spot/daily/klines/ETHUSDT/</s3:Prefix>"
            "</s3:CommonPrefixes></s3:ListBucketResult>",
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            "<IsTruncated>false</IsTruncated>"
            "<CommonPrefixes><Prefix>data/spot/daily/klines/BTCUSDT/</Prefix></CommonPrefixes>"
            "<CommonPrefixes><Prefix>data/spot/daily/klines/BNBUSDT/</Prefix></CommonPrefixes>"
            "</ListBucketResult>",
        ]
    )

    symbols = await ArchiveClient().list_symbols(
        TradeType.spot, DataFrequency.daily, DataType.klines
    )

    assert symbols == ["BNBUSDT", "BTCUSDT", "ETHUSDT"]
    assert queries == [
        {"delimiter": ["/"], "prefix": ["data/spot/daily/klines/"]},
        {
            "delimiter": ["/"],
            "prefix": ["data/spot/daily/klines/"],
            "marker": ["data/spot/daily/klines/ETHUSDT/"],
        },
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 3])
async def test_archive_client_list_symbols_parses_xml(
    xml_responses: XmlResponses,
    count: int,
) -> None:
    """Symbol listings return sorted names for absent, single and many child prefixes."""
    pages, _ = xml_responses
    prefixes = [
        "<CommonPrefixes><Prefix>data/spot/daily/klines/ETHUSDT/</Prefix></CommonPrefixes>",
        "<CommonPrefixes><Prefix>data/spot/daily/klines/BTCUSDT/</Prefix></CommonPrefixes>",
        "<CommonPrefixes><Prefix>data/spot/daily/klines/BNBUSDT/</Prefix></CommonPrefixes>",
    ]
    pages.append("<ListBucketResult>" + "".join(prefixes[:count]) + "</ListBucketResult>")

    symbols = await ArchiveClient().list_symbols(
        TradeType.spot, DataFrequency.daily, DataType.klines
    )

    assert symbols == {0: [], 1: ["ETHUSDT"], 3: ["BNBUSDT", "BTCUSDT", "ETHUSDT"]}[count]


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit_marker", [False, True])
async def test_archive_client_list_symbols_uses_explicit_or_file_marker(
    xml_responses: XmlResponses,
    explicit_marker: bool,
) -> None:
    """A directory page with only objects falls back to its last key when needed."""
    pages, queries = xml_responses
    marker_xml = "<NextMarker>resume</NextMarker>" if explicit_marker else ""
    pages.extend(
        [
            "<ListBucketResult><IsTruncated>true</IsTruncated>"
            + marker_xml
            + "<Contents><Key>data/object.zip</Key></Contents></ListBucketResult>",
            "<ListBucketResult><IsTruncated>false</IsTruncated>"
            "<CommonPrefixes><Prefix>data/spot/daily/klines/BTCUSDT/</Prefix></CommonPrefixes>"
            "</ListBucketResult>",
        ]
    )

    symbols = await ArchiveClient().list_symbols(
        TradeType.spot, DataFrequency.daily, DataType.klines
    )

    assert symbols == ["BTCUSDT"]
    assert queries[1]["marker"] == ["resume" if explicit_marker else "data/object.zip"]


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


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 2])
@pytest.mark.parametrize("namespace", ["", ' xmlns="http://s3.amazonaws.com/doc/2006-03-01/"'])
async def test_archive_client_list_symbol_files_parses_xml(
    xml_responses: XmlResponses,
    count: int,
    namespace: str,
) -> None:
    """File listings preserve metadata and order for absent, single and many entries."""
    pages, _ = xml_responses
    entries = [
        "<Contents><Key>data/BTCUSDT.zip</Key><Size>1048</Size>"
        "<LastModified>2026-04-01T08:06:34.000Z</LastModified></Contents>",
        "<Contents><Key>data/BTCUSDT.zip.CHECKSUM</Key><Size>105</Size>"
        "<LastModified>2026-04-01T08:06:34.000Z</LastModified></Contents>",
    ]
    pages.append(
        f"<ListBucketResult{namespace}><IsTruncated>false</IsTruncated>"
        + "".join(entries[:count])
        + "</ListBucketResult>"
    )

    files = await ArchiveClient().list_symbol_files(
        TradeType.um, DataFrequency.monthly, DataType.funding_rate, "BTCUSDT"
    )

    expected = [
        ArchiveFile("data/BTCUSDT.zip", 1048, datetime(2026, 4, 1, 8, 6, 34, tzinfo=UTC)),
        ArchiveFile("data/BTCUSDT.zip.CHECKSUM", 105, datetime(2026, 4, 1, 8, 6, 34, tzinfo=UTC)),
    ]
    assert files == expected[:count]


@pytest.mark.asyncio
async def test_archive_client_list_symbol_files_normalizes_xml_text(
    xml_responses: XmlResponses,
) -> None:
    """Whitespace around S3 field text retains the previous parser's normalization."""
    pages, _ = xml_responses
    pages.append(
        "<ListBucketResult><Contents><Key> data/file.zip </Key><Size> 1048 </Size>"
        "<LastModified> 2026-04-01T08:06:34.000Z </LastModified>"
        "</Contents></ListBucketResult>"
    )

    files = await ArchiveClient().list_symbol_files(
        TradeType.um, DataFrequency.monthly, DataType.funding_rate, "BTCUSDT"
    )

    assert files == [ArchiveFile("data/file.zip", 1048, datetime(2026, 4, 1, 8, 6, 34, tzinfo=UTC))]


@pytest.mark.asyncio
@pytest.mark.parametrize("explicit_marker", [False, True])
@pytest.mark.parametrize("batch", [False, True])
async def test_archive_client_list_symbol_files_follows_markers(
    xml_responses: XmlResponses,
    explicit_marker: bool,
    batch: bool,
) -> None:
    """File pagination honors NextMarker and otherwise uses the final object key."""
    pages, queries = xml_responses
    marker_xml = "<NextMarker>resume+after&amp;key</NextMarker>" if explicit_marker else ""
    pages.extend(
        [
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            "<IsTruncated>true</IsTruncated>"
            + marker_xml
            + "<CommonPrefixes><Prefix>ignored/directory/</Prefix></CommonPrefixes>"
            "<Contents><Key>data/BTCUSDT.zip</Key><Size>1048</Size>"
            "<LastModified>2026-04-01T08:06:34.000Z</LastModified></Contents></ListBucketResult>",
            "<ListBucketResult><IsTruncated>false</IsTruncated>"
            "<Contents><Key>data/BTCUSDT.zip.CHECKSUM</Key><Size>105</Size>"
            "<LastModified>2026-04-01T08:06:34.000Z</LastModified></Contents></ListBucketResult>",
        ]
    )

    client = ArchiveClient()
    if batch:
        outcomes = await client.list_symbol_files_batch(
            TradeType.um, DataFrequency.monthly, DataType.funding_rate, ["BTCUSDT"]
        )
        files, error = outcomes["BTCUSDT"]
        assert error is None
    else:
        files = await client.list_symbol_files(
            TradeType.um, DataFrequency.monthly, DataType.funding_rate, "BTCUSDT"
        )

    assert [file.key for file in files] == ["data/BTCUSDT.zip", "data/BTCUSDT.zip.CHECKSUM"]
    assert queries[1]["marker"] == ["resume+after&key" if explicit_marker else "data/BTCUSDT.zip"]


@pytest.mark.asyncio
@pytest.mark.parametrize("marker_xml", ["", "<NextMarker>resume</NextMarker>"])
async def test_archive_client_list_symbols_handles_empty_truncated_pages(
    xml_responses: XmlResponses,
    marker_xml: str,
) -> None:
    """An empty truncated page continues only when S3 supplies a next marker."""
    pages, queries = xml_responses
    pages.append(
        "<ListBucketResult><IsTruncated>true</IsTruncated>" + marker_xml + "</ListBucketResult>"
    )
    if marker_xml:
        pages.append("<ListBucketResult><IsTruncated>false</IsTruncated></ListBucketResult>")

    symbols = await ArchiveClient().list_symbols(
        TradeType.spot, DataFrequency.daily, DataType.klines
    )

    assert symbols == []
    assert len(queries) == (2 if marker_xml else 1)
    if marker_xml:
        assert queries[1]["marker"] == ["resume"]


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 2])
async def test_archive_client_list_symbol_files_batch_parses_xml(
    xml_responses: XmlResponses,
    count: int,
) -> None:
    """Batch listings retain ordered empty, single and many-entry XML outcomes."""
    pages, _ = xml_responses
    entry = (
        "<Contents><Key>data/file.zip</Key><Size>1048</Size>"
        "<LastModified>2026-04-01T08:06:34.000Z</LastModified></Contents>"
    )
    # Identical pages keep concurrent request scheduling irrelevant to the fixture.
    pages.extend(
        [
            '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
            + entry * count
            + "</ListBucketResult>"
        ]
        * 2
    )

    result = await ArchiveClient().list_symbol_files_batch(
        TradeType.um, DataFrequency.monthly, DataType.funding_rate, ["ETHUSDT", "BTCUSDT"]
    )

    expected = [
        ArchiveFile("data/file.zip", 1048, datetime(2026, 4, 1, 8, 6, 34, tzinfo=UTC))
    ] * count
    assert list(result) == ["ETHUSDT", "BTCUSDT"]
    assert result == {"ETHUSDT": (expected, None), "BTCUSDT": (expected, None)}


@pytest.mark.asyncio
async def test_archive_client_list_symbol_files_rejects_non_listing_xml(
    xml_responses: XmlResponses,
) -> None:
    """A non-listing XML response must fail rather than look like an empty directory."""
    pages, _ = xml_responses
    pages.append("<Error><Code>AccessDenied</Code></Error>")

    with pytest.raises(ValueError):
        await ArchiveClient().list_symbol_files(
            TradeType.um, DataFrequency.monthly, DataType.funding_rate, "BTCUSDT"
        )


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
