# binance_datatool.common.filter

Typed symbol filters for inferred Binance symbol metadata.

The package-level `binance_datatool.common` re-exports every public filter
type, so most imports can use:

```python
from binance_datatool.common import SpotSymbolFilter, build_symbol_filter
```

Filters operate on parsed `SymbolInfo` values, not raw symbol strings. Callers
infer first, then filter.

Each filter class supports two call shapes:

- `filter_.matches(info) -> bool`
- `filter_(infos) -> list[...]`

All three filter classes are `@dataclass(slots=True)` without `frozen=True`.

## `SpotSymbolFilter`

```python
from binance_datatool.common import SpotSymbolFilter

spot_filter = SpotSymbolFilter(
    quote_assets=frozenset({"USDT"}),
    exclude_leverage=True,
    exclude_stable_pairs=True,
)
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `quote_assets` | `frozenset[str] \| None` | `None` | Quote-asset allowlist. `None` disables the check. |
| `exclude_leverage` | `bool` | `False` | Reject symbols where `info.is_leverage` is true. |
| `exclude_stable_pairs` | `bool` | `False` | Reject symbols where `info.is_stable_pair` is true. |

## `UmSymbolFilter`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `quote_assets` | `frozenset[str] \| None` | `None` | Quote-asset allowlist. |
| `contract_type` | `ContractType \| None` | `None` | Restrict to `perpetual` or `delivery` contracts. |
| `exclude_stable_pairs` | `bool` | `False` | Reject stablecoin pairs. |

## `CmSymbolFilter`

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `contract_type` | `ContractType \| None` | `None` | Restrict to `perpetual` or `delivery` contracts. |

## `SymbolFilter`

Union alias `SpotSymbolFilter | UmSymbolFilter | CmSymbolFilter`.

## `build_symbol_filter()`

```python
from binance_datatool.common import MarketType, build_symbol_filter

symbol_filter = build_symbol_filter(
    market_type=MarketType.spot,
    quote_assets=frozenset({"USDT"}),
    exclude_leverage=True,
    exclude_stable_pairs=False,
    contract_type=None,
)
```

Constructs the market-specific filter class for a given `market_type` using only
the arguments that apply to that market. Arguments that do not apply are
silently ignored, for example:

- `exclude_leverage` for USDⓈ-M and COIN-M
- `quote_assets` for COIN-M

Returns `None` when every applicable argument is at its no-op default, so
callers can pass the result straight to `ArchiveListSymbolsWorkflow` and
short-circuit filtering when no constraints are active.

---

See also: [Common symbols](symbols.md) | [Common types](types.md) | [Architecture](../../architecture.md)
