#!/usr/bin/env bash

set -euo pipefail

# Preview remote download diff without writing files.
# Verify is skipped in dry-run mode because there are no newly downloaded files to check.
dry_run=false
case "${1-}" in
  "")
    ;;
  -n|--dry-run)
    dry_run=true
    ;;
  -h|--help)
    echo "Usage: $0 [--dry-run]"
    exit 0
    ;;
  *)
    echo "Unknown argument: $1" >&2
    echo "Usage: $0 [--dry-run]" >&2
    exit 2
    ;;
esac

# Build optional CLI flags once so the main command remains readable.
download_args=()
if "$dry_run"; then
  download_args+=(--dry-run)
fi

# Query the remote symbol set once, then reuse it for both download and verify.
symbols_file="$(mktemp)"
cleanup() {
  rm -f "$symbols_file"
}
trap cleanup EXIT

echo "[1/3] Listing USDⓈ-M perpetual funding-rate symbols (quote=USDT, exclude stable pairs)..." >&2
uv run binance-datatool -v list-symbols um \
  --freq monthly \
  --type fundingRate \
  --quote USDT \
  --exclude-stables \
  --contract-type perpetual \
  > "$symbols_file"

symbol_count="$(wc -l < "$symbols_file" | tr -d '[:space:]')"
echo "Selected ${symbol_count} symbols." >&2

echo "[2/3] Downloading USDⓈ-M monthly funding rates..." >&2
uv run binance-datatool -v download um \
  --freq monthly \
  --type fundingRate \
  "${download_args[@]}" \
  < "$symbols_file"

if "$dry_run"; then
  echo "[3/3] Skipping verify in dry-run mode." >&2
  echo "Dry-run mode: skipped verify because no files were downloaded." >&2
  exit 0
fi

# Verify only the symbols selected by the same remote snapshot.
echo "[3/3] Verifying downloaded USDⓈ-M monthly funding rates..." >&2
uv run binance-datatool -v verify um \
  --freq monthly \
  --type fundingRate \
  < "$symbols_file"
