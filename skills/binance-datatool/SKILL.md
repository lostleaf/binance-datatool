---
name: binance-datatool
description: >
  Manage Binance historical market data from data.binance.vision using the binance-datatool CLI.
  List available symbols, browse remote archive files, download klines/trades/funding rates with
  aria2, and verify SHA256 checksums. Use this skill whenever the user mentions Binance historical
  data, klines, candlestick data, trade data, funding rates, data.binance.vision, or asks to
  download, list, or verify Binance market data — even if they don't mention binance-datatool by
  name. Also use when the user asks about available Binance symbols or wants to build a local
  crypto data archive from Binance. Do NOT use this skill for Binance REST API, WebSocket, or
  real-time market data — it only covers historical archive downloads from data.binance.vision.
---

# binance-datatool

A CLI for downloading and managing Binance historical market data from data.binance.vision.

## Verbosity

By default, the CLI runs at WARNING level and produces almost no log output. For agent use,
**always pass `-v`** so loguru prints INFO-level progress to stderr. This gives you visibility
into what the tool is doing (listing symbols, downloading files, verifying checksums). Use `-vv`
for DEBUG-level output when troubleshooting.

All log output goes to stderr. Command results (symbol lists, file paths, dry-run diffs) go to
stdout. This separation means piping stdout is always safe.

## Prerequisites

Before running any command, ensure three things are in place:

1. **binance-datatool installed** — `pip install binance-datatool` or `pipx install binance-datatool`
2. **Archive home configured** — set `BINANCE_DATATOOL_ARCHIVE_HOME` to a directory for local data
   storage. Required by `download` and `verify`. Can also be passed per-command via `--archive-home`.
   ```bash
   export BINANCE_DATATOOL_ARCHIVE_HOME="$HOME/crypto_data/binance_archive"
   ```
3. **aria2 installed** — required by the `download` command for parallel, resumable downloads.
   - macOS: `brew install aria2`
   - Ubuntu/Debian: `sudo apt install aria2`

## Core Concepts

### Trade Types

| Value  | Market segment                       |
|--------|--------------------------------------|
| `spot` | Spot trading market                  |
| `um`   | USD-M perpetual and delivery futures |
| `cm`   | COIN-M perpetual and delivery futures|

### Data Frequencies

| Value     | Meaning                    |
|-----------|----------------------------|
| `daily`   | Files partitioned by day   |
| `monthly` | Files partitioned by month |

### Data Types

| CLI value              | Description              | Needs `--interval`? |
|------------------------|--------------------------|---------------------|
| `klines`               | Candlestick (OHLCV) data | Yes                 |
| `aggTrades`            | Aggregated trades        | No                  |
| `trades`               | Individual trades        | No                  |
| `fundingRate`          | Futures funding rates    | No                  |
| `bookDepth`            | Order book depth         | No                  |
| `bookTicker`           | Best bid/ask updates     | No                  |
| `indexPriceKlines`     | Index price klines       | Yes                 |
| `markPriceKlines`      | Mark price klines        | Yes                 |
| `premiumIndexKlines`   | Premium index klines     | Yes                 |
| `metrics`              | Futures metrics          | No                  |
| `liquidationSnapshot`  | Liquidation snapshots    | No                  |

### Kline Intervals

`1m` `3m` `5m` `15m` `30m` `1h` `2h` `4h` `6h` `8h` `12h` `1d` `3d` `1w` `1mo`

Only required for data types marked "Yes" in the table above.

### Contract Types (futures only)

| Value       | Meaning                            |
|-------------|------------------------------------|
| `perpetual` | No expiry; open until closed       |
| `delivery`  | Expires on a fixed settlement date |

## Commands

All commands accept the global options `-v` (verbosity) and `--archive-home PATH`.

### list-symbols

List available symbols from the remote archive.

```
binance-datatool -v list-symbols <TRADE_TYPE> [OPTIONS]
```

| Option               | Description                                         |
|----------------------|-----------------------------------------------------|
| `--freq`             | Partition frequency (default: `daily`)               |
| `--type`             | Dataset type (default: `klines`)                     |
| `--quote ASSET`      | Filter by quote asset (repeatable)                   |
| `--exclude-leverage` | Exclude leveraged tokens (spot only)                 |
| `--exclude-stables`  | Exclude stablecoin pairs                             |
| `--contract-type`    | Filter futures by contract type                      |

Output: one symbol per line to stdout. With no filter flags, every archive symbol directory
is printed in listing order, including symbols whose metadata cannot be inferred. `--freq`
and `--type` select the archive prefix and do not enable filtering.

With any filter flag, uninferable symbols are skipped and one stderr warning gives their
count and names, even without `-v`. This applies even if the flag is ignored for the selected
market. No warning is emitted when every symbol is inferable. Both modes exit `0` on success.

### list-files

List archive files for given symbols. Reads symbols from stdin if none given as arguments.

```
binance-datatool -v list-files <TRADE_TYPE> [SYMBOLS...] [OPTIONS]
```

