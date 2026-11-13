"""Helpers for inferring symbol metadata from Binance symbol strings.

Each ``infer_*`` function accepts a raw symbol as it appears in the
data.binance.vision S3 listing and returns a typed dataclass, or ``None``
when the symbol cannot be parsed.

Parsing strategy:

1. Strip all trailing ``_SETTLED[N]`` / ``SETTLED[N]`` suffixes that mark
   delisted or gap-split symbols.  These suffixes are removed before any
   further matching so that ``ICPUSDT_SETTLED`` is treated identically
   to ``ICPUSDT``.

2. Walk ``QUOTE_ASSETS`` from longest to shortest suffix.  Longer
   suffixes are tried first so that ``RLUSD`` beats ``USD`` for a
   symbol like ``XRPRLUSD``.

3. For spot and USD-M, apply ``QUOTE_BASE_EXCLUDES`` to handle the
   small set of symbols where greedy long-quote matching disagrees
   with Binance's own ``exchangeInfo`` base/quote split (e.g.
   ``ADAEUR`` must be ``ADA + EUR``, not ``AD + AEUR``).
"""

from __future__ import annotations

import re

from binance_datatool.common.constants import (
    LEVERAGE_EXCLUDES,
    LEVERAGE_SUFFIXES,
    QUOTE_ASSETS,
    QUOTE_BASE_EXCLUDES,
    STABLECOINS,
)
from binance_datatool.common.enums import ContractType
from binance_datatool.common.types import CmSymbolInfo, SpotSymbolInfo, UmSymbolInfo

_SETTLED_SUFFIX_RE = re.compile(r"(?:_?SETTLED\d*)+$")


def _strip_settled_suffix(symbol: str) -> str:
    """Strip all trailing settled suffixes used for delisted or split symbols."""

    return _SETTLED_SUFFIX_RE.sub("", symbol)


def _should_skip_quote_match(symbol: str, quote: str) -> bool:
    """Return whether a greedy quote match should fall back to a shorter quote."""

    rule = QUOTE_BASE_EXCLUDES.get(quote)
    if rule is None:
        return False

    fallback_quote, bases = rule
    return symbol.endswith(fallback_quote) and symbol[: -len(fallback_quote)] in bases


def infer_spot_info(symbol: str) -> SpotSymbolInfo | None:
    """Infer metadata from a spot symbol string.

    Args:
        symbol: Original Binance spot symbol, including any settled suffix.

    Returns:
        Parsed symbol metadata, or ``None`` when no valid quote suffix matches.

    Examples:
        >>> infer_spot_info("BTCUSDT")
        SpotSymbolInfo(symbol='BTCUSDT', base_asset='BTC', quote_asset='USDT',
                       is_leverage=False, is_stable_pair=False)
        >>> infer_spot_info("LUNAUSDT_SETTLED")
        SpotSymbolInfo(symbol='LUNAUSDT_SETTLED', base_asset='LUNA',
                       quote_asset='USDT', is_leverage=False, is_stable_pair=False)
        >>> infer_spot_info("XYZABC")  # no known quote suffix
    """

    cleaned = _strip_settled_suffix(symbol)
    for quote in QUOTE_ASSETS:
        if not cleaned.endswith(quote):
            continue

        base = cleaned[: -len(quote)]
        if not base:
            continue
        if _should_skip_quote_match(cleaned, quote):
            continue

        return SpotSymbolInfo(
            symbol=symbol,
            base_asset=base,
            quote_asset=quote,
            is_leverage=base.endswith(LEVERAGE_SUFFIXES) and base not in LEVERAGE_EXCLUDES,
            is_stable_pair=base in STABLECOINS and quote in STABLECOINS,
        )

    return None


def infer_um_info(symbol: str) -> UmSymbolInfo | None:
    """Infer metadata from a USD-M futures symbol string.

    Args:
        symbol: Original Binance USD-M symbol, including settled suffixes.

    Returns:
        Parsed symbol metadata, or ``None`` when the quote asset cannot be inferred.

    Examples:
        >>> infer_um_info("BTCUSDT")
        UmSymbolInfo(symbol='BTCUSDT', base_asset='BTC', quote_asset='USDT',
                     contract_type=<ContractType.perpetual: 'perpetual'>,
                     is_stable_pair=False)
        >>> infer_um_info("ETHUSDT_240927")
        UmSymbolInfo(symbol='ETHUSDT_240927', base_asset='ETH', quote_asset='USDT',
                     contract_type=<ContractType.delivery: 'delivery'>,
                     is_stable_pair=False)
        >>> infer_um_info("AERGOUSDTSETTLED")
        UmSymbolInfo(symbol='AERGOUSDTSETTLED', base_asset='AERGO',
                     quote_asset='USDT',
                     contract_type=<ContractType.perpetual: 'perpetual'>,
                     is_stable_pair=False)
    """

    cleaned = _strip_settled_suffix(symbol)
    if "_" in cleaned:
        contract_type = ContractType.delivery
        cleaned = cleaned.split("_", maxsplit=1)[0]
    else:
        contract_type = ContractType.perpetual

    for quote in QUOTE_ASSETS:
        if not cleaned.endswith(quote):
            continue

        base = cleaned[: -len(quote)]
        if not base:
            continue
        if _should_skip_quote_match(cleaned, quote):
            continue

        return UmSymbolInfo(
            symbol=symbol,
            base_asset=base,
            quote_asset=quote,
            contract_type=contract_type,
            is_stable_pair=base in STABLECOINS and quote in STABLECOINS,
        )

    return None


def infer_cm_info(symbol: str) -> CmSymbolInfo | None:
    """Infer metadata from a COIN-M futures symbol string.

    Args:
        symbol: Original Binance COIN-M symbol, including settled suffixes.

    Returns:
        Parsed symbol metadata, or ``None`` when the format is invalid.

    Examples:
        >>> infer_cm_info("BTCUSD_PERP")
        CmSymbolInfo(symbol='BTCUSD_PERP', base_asset='BTC', quote_asset='USD',
                     contract_type=<ContractType.perpetual: 'perpetual'>)
        >>> infer_cm_info("ETHUSD_240927")
        CmSymbolInfo(symbol='ETHUSD_240927', base_asset='ETH', quote_asset='USD',
                     contract_type=<ContractType.delivery: 'delivery'>)
        >>> infer_cm_info("BTCUSD")  # missing underscore
    """

    cleaned = _strip_settled_suffix(symbol)
    if "_" not in cleaned:
        return None

    underlying, suffix = cleaned.split("_", maxsplit=1)
    if suffix == "PERP":
        contract_type = ContractType.perpetual
    elif suffix.isdigit():
        contract_type = ContractType.delivery
    else:
        return None

    if not underlying.endswith("USD"):
        return None

    base = underlying[:-3]
    if not base:
        return None

    return CmSymbolInfo(
        symbol=symbol,
        base_asset=base,
        quote_asset="USD",
        contract_type=contract_type,
    )
