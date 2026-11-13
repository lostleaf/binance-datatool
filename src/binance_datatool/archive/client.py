"""S3 directory listing client for data.binance.vision."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, TypeAlias
from urllib.parse import urlencode
from xml.etree import ElementTree

import aiohttp
from loguru import logger
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from binance_datatool.common import S3_HTTP_TIMEOUT_SECONDS, S3_LISTING_PREFIX
from binance_datatool.common.progress import ProgressEvent, make_reporter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Sequence

    from binance_datatool.common.enums import DataFrequency, DataType, TradeType


def _build_prefix(
    trade_type: TradeType,
    data_freq: DataFrequency,
    data_type: DataType,
) -> str:
    """Build an S3 prefix for a market archive directory."""
    return f"data/{trade_type.s3_path}/{data_freq.value}/{data_type.value}/"


def _build_listing_url(prefix: str, marker: str | None = None) -> str:
    """Build an S3 bucket listing URL for a prefix."""
    query: dict[str, str] = {"delimiter": "/", "prefix": prefix}
    if marker is not None:
        query["marker"] = marker
    return f"{S3_LISTING_PREFIX}?{urlencode(query)}"


def _namespace(root: ElementTree.Element) -> str:
    """Return the expanded namespace prefix, or empty text for unqualified XML."""
    return root.tag.rpartition("}")[0] + "}" if root.tag.startswith("{") else ""


def _required_text(element: ElementTree.Element, tag: str) -> str:
    """Read a required S3 field with the previous parser's whitespace handling."""
    text = element.findtext(tag)
    if text is None:
        msg = f"Missing S3 XML field: {tag}"
        raise ValueError(msg)
    return text.strip()


def _extract_prefixes(root: ElementTree.Element) -> list[str]:
    """Extract child prefixes from an S3 listing page."""
    namespace = _namespace(root)
    return [
        _required_text(entry, f"{namespace}Prefix")
        for entry in root.findall(f"{namespace}CommonPrefixes")
    ]


def _extract_files(root: ElementTree.Element) -> list[ArchiveFile]:
    """Extract file metadata from an S3 listing page."""
    namespace = _namespace(root)
    key_tag = f"{namespace}Key"
    size_tag = f"{namespace}Size"
    modified_tag = f"{namespace}LastModified"
    return [
        ArchiveFile(
            key=_required_text(entry, key_tag),
            size=int(_required_text(entry, size_tag)),
            last_modified=datetime.fromisoformat(
                _required_text(entry, modified_tag).replace("Z", "+00:00")
            ),
        )
        for entry in root.findall(f"{namespace}Contents")
    ]


def _is_truncated(root: ElementTree.Element) -> bool:
    """Return whether the S3 listing response is truncated."""
    return root.findtext(f"{_namespace(root)}IsTruncated", "false").strip().lower() == "true"


def _next_marker(root: ElementTree.Element, *, file_listing: bool) -> str | None:
    """Return the explicit next marker or the last emitted prefix or key."""
    namespace = _namespace(root)
    marker = root.findtext(f"{namespace}NextMarker")
    if marker and marker.strip():
        return marker.strip()
    if not file_listing:
        prefixes = root.findall(f"{namespace}CommonPrefixes")
        if prefixes:
            return _required_text(prefixes[-1], f"{namespace}Prefix")
    contents = root.findall(f"{namespace}Contents")
    return _required_text(contents[-1], f"{namespace}Key") if contents else None


def _extract_symbol(prefix: str) -> str:
    """Extract the last non-empty path segment from a prefix."""
    return prefix.rstrip("/").rsplit("/", maxsplit=1)[-1]


@dataclass(slots=True, frozen=True)
class ArchiveFile:
    """Metadata for a single file on the Binance public data archive."""

    key: str
    size: int
    last_modified: datetime


SymbolListingResult: TypeAlias = tuple[list[ArchiveFile], str | None]


