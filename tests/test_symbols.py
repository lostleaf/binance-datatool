"""Tests for symbol inference helpers in ``binance_datatool.common``."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from binance_datatool.archive.client import ArchiveClient
from binance_datatool.common import (
    QUOTE_ASSETS,
    CmSymbolInfo,
    ContractType,
    DataFrequency,
    DataType,
    SpotSymbolInfo,
    TradeType,
    UmSymbolInfo,
    infer_cm_info,
    infer_spot_info,
    infer_um_info,
)

ARCHIVE_ALLOWLIST: dict[TradeType, set[str]] = {
    TradeType.spot: {"这是测试币456"},
    TradeType.um: set(),
    TradeType.cm: set(),
}


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        (
            "BTCUSDT",
            SpotSymbolInfo(
                symbol="BTCUSDT",
                base_asset="BTC",
                quote_asset="USDT",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "ETHBTC",
            SpotSymbolInfo(
                symbol="ETHBTC",
                base_asset="ETH",
                quote_asset="BTC",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "USDTKZT",
            SpotSymbolInfo(
                symbol="USDTKZT",
                base_asset="USDT",
                quote_asset="KZT",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "ASTERTHB",
            SpotSymbolInfo(
                symbol="ASTERTHB",
                base_asset="ASTER",
                quote_asset="THB",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "USDCAED",
            SpotSymbolInfo(
                symbol="USDCAED",
                base_asset="USDC",
                quote_asset="AED",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "BNBUPUSDT",
            SpotSymbolInfo(
                symbol="BNBUPUSDT",
                base_asset="BNBUP",
                quote_asset="USDT",
                is_leverage=True,
                is_stable_pair=False,
            ),
        ),
        (
            "BTCDOWNUSDT",
            SpotSymbolInfo(
                symbol="BTCDOWNUSDT",
                base_asset="BTCDOWN",
                quote_asset="USDT",
                is_leverage=True,
                is_stable_pair=False,
            ),
        ),
        (
            "JUPUSDT",
            SpotSymbolInfo(
                symbol="JUPUSDT",
                base_asset="JUP",
                quote_asset="USDT",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "SYRUPUSDT",
            SpotSymbolInfo(
                symbol="SYRUPUSDT",
                base_asset="SYRUP",
                quote_asset="USDT",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "USDCUSDT",
            SpotSymbolInfo(
                symbol="USDCUSDT",
                base_asset="USDC",
                quote_asset="USDT",
                is_leverage=False,
                is_stable_pair=True,
            ),
        ),
        (
            "USDSBUSDT",
            SpotSymbolInfo(
                symbol="USDSBUSDT",
                base_asset="USDSB",
                quote_asset="USDT",
                is_leverage=False,
                is_stable_pair=True,
            ),
        ),
        (
            "SUSDUSDT",
            SpotSymbolInfo(
                symbol="SUSDUSDT",
                base_asset="SUSD",
                quote_asset="USDT",
                is_leverage=False,
                is_stable_pair=True,
            ),
        ),
        (
            "BTCU",
            SpotSymbolInfo(
                symbol="BTCU",
                base_asset="BTC",
                quote_asset="U",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "BTCEURI",
            SpotSymbolInfo(
                symbol="BTCEURI",
                base_asset="BTC",
                quote_asset="EURI",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "ADAEUR",
            SpotSymbolInfo(
                symbol="ADAEUR",
                base_asset="ADA",
                quote_asset="EUR",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "XRPRLUSD",
            SpotSymbolInfo(
                symbol="XRPRLUSD",
                base_asset="XRP",
                quote_asset="RLUSD",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "BTCUSD1",
            SpotSymbolInfo(
                symbol="BTCUSD1",
                base_asset="BTC",
                quote_asset="USD1",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "ARBIDR",
            SpotSymbolInfo(
                symbol="ARBIDR",
                base_asset="ARB",
                quote_asset="IDR",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "BNBUSD",
            SpotSymbolInfo(
                symbol="BNBUSD",
                base_asset="BNB",
                quote_asset="USD",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "USDTUSD",
            SpotSymbolInfo(
                symbol="USDTUSD",
                base_asset="USDT",
                quote_asset="USD",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "BTCUSDSOLD",
            SpotSymbolInfo(
                symbol="BTCUSDSOLD",
                base_asset="BTC",
                quote_asset="USDSOLD",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "USDSBUSDSOLD",
            SpotSymbolInfo(
                symbol="USDSBUSDSOLD",
                base_asset="USDSB",
                quote_asset="USDSOLD",
                is_leverage=False,
                is_stable_pair=True,
            ),
        ),
        (
            "BTCPAX",
            SpotSymbolInfo(
                symbol="BTCPAX",
                base_asset="BTC",
                quote_asset="PAX",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "LUNAUSDT_SETTLED1SETTLED2_SETTLED",
            SpotSymbolInfo(
                symbol="LUNAUSDT_SETTLED1SETTLED2_SETTLED",
                base_asset="LUNA",
                quote_asset="USDT",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "LUNAUSDT_SETTLED",
            SpotSymbolInfo(
                symbol="LUNAUSDT_SETTLED",
                base_asset="LUNA",
                quote_asset="USDT",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "LUNAUSDT_SETTLED1",
            SpotSymbolInfo(
                symbol="LUNAUSDT_SETTLED1",
                base_asset="LUNA",
                quote_asset="USDT",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
        (
            "币安人生USDT",
            SpotSymbolInfo(
                symbol="币安人生USDT",
                base_asset="币安人生",
                quote_asset="USDT",
                is_leverage=False,
                is_stable_pair=False,
            ),
        ),
    ],
)
def test_infer_spot_info(symbol: str, expected: SpotSymbolInfo) -> None:
    """Spot symbol inference should return stable dataclass results."""

    assert infer_spot_info(symbol) == expected


@pytest.mark.parametrize("symbol", ["XYZABC", "USDT"])
def test_infer_spot_info_returns_none_for_invalid_symbols(symbol: str) -> None:
    """Spot inference should reject unmatched or empty-base symbols."""

    assert infer_spot_info(symbol) is None


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        (
            "BTCUSDT",
            UmSymbolInfo(
                symbol="BTCUSDT",
                base_asset="BTC",
                quote_asset="USDT",
                contract_type=ContractType.perpetual,
                is_stable_pair=False,
            ),
        ),
        (
            "ETHUSDT_240927",
            UmSymbolInfo(
                symbol="ETHUSDT_240927",
                base_asset="ETH",
                quote_asset="USDT",
                contract_type=ContractType.delivery,
                is_stable_pair=False,
            ),
        ),
        (
            "AERGOUSDTSETTLEDSETTLED",
            UmSymbolInfo(
                symbol="AERGOUSDTSETTLEDSETTLED",
                base_asset="AERGO",
                quote_asset="USDT",
                contract_type=ContractType.perpetual,
                is_stable_pair=False,
            ),
        ),
        (
            "AERGOUSDTSETTLED",
            UmSymbolInfo(
                symbol="AERGOUSDTSETTLED",
                base_asset="AERGO",
                quote_asset="USDT",
                contract_type=ContractType.perpetual,
                is_stable_pair=False,
            ),
        ),
        (
            "ICPUSDT_SETTLED_SETTLED1",
            UmSymbolInfo(
                symbol="ICPUSDT_SETTLED_SETTLED1",
                base_asset="ICP",
                quote_asset="USDT",
                contract_type=ContractType.perpetual,
                is_stable_pair=False,
            ),
        ),
        (
            "ETHUSDT_240927_SETTLEDSETTLED",
            UmSymbolInfo(
                symbol="ETHUSDT_240927_SETTLEDSETTLED",
                base_asset="ETH",
                quote_asset="USDT",
                contract_type=ContractType.delivery,
                is_stable_pair=False,
            ),
        ),
        (
            "ICPUSDT_SETTLED",
            UmSymbolInfo(
                symbol="ICPUSDT_SETTLED",
                base_asset="ICP",
                quote_asset="USDT",
                contract_type=ContractType.perpetual,
                is_stable_pair=False,
            ),
        ),
        (
            "ICPUSDT_SETTLED1",
            UmSymbolInfo(
                symbol="ICPUSDT_SETTLED1",
                base_asset="ICP",
                quote_asset="USDT",
                contract_type=ContractType.perpetual,
                is_stable_pair=False,
            ),
        ),
    ],
)
def test_infer_um_info(symbol: str, expected: UmSymbolInfo) -> None:
    """USD-M symbol inference should parse contract type and assets."""

    assert infer_um_info(symbol) == expected


@pytest.mark.parametrize(
    ("symbol", "expected"),
    [
        (
            "BTCUSD_PERP",
            CmSymbolInfo(
                symbol="BTCUSD_PERP",
                base_asset="BTC",
                quote_asset="USD",
                contract_type=ContractType.perpetual,
            ),
        ),
        (
            "ETHUSD_240927",
            CmSymbolInfo(
                symbol="ETHUSD_240927",
                base_asset="ETH",
                quote_asset="USD",
                contract_type=ContractType.delivery,
            ),
        ),
        (
            "BTCUSD_PERP_SETTLED2_SETTLED",
            CmSymbolInfo(
                symbol="BTCUSD_PERP_SETTLED2_SETTLED",
                base_asset="BTC",
                quote_asset="USD",
                contract_type=ContractType.perpetual,
            ),
        ),
        (
            "BTCUSD_PERP_SETTLED2",
            CmSymbolInfo(
                symbol="BTCUSD_PERP_SETTLED2",
                base_asset="BTC",
                quote_asset="USD",
                contract_type=ContractType.perpetual,
            ),
        ),
    ],
)
def test_infer_cm_info(symbol: str, expected: CmSymbolInfo) -> None:
    """COIN-M symbol inference should parse perp and delivery contracts."""

    assert infer_cm_info(symbol) == expected


@pytest.mark.parametrize("symbol", ["BTCUSD", "BTCUSD_FOO", "USD_PERP"])
def test_infer_cm_info_returns_none_for_invalid_symbols(symbol: str) -> None:
    """COIN-M inference should reject malformed symbols."""

    assert infer_cm_info(symbol) is None


def test_quote_assets_are_sorted_and_unique() -> None:
    """Quote asset suffixes should preserve the matching invariant."""

    assert len(QUOTE_ASSETS) == len(set(QUOTE_ASSETS))
    assert tuple(sorted(QUOTE_ASSETS, key=lambda quote: (-len(quote), quote))) == QUOTE_ASSETS


@pytest.mark.integration
@pytest.mark.asyncio
async def test_archive_symbols_are_inferable_with_explicit_allowlist() -> None:
    """Archive symbol listings should only contain known unmatched exceptions."""

    client = ArchiveClient()
    infer_fns = {
        TradeType.spot: infer_spot_info,
        TradeType.um: infer_um_info,
        TradeType.cm: infer_cm_info,
    }

    for trade_type, infer_fn in infer_fns.items():
        symbols = await client.list_symbols(trade_type, DataFrequency.daily, DataType.klines)
        unmatched = {symbol for symbol in symbols if infer_fn(symbol) is None}
        assert unmatched == ARCHIVE_ALLOWLIST[trade_type]


def _expected_contract_type(payload: dict[str, Any]) -> ContractType:
    """Map exchangeInfo contract payloads to the local contract type enum."""

    return (
        ContractType.perpetual
        if "PERPETUAL" in str(payload.get("contractType"))
        else ContractType.delivery
    )


@pytest.mark.integration
def test_exchange_info_matches_symbol_inference() -> None:
    """exchangeInfo should agree with local symbol parsing for online markets."""

    binance = pytest.importorskip("binance")
    client = None
    try:
        client = binance.Client()
        spot_info = client.get_exchange_info()
        for payload in spot_info["symbols"]:
            result = infer_spot_info(payload["symbol"])
            assert result is not None
            assert result.base_asset == payload["baseAsset"]
            assert result.quote_asset == payload["quoteAsset"]

        um_info = client.futures_exchange_info()
        for payload in um_info["symbols"]:
            result = infer_um_info(payload["symbol"])
            assert result is not None
            assert result.base_asset == payload["baseAsset"]
            assert result.quote_asset == payload["quoteAsset"]
            assert result.contract_type == _expected_contract_type(payload)

        cm_info = client.futures_coin_exchange_info()
        for payload in cm_info["symbols"]:
            result = infer_cm_info(payload["symbol"])
            assert result is not None
            assert result.base_asset == payload["baseAsset"]
            assert result.quote_asset == payload["quoteAsset"]
            assert result.contract_type == _expected_contract_type(payload)
    except binance.BinanceAPIException as error:
        if error.status_code in {403, 451}:
            pytest.skip(f"exchangeInfo access refused (HTTP {error.status_code}): {error}")
        raise
    finally:
        if client is not None:
            client.close_connection()


@pytest.mark.parametrize("status_code", [403, 451])
def test_exchange_info_comparison_skips_access_refused_during_construction(
    monkeypatch: pytest.MonkeyPatch, status_code: int
) -> None:
    """An endpoint refusal from the SDK's initial ping should report a skip."""
    binance = pytest.importorskip("binance")
    response = SimpleNamespace(text='{"code": 0, "msg": "Restricted location"}')
    error = binance.BinanceAPIException(response, status_code, response.text)

    def refused_client() -> None:
        raise error

    monkeypatch.setattr(binance, "Client", refused_client)

    with pytest.raises(pytest.skip.Exception) as skipped:
        test_exchange_info_matches_symbol_inference()
    assert str(status_code) in str(skipped.value)
    assert "Restricted location" in str(skipped.value)


