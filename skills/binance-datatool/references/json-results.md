# CLI JSON results

The four archive commands support `--json` starting in CLI 0.2.0.
Each returned workflow result in this mode is one JSON document on stdout, including
empty results and results returned with exit `2`. Logs, progress, summaries, and aria2
diagnostics go to stderr. Argument errors, missing configuration, or unavailable aria2
can leave stdout empty. Interrupted verification exits `130` without a completed result.

Every document contains `command` (the CLI command name), `dry_run` (boolean), and
`summary` (an object of nonnegative integer counts). The sections below give the other
top-level fields and the counts for each mode. Required fields remain present at zero
or empty. Arrays preserve result order. Object key order and whitespace are unspecified.
The format has no schema version or success field and can change between CLI releases.

## list-symbols

`dry_run` is always `false`. Each top-level array has a corresponding count in `summary`.

| Array | Count | Contents |
|-------|-------|----------|
| `symbols` | `returned_symbols` | Selected symbol names in archive listing order. |
| `matched` | `matched_symbols` | Inferred records that pass the filters. |
| `filtered_out` | `filtered_out_symbols` | Inferred records excluded by the filters. |
| `inference_failures` | `inference_failure_count` | Raw symbol names whose metadata inference failed. |

`summary.total_raw_symbols` is the sum of the three classification counts. With no filter
flags, `symbols` contains all raw names. With any filter flag, it contains the names in
`matched`, even if the chosen market ignores the filter. Both selections can exit `0`.

Every inferred record contains the strings `symbol`, `base_asset`, and `quote_asset`.
The additional attributes depend on the market.

| Market | Additional attributes |
|--------|-----------------------|
| `spot` | `is_leverage` and `is_stable_pair` (booleans) |
| `um` | `contract_type` (`perpetual` or `delivery`) and `is_stable_pair` (boolean) |
| `cm` | `contract_type` (`perpetual` or `delivery`) |

## list-files

`dry_run` is always `false`. The top-level `per_symbol` array contains one record per
distinct normalized symbol, in first-occurrence order. Each record has three fields.

| Field | Contents |
|-------|----------|
| `symbol` | Trimmed, uppercased symbol name. |
| `files` | Array of objects with `url` (full HTTPS object URL), `size` (integer bytes), and `last_modified` (UTC timestamp to the second, ending in `Z`). |
| `error` | `null` for success, including an empty directory. A failed listing has an empty `files` array and a nonempty error string. An empty exception message falls back to its class name. |

| Summary field | Meaning |
|---------------|---------|
| `requested_symbols` | Number of records in `per_symbol`. |
| `successful_symbols` | Records with `error` equal to `null`. |
| `failed_symbols` | Records with a listing error. |
| `total_remote_files` | Files from successful listings before output filtering. |
| `returned_files` | Sum of emitted `files` array lengths after filtering. |

`--only-checksum` selects keys ending in `.CHECKSUM`. `--only-zip` excludes those keys.
Both preserve symbol records even when their file arrays become empty. Choose at most one.
`--long` has no effect on the JSON fields. Any listing failure exits `2`. Successful
listings, including empty ones, exit `0`. An empty-result warning uses the unfiltered
inventory and is suppressed when a symbol listing failed.

## download

Both modes include a top-level `listing_errors` array of objects with string fields
`symbol` and `error`. The error uses the same nonempty message rule as `list-files`.
ZIPs and checksums count as separate remote objects.

| Summary field | Mode | Meaning |
|---------------|------|---------|
| `total_remote` | Both | Objects from successful listings. A listing failure leaves the inventory incomplete. |
| `skipped` | Both | Objects already up to date under the download comparison rules. |
| `listing_failed_symbols` | Both | Length of `listing_errors`. |
| `to_download` | Dry-run | Length of the top-level `to_download` array. |
| `downloaded` | Real | Objects successfully transferred, including retry successes. |
| `failed` | Real | Length of the top-level `failed_paths` array. |

- **Dry-run** adds `to_download`. Each record has `path` (absolute local path),
  `size` (integer bytes), and `reason` (`new` or `updated`).
  Counts satisfy `total_remote = skipped + to_download`.
- **Real download** adds `failed_paths`, the absolute path strings still failing after
  retries. Counts satisfy `total_remote = skipped + downloaded + failed`.

Any listing failure or final transfer failure exits `2`. Other returned results exit `0`.
For both download and verify, paths are absolute relative to the invocation's working
directory when the Archive home is relative. Paths preserve symlinks and can identify a
planned, missing, or deleted file.

## verify

Verification counts local ZIPs. The sibling checksum participates in the comparison.

| Summary field | Mode | Meaning |
|---------------|------|---------|
| `total_zips` | Both | ZIPs discovered, including orphan ZIPs. |
| `orphan_zips` | Both | ZIPs missing a checksum. Real runs keep the ZIP and clear its markers. |
| `orphan_checksums` | Both | Checksums missing a ZIP. Real runs delete the checksum and clear related markers. These checksums are outside `total_zips`. |
| `to_verify` | Dry-run | Length of the top-level `to_verify` array. |
| `already_verified` | Dry-run | ZIPs accepted using current verification markers. |
| `verified` | Real | ZIPs that passed SHA256 comparison during this run. |
| `failed` | Real | Length of the top-level `failed_details` array. |
| `skipped` | Real | ZIPs accepted using current verification markers. |

- **Dry-run** adds `to_verify`, the absolute ZIP path strings awaiting hashing.
  Counts satisfy `total_zips = to_verify + already_verified + orphan_zips`.
- **Real verification** adds `failed_details`, ordered by input symbol and then by path.
  Each record has `path` (absolute ZIP path) and `detail` (failure message). These records
  survive default deletion of failed pairs. Successful and cached ZIPs have counts only.
  Counts satisfy `total_zips = verified + failed + skipped + orphan_zips`.

A failed comparison exits `2`, including with `--keep-failed`. A completed empty scan,
orphan cleanup alone, or a successful verification exits `0`.