class ArchiveClient:
    """Client for listing directory contents on the Binance public data archive.

    Communicates with data.binance.vision over its S3-compatible XML listing
    API.  Set ``trust_env=True`` (the default) to honour ``http_proxy`` /
    ``https_proxy`` environment variables.
    """

    def __init__(
        self,
        *,
        timeout_seconds: int | float = S3_HTTP_TIMEOUT_SECONDS,
        trust_env: bool = True,
    ) -> None:
        """Initialize the archive client.

        Args:
            timeout_seconds: Total timeout in seconds for each HTTP request.
            trust_env: When ``True``, the underlying ``aiohttp`` session reads
                proxy configuration from standard environment variables
                (``http_proxy``, ``https_proxy``, ``no_proxy``).
        """
        self.timeout_seconds = timeout_seconds
        self.trust_env = trust_env

    def _create_session(self) -> aiohttp.ClientSession:
        """Create an HTTP session for archive requests."""
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)
        return aiohttp.ClientSession(timeout=timeout, trust_env=self.trust_env)

    async def _fetch_xml(self, session: aiohttp.ClientSession, url: str) -> ElementTree.Element:
        """Fetch and parse a single S3 XML listing page."""
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=1, min=1, max=8),
            retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError)),
            reraise=True,
        ):
            with attempt:
                async with session.get(url) as response:
                    response.raise_for_status()
                    text = await response.text()
                root = ElementTree.fromstring(text)
                if root.tag != f"{_namespace(root)}ListBucketResult":
                    msg = f"Unexpected S3 XML root: {root.tag}"
                    raise ValueError(msg)
                return root

        msg = "unreachable"
        raise RuntimeError(msg)

    async def _iter_listing_pages(
        self,
        session: aiohttp.ClientSession,
        prefix: str,
        *,
        file_listing: bool,
    ) -> AsyncIterator[ElementTree.Element]:
        """Yield pages using the marker fallback appropriate to the requested listing."""
        marker: str | None = None
        while True:
            logger.debug("fetching listing page for prefix={} marker={}", prefix, marker)
            root = await self._fetch_xml(session, _build_listing_url(prefix, marker))
            yield root
            if not _is_truncated(root):
                break
            marker = _next_marker(root, file_listing=file_listing)
            if marker is None:
                break

    async def list_dir(self, session: aiohttp.ClientSession, prefix: str) -> list[str]:
        """List all child prefixes under an S3 directory prefix.

        Automatically follows S3 pagination when the result set exceeds a
        single response page.

        Args:
            session: An active ``aiohttp`` client session.
            prefix: S3 object key prefix to list
                (e.g. ``"data/spot/daily/klines/"``).

        Returns:
            Full S3 prefix strings for each child directory.
        """
        prefixes: list[str] = []
        async for root in self._iter_listing_pages(session, prefix, file_listing=False):
            prefixes.extend(_extract_prefixes(root))

        return prefixes

    async def list_files_in_dir(
        self,
        session: aiohttp.ClientSession,
        prefix: str,
    ) -> list[ArchiveFile]:
        """List all files directly under an S3 directory prefix.

        Files are listed without recursion.  Automatically follows S3
        pagination when the result set exceeds a single response page.

        Args:
            session: An active ``aiohttp`` client session.
            prefix: S3 object key prefix to list
                (e.g. ``"data/futures/um/monthly/fundingRate/BTCUSDT/"``).

        Returns:
            Archive file metadata entries for each file directly under
            the prefix.
        """
        files: list[ArchiveFile] = []
        async for root in self._iter_listing_pages(session, prefix, file_listing=True):
            files.extend(_extract_files(root))

        return files

    async def list_symbols(
        self,
        trade_type: TradeType,
        data_freq: DataFrequency,
        data_type: DataType,
    ) -> list[str]:
        """List available symbols from the Binance archive.

        Queries data.binance.vision's S3 XML API and returns a sorted list
        of symbol directory names under the given path parameters.

        Args:
            trade_type: Market segment (spot, um, cm).
            data_freq: Partition frequency (daily, monthly).
            data_type: Dataset type (klines, fundingRate, etc.).

        Returns:
            Sorted list of symbol names (e.g. ``["BTCUSDT", "ETHUSDT"]``).
        """
        prefix = _build_prefix(trade_type, data_freq, data_type)

        async with self._create_session() as session:
            child_prefixes = await self.list_dir(session, prefix)

        return sorted(_extract_symbol(prefix) for prefix in child_prefixes)

    async def list_symbol_files(
        self,
        trade_type: TradeType,
        data_freq: DataFrequency,
        data_type: DataType,
        symbol: str,
        interval: str | None = None,
        *,
        session: aiohttp.ClientSession | None = None,
    ) -> list[ArchiveFile]:
        """List files for a single symbol directory on the Binance archive.

        Builds the S3 prefix from the requested path parameters and
        delegates to :meth:`list_files_in_dir`.  Callers that run many
        concurrent symbol listings should pass a shared ``session`` so
        every request reuses the same connection pool.

        Args:
            trade_type: Market segment (spot, um, cm).
            data_freq: Partition frequency (daily, monthly).
            data_type: Dataset type (klines, fundingRate, etc.).
            symbol: Symbol directory to list (e.g. ``"BTCUSDT"``).
            interval: Kline interval directory such as ``"1m"``.  Required
                when ``data_type.has_interval_layer`` is ``True`` and must
                be ``None`` otherwise.
            session: Optional pre-existing ``aiohttp`` client session to
                reuse.  When ``None`` a short-lived session is created
                and closed inside this call.  When provided the caller
                owns its lifecycle and this method does not close it.

        Returns:
            Archive file metadata entries for each file under the symbol
            directory.

        Raises:
            ValueError: If ``interval`` does not match
                ``data_type.has_interval_layer``.
        """
        if data_type.has_interval_layer and interval is None:
            msg = "interval is required for kline-class data_type"
            raise ValueError(msg)
        if not data_type.has_interval_layer and interval is not None:
            msg = "interval is not applicable to non-kline data_type"
            raise ValueError(msg)

        prefix = f"{_build_prefix(trade_type, data_freq, data_type)}{symbol}/"
        if interval is not None:
            prefix = f"{prefix}{interval}/"

        if session is None:
            async with self._create_session() as local_session:
                return await self.list_files_in_dir(local_session, prefix)

        return await self.list_files_in_dir(session, prefix)

    async def list_symbol_files_batch(
        self,
        trade_type: TradeType,
        data_freq: DataFrequency,
        data_type: DataType,
        symbols: Sequence[str],
        interval: str | None = None,
        *,
        progress_bar: bool = False,
    ) -> dict[str, SymbolListingResult]:
        """List files for multiple symbols concurrently via a shared session.

        Args:
            trade_type: Market segment (spot, um, cm).
            data_freq: Partition frequency (daily, monthly).
            data_type: Dataset type (klines, fundingRate, etc.).
            symbols: Symbols to list in caller-provided order.
            interval: Kline interval directory such as ``"1m"``. Required
                when ``data_type.has_interval_layer`` is ``True`` and must
                be ``None`` otherwise.
            progress_bar: Whether to render an interactive tqdm progress bar.

        Returns:
            Ordered mapping from each input symbol to ``(files, error)``.
            Successful results store ``([], None)`` for empty directories.
            Failed results store ``([], "<message>")``.
        """
        if not symbols:
            return {}

        async with self._create_session() as session:

            async def _one(symbol: str) -> tuple[str, list[ArchiveFile], str | None]:
                try:
                    files = await self.list_symbol_files(
                        trade_type,
                        data_freq,
                        data_type,
                        symbol,
                        interval,
                        session=session,
                    )
                    return symbol, files, None
                except Exception as exc:
                    return symbol, [], str(exc)

            coroutines = [_one(symbol) for symbol in symbols]
            outcomes: dict[str, SymbolListingResult] = {}
            with make_reporter(
                progress_bar,
                total=len(symbols),
                description="List files",
            ) as reporter:
                for coroutine in asyncio.as_completed(coroutines):
                    symbol, files, error = await coroutine
                    outcomes[symbol] = (files, error)
                    reporter.tick(ProgressEvent(name=symbol, ok=error is None))

        return {symbol: outcomes[symbol] for symbol in symbols}


async def list_symbols(
    trade_type: TradeType,
    data_freq: DataFrequency,
    data_type: DataType,
) -> list[str]:
    """List available symbols using the default archive client.

    Convenience wrapper that creates a temporary :class:`ArchiveClient` and
    delegates to :meth:`ArchiveClient.list_symbols`.

    Args:
        trade_type: Market segment (spot, um, cm).
        data_freq: Partition frequency (daily, monthly).
        data_type: Dataset type (klines, fundingRate, etc.).

    Returns:
        Sorted list of symbol names.
    """
    return await ArchiveClient().list_symbols(trade_type, data_freq, data_type)
