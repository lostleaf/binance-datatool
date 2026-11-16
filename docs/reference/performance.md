# Performance Evidence

Recorded measurements that support performance and interruption design decisions. The
measurement scripts were removed after the work was complete. To rerun one, restore it from
commit `216a72c`, for example `git show 216a72c:benchmarks/download_comparison.py`; that
commit's `benchmarks/README.md` has the run commands.

All results are controlled warm-cache measurements on one machine. They establish neither
cold-cache performance nor end-to-end throughput, and they are not guarantees for other
filesystems or machines. No machine-dependent threshold runs in CI.

## Download comparison

Issue #48. Compares `ArchiveDownloadWorkflow` local comparison at baseline
`c9f9aa1e66bf4790f206c2c305729eeeb42bf524` with the candidate. Listing, hashing, transfer,
and fixture construction are excluded.

Every workload uses ten directories and 20,000 remotely sized four-byte objects, alternating
ZIP/checksum names, with two interleaved listing failures:

| Workload | Remote selection | Local entries | Expected classification |
|----------|------------------|---------------|-------------------------|
| Dense | All 20,000 objects | 20,000 complete objects | 20,000 skipped |
| Mixed | All 20,000 objects | 16,000 objects plus 4,000 `.aria2` controls | 4,000 new, 12,000 updated, 4,000 skipped |
| Sparse | Every 200th name, 100 objects (ten per directory) | 20,000 complete objects | 100 skipped |

Mixed updates comprise 4,000 older, 4,000 wrong-sized, and 4,000 complete-sized objects with
controls. Each implementation had one warm-up and seven alternating rounds. Every result
matched the baseline's complete ordered plan. Peak allocation is a `tracemalloc` peak of Python
allocations, not process RSS.

Measured 2026-11-15: Python 3.13.18, Linux 7.0.0-42-generic x86_64, AMD Ryzen 9 9950X,
ext4 `/tmp`. Candidate commit `68ede56`.

| Workload / implementation | Median (ms) | Min–max (ms) | Peak Python allocation (KiB) |
|---------------------------|-------------|--------------|------------------------------|
| Dense baseline | 162.092 | 160.387–164.658 | 2.0 |
| Dense candidate | 85.839 | 83.526–90.848 | 8414.4 |
| Mixed baseline | 156.561 | 152.082–180.256 | 8033.9 |
| Mixed candidate | 97.475 | 96.600–118.380 | 10426.3 |
| Sparse baseline | 0.774 | 0.770–0.785 | 2.0 |
| Sparse candidate | 0.770 | 0.764–0.774 | 19.8 |

Dense improved 1.89 times and mixed 1.61 times, with disjoint ranges; sparse overlaps.

**Sparse-selection threshold.** An earlier bounded-enumeration candidate regressed sparse from
0.783 ms to 1.781 ms: opening a directory stayed costly even with bounded entry visits. The
final implementation therefore uses one direct object stat plus a control existence check for
selections of at most 16 names per directory. The value 16 is a conservative threshold, not a
measured filesystem crossover.

## Directory scans

Issue #30. Compares the original three-glob `SymbolArchiveDir` scan at baseline
`4d8830b87ac00a9e4b33ce4d39ef9761bb448863` with the single directory pass.

The single directory holds 30,014 entries: 10,000 fresh ZIP/checksum/marker triples, four
pending pairs, three stale/legacy/malformed markers, one orphan ZIP, one orphan checksum, and one
unrelated file. Every timed scan matched the original classification, including a missing
directory. A second comparison scans five Symbol directories with the same total pair count,
serially and with five threads.

Measured 2026-11-13: Python 3.13.18, Linux 7.0.0-30-generic x86_64, AMD Ryzen 9 9950X,
ext4 `/tmp`. Seven rounds each.

| Operation | Median (ms) |
|-----------|-------------|
| Original three-glob scan | 182.140 |
| Single directory pass | 40.391 |
| Five Symbols, serial | 34.566 |
| Five Symbols, five threads | 96.071 |

The single pass improved 4.51 times. Serial scanning beat threading, so the verify workflow
scans serially.

## XML listing parser

