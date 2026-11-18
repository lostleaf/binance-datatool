"""Tests for common symbol filters."""

from __future__ import annotations

from binance_datatool.common import (
    CmSymbolFilter,
    CmSymbolInfo,
    ContractType,
    SpotSymbolFilter,
    SpotSymbolInfo,
    TradeType,
    UmSymbolFilter,
    UmSymbolInfo,
    build_symbol_filter,
)


def test_spot_symbol_filter_matches_all_supported_dimensions() -> None:
    """Spot filters should honor quote, leverage, and stable-pair constraints."""
    regular = SpotSymbolInfo(
        symbol="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
        is_leverage=False,
        is_stable_pair=False,
    )
    leverage = SpotSymbolInfo(
        symbol="BNBUPUSDT",
        base_asset="BNBUP",
        quote_asset="USDT",
        is_leverage=True,
        is_stable_pair=False,
    )
    stable_pair = SpotSymbolInfo(
        symbol="USDCUSDT",
        base_asset="USDC",
        quote_asset="USDT",
        is_leverage=False,
        is_stable_pair=True,
    )

    assert SpotSymbolFilter().matches(regular) is True
    assert SpotSymbolFilter(quote_assets=frozenset({"USDT"})).matches(regular) is True
    assert SpotSymbolFilter(quote_assets=frozenset({"BTC"})).matches(regular) is False
    assert SpotSymbolFilter(exclude_leverage=True).matches(leverage) is False
    assert SpotSymbolFilter(exclude_stable_pairs=True).matches(stable_pair) is False


def test_spot_symbol_filter_call_preserves_order_and_handles_edge_cases() -> None:
    """Spot batch filtering should preserve input order and accept empty input."""
    symbols = [
        SpotSymbolInfo(
            symbol="ETHBTC",
            base_asset="ETH",
            quote_asset="BTC",
            is_leverage=False,
            is_stable_pair=False,
        ),
        SpotSymbolInfo(
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            is_leverage=False,
            is_stable_pair=False,
        ),
        SpotSymbolInfo(
            symbol="BNBUPUSDT",
            base_asset="BNBUP",
            quote_asset="USDT",
            is_leverage=True,
            is_stable_pair=False,
        ),
    ]
    symbol_filter = SpotSymbolFilter(
        quote_assets=frozenset({"USDT"}),
        exclude_leverage=True,
    )

    assert symbol_filter(symbols) == [symbols[1]]
    assert symbol_filter([]) == []
    assert SpotSymbolFilter(quote_assets=frozenset({"EUR"}))(symbols) == []


def test_um_symbol_filter_matches_quote_contract_type_and_stable_pair() -> None:
    """USDⓈ-M filters should honor quote, contract type, and stable-pair constraints."""
    perpetual = UmSymbolInfo(
        symbol="BTCUSDT",
        base_asset="BTC",
        quote_asset="USDT",
        contract_type=ContractType.perpetual,
        is_stable_pair=False,
    )
    delivery = UmSymbolInfo(
        symbol="ETHUSDT_240927",
        base_asset="ETH",
        quote_asset="USDT",
        contract_type=ContractType.delivery,
        is_stable_pair=False,
    )
    stable_pair = UmSymbolInfo(
        symbol="USDCUSDT",
        base_asset="USDC",
        quote_asset="USDT",
        contract_type=ContractType.perpetual,
        is_stable_pair=True,
    )

    assert UmSymbolFilter().matches(perpetual) is True
    assert UmSymbolFilter(quote_assets=frozenset({"USDT"})).matches(perpetual) is True
    assert UmSymbolFilter(quote_assets=frozenset({"BTC"})).matches(perpetual) is False
    assert UmSymbolFilter(contract_type=ContractType.perpetual).matches(perpetual) is True
    assert UmSymbolFilter(contract_type=ContractType.perpetual).matches(delivery) is False
    assert UmSymbolFilter(exclude_stable_pairs=True).matches(stable_pair) is False


