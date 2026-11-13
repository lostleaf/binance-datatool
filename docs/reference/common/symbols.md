# binance_datatool.common.symbols

Symbol inference helpers that accept raw Binance symbols and return typed metadata objects.
They strip all trailing settled suffixes across spot, USD-M, and COIN-M inputs before
matching contract types and quote assets. Each suffix is `SETTLED`, optionally preceded
by an underscore and followed by digits; repeated suffixes are supported too. For example,
`AERGOUSDTSETTLEDSETTLED` infers as AERGO/USDT perpetual. Returned metadata preserves the
original, unmodified symbol string.

| Function | Return Type | Description |
|----------|-------------|-------------|
| `infer_spot_info(symbol)` | `SpotSymbolInfo \| None` | Parse a spot symbol by matching `QUOTE_ASSETS` suffixes. |
| `infer_um_info(symbol)` | `UmSymbolInfo \| None` | Parse a USD-M futures symbol and infer perpetual vs delivery from the remaining underscore suffix. |
| `infer_cm_info(symbol)` | `CmSymbolInfo \| None` | Parse a COIN-M futures symbol in `BASEUSD_PERP` or `BASEUSD_YYMMDD` form. |

## Quote Parsing Rules

`infer_spot_info()` and `infer_um_info()` parse symbols by walking `QUOTE_ASSETS` from longest suffix to
shortest suffix. This is necessary because Binance has overlapping quote tokens such as `RLUSD` and
`USD`; without greedy matching, `XRPRLUSD` would be misparsed as `XRPRL + USD` instead of `XRP + RLUSD`.

Greedy matching is necessary, but it is not sufficient. A smaller set of live Binance symbols also
creates the reverse ambiguity: the symbol ends with a longer quote token, but the correct parse uses a
shorter quote. `ADAEUR` is the canonical example. The string ends with `AEUR`, but Binance's
`exchangeInfo` defines the pair as `ADA + EUR`, not `AD + AEUR`.

`QUOTE_BASE_EXCLUDES` captures those known fallback rules explicitly. Each entry has this shape:

```python
LONG_QUOTE: (FALLBACK_QUOTE, {VALID_BASES_FOR_FALLBACK})
```

Interpretation:

- Try `LONG_QUOTE` first because it is longer.
- If the same symbol also ends with `FALLBACK_QUOTE` and the base asset derived from that fallback is
  listed in `VALID_BASES_FOR_FALLBACK`, reject the greedy `LONG_QUOTE` match.
- Continue parsing with the shorter quote.

Example:

```python
"AEUR": ("EUR", {"ADA", "ENA", "GALA", "LUNA", "THETA"})
```

This means symbols such as `ADAEUR` and `LUNAEUR` should not be accepted as `AD + AEUR` or
`LUN + AEUR`. They must fall back to `ADA + EUR` and `LUNA + EUR`.

The mapping is intentionally small and evidence-driven. It is not a general symbol registry. Add new
entries only when live Binance metadata proves that a greedy long-quote match is wrong.

---

See also: [constants](constants.md) | [types](types.md) | [Architecture](../../architecture.md)