@pytest.mark.parametrize("status_code", [403, 451])
@pytest.mark.parametrize(
    "endpoint", ["get_exchange_info", "futures_exchange_info", "futures_coin_exchange_info"]
)
def test_exchange_info_comparison_skips_access_refused_requests_and_closes_client(
    monkeypatch: pytest.MonkeyPatch, status_code: int, endpoint: str
) -> None:
    """Only the comparison should skip when any exchangeInfo endpoint refuses access."""
    binance = pytest.importorskip("binance")
    response = SimpleNamespace(text='{"code": 0, "msg": "Restricted location"}')
    error = binance.BinanceAPIException(response, status_code, response.text)
    closed = []
    client = SimpleNamespace(
        get_exchange_info=lambda: {"symbols": []},
        futures_exchange_info=lambda: {"symbols": []},
        futures_coin_exchange_info=lambda: {"symbols": []},
        close_connection=lambda: closed.append(True),
    )

    def refused_request() -> None:
        raise error

    monkeypatch.setattr(client, endpoint, refused_request)
    monkeypatch.setattr(binance, "Client", lambda: client)

    with pytest.raises(pytest.skip.Exception) as skipped:
        test_exchange_info_matches_symbol_inference()
    assert str(status_code) in str(skipped.value)
    assert "Restricted location" in str(skipped.value)
    assert closed == [True]