| Option             | Description                                        |
|--------------------|----------------------------------------------------|
| `--freq`           | Partition frequency (default: `daily`)              |
| `--type`           | Dataset type (default: `klines`)                    |
| `--interval`       | Interval for kline-class data types                 |
| `-l` / `--long`    | Three-column TSV output: size, timestamp, path      |
| `--only-zip`       | Print only .zip files                               |
| `--only-checksum`  | Print only .CHECKSUM files                          |
| `--progress-bar`   | Show progress bar on stderr                         |

Output: one path per line, or TSV with `-l`.

### download

Download archive files into the local archive directory using aria2.

```
binance-datatool -v download <TRADE_TYPE> [SYMBOLS...] [OPTIONS]
```

| Option            | Description                                           |
|-------------------|-------------------------------------------------------|
| `--freq`          | Partition frequency (default: `daily`)                 |
| `--type`          | Dataset type (default: `klines`)                       |
| `--interval`      | Interval for kline-class data types                    |
| `-n` / `--dry-run`| Preview what would be downloaded without writing files |
| `--aria2-proxy`   | Let aria2c inherit proxy env vars                      |
| `--progress-bar`  | Show progress bar on stderr                            |

Dry-run output: TSV lines `<reason>\t<size>\t<path>` where reason is `new` or `updated`.
Real-run output: download stats on stderr (downloaded/failed/skipped counts).

Exit codes: 0 = success, 2 = partial failure.

### verify

Verify local zip files against SHA256 checksums.

```
binance-datatool -v verify <TRADE_TYPE> [SYMBOLS...] [OPTIONS]
```

| Option            | Description                                           |
|-------------------|-------------------------------------------------------|
| `--freq`          | Partition frequency (default: `daily`)                 |
| `--type`          | Dataset type (default: `klines`)                       |
| `--interval`      | Interval for kline-class data types                    |
| `--keep-failed`   | Keep failed files instead of deleting them             |
| `-n` / `--dry-run`| Scan without verifying                                 |
| `--progress-bar`  | Show progress bar on stderr                            |

| Situation | Exit code |
|-----------|-----------|
| No verification failures (including empty scans, orphan cleanup alone, or a completed dry-run) | `0` |
| At least one ZIP failed verification, with or without `--keep-failed` | `2` |
| Missing archive home or invalid arguments | `2` |

Failure details identify malformed `.CHECKSUM` files as invalid. Inspect or replace the
checksum file before retrying verification.

## Workflow Templates

### Download Spot USDT 1m Klines

A three-step pipeline: list symbols, download, verify.

```bash
# Step 1: List USDT spot symbols (exclude stablecoins and leveraged tokens)
binance-datatool -v list-symbols spot \
  --quote USDT --exclude-stables --exclude-leverage > symbols.txt

# Step 2: Download daily 1m klines
binance-datatool -v download spot \
  --freq daily --type klines --interval 1m < symbols.txt

# Step 3: Verify downloaded files
binance-datatool -v verify spot \
  --freq daily --type klines --interval 1m < symbols.txt
```

### Download USD-M Perpetual 1m Klines

```bash
binance-datatool -v list-symbols um \
  --quote USDT --exclude-stables --contract-type perpetual > symbols.txt

binance-datatool -v download um \
  --freq daily --type klines --interval 1m < symbols.txt

binance-datatool -v verify um \
  --freq daily --type klines --interval 1m < symbols.txt
```

### Download USD-M Funding Rates

Note: funding rates use `monthly` frequency and no interval.

```bash
binance-datatool -v list-symbols um \
  --freq monthly --type fundingRate \
  --quote USDT --exclude-stables --contract-type perpetual > symbols.txt

binance-datatool -v download um \
  --freq monthly --type fundingRate < symbols.txt

binance-datatool -v verify um \
  --freq monthly --type fundingRate < symbols.txt
```

## Best Practices

- **Always use `-v`** so you can see INFO-level progress on stderr. Without it the tool is
  nearly silent under normal operation.
- **Dry-run before downloading.** Run `download --dry-run` first to preview what will be
  fetched, especially for broad queries like all USDT symbols.
- **Reuse symbol lists.** Save `list-symbols` output to a file and pipe it into both `download`
  and `verify` to keep the symbol set consistent across steps.
- **Check exit codes.** Exit code 2 means partial failure — some symbols succeeded while others
  failed. Review stderr for details.
- **Frequency matters.** Some data types are only available at specific frequencies. For example,
  futures `fundingRate` typically requires `--freq monthly`. If `list-files` returns nothing,
  try switching the frequency.
- **stdin composition.** When no positional `SYMBOLS` arguments are given, commands read symbols
  from stdin. This enables `list-symbols | download` pipelines or file-based workflows.
- **`--type` values are camelCase.** Use the exact values from the Data Types table above (e.g.
  `fundingRate`, `aggTrades`, `bookDepth`), not snake_case variants like `funding_rate`.