def test_um_symbol_filter_call_handles_empty_and_all_filtered() -> None:
    """USDⓈ-M batch filtering should preserve order and support empty results."""
    symbols = [
        UmSymbolInfo(
            symbol="BTCUSDT",
            base_asset="BTC",
            quote_asset="USDT",
            contract_type=ContractType.perpetual,
            is_stable_pair=False,
        ),
        UmSymbolInfo(
            symbol="ETHUSDT_240927",
            base_asset="ETH",
            quote_asset="USDT",
            contract_type=ContractType.delivery,
            is_stable_pair=False,
        ),
    ]

    assert UmSymbolFilter(contract_type=ContractType.delivery)(symbols) == [symbols[1]]
    assert UmSymbolFilter(contract_type=ContractType.delivery)([]) == []
    assert UmSymbolFilter(quote_assets=frozenset({"BTC"}))(symbols) == []


def test_cm_symbol_filter_matches_contract_type() -> None:
    """COIN-M filters should only depend on contract type."""
    perpetual = CmSymbolInfo(
        symbol="BTCUSD_PERP",
        base_asset="BTC",
        quote_asset="USD",
        contract_type=ContractType.perpetual,
    )
    delivery = CmSymbolInfo(
        symbol="ETHUSD_240927",
        base_asset="ETH",
        quote_asset="USD",
        contract_type=ContractType.delivery,
    )

    assert CmSymbolFilter().matches(perpetual) is True
    assert CmSymbolFilter(contract_type=ContractType.perpetual).matches(perpetual) is True
    assert CmSymbolFilter(contract_type=ContractType.perpetual).matches(delivery) is False
    assert CmSymbolFilter(contract_type=ContractType.delivery)([perpetual, delivery]) == [delivery]
    assert CmSymbolFilter(contract_type=ContractType.delivery)([]) == []


def test_build_symbol_filter_returns_none_when_no_applicable_constraints_are_enabled() -> None:
    """The builder should skip creating filters when every relevant option is a no-op."""
    assert (
        build_symbol_filter(
            trade_type=TradeType.spot,
            quote_assets=None,
            exclude_leverage=False,
            exclude_stable_pairs=False,
            contract_type=None,
        )
        is None
    )
    assert (
        build_symbol_filter(
            trade_type=TradeType.um,
            quote_assets=None,
            exclude_leverage=True,
            exclude_stable_pairs=False,
            contract_type=None,
        )
        is None
    )
    assert (
        build_symbol_filter(
            trade_type=TradeType.cm,
            quote_assets=frozenset({"USDT"}),
            exclude_leverage=True,
            exclude_stable_pairs=True,
            contract_type=None,
        )
        is None
    )


def test_build_symbol_filter_returns_market_specific_filter_types() -> None:
    """The builder should produce the expected filter dataclass for each market."""
    spot_filter = build_symbol_filter(
        trade_type=TradeType.spot,
        quote_assets=frozenset({"USDT"}),
        exclude_leverage=True,
        exclude_stable_pairs=True,
        contract_type=ContractType.delivery,
    )
    um_filter = build_symbol_filter(
        trade_type=TradeType.um,
        quote_assets=frozenset({"USDT"}),
        exclude_leverage=True,
        exclude_stable_pairs=True,
        contract_type=ContractType.perpetual,
    )
    cm_filter = build_symbol_filter(
        trade_type=TradeType.cm,
        quote_assets=frozenset({"USDT"}),
        exclude_leverage=True,
        exclude_stable_pairs=True,
        contract_type=ContractType.delivery,
    )

    assert isinstance(spot_filter, SpotSymbolFilter)
    assert spot_filter.quote_assets == frozenset({"USDT"})
    assert spot_filter.exclude_leverage is True
    assert spot_filter.exclude_stable_pairs is True

    assert isinstance(um_filter, UmSymbolFilter)
    assert um_filter.quote_assets == frozenset({"USDT"})
    assert um_filter.contract_type is ContractType.perpetual
    assert um_filter.exclude_stable_pairs is True

    assert isinstance(cm_filter, CmSymbolFilter)
    assert cm_filter.contract_type is ContractType.delivery