@pytest.mark.parametrize("during_construction", [True, False])
@pytest.mark.parametrize("failure", ["server-error", "unrelated-error"])
def test_exchange_info_comparison_preserves_other_errors(
    monkeypatch: pytest.MonkeyPatch, during_construction: bool, failure: str
) -> None:
    """Server errors and unrelated failures should remain failures at either stage."""
    binance = pytest.importorskip("binance")
    response = SimpleNamespace(text='{"code": -1000, "msg": "Server error"}')
    error = (
        binance.BinanceAPIException(response, 500, response.text)
        if failure == "server-error"
        else RuntimeError("Unexpected failure")
    )
    closed = []

    def fail() -> None:
        raise error

    client = SimpleNamespace(get_exchange_info=fail, close_connection=lambda: closed.append(True))
    monkeypatch.setattr(binance, "Client", fail if during_construction else lambda: client)

    with pytest.raises(type(error)) as raised:
        test_exchange_info_matches_symbol_inference()
    assert raised.value is error
    assert closed == ([] if during_construction else [True])


def test_exchange_info_comparison_preserves_inference_mismatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid response disagreeing with inference should still fail the comparison."""
    binance = pytest.importorskip("binance")
    closed = []
    client = SimpleNamespace(
        get_exchange_info=lambda: {
            "symbols": [{"symbol": "BTCUSDT", "baseAsset": "UNEXPECTED", "quoteAsset": "USDT"}]
        },
        close_connection=lambda: closed.append(True),
    )
    monkeypatch.setattr(binance, "Client", lambda: client)

    with pytest.raises(AssertionError):
        test_exchange_info_matches_symbol_inference()
    assert closed == [True]
