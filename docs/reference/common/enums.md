# binance_datatool.common.enums

Enumerations for market segments, data frequencies, dataset types, and contract styles.

**`TradeType(StrEnum)`** — Binance market segment.

| Member | Value | `s3_path` | Description |
|--------|-------|-----------|-------------|
| `spot` | `spot` | `spot` | Spot trading market. |
| `um` | `um` | `futures/um` | USD-M perpetual and delivery futures. |
| `cm` | `cm` | `futures/cm` | COIN-M perpetual and delivery futures. |

**`DataFrequency(StrEnum)`** — Archive partition frequency.

| Member | Value | Description |
|--------|-------|-------------|
| `daily` | `daily` | Files partitioned by day. |
| `monthly` | `monthly` | Files partitioned by month. |

**`DataType(StrEnum)`** — Dataset type on data.binance.vision.

| Member | Value | `has_interval_layer` |
|--------|-------|----------------------|
| `klines` | `klines` | `True` |
| `agg_trades` | `aggTrades` | `False` |
| `trades` | `trades` | `False` |
| `funding_rate` | `fundingRate` | `False` |
| `book_depth` | `bookDepth` | `False` |
| `book_ticker` | `bookTicker` | `False` |
| `index_price_klines` | `indexPriceKlines` | `True` |
| `mark_price_klines` | `markPriceKlines` | `True` |
| `premium_index_klines` | `premiumIndexKlines` | `True` |
| `metrics` | `metrics` | `False` |
| `liquidation_snapshot` | `liquidationSnapshot` | `False` |

> Member names use `snake_case`; values match the S3 path segment exactly.

The `has_interval_layer` property returns `True` for data types whose archive
path includes an interval directory segment (e.g. `1m`, `1h`) between the symbol
and the data files. It supplies the dataset classification used by the shared
[`validate_interval()`](path.md#validate_interval) rule. The CLI, workflow constructors,
and archive client invoke that rule at their existing validation boundaries.

**`ContractType(StrEnum)`** — Futures contract settlement style.

| Member | Value | Description |
|--------|-------|-------------|
| `perpetual` | `perpetual` | Perpetual futures contract. |
| `delivery` | `delivery` | Dated delivery futures contract. |

---

See also: [constants](constants.md) | [types](types.md) | [Architecture](../../architecture.md)
