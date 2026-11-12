# binance_datatool.common.constants

Shared constants imported by all other packages.

## Constants

| Constant | Type | Value | Description |
|----------|------|-------|-------------|
| `S3_LISTING_PREFIX` | `str` | `https://s3-ap-northeast-1.amazonaws.com/data.binance.vision` | Base URL for the S3 listing endpoint. |
| `S3_DOWNLOAD_PREFIX` | `str` | `https://data.binance.vision` | Base URL for direct archive file downloads. |
| `S3_HTTP_TIMEOUT_SECONDS` | `int` | `15` | Default timeout per HTTP request. |
| `QUOTE_ASSETS` | `tuple[str, ...]` | [Source](../../../src/binance_datatool/common/constants.py) | Quote suffixes used by spot and USD-M parsing. Ordered by descending length, then alphabetically within the same length. See [symbols](symbols.md) for parsing rules. |
| `STABLECOINS` | `frozenset[str]` | 24-item set | Stablecoin and fiat-pegged assets used for `is_stable_pair` detection. |
| `LEVERAGE_SUFFIXES` | `tuple[str, ...]` | `("UP", "DOWN", "BULL", "BEAR")` | Leveraged-token suffixes for spot symbols. |
| `LEVERAGE_EXCLUDES` | `frozenset[str]` | `{"JUP", "SYRUP"}` | Base assets that would otherwise be false positives for leveraged-token detection. |
| `QUOTE_BASE_EXCLUDES` | `dict[str, tuple[str, frozenset[str]]]` | 4-entry mapping | Known fallback rules for greedy quote matching. See [symbols](symbols.md) for parsing rules. |

Import note: `QUOTE_BASE_EXCLUDES` is defined in
`binance_datatool.common.constants` and is not re-exported from
`binance_datatool.common`.

---

See also: [enums](enums.md) | [symbols](symbols.md) | [Architecture](../../architecture.md)
