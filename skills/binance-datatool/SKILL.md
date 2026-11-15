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
stdout. Use `--json` with `list-symbols`, `list-files`, `download`, or `verify` for a single
structured result, including when aria2 writes stdout during downloads.

## JSON results

`list-symbols`, `list-files`, `download`, and `verify` support `--json`; download and verify
support real and dry-run modes.
Parse the entire stdout as one JSON document after a returned result, including exit `2`;
logs, progress, diagnostic payloads,
and existing summaries remain on stderr. No-flag output is unchanged.

The envelope contains `command` (CLI name), boolean `dry_run`, and object `summary`.
Names use `snake_case`; counts and byte sizes are nonnegative integers. Required fields
remain present at zero/empty, collections use `[]`, and fields specific to another mode
are omitted. Array order follows existing results; whitespace and object key order are
unspecified. There is no schema version or success/status field. This initial format has
no long-term stability promise. Future field or semantic changes must update the CLI
reference and this skill with the implementation.

The document guarantee starts when the workflow returns a result. Argument errors, missing
configuration, and unhandled exceptions without a result retain existing failures and may
leave stdout empty. Treat that as no result, rather than an empty completed plan.

## Prerequisites

Before running any command, ensure three things are in place:

1. **binance-datatool installed** — `pip install binance-datatool` or `pipx install binance-datatool`
2. **Archive home configured** — set `BINANCE_DATATOOL_ARCHIVE_HOME` to a directory for local data
   storage. Required by `download` and `verify`. Can also be passed per-command via `--archive-home`.
   ```bash
   export BINANCE_DATATOOL_ARCHIVE_HOME="$HOME/crypto_data/binance_archive"
   ```
3. **aria2 installed** — required when a real `download` run has objects to transfer.
   Dry-runs and empty transfer plans need no aria2.
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
| `--json`            | Return symbol selection and classification records   |

Selection: with no filter flags, every archive symbol directory is returned in listing
order, including symbols whose metadata cannot be inferred. `--freq` and `--type` select
the archive prefix and do not enable filtering.

With any filter flag, only matching inferred symbols are selected; uninferable symbols are
skipped and one stderr warning gives their count and names, even without `-v`. This applies
even if the flag is ignored for the selected market. No warning is emitted when every
symbol is inferable. These selection and warning rules apply to text and JSON output.
Text output writes one selected symbol per line to stdout. Every returned result exits `0`,
including filtered-out or uninferable names.

With `--json`, `command` is `list-symbols` and `dry_run` is `false`; no dry-run option is
added. Every returned result, including an empty listing, contains:

| Field | Contents |
|-------|----------|
| `symbols` | Selected names in the order defined above. |
| `matched` | Inferred records that pass filtering, in result order. |
| `filtered_out` | Inferred records excluded by filtering, in result order. |
| `uninferable` | Names only, without fabricated metadata. |

All inferred records contain `symbol`, `base_asset`, and `quote_asset`. Spot adds boolean
`is_leverage` and `is_stable_pair`; USD-M adds `contract_type` and boolean `is_stable_pair`;
COIN-M adds only `contract_type`. Contract values are `perpetual` or `delivery`.
Inapplicable attributes are omitted from both inferred-record arrays.

`summary` contains `total_raw_symbols`, `returned_symbols`, `matched_symbols`,
`filtered_out_symbols`, and `uninferable_symbols`. Returned and classification counts equal
their array lengths; the three classification counts sum to `total_raw_symbols`. Empty
results retain zero counts and `[]` arrays.

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
| `--json`           | Emit remote URLs and metadata as one JSON result     |

Output: one path per line, or TSV with `-l`.

With `--json`, the envelope uses `command: "list-files"` and `dry_run: false`. No Archive home
configuration is needed, and this command has no dry-run option. `--long --json` is accepted;
`--long` has no effect on JSON fields.

The required `per_symbol` array contains records with `symbol`, `files`, and `error`.
Each file has `url`, integer byte `size`, and `last_modified` as UTC ISO 8601 at second
precision ending in `Z`. URLs join `https://data.binance.vision` and the complete object key;
there are no local or relative-path fields. For example, a URL can be
`https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-03.zip`.
Successful listings use `error: null`, including empty directories. Failed listings have
empty `files` and a non-empty `error`. Existing exception messages are preserved verbatim;
an empty message uses the exception class name, such as `TimeoutError`. Treat this as a
failed listing, counted in `failed_symbols`, rather than an empty success. Text and JSON
modes retain its Symbol and error on stderr, exit `2`, and suppress empty-result warnings
when any listing failed.

Symbol and file order follow the workflow. Inputs are stripped and uppercased; repeated
normalized symbols collapse to one record in first-occurrence order. `--only-zip` and
`--only-checksum` filter file arrays using text-mode selection rules and remain mutually
exclusive. Keep symbol records whose file arrays become empty. The summary contains:

| Field | Meaning |
|-------|---------|
| `requested_symbols` | Number of workflow symbol records after duplicate collapse. |
| `successful_symbols` | Number of records with null error. |
| `failed_symbols` | Number of records with a listing error. |
| `total_remote_files` | Successfully listed files before output filtering. Failed listings contribute no invented file counts. |
| `returned_files` | Sum of emitted file-array lengths after filtering. |

A ZIP/checksum pair filtered with `--only-zip` has remote total `2` and returned total `1`.
Empty-result warnings use the unfiltered result, so filtering a nonempty listing to zero
returned files does not create a warning. Diagnostics retain symbol/error associations on
stderr. JSON is emitted before exit `2` for any symbol failure; other returned results exit
`0`, including empty results. Validation failures and other errors without a result may
leave stdout empty, following the shared JSON contract above.

