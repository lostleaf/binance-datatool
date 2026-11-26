# Archive Path Structure

S3 directory hierarchy used by data.binance.vision. For the XML listing protocol
that queries these paths, see [S3 protocol](s3-protocol.md).

## Top-level Tree

```
data/
├── spot/                       # Spot market
│   ├── daily/
│   └── monthly/
├── futures/
│   ├── um/                     # USDⓈ-M futures
│   │   ├── daily/
│   │   └── monthly/
│   └── cm/                     # COIN-M futures
│       ├── daily/
│       └── monthly/
└── option/                     # Options (BVOLIndex, EOHSummary — not covered by this tool)
    └── daily/
```

The first two path segments map directly to `MarketType.s3_path` and `DataFrequency`:

| `MarketType` | S3 path segment |
|-------------|-----------------|
| `spot` | `data/spot/` |
| `um` | `data/futures/um/` |
| `cm` | `data/futures/cm/` |

## Data Type Availability

The next path segment is the `DataType` value. For published market types and partition
combinations, see [datasets by market type](../../../skills/binance-datatool/references/archive-availability.md#datasets-by-market-type).

## Symbol Layer

`MarketType.s3_path` supplies the market path in `data/{market_path}/{data_freq}/{data_type}/{symbol}/`.

### Naming conventions

| Market | Contract style | Symbol format |
|--------|----------------|---------------|
| Spot | — | `{BASE}{QUOTE}`, e.g. `BTCUSDT` |
| USDⓈ-M | Perpetual | `{BASE}{QUOTE}`, e.g. `BTCUSDT` |
| USDⓈ-M | Delivery | `{BASE}{QUOTE}_{YYMMDD}`, e.g. `BTCUSDT_260925` |
| COIN-M | Perpetual | `{BASE}USD_PERP` |
| COIN-M | Delivery | `{BASE}USD_{YYMMDD}` |

**Notes:**

- Some symbols have numeric prefixes: `1000BONKUSDT`, `1000000MOGUSDT`, `0GUSDT`.
- A `SETTLED` suffix marks delisted contracts: `CVCUSDTSETTLED`, `ICPUSDTSETTLED`.
- For dataset-specific pair and contract names, see
  [COIN-M price kline symbols](../../../skills/binance-datatool/references/archive-availability.md#coin-m-price-kline-symbols).

## Interval Layer

When `DataType.has_interval_layer` is true, the interval directory sits between the
symbol and the data files.

### Available intervals

For interval values and their observed partitions, see
[Kline intervals](../../../skills/binance-datatool/references/archive-availability.md#kline-intervals).

## File Naming

Each file covers a single time partition and sits directly under the symbol (or interval)
directory.

**daily files** (date format `YYYY-MM-DD`):

| Has interval layer | Pattern | Example |
|:------------------:|---------|---------|
| Yes | `{SYMBOL}-{interval}-{YYYY-MM-DD}.zip` | `BTCUSDT-1m-2024-01-01.zip` |
| No | `{SYMBOL}-{data_type}-{YYYY-MM-DD}.zip` | `BTCUSDT-aggTrades-2024-01-01.zip` |

**monthly files** (date format `YYYY-MM`):

| Has interval layer | Pattern | Example |
|:------------------:|---------|---------|
| Yes | `{SYMBOL}-{interval}-{YYYY-MM}.zip` | `BTCUSDT-1m-2024-01.zip` |
| No | `{SYMBOL}-{data_type}-{YYYY-MM}.zip` | `BTCUSDT-fundingRate-2024-01.zip` |

### Sidecar files

Every `.zip` file may have a companion checksum file:

| Suffix | Description |
|--------|-------------|
| `.zip.CHECKSUM` | SHA256 hash in the format `{hash}  {filename}`. |

## Path Hierarchy Summary

Kline-class data types (`has_interval_layer=True`):

```
data / {market_path} / {data_freq} / {data_type} / {symbol} / {interval} / {filename}.zip
```

Non-kline data types:

```
data / {market_path} / {data_freq} / {data_type} / {symbol} / {filename}.zip
```

### Full path examples

```
data/spot/daily/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01-01.zip
data/spot/monthly/klines/BTCUSDT/1m/BTCUSDT-1m-2024-01.zip
data/futures/um/daily/markPriceKlines/BTCUSDT/5m/BTCUSDT-5m-2024-01-01.zip
data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2024-01.zip
```

---

See also: [Enums](../common/enums.md) | [S3 protocol](s3-protocol.md) | [Symbol directory](symbol_dir.md) | [Architecture](../../architecture.md)
