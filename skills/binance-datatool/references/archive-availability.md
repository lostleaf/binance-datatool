# Archive availability

## Datasets by market type

Each cell gives the published archive partitions (`--freq`) for a dataset (`--type`).
A dash marks a combination with no observed directory.

| Dataset | Spot (`spot`) | USDⓈ-Margined (USDⓈ-M, `um`) | COIN-Margined (COIN-M, `cm`) |
|---------|---------------|--------------|---------------|
| `klines`, `aggTrades`, `trades` | daily, monthly | daily, monthly | daily, monthly |
| `bookTicker`, `indexPriceKlines`, `markPriceKlines`, `premiumIndexKlines` | — | daily, monthly | daily, monthly |
| `fundingRate` | — | monthly | monthly |
| `bookDepth`, `metrics` | — | daily | daily |
| `liquidationSnapshot` | — | — | daily |

To list the published BTCUSDT funding-rate ZIPs on USDⓈ-M, use the monthly partition.

```bash
binance-datatool list-files um BTCUSDT --freq monthly --type fundingRate --only-zip
```

## Kline intervals

For `klines`, `indexPriceKlines`, `markPriceKlines`, and `premiumIndexKlines`, supply
`--interval` to `list-files`, `download`, and `verify`. Omit it for other datasets and
for `list-symbols`. Use `1m` for one-minute candles and `1mo` for one-month candles.
A misspelled interval can produce a successful, empty listing.

| Candle interval | BTCUSDT spot daily | BTCUSDT spot monthly | Futures kline archives |
|-----------------|:------------------:|:--------------------:|:----------------------:|
| `1s` | Yes | Yes | — |
| `1m`, `3m`, `5m`, `15m`, `30m` | Yes | Yes | Yes |
| `1h`, `2h`, `4h`, `6h`, `8h`, `12h` | Yes | Yes | Yes |
| `1d` | Yes | Yes | Yes |
| `3d`, `1w`, `1mo` | — | Yes | Yes |

The spot columns describe BTCUSDT. The futures column combines intervals seen across
USDⓈ-M and COIN-M kline datasets.
[BTCUSDT spot daily directories](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/spot/daily/klines/BTCUSDT/) ·
[BTCUSDT spot monthly directories](https://s3-ap-northeast-1.amazonaws.com/data.binance.vision?delimiter=/&prefix=data/spot/monthly/klines/BTCUSDT/)

Check a specific symbol and partition with `list-files`. For BTCUSDT spot weekly candles, run

```bash
binance-datatool list-files spot BTCUSDT --freq monthly --type klines --interval 1w --only-zip
```

## COIN-M price kline symbols

| Dataset | Archive symbol format |
|---------|-----------------------|
| `indexPriceKlines` | Bare pair (`{BASE}USD`) |
| `premiumIndexKlines` | Perpetual contract (`{BASE}USD_PERP`) |
| `markPriceKlines` | Perpetual or delivery contract (`{BASE}USD_PERP` or `{BASE}USD_{YYMMDD}`) |

For COIN-M index prices, run `list-symbols` without filters. The CLI cannot infer a
contract type for a bare pair, so any filter drops it. Use the returned name with `list-files`.
