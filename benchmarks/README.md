# Benchmarks

## Download comparison

Run from the repository root with the project's environment:

```bash
uv run python benchmarks/download_comparison.py --objects 20000 --directories 10 --repeats 7
```

The maintained script loads `ArchiveDownloadWorkflow` from pinned revision
`c9f9aa1e66bf4790f206c2c305729eeeb42bf524` through Git and compares its local comparison
method with the current checkout. `--baseline` selects another revision, and `--temp-root`
selects the scratch filesystem. The source path identifies the imported candidate. Fixtures
are disposable and shared by both implementations. Listing, hashing, transfer, and fixture
construction are excluded from measurement.

All workloads use ten directories and 20,000 remotely sized four-byte objects, alternating
ZIP/checksum filenames. Each directory contains 2,000 object names:

| Workload | Remote selection | Local entries | Expected classification |
|----------|------------------|---------------|-------------------------|
| Dense | All 20,000 objects | 20,000 complete objects | 20,000 skipped |
| Mixed | All 20,000 objects | 16,000 objects plus 4,000 ordinary `.aria2` controls | 4,000 new, 12,000 updated, 4,000 skipped |
| Sparse | Every 200th name, 100 objects total (ten checksums per directory) | 20,000 complete objects | 100 skipped |

Mixed updates comprise 4,000 older objects, 4,000 wrong-sized objects, and 4,000 complete-sized
objects with controls. Equal/newer mtimes, symlinks, marker independence, real permissions,
filesystem faults, dry-run preservation, and missing directories are covered by workflow
tests. Each workload also interleaves two listing failures in a fixed order.

Each implementation receives one warm-up. Seven measured rounds alternate execution order,
and every result must equal the baseline's complete ordered plan: remote metadata, local
paths, reasons, skipped/remote counts, and ordered listing failures. A separate `tracemalloc`
run records peak Python allocations for the whole comparison, including selected result
objects and snapshots; it excludes existing remote input and filesystem page cache. This is
an allocation peak, not process RSS. No machine-dependent threshold runs in ordinary CI.

### Recorded result

Measured on 2026-11-15 with Python 3.13.18, Linux 7.0.0-42-generic x86_64, glibc 2.39,
AMD Ryzen 9 9950X (32 reported CPUs), and `/tmp` on ext4 at `/dev/nvme0n1p2`. Candidate code
commit: `68ede56`. Every complete ordered classification matched.

| Workload / implementation | Seven warm-cache timings (ms) | Median (ms) | Min–max (ms) | Peak Python allocation (KiB) |
|---------------------------|-------------------------------|-------------|--------------|------------------------------|
| Dense baseline | 164.658, 160.656, 160.827, 164.563, 162.554, 162.092, 160.387 | 162.092 | 160.387–164.658 | 2.0 |
| Dense candidate | 86.903, 83.847, 85.920, 90.848, 85.839, 83.526, 85.181 | 85.839 | 83.526–90.848 | 8414.4 |
| Mixed baseline | 152.082, 154.102, 180.256, 172.236, 154.110, 156.620, 156.561 | 156.561 | 152.082–180.256 | 8033.9 |
| Mixed candidate | 97.376, 97.475, 97.323, 98.025, 96.600, 115.621, 118.380 | 97.475 | 96.600–118.380 | 10426.3 |
| Sparse baseline | 0.785, 0.775, 0.770, 0.774, 0.773, 0.779, 0.774 | 0.774 | 0.770–0.785 | 2.0 |
| Sparse candidate | 0.770, 0.766, 0.773, 0.774, 0.770, 0.764, 0.769 | 0.770 | 0.764–0.774 | 19.8 |

Dense comparison improved by 1.89 times and mixed comparison by 1.61 times, with disjoint
timing ranges. Sparse timings overlap. Dense snapshots add about 8.2 MiB of peak Python
allocation; mixed adds about 2.3 MiB above its existing selected-result allocation. Only
requested entries are retained, and completed directories release their snapshots.

An initial bounded-enumeration candidate still regressed this sparse workload from a median
0.783 ms to 1.781 ms. Opening a directory remained costly even after bounding unrelated entry
visits. The final implementation therefore refines the planned one-enumeration approach:
selections of at most 16 names per directory bypass enumeration and use one direct object
stat plus a control existence check. This measured workload selects ten names per directory;
16 is a conservative implementation threshold, not a universal filesystem crossover. Larger
selections bound unrelated visits and fall back to direct lookups when the snapshot is partial.

These are warm-cache comparison measurements. They establish neither cold-cache performance
nor end-to-end download throughput, and the earlier roughly four-times prototype gain is
supporting evidence rather than a promised ratio.

## Directory scans

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

### Recorded result

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

## XML listing parser

Run from the repository root:

```bash
uv run --with xmltodict==1.0.4 python benchmarks/xml_listing.py
```

The extra dependency is isolated to this benchmark invocation. The script loads
the original client from pinned revision `4d8830b87ac00a9e4b33ce4d39ef9761bb448863`
through Git and compares its complete XML-to-file-record conversion with the
current worktree's implementation. `--baseline` selects another revision that
still exposes the original parser. The printed current source path identifies
the package being measured.

Both parsers receive the same synthetic S3 page: 1,000 `Contents` elements,
222,117 bytes, the standard S3 namespace, object keys, sizes, UTC modification
timestamps, ETags, and storage classes. All ordered `(key, size, last_modified)`
records must match before timing. Network requests are excluded.

Each parser receives one warmup, then seven repetitions of 30 complete page
conversions. `--repeats` and `--iterations` change those counts. The result is the
median time per page; this is a manual benchmark, separate from unit-test timing.