Issue #28. Compares complete XML-to-`ArchiveFile` conversion of the original `xmltodict`
parser at baseline `4d8830b87ac00a9e4b33ce4d39ef9761bb448863` with the standard-library
ElementTree parser. Input is one synthetic 1,000-entry S3 page (222,117 bytes); all ordered
`(key, size, last_modified)` records matched. Network requests are excluded.

Measured 2026-11-13: Python 3.13.18, Linux 7.0.0-30-generic x86_64, `xmltodict==1.0.4`.
Seven repetitions of 30 pages.

| Parser | Median per page (ms) |
|--------|----------------------|
| Original `xmltodict` | 8.654 |
| ElementTree | 2.193 |

The median improved 3.95 times, above the issue's three-times target.

## Verification interruption

Issue #47. A real CLI run in a disposable Archive home receives one process-group SIGINT
while unfinished targets remain. Workers are real spawned processes doing real SHA256
comparison; the child reports four CPUs, which selects two workers.

### Diagnosis

Baseline `c9f9aa1e66bf4790f206c2c305729eeeb42bf524`. With 400 hard-linked 256 MiB targets and
active hashes at interruption, the baseline stalled until the harness deadline and saved zero
markers after 20 reported successes. A live stack placed the parent in
`ProcessPoolExecutor.__exit__ → shutdown → thread.join`. In two seconds after the signal, each
worker's `/proc` `rchar` rose from 2,692,908,944 to 7,977,524,916 bytes, about twenty more
payloads per worker. This identified queued-work drainage during context-manager shutdown as
the cause. Uninterrupted, the baseline finished the same workload in 21.077 s.

In baseline tiny-file trials, one SIGINT often exited quickly with worker `KeyboardInterrupt`
tracebacks; the historical tiny-file stall did not recur. Every baseline trial lost all new
markers despite reported successes.

### Candidate results

Candidate commit `6854056`, fixture improvements `e47deed`. Measured 2026-11-15, Linux
7.0.0-42-generic x86_64, ext4 `/tmp`. Latency runs from SIGINT to exit and process-group
cleanup; uninterrupted rows time the whole CLI run.

| Python | Workload | Latency / run time (s) | Acknowledged successes | Verified markers retained | Rescan pending |
|--------|----------|------------------------|------------------------|---------------------------|----------------|
| 3.11.18 | 60,000 × 8 KiB, trial 1 | 0.185 | 3,008 | 3,008 | 56,992 |
| 3.11.18 | 60,000 × 8 KiB, trial 2 | 0.181 | 3,002 | 3,002 | 56,998 |
| 3.11.18 | 60,000 × 8 KiB, trial 3 | 0.184 | 3,004 | 3,004 | 56,996 |
| 3.11.18 | 60,000 × 8 KiB, uninterrupted | 3.471 | 60,000 | 60,000 | 0 |
| 3.14.10 | 60,000 × 8 KiB, trial 1 | 0.111 | 3,002 | 3,002 | 56,998 |
| 3.14.10 | 60,000 × 8 KiB, trial 2 | 0.111 | 3,001 | 3,002 | 56,998 |
| 3.14.10 | 60,000 × 8 KiB, trial 3 | 0.109 | 3,001 | 3,002 | 56,998 |
| 3.14.10 | 60,000 × 8 KiB, uninterrupted | 3.291 | 60,000 | 60,000 | 0 |
| 3.11.18 | 400 × 256 MiB, active hashes | 0.369 | 20 | 20 | 380 |
| 3.14.10 | 400 × 256 MiB, active hashes | 0.373 | 20 | 20 | 380 |
| 3.14.10 | 400 × 256 MiB, uninterrupted | 20.792 | 400 | 400 | 0 |

Every interrupted run exited `130` after one signal, with empty stdout, no worker traceback, no
surviving workers, and at least as many retained markers as acknowledged successes. A marker
saved just before interruption can lack a progress tick, which explains the one-marker
differences. Already-started and prefetched work can make other runs wait longer. The signal
regressions in `tests/test_verify_interrupt.py` keep this behavior covered.

---

See also: [Workflow reference](workflow/README.md) | [Test organization](testing.md)
