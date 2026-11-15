# Retain useful API conveniences and remove the ambiguous symbol count alias

Retain the module-level `list_symbols()`, all three symbol filters' `__call__` methods, and
`SymbolArchiveDir.clear_markers()`: their documented call shapes offer useful convenience
while reusing the underlying operations. The internal non-use established by
[Issue #34](https://github.com/lostleaf/binance-datatool/issues/34) does not establish external non-use.

Remove `ListSymbolsResult.unmatched_symbols` directly in the next normal release to make
the inference-failure count unambiguous. The maintainer accepts the compatibility break to
keep one canonical name for this count. Caller changes belong in the
[migration guidance](../reference/workflow/README.md#listsymbolsresult).
