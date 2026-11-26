"""Tests for shared enum helpers."""

import pytest

from binance_datatool.common import DataType, MarketType


def test_market_type_names_values_and_archive_paths() -> None:
    """The common export preserves the supported market values and archive paths."""
    assert [(member.name, member.value, member.s3_path) for member in MarketType] == [
        ("spot", "spot", "spot"),
        ("um", "um", "futures/um"),
        ("cm", "cm", "futures/cm"),
    ]


@pytest.mark.parametrize(
    "module_name",
    [
        "binance_datatool.common",
        "binance_datatool.common.enums",
        "binance_datatool.common.filter",
        "binance_datatool.cli.archive",
    ],
)
def test_trade_type_is_no_longer_importable(module_name: str) -> None:
    """Each former public import path rejects the removed enum name."""
    with pytest.raises(ImportError) as error:
        exec(f"from {module_name} import TradeType", {})
    assert error.value.name == module_name


def test_data_type_has_interval_layer() -> None:
    """Only kline-class data types should require an interval layer."""
    true_members = {
        DataType.klines,
        DataType.index_price_klines,
        DataType.mark_price_klines,
        DataType.premium_index_klines,
    }

    for member in DataType:
        assert member.has_interval_layer is (member in true_members)
