"""Shared constants for the binance_datatool package."""

# Base URL for S3-compatible HTTP listing of the Binance public data archive.
S3_LISTING_PREFIX = "https://s3-ap-northeast-1.amazonaws.com/data.binance.vision"

# Base URL for direct archive file downloads from the Binance public data archive.
S3_DOWNLOAD_PREFIX = "https://data.binance.vision"

# Default timeout in seconds for a single HTTP request to the S3 listing endpoint.
S3_HTTP_TIMEOUT_SECONDS = 15

# Quote assets observed in Binance spot and USD-M symbols.
# Ordering is significant: longer suffixes must be matched before shorter ones.
# fmt: off
QUOTE_ASSETS: tuple[str, ...] = (
    # 7 chars
    "USDSOLD",
    # 5 chars
    "FDUSD", "RLUSD",
    # 4 chars
    "AEUR", "BIDR", "BKRW", "BUSD", "BVND", "DOGE", "EURI", "GYEN",
    "IDRT", "TUSD", "USD1", "USDC", "USDP", "USDS", "USDT",
    # 3 chars
    "AED", "ARS", "AUD", "BNB", "BRL", "BTC", "COP", "CZK", "DAI", "DOT",
    "ETH", "EUR", "GBP", "IDR", "JPY", "KZT", "MXN", "NGN", "PAX", "PLN",
    "RON", "RUB", "SOL", "THB", "TRX", "TRY", "UAH", "USD", "UST", "VAI",
    "XRP", "ZAR",
    # 1 char
    "U",
)
# fmt: on

# fmt: off
STABLECOINS: frozenset[str] = frozenset({
    # USD-pegged
    "USDT", "USDC", "BUSD", "TUSD", "FDUSD", "USDP", "USDS", "USDSOLD",
    "DAI", "USD1", "RLUSD", "U", "PAX", "UST", "VAI",
    # USD-pegged (only appear as base, not as quote)
    "USDSB", "SUSD",
    # EUR-pegged
    "AEUR", "EURI",
    # Other fiat-pegged
    "BKRW", "BIDR", "IDRT", "BVND", "GYEN",
})
# fmt: on

# Suffixes that identify leveraged-token bases on spot (e.g. BNBUP, BTCDOWN).
LEVERAGE_SUFFIXES: tuple[str, ...] = ("UP", "DOWN", "BULL", "BEAR")

# Base assets ending in a leverage suffix that are not leveraged tokens.
LEVERAGE_EXCLUDES: frozenset[str] = frozenset({"JUP", "SYRUP"})

# Greedy quote matches that must fall back to a shorter quote for specific bases.
# Each entry maps a long quote to (fallback_quote, {bases_requiring_fallback}).
# Update this mapping when exchangeInfo reveals a long-quote match is wrong.
QUOTE_BASE_EXCLUDES: dict[str, tuple[str, frozenset[str]]] = {
    "AEUR": ("EUR", frozenset({"ADA", "ENA", "GALA", "LUNA", "THETA"})),
    "BIDR": ("IDR", frozenset({"ARB", "BNB"})),
    "BUSD": ("USD", frozenset({"BNB"})),
    "TUSD": ("USD", frozenset({"USDT"})),
}
