# binance-datatool commands

Root CLI commands for remote archive discovery and download, plus local-only SHA256 verification.
Domain terms are defined in the [glossary](../../../GLOSSARY.md).

## Structured JSON results

`list-symbols`, `list-files`, `download`, and `verify` accept `--json`; download and verify
support real and dry-run modes.
Each returned workflow result emits exactly one JSON document on stdout, including empty
listings or plans, no-work runs, and partial or all-symbol listing failures.
Logs, progress, existing summaries, and diagnostic payloads
remain on stderr, including aria2 subprocess output. Output without `--json` is unchanged.

The common envelope contains `command` (the CLI command name), `dry_run` (boolean), and
`summary` (an object). Field names use `snake_case`; counts and byte sizes are nonnegative
integers. Required fields remain present when zero or empty; collections use `[]`. Fields
belonging only to another mode are omitted. Array order follows the workflow result; object
key order and whitespace are not contracts. There is no schema version or success/status
field. This initial format carries no long-term stability promise: future field or semantic
changes must update this reference and the packaged agent skill with the implementation.

The single-document guarantee starts when the workflow returns a result. Argument validation,
missing configuration, and unhandled exceptions without a result retain existing behavior;
stdout may be empty. Returned failures emit their JSON before the command exits `2`.

## `list-symbols`

```
binance-datatool list-symbols <TRADE_TYPE>
    [--freq FREQ] [--type TYPE]
    [--quote QUOTE ...] [--exclude-leverage] [--exclude-stables]
    [--contract-type CONTRACT_TYPE] [--json]
```

| Argument / Option | Type | Default | Description |
|-------------------|------|---------|-------------|
| `TRADE_TYPE` | `TradeType` | *(required)* | Market segment (positional argument). |
| `--freq` | `DataFrequency` | `daily` | Partition frequency. |
| `--type` | `DataType` | `klines` | Dataset type. |
| `--quote` | `list[str]` | `None` | Filter by quote asset. Repeat to allow multiple values. Normalized to uppercase and deduplicated. |
| `--exclude-leverage` | `bool` | `False` | Exclude leveraged spot tokens. Ignored for USD-M and COIN-M. |
| `--exclude-stables` | `bool` | `False` | Exclude stablecoin pairs. Ignored for COIN-M. |
| `--contract-type` | `ContractType` | `None` | Restrict futures symbols to `perpetual` or `delivery`. Ignored for spot. |
| `--json` | `bool` | `False` | Emit one structured result with symbol selection and classification details. |

**Selection:** when every filter flag is at its default, no filter is constructed and every
symbol directory is returned in the archive's sorted listing order, including symbols whose
metadata cannot be inferred. With any filter flag, only `ListSymbolsResult.matched` is
selected. Flags that do not apply to the chosen market are ignored when filtering metadata
but still enable filtered selection. Uninferable symbols are skipped and one warning on
stderr gives their count and names, visible without `-v`. No warning is emitted when every
symbol is inferable. `--freq` and `--type` select the archive prefix and do not enable filtering.

These selection and warning rules apply to text and JSON output. Text output writes one
selected symbol per line to stdout. Every returned result exits `0`, including filtered-out
or uninferable names.

### JSON output

`--json` emits `command: "list-symbols"` and `dry_run: false`; the command has no dry-run
option. Every returned result, including an empty listing, contains these arrays:

| Field | Contents |
|-------|----------|
| `symbols` | Selected symbol strings in the order defined above. |
| `matched` | Inferred records that pass filtering, in result order. |
| `filtered_out` | Inferred records excluded by filtering, in result order. |
| `uninferable` | Symbol strings whose metadata cannot be inferred; no fabricated attributes. |

Every inferred record contains `symbol`, `base_asset`, and `quote_asset`. Spot records add
boolean `is_leverage` and `is_stable_pair`; USD-M records add `contract_type` and boolean
`is_stable_pair`; COIN-M records add only `contract_type`. Contract values are `perpetual`
or `delivery`. Inapplicable attributes are omitted from both inferred-record arrays.

The `summary` fields are `total_raw_symbols`, `returned_symbols`, `matched_symbols`,
`filtered_out_symbols`, and `uninferable_symbols`. `returned_symbols` equals the length of
`symbols`; the three classification counts equal their respective array lengths, and their
sum equals `total_raw_symbols`. Empty results retain all fields with zero counts and `[]`.

