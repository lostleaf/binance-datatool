# Benchmarks

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