### Recorded result

Measured on 2026-11-13 with Python 3.13.18, Linux 7.0.0-30-generic x86_64,
glibc 2.39, and 32 reported CPUs. The isolated comparison dependency was
`xmltodict==1.0.4`. All 1,000 output records were equal.

| Parser | Median per page (ms) |
|--------|----------------------|
| Original XML parsing and file-record conversion | 8.654 |
| Standard-library ElementTree and file-record conversion | 2.193 |

The median improved by **3.95 times**, exceeding the issue's three-times target
on this environment. This controlled parser measurement does not remeasure the
historical full-archive listing runs or guarantee a speedup on every machine.

## Verification interruption

`verify_interrupt.py` is a Linux-only real CLI/process-group signal harness. Run from the
repository root with the desired interpreter and this checkout on `PYTHONPATH`:

```bash
PYTHONPATH=src uv run python benchmarks/verify_interrupt.py --count 60000 --size 8192 --repeat 3
PYTHONPATH=src uv run python benchmarks/verify_interrupt.py --count 60000 --size 8192 --repeat 1 --control
PYTHONPATH=src uv run python benchmarks/verify_interrupt.py --count 400 --size 268435456 --repeat 1
PYTHONPATH=src uv run python benchmarks/verify_interrupt.py --count 400 --size 268435456 --repeat 1 --control
```

`--count` and `--repeat` must be positive, `--size` must be nonnegative, and `--deadline`
must be finite and positive. Invalid arguments exit 2 before creating a disposable Archive home.

Every repetition creates and deletes a disposable Archive home. Small payloads use independent
files; larger payloads use hard links to a single finite payload so the slower workload hashes
100 GiB without reserving 100 GiB of storage. Checksums are independent files. Both variants
perform real SHA256 comparisons through real spawned workers. The harness overrides the child
CPU count to four, selecting two workers through the existing default; it adds no production
worker option. Results measure warm local storage, not cold-cache behavior.

The harness drains stdout/stderr concurrently and sends exactly one process-group SIGINT after
sampled verification progress while unfinished targets remain. It records acknowledged successes
including the final aborted progress count, fresh markers retained by rescan, remaining targets,
exit latency, output, and surviving non-zombie group members. Its 60-second default deadline
forces cleanup on failure; this safeguard does not define a product shutdown limit. `--trace`
captures the parent's thread stacks two seconds after a signal if the process is still alive,
alongside per-process `/proc/PID/io` character counts at signal time and capture time.

For baseline diagnosis, create a detached disposable checkout at
`c9f9aa1e66bf4790f206c2c305729eeeb42bf524` and set `PYTHONPATH` to that checkout's `src` while
running this harness. This pins the implementation without editing the current checkout or
using a user's Archive home. To reproduce the original stall path, use the slower workload
with `--trace --deadline 8`. No temporary planning script is required.

### Diagnosis and regression evidence

Measured on 2026-11-15, Linux 7.0.0-42-generic x86_64 and ext4 on `/dev/nvme0n1p2` at `/tmp`.
The baseline and candidate both retain the spawned process pool. In baseline tiny-file trials,
one group SIGINT often exited quickly by interrupting idle workers, which emitted worker
`KeyboardInterrupt` tracebacks. The historical tiny-file stall was timing-sensitive and did
not recur in those trials. Every trial still lost all new markers despite reported successes.

With 400 finite 256 MiB targets and active hashes at interruption, the baseline stalled until
the harness deadline with zero saved markers after 20 reported successes. A live stack capture
located the parent in `ProcessPoolExecutor.__exit__ → shutdown → thread.join`; the executor
manager thread was waiting for worker results. In two seconds after the signal, each worker's
`rchar` increased from 2,692,908,944 to 7,977,524,916 bytes: roughly twenty additional payloads
per worker, exceeding the prefetched active subset. This establishes queued-work drainage during
normal context-manager shutdown as the reproduced stall's cause, rather than inferring it from
elapsed time alone. The uninterrupted baseline completed the same finite workload in 21.077 s.
It does not establish the exact stack of the historical uninstrumented tiny-file run.

The workflow regression first failed with zero fresh markers at the first reported success.
The real CLI signal/resume regression also failed against the baseline: six acknowledged
successes and zero fresh markers. Both pass with incremental parent effects and cancellation
before waiting. Maintained tests additionally cover text/JSON parity, process ownership during
submission/startup, no surviving workers, mixed markers/failure policies, progress after effects,
and deterministic completed failure order. The completion-order test uses a FIFO checksum gate,
so its order assertion does not depend on relative hashing speeds.

### Recorded candidate results

Candidate code: `6854056`, with fixture/reporting improvements in `e47deed`. Each tiny-file row
is a separate 60,000-pair, 8 KiB run using independent ZIP files. Time is measured from SIGINT
to exit and process-group cleanup; control rows measure the entire CLI invocation.

| Python | Workload | Exit latency / control time (s) | Acknowledged successes | Fresh markers retained | Rescan pending |
|--------|----------|--------------------------------|------------------------|------------------------|----------------|
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

Every interrupted candidate invocation exited `130` after one signal, with empty stdout,
no worker traceback, no surviving workers, and at least as many fresh markers as acknowledged
successes. Controls exited `0`. The real CLI tests rerun the interrupted fixture, skip retained
markers, and finish all remaining files on Python 3.11 and 3.14. These finite-workload latencies
are measurements, not guarantees: already-started and executor-prefetched non-cancellable work
can make other invocations wait longer. A marker created immediately before interruption can
be saved without a corresponding progress tick, explaining the one-marker differences above.
