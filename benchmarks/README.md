# Scan benchmark

Run from the repository root with the project's environment:

```bash
uv run python benchmarks/scan_symbol_dir.py --pairs 10000 --repeats 7
```

The script loads the original `SymbolArchiveDir` implementation from the specified
Git revision without changing the working tree. It creates disposable directories
under `/tmp` by default; `--temp-root PATH` selects another filesystem. It prints
the imported package path so a worktree run can confirm which source it measures.
The default baseline is pinned to `4d8830b87ac00a9e4b33ce4d39ef9761bb448863`;
its scanner is identical to the implementation immediately before #30.

The single-directory input contains 30,014 entries: 10,000 fresh ZIP/checksum/marker
triples, four additional ZIP/checksum pairs, three stale/legacy/malformed markers,
one orphan ZIP, one orphan checksum, and one unrelated file. Source mtimes are
1000.9 seconds; fresh markers carry timestamp 1001, exercising upward rounding.
Every timed scan compares its full classification with the original implementation.
Expected counts are 10,000 skipped, four pending, one orphan ZIP, and one orphan
checksum. The script also checks equal results for a missing directory.

Each operation runs once before measurement to warm the filesystem cache. Timing
rounds alternate the order of the old and current scanners. A second comparison
scans five separate symbol directories, sharing the same total fresh pair count,
serially and with five threads; executor construction is included in each threaded
measurement. No hashing or marker writes occur during timed scans.

## Recorded result

Measured on 2026-11-13 with Python 3.13.18, Linux 7.0.0-30-generic x86_64,
glibc 2.39, AMD Ryzen 9 9950X (32 reported CPUs), and an ext4 filesystem on
`/dev/nvme0n1p2` mounted at `/tmp`. Baseline revision:
`4d8830b87ac00a9e4b33ce4d39ef9761bb448863` (before #30).
All classifications were equal, including the missing-directory case.

| Operation | Seven warm-cache timings (ms) | Median (ms) |
|-----------|-------------------------------|-------------|
| Original three-glob scan | 182.140, 182.121, 182.026, 182.995, 182.222, 181.869, 193.371 | 182.140 |
| Single directory pass | 40.648, 39.613, 40.391, 49.011, 39.856, 39.761, 40.748 | 40.391 |
| Five symbols, serial | 34.928, 40.390, 35.518, 34.566, 33.192, 34.154, 32.471 | 34.566 |
| Five symbols, five threads | 102.259, 87.392, 106.831, 73.664, 106.545, 94.446, 96.071 | 96.071 |

The single-directory median improved by **4.51 times**. Serial scanning was faster
than threading in this environment, so the workflow scans serially. These are
controlled warm-cache measurements, not a guarantee for every filesystem or machine.