**Examples:**

```
binance-datatool list-symbols spot --quote USDT --exclude-leverage --exclude-stables
binance-datatool list-symbols um --quote USDT --quote USDC --contract-type perpetual
binance-datatool list-symbols cm --contract-type delivery
binance-datatool list-symbols um --quote USDT --json
```

### Data flow

```
User runs:
  binance-datatool list-symbols spot --quote USDT

  ┌──────────────────────────────────────────────────────┐
  │ CLI layer  (cli/archive.py)                     │
  │  Parses arguments, builds a typed symbol filter,     │
  │  runs the workflow, prints raw or matched symbols,   │
  │  and warns about uninferable symbols when filtering. │
  └──────────────────────┬───────────────────────────────┘
                         │ trade_type, data_freq, data_type,
                         │ symbol_filter
  ┌──────────────────────▼───────────────────────────────┐
  │ Workflow  (workflow/)                  │
  │  Fetches raw symbols, infers typed metadata per      │
  │  market, applies the filter, and returns a           │
  │  ListSymbolsResult.                                  │
  └──────────────────────┬───────────────────────────────┘
                         │ trade_type, data_freq, data_type
  ┌──────────────────────▼───────────────────────────────┐
  │ Archive Client  (archive/client.py)             │
  │  Issues paginated S3 XML listings against            │
  │  data.binance.vision and returns sorted symbol       │
  │  names.                                              │
  └──────────────────────────────────────────────────────┘
```

## `list-files`

```
binance-datatool list-files <TRADE_TYPE> [SYMBOLS...]
    [--freq FREQ] [--type TYPE] [--interval INTERVAL]
    [-l | --long]
    [--only-zip | --only-checksum]
    [--progress-bar] [--json]
```

Lists every file under one or more symbol directories on `data.binance.vision`,
preserving the caller-provided symbol order.

| Argument / Option | Type | Default | Description |
|-------------------|------|---------|-------------|
| `TRADE_TYPE` | `TradeType` | *(required)* | Market segment (positional argument). |
| `SYMBOLS` | `list[str]` | *(see below)* | Symbols to list, as variadic positional arguments. Accepts lowercase input; every symbol is normalized to uppercase before being passed to the workflow. |
| `--freq` | `DataFrequency` | `daily` | Partition frequency. |
| `--type` | `DataType` | `klines` | Dataset type. |
| `--interval` | `str \| None` | `None` | Kline interval directory. **Required** when `data_type.has_interval_layer` is `True` (the four kline-class data types); **rejected** otherwise. |
| `-l` / `--long` | `bool` | `False` | Switch from short relative-path output to a three-column TSV: `size_bytes<TAB>last_modified_iso<TAB>relative_path`. |
| `--only-zip` | `bool` | `False` | Print only `.zip` files. Mutually exclusive with `--only-checksum`. |
| `--only-checksum` | `bool` | `False` | Print only `.zip.CHECKSUM` files. Mutually exclusive with `--only-zip`. |
| `--progress-bar` | `bool` | `False` | Show interactive tqdm progress bar on stderr. By default no interactive progress is shown; sampled log lines at INFO level are emitted instead. See [`common.progress`](../common/progress.md). |
| `--json` | `bool` | `False` | Emit remote metadata in one structured result. Accepts `--long`, which has no effect on JSON fields. |

### Symbol input resolution

| State | Behavior |
|-------|----------|
| Positional args present | Use positional args, ignoring stdin (same convention as `grep` / `cat`). |
| No positional args and stdin is piped (`isatty()` is `False`) | Read `sys.stdin`, split on newlines, drop empty lines. |
| No positional args and stdin is a tty | Raise `typer.BadParameter` → exit 2. |

Every resolved symbol is stripped and uppercased before the workflow sees it, so
`btcusdt` and `BTCUSDT` behave identically. Repeated normalized symbols collapse to one
result record, preserving the order of their first occurrence.

### Output formats

**Short (default):** one relative path per line, `{symbol}[/{interval}]/{filename}`:

