# binance-datatool commands

Root CLI commands for remote archive discovery and download, plus local-only SHA256 verification.
Domain terms are defined in the [glossary](../../../GLOSSARY.md).

## `list-symbols`

```
binance-datatool list-symbols <TRADE_TYPE>
    [--freq FREQ] [--type TYPE]
    [--quote QUOTE ...] [--exclude-leverage] [--exclude-stables]
    [--contract-type CONTRACT_TYPE]
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

Flags that do not apply to the chosen market are silently ignored. When every filter flag is
at its default, no filter is constructed and the workflow runs in unfiltered mode.

**Output:** one matched symbol per line to stdout. The CLI only prints
`ListSymbolsResult.matched`; raw symbols that failed inference and symbols that were
filtered out are not printed, regardless of whether any filter flag was passed.

**Examples:**

```
binance-datatool list-symbols spot --quote USDT --exclude-leverage --exclude-stables
binance-datatool list-symbols um --quote USDT --quote USDC --contract-type perpetual
binance-datatool list-symbols cm --contract-type delivery
```

### Data flow

```
User runs:
  binance-datatool list-symbols spot --quote USDT

  ┌──────────────────────────────────────────────────────┐
  │ CLI layer  (cli/archive.py)                     │
  │  Parses arguments, builds a typed symbol filter,     │
  │  runs the workflow, and prints matched symbols.      │
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
    [--progress-bar]
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

### Symbol input resolution

| State | Behavior |
|-------|----------|
| Positional args present | Use positional args, ignoring stdin (same convention as `grep` / `cat`). |
| No positional args and stdin is piped (`isatty()` is `False`) | Read `sys.stdin`, split on newlines, drop empty lines. |
| No positional args and stdin is a tty | Raise `typer.BadParameter` → exit 2. |

Every resolved symbol is stripped and uppercased before the workflow sees it, so
`btcusdt` and `BTCUSDT` behave identically.

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

The `interval` vs `data_type.has_interval_layer` consistency check is enforced at
all three layers (CLI, Workflow, and Client) so every entry point fails loud on the
same contract violation. See the [archive client reference](../archive/client.md)
and [S3 protocol reference](../archive/s3-protocol.md) for archive listing details.

## `download`

```
binance-datatool [--archive-home PATH] download <TRADE_TYPE> [SYMBOLS...]
    [--freq FREQ] [--type TYPE] [--interval INTERVAL]
    [-n | --dry-run]
    [--aria2-proxy]
    [--progress-bar]
```

Downloads new or updated archive files into the local archive data directory.
Requires `aria2c` to be available in `PATH`.

| Argument / Option | Type | Default | Description |
|-------------------|------|---------|-------------|
| `TRADE_TYPE` | `TradeType` | *(required)* | Market segment (positional argument). |
| `SYMBOLS` | `list[str]` | *(see below)* | Symbols to download, as variadic positional arguments. Same resolution rules as `list-files`. |
| `--freq` | `DataFrequency` | `daily` | Partition frequency. |
| `--type` | `DataType` | `klines` | Dataset type. |
| `--interval` | `str \| None` | `None` | Kline interval directory. Same validation as `list-files`. |
| `-n` / `--dry-run` | `bool` | `False` | Show what would be downloaded without writing files. Outputs TSV to stdout. |
| `--aria2-proxy` | `bool` | `False` | Allow aria2c to inherit system proxy environment variables. By default, proxy env vars (`HTTP_PROXY`, `HTTPS_PROXY`, etc.) are stripped from the aria2c subprocess. |
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

In dry-run mode (`-n`), the command prints a three-column TSV to stdout:

```
new	1048	BTCUSDT/BTCUSDT-fundingRate-2026-03.zip
updated	105	BTCUSDT/BTCUSDT-fundingRate-2026-03.zip.CHECKSUM
```

Columns: `reason<TAB>size_bytes<TAB>relative_path`. A summary line is printed
to stderr: `N files to download, M up to date`.

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

### Exit codes

| Situation | Exit code |
|-----------|-----------|
| All files downloaded successfully | `0` |
| Any symbol listing failed | `2` |
| Any download failed | `2` |
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
  │  invalidates stale .verified markers; deletes stale  │
  │  local copies; invokes aria2 downloader with retry.  │
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
| `--progress-bar` | `bool` | `False` | Show interactive tqdm progress bar on stderr. By default no interactive progress is shown; sampled log lines at INFO level are emitted instead. See [`common.progress`](../common/progress.md). |

### Symbol input resolution

Same convention as `list-files` and `download`: positional args win over piped
stdin, every symbol is stripped and uppercased.

### Dry-run output

In dry-run mode (`-n`), the command prints one relative path per line to stdout
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

### Orphan handling

| Orphan type | Action |
|-------------|--------|
| Zip without sibling `.CHECKSUM` | Clear all markers for the zip; **keep** the zip file. |
| `.CHECKSUM` without sibling `.zip` | Delete the checksum file and clear its markers. |

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
  │  ProcessPoolExecutor (spawn); writes/clears markers; │
  │  optionally deletes failed files. Reports progress   │
  │  via the shared progress-reporting framework.        │
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