```bash
binance-datatool -v list-files um --freq monthly --type fundingRate --only-zip --json BTCUSDT
```

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
| `--json`         | Emit the structured result described below             |
| `--aria2-proxy`   | Let aria2c inherit proxy env vars                      |
| `--concurrency N` | Concurrent aria2 downloads (default: `64`, minimum: `1`) |
| `--progress-bar`  | Show progress bar on stderr                            |

Without `--json`, dry-run output is TSV lines `<reason>\t<size>\t<path>`, where reason is
`new` or `updated`.
Real runs always print download stats on stderr (downloaded/failed/skipped counts).
With `-v` or `--progress-bar`, download progress advances after each batch of at most
512 files, including retry rounds. Invalid concurrency exits `2`.

The command lists remote objects and compares local files before checking aria2 availability.
For a nonempty transfer plan, unavailable `aria2c` leaves local objects, verification markers,
control files, and directories intact. Text and JSON modes print installation guidance to
stderr and exit `2` with empty stdout and no traceback. Treat empty stdout as no workflow
result; JSON mode emits no error envelope. After preparation succeeds, later transfer failures
retain existing replacement and retry behavior, with no rollback.

With `--json`, both modes include `listing_errors`: records with `symbol` and the non-empty
`error` text, using the same exception-message fallback as `list-files`.
`summary.listing_failed_symbols` equals its length, separately from transfer
failures. ZIP and checksum objects count individually. `total_remote` counts only objects
from successful listings; listing errors mean this inventory may be incomplete.

| Mode | Required `summary` fields | Additional result field |
|------|---------------------------|-------------------------|
| Dry-run | `total_remote`, `skipped`, `to_download`, `listing_failed_symbols` | `to_download`: records with absolute `path`, integer byte `size`, and `reason` (`new` or `updated`). |
| Real run | `total_remote`, `skipped`, `downloaded`, `failed`, `listing_failed_symbols` | `failed_paths`: absolute strings for requests still failing after every retry. |

Dry-run satisfies `total_remote = skipped + to_download`, and `summary.to_download` is the
plan length. It modifies no local files and includes no completed-download counts or
`failed_paths`. Real runs satisfy `total_remote = skipped + downloaded + failed`, and
`summary.failed` equals the failed-path count. Eventual retry successes are absent from
failures. Real runs omit `to_download`.

Paths use the invocation working directory for a relative Archive home, without requiring
existence, resolving symlinks, or changing storage behavior. Downloaded and Up to date do
not establish Verified status; paths may name files that do not exist.

```bash
binance-datatool -v --archive-home ./archive download um --freq monthly --type fundingRate --dry-run --json BTCUSDT
binance-datatool -v --archive-home ./archive download um --freq monthly --type fundingRate --json BTCUSDT
```

Exit codes: `2` for any symbol listing failure or, in real mode, a final transfer failure;
`0` for other returned results, including empty results. JSON is emitted before these exits.

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
| `--json`         | Emit the structured verification result described below |
| `--progress-bar`  | Show progress bar on stderr                            |

With `--json`, the envelope uses `command: "verify"`. Counts describe ZIP verification
targets; checksums are not separate verification targets.

| Mode | Required `summary` fields | Additional result field |
|------|---------------------------|-------------------------|
| Dry-run | `total_zips`, `to_verify`, `skipped`, `orphan_zips`, `orphan_checksums` | `to_verify`: absolute ZIP path strings awaiting verification. |
| Real run | `total_zips`, `verified`, `failed`, `skipped`, `orphan_zips`, `orphan_checksums` | `failed_details`: records containing absolute `path` and the workflow's failure `detail`. |

Dry-run only scans: no hashing, cleanup, or marker changes. It satisfies
`total_zips = to_verify + skipped + orphan_zips`; `summary.to_verify` equals the plan length.
Real runs satisfy `total_zips = verified + failed + skipped + orphan_zips`; `summary.failed`
equals the detail-array length. Each mode omits the other mode's fields. Successful and
skipped files have no manifests.

Paths are absolute, using the invocation working directory for a relative Archive home.
Formatting requires no file existence, leaves symlinks unresolved, and keeps filesystem
targets unchanged. A path may name an already deleted file and does not establish existence
or Verified status. Failed ZIPs and their checksums are deleted by default; `--keep-failed`
retains them. Either way, JSON retains their paths and details before exit `2`.

Orphan ZIPs are kept with their verification markers cleared. Orphan checksums are deleted
with related markers cleared. The two orphan counts describe artifacts, rather than the
number of markers deleted: discoveries in dry-run, artifacts processed in real runs.
An orphan ZIP counts even without an existing marker. Orphan checksums are excluded from
`total_zips`. Orphan cleanup alone exits `0` and does not count as a verification failure.

```bash
binance-datatool -v --archive-home ./archive verify um --freq monthly --type fundingRate --dry-run --json BTCUSDT
binance-datatool -v --archive-home ./archive verify um --freq monthly --type fundingRate --json BTCUSDT
```

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
- **Check exit codes.** Exit code 2 can report listing or transfer failures, invalid arguments,
  missing configuration, or unavailable download tooling. Review stderr for details.
- **Frequency matters.** Some data types are only available at specific frequencies. For example,
  futures `fundingRate` typically requires `--freq monthly`. If `list-files` returns nothing,
  try switching the frequency.
- **stdin composition.** When no positional `SYMBOLS` arguments are given, commands read symbols
  from stdin. This enables `list-symbols | download` pipelines or file-based workflows.
- **`--type` values are camelCase.** Use the exact values from the Data Types table above (e.g.
  `fundingRate`, `aggTrades`, `bookDepth`), not snake_case variants like `funding_rate`.