```
BTCUSDT/BTCUSDT-fundingRate-2026-03.zip
BTCUSDT/BTCUSDT-fundingRate-2026-03.zip.CHECKSUM
```

For kline-class data types the interval directory appears between symbol and
filename:

```
BTCUSDT/1m/BTCUSDT-1m-2024-01-01.zip
```

**Long (`-l` / `--long`):** three-column TSV, **no header row**, suitable for
piping into `awk` / `cut`:

```
1048	2026-04-01T08:06:34Z	BTCUSDT/BTCUSDT-fundingRate-2026-03.zip
105	2026-04-01T08:06:34Z	BTCUSDT/BTCUSDT-fundingRate-2026-03.zip.CHECKSUM
```

Columns are:

| # | Field | Format |
|---|-------|--------|
| 1 | `size_bytes` | Raw integer byte count. No human-readable suffix (so `awk '{sum+=$1}'` works). |
| 2 | `last_modified_iso` | ISO 8601 UTC second precision with `Z` suffix, produced via `datetime.strftime("%Y-%m-%dT%H:%M:%SZ")`. |
| 3 | `relative_path` | Same value as the short-format line. |

No header line is emitted; this matches `ls -l` / `find -printf` / `du` / `git ls-files`
conventions so the output is pipe-safe without `tail -n +2` gymnastics.

If every requested symbol is listed successfully but no files are found, the
command still exits `0` and prints a warning to stderr. Treat that warning as a
hint to verify the upstream directory layout on `data.binance.vision` for the
selected market, frequency, and data type rather than as a local runtime error.

### JSON output

With `--json`, the envelope uses `command: "list-files"` and `dry_run: false`. This command
has no dry-run option and needs no Archive home configuration. The required `per_symbol`
array retains workflow symbol order and file order. Each symbol record contains:

| Field | Meaning |
|-------|---------|
| `symbol` | Normalized symbol name. |
| `files` | Array of objects with `url`, integer byte `size`, and `last_modified`. |
| `error` | `null` for a successful listing, including an empty directory; original workflow error text for a failed listing. Failed listings have empty `files`. |

Listing errors are non-empty: existing exception messages are preserved verbatim, and an
empty exception message uses its class name, such as `TimeoutError`. Text and JSON modes
retain the error and its Symbol on stderr and exit `2`. A failed timeout contributes to
`failed_symbols`, and suppresses the successful-empty-listing warning even if no files were
returned. JSON stdout remains one result document with the failed Symbol's `files: []`
and non-empty `error`; a successful empty listing has `error: null`.

`url` combines the existing download base `https://data.binance.vision` with the complete
object key, for example
`https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-03.zip`.
There is no local or relative-path field. `last_modified` is UTC ISO 8601 at second precision,
ending in `Z`, such as `2026-04-01T08:06:34Z`.

`--only-zip` and `--only-checksum` select files using the same rules as text mode; together
they remain invalid. A symbol record remains present when all its files are filtered out.
The summary contains:

| Field | Meaning |
|-------|---------|
| `requested_symbols` | Number of workflow symbol records after existing duplicate-input collapse. |
| `successful_symbols` | Records whose `error` is `null`. |
| `failed_symbols` | Records with a listing error. |
| `total_remote_files` | Successfully listed files before output filtering. Failed symbols contribute no invented file counts. |
| `returned_files` | Sum of emitted file-array lengths after filtering. |

A ZIP/checksum pair with `--only-zip` has `total_remote_files: 2` and `returned_files: 1`.
Empty-result warnings use the unfiltered workflow result: filtering a nonempty listing to
zero returned files does not produce a warning. Symbol/error diagnostics remain on stderr.
JSON is serialized before exit `2` for any listing failure; all other returned results,
including empty results, exit `0`. Validation and other failures without a result retain
the shared no-result behavior described above.

### Exit codes

| Situation | Exit code |
|-----------|-----------|
| All symbols succeeded (empty results still count as success) | `0` |
| Any symbol failed | `2` (per-symbol errors are logged to stderr as `ERROR: {symbol}: {message}`) |
| Argument validation error (mutually exclusive flags, missing interval, extra interval, no symbols) | `2` |
| `KeyboardInterrupt` | `130` |

### Composition with `list-symbols`

`list-files` is designed to be piped from `list-symbols`:

```
binance-datatool list-symbols um --quote USDT --exclude-stables \
  | binance-datatool list-files um --type klines --interval 1m
```

### Examples

```
# Single-symbol funding-rate listing
binance-datatool list-files um --freq monthly --type fundingRate BTCUSDT

# Multi-symbol klines listing (long TSV, zip-only)
binance-datatool list-files um --type klines --interval 1m -l --only-zip BTCUSDT ETHUSDT

# Pipe from list-symbols, verbose logging
binance-datatool -v list-symbols um --quote USDT --exclude-stables \
  | binance-datatool -v list-files um --type klines --interval 1m
```

### Data flow

```
User runs:
  binance-datatool list-symbols um --quote USDT --exclude-stables \
    | binance-datatool list-files um --type klines --interval 1m

  ┌──────────────────────────────────────────────────────┐
  │ CLI layer  (cli/archive.py)                     │
  │  Validates --only-zip / --only-checksum exclusivity  │
  │  and --interval vs data_type consistency; resolves   │
  │  symbols from positional args (winning) or piped     │
  │  stdin; uppercases each symbol; runs the workflow;   │
  │  prints short or TSV long output; logs per-symbol    │
  │  failures to stderr and exits 2 if any failed.       │
  └──────────────────────┬───────────────────────────────┘
                         │ trade_type, data_freq, data_type,
                         │ symbols, interval
  ┌──────────────────────▼───────────────────────────────┐
  │ Workflow  (workflow/)                  │
  │  Re-validates interval consistency at construction;  │
  │  delegates to ArchiveClient.list_symbol_files_batch  │
  │  which opens one shared aiohttp session and          │
  │  concurrently lists every symbol; wraps exceptions   │
  │  into SymbolListFilesResult.error and preserves      │
  │  caller input order.                                 │
  └──────────────────────┬───────────────────────────────┘
                         │ trade_type, data_freq, data_type,
                         │ symbol, interval, session
  ┌──────────────────────▼───────────────────────────────┐
  │ Archive Client  (archive/client.py)             │
  │  list_symbol_files builds the prefix and calls       │
  │  list_files_in_dir, which paginates S3 Contents      │
  │  entries into ArchiveFile dataclasses (key, size,    │
  │  last_modified tz-aware UTC).                        │
  └──────────────────────────────────────────────────────┘
```

