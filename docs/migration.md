# Migration notes

## Verification dry-run

For `verify --dry-run`, the terminal summary now says `already verified` where it used to say
`up to date`. Update JSON consumers of this mode to read `summary.already_verified` in place of
`summary.skipped`. The count represents ZIPs skipped because they have current verification
markers.

## Inference failures

Update Python callers of `ListSymbolsResult` and scripts that read `list-symbols --json`.

| Interface | Previous name | New name |
|-----------|---------------|----------|
| Python `ListSymbolsResult` | `unmatched` | `inference_failures` |
| Python `ListSymbolsResult` | `inference_failed_symbols` | `inference_failure_count` |
| `list-symbols` JSON | `uninferable` | `inference_failures` |
| `list-symbols` JSON | `summary.uninferable_symbols` | `summary.inference_failure_count` |

The list contains raw symbol names whose metadata inference failed. The count equals the
length of that list. Symbols with inferred metadata that the filter excludes still belong
to `filtered_out`. If you are upgrading from a version that exposed the older
`unmatched_symbols` count, switch directly to `inference_failure_count`.
