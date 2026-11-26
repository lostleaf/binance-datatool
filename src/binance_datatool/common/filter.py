"""Typed symbol filters shared across archive workflows and CLI entrypoints."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from binance_datatool.common.enums import MarketType

if TYPE_CHECKING:
    from collections.abc import Iterable

    from binance_datatool.common.enums import ContractType
    from binance_datatool.common.types import CmSymbolInfo, SpotSymbolInfo, UmSymbolInfo


@dataclass(slots=True)
class SpotSymbolFilter:
    """Filter for spot symbols."""

    quote_assets: frozenset[str] | None = None
    exclude_leverage: bool = False
    exclude_stable_pairs: bool = False

    def matches(self, info: SpotSymbolInfo) -> bool:
        """Return whether the symbol matches the configured spot filters.

        Args:
            info: Parsed spot symbol metadata.

        Returns:
            ``True`` when the symbol passes every enabled filter.
        """
        if self.quote_assets is not None and info.quote_asset not in self.quote_assets:
            return False
        if self.exclude_leverage and info.is_leverage:
            return False
        return not (self.exclude_stable_pairs and info.is_stable_pair)

    def __call__(self, infos: Iterable[SpotSymbolInfo]) -> list[SpotSymbolInfo]:
        """Return the matching spot symbols in input order."""
        return [info for info in infos if self.matches(info)]


@dataclass(slots=True)
class UmSymbolFilter:
    """Filter for USDⓈ-M futures symbols."""

    quote_assets: frozenset[str] | None = None
    contract_type: ContractType | None = None
    exclude_stable_pairs: bool = False

    def matches(self, info: UmSymbolInfo) -> bool:
        """Return whether the symbol matches the configured USDⓈ-M filters.

        Args:
            info: Parsed USDⓈ-M futures symbol metadata.

        Returns:
            ``True`` when the symbol passes every enabled filter.
        """
        if self.quote_assets is not None and info.quote_asset not in self.quote_assets:
            return False
        if self.contract_type is not None and info.contract_type is not self.contract_type:
            return False
        return not (self.exclude_stable_pairs and info.is_stable_pair)

    def __call__(self, infos: Iterable[UmSymbolInfo]) -> list[UmSymbolInfo]:
        """Return the matching USDⓈ-M futures symbols in input order."""
        return [info for info in infos if self.matches(info)]


@dataclass(slots=True)
class CmSymbolFilter:
    """Filter for COIN-M futures symbols."""

    contract_type: ContractType | None = None

    def matches(self, info: CmSymbolInfo) -> bool:
        """Return whether the symbol matches the configured COIN-M filters.

        Args:
            info: Parsed COIN-M futures symbol metadata.

        Returns:
            ``True`` when the symbol passes every enabled filter.
        """
        return not (self.contract_type is not None and info.contract_type is not self.contract_type)

    def __call__(self, infos: Iterable[CmSymbolInfo]) -> list[CmSymbolInfo]:
        """Return the matching COIN-M futures symbols in input order."""
        return [info for info in infos if self.matches(info)]


SymbolFilter = SpotSymbolFilter | UmSymbolFilter | CmSymbolFilter


def build_symbol_filter(
    market_type: MarketType,
    *,
    quote_assets: frozenset[str] | None,
    exclude_leverage: bool,
    exclude_stable_pairs: bool,
    contract_type: ContractType | None,
) -> SymbolFilter | None:
    """Build the market-specific symbol filter.

    Args:
        market_type: Market type for the symbol listing.
        quote_assets: Optional normalized quote-asset allowlist.
        exclude_leverage: Whether leveraged spot tokens should be excluded.
        exclude_stable_pairs: Whether stablecoin pairs should be excluded.
        contract_type: Optional futures contract-type constraint.

    Returns:
        A market-specific symbol filter, or ``None`` when no applicable
        filters are enabled for the given market.
    """
    match market_type:
        case MarketType.spot:
            if quote_assets is None and not exclude_leverage and not exclude_stable_pairs:
                return None
            return SpotSymbolFilter(
                quote_assets=quote_assets,
                exclude_leverage=exclude_leverage,
                exclude_stable_pairs=exclude_stable_pairs,
            )
        case MarketType.um:
            if quote_assets is None and contract_type is None and not exclude_stable_pairs:
                return None
            return UmSymbolFilter(
                quote_assets=quote_assets,
                contract_type=contract_type,
                exclude_stable_pairs=exclude_stable_pairs,
            )
        case MarketType.cm:
            if contract_type is None:
                return None
            return CmSymbolFilter(contract_type=contract_type)