The CLI, workflow constructors, and archive client call the shared
[`validate_interval()`](../common/path.md#validate_interval) rule at their existing
entrypoints before I/O. Library callers receive `ValueError`; the CLI converts it
to an `--interval` usage error with exit status 2. See the
[archive client reference](../archive/client.md) and
[S3 protocol reference](../archive/s3-protocol.md) for archive listing details.

## `download`

```
binance-datatool [--archive-home PATH] download <TRADE_TYPE> [SYMBOLS...]
    [--freq FREQ] [--type TYPE] [--interval INTERVAL]
    [-n | --dry-run]
    [--aria2-proxy] [--concurrency N]
    [--progress-bar] [--json]
```

Downloads new or updated archive files into the local archive data directory.
Requires `aria2c` in `PATH` when a real run has objects to transfer. Remote listing and
local comparison happen first; dry-runs and empty transfer plans need no aria2. Missing
tooling is detected before creating archive directories, clearing verification markers,
or deleting replacement objects. Both text and JSON modes print installation guidance to
stderr, leave stdout empty, and exit `2` without a traceback. No workflow result exists in
this case, so JSON mode emits no result document.

| Argument / Option | Type | Default | Description |
|-------------------|------|---------|-------------|
| `TRADE_TYPE` | `TradeType` | *(required)* | Market segment (positional argument). |
| `SYMBOLS` | `list[str]` | *(see below)* | Symbols to download, as variadic positional arguments. Same resolution rules as `list-files`. |
| `--freq` | `DataFrequency` | `daily` | Partition frequency. |
| `--type` | `DataType` | `klines` | Dataset type. |
| `--interval` | `str \| None` | `None` | Kline interval directory. Same validation as `list-files`. |
| `-n` / `--dry-run` | `bool` | `False` | Show what would be downloaded without writing files. Outputs TSV unless `--json` is used. |
| `--json` | `bool` | `False` | Emit one structured result. See [shared conventions](#structured-json-results). |
| `--aria2-proxy` | `bool` | `False` | Allow aria2c to inherit system proxy environment variables. By default, proxy env vars (`HTTP_PROXY`, `HTTPS_PROXY`, etc.) are stripped from the aria2c subprocess. |
| `--concurrency` | `int` | `64` | Number of concurrent aria2 downloads. Values below 1 are usage errors (exit `2`). |
| `--progress-bar` | `bool` | `False` | Show interactive tqdm progress bar on stderr. By default no interactive progress is shown; sampled log lines at INFO level are emitted instead. See [`common.progress`](../common/progress.md). |

### archive-home resolution

The download command requires a local data directory. Resolution priority:

| Priority | Source |
|----------|--------|
| 1 | `--archive-home` (root-level option) |
| 2 | `$BINANCE_DATATOOL_ARCHIVE_HOME` environment variable |
| 3 | Exit 2 with a descriptive error |

See [`common.path`](../common/path.md) for implementation details.

### Diff semantics

Each ZIP and checksum file is compared independently against its local copy. Downloaded
means successful transfer; Up to date means eligible to skip transfer. Neither establishes
Verified status. The [workflow comparison rules](../workflow/README.md#download-comparison)
explain size, timestamp, partial-download, and verification-marker handling.

### Dry-run output

Without `--json`, dry-run mode (`-n`) prints a three-column TSV to stdout:

```
new	1048	BTCUSDT/BTCUSDT-fundingRate-2026-03.zip
updated	105	BTCUSDT/BTCUSDT-fundingRate-2026-03.zip.CHECKSUM
```

Columns: `reason<TAB>size_bytes<TAB>relative_path`. A summary line is printed
to stderr: `N files to download, M up to date`.

### JSON output

Both modes include `listing_errors`, an array of `{ "symbol": "ETHUSDT", "error": "..." }`
records retaining the non-empty listing error text, with the exception class name used for
an empty exception message. `summary.listing_failed_symbols` equals this array's
length and is separate from transfer failures. `total_remote` counts only successfully listed
objects; ZIP and checksum objects count separately. Failed listings leave the inventory
incomplete and do not contribute estimated file counts.

| Mode | Required `summary` fields | Additional result field |
|------|---------------------------|-------------------------|
| Dry-run | `total_remote`, `skipped`, `to_download`, `listing_failed_symbols` | `to_download`: records with absolute `path`, integer byte `size`, and `reason` (`new` or `updated`). |
| Real run | `total_remote`, `skipped`, `downloaded`, `failed`, `listing_failed_symbols` | `failed_paths`: absolute path strings for requests still failing after all retries. |

Dry-run satisfies `total_remote = skipped + to_download`; `summary.to_download` equals the
plan length. It modifies no local files and includes neither completed-download counts nor
`failed_paths`. A real run satisfies `total_remote = skipped + downloaded + failed`;
`summary.failed` equals the length of `failed_paths`. Requests succeeding on retry are absent
from failures. Real runs omit `to_download`.

Local paths are absolute, interpreting a relative Archive home against the invocation working
directory. Formatting requires no file existence and does not resolve symlinks or change
storage behavior. Plans and failures may name absent files. Downloaded and Up to date do not
establish Verified status.

```bash
binance-datatool -v --archive-home ./archive download um --freq monthly --type fundingRate --dry-run --json BTCUSDT
binance-datatool -v --archive-home ./archive download um --freq monthly --type fundingRate --json BTCUSDT
```

Both modes emit JSON before exit `2` for any symbol listing failure. Real runs also exit `2`
for final transfer failures. Other returned results exit `0`, including empty results.

### Normal output

Download counts refer to individual archive objects, including ZIP and checksum files, rather
than ZIP/checksum pairs. `downloaded` counts successful transfers in this run, `failed` counts
unsuccessful transfers, and `skipped` counts objects eligible to skip. Listing failures are
reported separately by symbol.

In download mode, the following are printed to stderr:

- Scan/diff diagnostics at INFO verbosity (`-v`).
- A final summary line: `Done: N downloaded, M failed, K skipped`.
- If `--progress-bar` is passed, an interactive tqdm bar is rendered on stderr
  during both the listing and download phases. Otherwise, sampled INFO log lines
  report progress.

Download progress updates after each aria2 batch of at most 512 files, including
retry rounds. With `-v`, each download progress event produces an INFO line;
`--progress-bar` advances the bar at the same cadence. Listing progress retains
its proportional sampling.

### Exit codes

| Situation | Exit code |
|-----------|-----------|
| All files downloaded successfully | `0` |
| Any symbol listing failed | `2` |
| Any download failed | `2` |
| aria2c unavailable for a nonempty transfer plan | `2` |
| BINANCE_DATATOOL_ARCHIVE_HOME not configured | `2` |
| Argument validation error | `2` |

### Composition with other commands

```
# Dry-run: preview what would be downloaded
binance-datatool --archive-home ~/data download um --freq monthly --type fundingRate -n BTCUSDT

# Download with proxy passthrough
binance-datatool download um --type klines --interval 1m --aria2-proxy BTCUSDT ETHUSDT

# Pipe from list-symbols
binance-datatool list-symbols um --quote USDT --exclude-stables \
  | binance-datatool download um --type klines --interval 1m
```

### Data flow

```
User runs:
  binance-datatool --archive-home ~/data download um --type fundingRate BTCUSDT

  ┌──────────────────────────────────────────────────────┐
  │ CLI layer  (cli/archive.py)                     │
  │  Validates interval vs data_type; resolves symbols   │
  │  from args or stdin; resolves archive home from      │
  │  --archive-home or $BINANCE_DATATOOL_ARCHIVE_HOME; constructs the download  │
  │  workflow; prints dry-run TSV or download summary;   │
  │  logs listing errors to stderr and exits 2 on fail.  │
  └──────────────────────┬───────────────────────────────┘
                         │ trade_type, data_freq, data_type,
                         │ symbols, archive_home, interval,
                         │ dry_run, inherit_aria2_proxy
  ┌──────────────────────▼───────────────────────────────┐
  │ Workflow  (workflow/)                  │
  │  Delegates to ArchiveListFilesWorkflow for remote    │
  │  listing; computes diff (new/updated/skipped) using  │
  │  local size, aria2 state, and timestamps;            │
  │  prepares aria2; clears stale .verified markers;     │
  │  deletes stale local copies; downloads with retry.   │
  └──────────────────────┬───────────────────────────────┘
                         │
          ┌──────────────┴──────────────┐
          │                             │
  ┌───────▼────────────────┐   ┌────────▼──────────────────┐
  │ Archive Client         │   │ Downloader                │
  │  (archive/        │   │  (archive/           │
  │   client.py)           │   │   downloader.py)          │
  │  Concurrent S3 file    │   │  aria2c batch download    │
  │  listings              │   │  with retry and proxy     │
  │                        │   │  control                  │
  └────────────────────────┘   └───────────────────────────┘
```

## `verify`

```
binance-datatool [--archive-home PATH] verify <TRADE_TYPE> [SYMBOLS...]
    [--freq FREQ] [--type TYPE] [--interval INTERVAL]
    [--keep-failed]
    [-n | --dry-run]
    [--progress-bar]
    [--json]
```

Verifies local archive zip files against their sibling `.CHECKSUM` files using
SHA256. Requires `BINANCE_DATATOOL_ARCHIVE_HOME` to be configured (same resolution as `download`).

| Argument / Option | Type | Default | Description |
|-------------------|------|---------|-------------|
| `TRADE_TYPE` | `TradeType` | *(required)* | Market segment (positional argument). |
| `SYMBOLS` | `list[str]` | *(see below)* | Symbols to verify, as variadic positional arguments. Same resolution rules as `list-files` and `download`. |
| `--freq` | `DataFrequency` | `daily` | Partition frequency. |
| `--type` | `DataType` | `klines` | Dataset type. |
| `--interval` | `str \| None` | `None` | Kline interval directory. Same validation as `list-files`. |
| `--keep-failed` | `bool` | `False` | Keep failed zip and checksum files instead of deleting them. |
| `-n` / `--dry-run` | `bool` | `False` | Show what would be verified without computing checksums or modifying files. |
| `--json` | `bool` | `False` | Emit one structured JSON result on stdout in either mode. |
| `--progress-bar` | `bool` | `False` | Show interactive tqdm progress bar on stderr. By default no interactive progress is shown; sampled log lines at INFO level are emitted instead. See [`common.progress`](../common/progress.md). |

### Symbol input resolution

Same convention as `list-files` and `download`: positional args win over piped
stdin, every symbol is stripped and uppercased.

### Dry-run output

Without `--json`, dry-run mode (`-n`) prints one relative path per line to stdout
for each zip file that would be verified:

```
BTCUSDT/1m/BTCUSDT-1m-2024-01-01.zip
BTCUSDT/1m/BTCUSDT-1m-2024-01-02.zip
```

A summary line is printed to stderr:

```
12 to verify, 5 up to date, 0 orphan zip, 0 orphan checksum
```

If no local zip files match the requested selection, the command still exits `0`
and prints a warning to stderr asking you to re-check `--archive-home`, the path
selection flags, and the symbol list.

### JSON output

Verification counts ZIPs as targets; their checksums are not separate verification targets.
Both modes use `command: "verify"` and the shared JSON conventions above.

| Mode | Required `summary` fields | Additional result field |
|------|---------------------------|-------------------------|
| Dry-run | `total_zips`, `to_verify`, `skipped`, `orphan_zips`, `orphan_checksums` | `to_verify`: absolute path strings for ZIPs awaiting verification. |
| Real run | `total_zips`, `verified`, `failed`, `skipped`, `orphan_zips`, `orphan_checksums` | `failed_details`: records containing absolute `path` and the workflow's failure `detail`. |

Dry-run only scans, without hashing, cleanup, or marker changes. It satisfies
`total_zips = to_verify + skipped + orphan_zips`, and `summary.to_verify` equals the plan
length. It omits completed verification counts and `failed_details`.

Real runs satisfy `total_zips = verified + failed + skipped + orphan_zips`, and
`summary.failed` equals the length of `failed_details`. They omit `to_verify` and supply
no successful or skipped file manifests. Failure details remain in the document after
the failed ZIP and its checksum are deleted by default; `--keep-failed` retains the pair.
The document is emitted before exit `2` for any verification failure. Other returned
results exit `0`, including empty scans and orphan cleanup alone.

Local paths are absolute, interpreting a relative Archive home against the invocation's
working directory. Formatting requires no file existence, leaves symlinks unresolved,
and does not change filesystem targets. A path may identify an already deleted file;
its presence does not establish existence or Verified status.

```bash
binance-datatool -v --archive-home ./archive verify um --freq monthly --type fundingRate --dry-run --json BTCUSDT
binance-datatool -v --archive-home ./archive verify um --freq monthly --type fundingRate --json BTCUSDT
```

### Normal output

Verification operates on ZIP files. `verified` counts ZIPs that passed SHA256 comparison in
this run, `failed` counts ZIPs that failed, and `skipped` counts ZIPs accepted through cached
verification without hashing again. Orphan ZIP and orphan checksum counts are separate;
clearing an orphan ZIP's markers does not delete the ZIP.

The dry-run summary's existing phrase `up to date` denotes cached verification skips. It does
not use the download comparison rules or mean those ZIPs were checked again in this run.

In verify mode, the following are printed to stderr:

- Scan diagnostics at INFO verbosity (`-v`).
- A final summary line: `Done: N verified, M failed, K skipped`.
- If `--progress-bar` is passed, interactive tqdm bars are rendered on stderr
  during both the scan and verify phases. Otherwise, sampled INFO log lines
  report progress.

If orphans were found, an additional line describes the cleanup:

```
Cleaned 1 orphan zip markers, deleted 2 orphan checksums
```

If `--keep-failed` is enabled and there are failures:

```
Failed files were kept because --keep-failed is enabled.
```

Per-file diagnostics on stderr include the failed filename and failure detail.

Like dry-run mode, a successful but empty local scan still emits a warning to
stderr instead of silently pretending everything is current.

### Interruption and resume

The parent applies each result's filesystem effects before reporting verification progress.
Fresh markers are written during the run; failures clear their markers and apply the selected
file-retention policy immediately. Completed failure details retain caller Symbol order and
sorted paths within each Symbol, even when workers finish out of order.

One Ctrl-C cancels pending work that can still be cancelled and waits for already-started
work, including prefetched tasks. It then releases workers, emits an interruption diagnostic
on stderr, and exits `130` in text and JSON modes. This wait has no fixed duration. An interrupted
invocation emits no completed-result document on stdout and returns no completed summary.

Rerun the same command to skip retained fresh markers and verify the unrecorded remainder.
Use `--dry-run` to preview that remainder without hashing, starting workers, or changing files.
Only results whose filesystem effects the parent applied are saved; hashes completed during
shutdown can be repeated. A signal between marker creation and reporting can leave slightly
more saved markers than the final reported success count.

### Orphan handling

| Orphan type | Action |
|-------------|--------|
| Zip without sibling `.CHECKSUM` | Clear all markers for the zip; **keep** the zip file. |
| `.CHECKSUM` without sibling `.zip` | Delete the checksum file and clear its markers. |

Orphan counts describe classified artifacts, rather than marker files deleted. Dry-run
reports discoveries; real-run counts describe artifacts processed under these rules.
An orphan ZIP counts even when it had no marker to clear. Orphan checksums do not
contribute to `total_zips`, and orphan cleanup does not count as failed verification.

### Verified marker protocol

A successful comparison is cached in a timestamped marker beside the ZIP. See the
[workflow reference](../workflow/README.md#timestamped-marker-protocol) for freshness and
invalidation rules. Verification reads only local files; it does not fetch missing checksums.

### Exit codes

| Situation | Exit code |
|-----------|-----------|
| No verification failures (including empty scans, orphan cleanup alone, or a completed dry-run) | `0` |
| At least one ZIP failed verification, with or without `--keep-failed` | `2` |
| Unhandled runtime error (e.g. process pool failure) | Propagates; not translated to exit `2` |
| BINANCE_DATATOOL_ARCHIVE_HOME not configured | `2` |
| Argument validation error | `2` |
| Ctrl-C during verification | `130` |

### Composition with other commands

```
# Dry-run: preview what would be verified
binance-datatool --archive-home ~/data verify um --type klines --interval 1m -n BTCUSDT

# Verify and delete failed files (default)
binance-datatool verify um --type klines --interval 1m BTCUSDT ETHUSDT

# Keep failed files for inspection
binance-datatool verify um --freq monthly --type fundingRate --keep-failed BTCUSDT

# Pipe from list-symbols
binance-datatool list-symbols um --quote USDT --exclude-stables \
  | binance-datatool verify um --type klines --interval 1m
```

### Data flow

```
User runs:
  binance-datatool --archive-home ~/data verify um --type klines --interval 1m BTCUSDT

  ┌──────────────────────────────────────────────────────┐
  │ CLI layer  (cli/archive.py)                     │
  │  Validates interval vs data_type; resolves symbols   │
  │  from args or stdin; resolves archive home; constructs  │
  │  the verify workflow; prints dry-run paths or verify │
  │  summary; logs per-file failures to stderr and      │
  │  exits 2 when any ZIP fails verification.            │
  └──────────────────────┬───────────────────────────────┘
                         │ trade_type, data_freq, data_type,
                         │ symbols, archive_home, interval,
                         │ keep_failed, dry_run
  ┌──────────────────────▼───────────────────────────────┐
  │ Workflow  (workflow/)                  │
  │  Scans local symbol directories; classifies zips     │
  │  into verify/skip/orphan buckets; cleans orphans;    │
  │  verifies SHA256 checksums in parallel via           │
  │  ProcessPoolExecutor (spawn); applies each result's  │
  │  marker/cleanup effects before reporting progress;  │
  │  cancels pending work on interruption.               │
  └──────────────────────┬───────────────────────────────┘
                         │ zip_path
  ┌──────────────────────▼───────────────────────────────┐
  │ Checksum  (archive/checksum.py)                 │
  │  verify_single_file reads the .CHECKSUM sibling,     │
  │  computes SHA256 via hashlib.file_digest, and        │
  │  returns VerifyFileResult (passed/failed + detail).  │
  └──────────────────────────────────────────────────────┘
```

---

See also: [CLI overview](README.md) | [Workflow layer](../workflow/) |
[Archive package](../archive/) | [Archive client](../archive/client.md)
