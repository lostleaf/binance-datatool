"""Compare local download plans against the pinned pre-#48 implementation."""

from __future__ import annotations

import argparse
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
import types
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from binance_datatool.archive import ArchiveFile
from binance_datatool.common import DataFrequency, DataType, TradeType
from binance_datatool.workflow import ArchiveDownloadWorkflow, ListFilesResult
from binance_datatool.workflow.results import SymbolListFilesResult

if TYPE_CHECKING:
    from collections.abc import Callable

    from binance_datatool.workflow import DiffResult

BASELINE = "c9f9aa1e66bf4790f206c2c305729eeeb42bf524"


def load_baseline(revision: str) -> type:
    """Load the pinned workflow without modifying the checkout."""
    source = subprocess.run(
        ["git", "show", f"{revision}:src/binance_datatool/workflow/download.py"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    module = types.ModuleType("binance_datatool.workflow._comparison_baseline")
    sys.modules[module.__name__] = module
    exec(compile(source, "<baseline-download>", "exec"), module.__dict__)
    return module.ArchiveDownloadWorkflow


def populate(home: Path, workload: str, objects: int, directories: int) -> ListFilesResult:
    """Create deterministic four-byte ZIP/checksum objects and sparse background."""
    symbols = []
    stamp = datetime(2026, 1, 1, tzinfo=UTC)
    for directory_index in range(directories):
        directory = home / str(directory_index)
        directory.mkdir(parents=True)
        files = []
        for index in range(objects // directories):
            name = f"{index:06d}.zip" + (".CHECKSUM" if index % 2 else "")
            path = directory / name
            state = index % 5 if workload == "mixed" else 4
            if state != 0:
                path.write_bytes(b"x" if state == 2 else b"data")
                os.utime(path, (stamp.timestamp() + (-1 if state == 1 else 1),) * 2)
                if state == 3:
                    path.with_name(f"{name}.aria2").touch()
            if workload != "sparse" or index % 200 == 199:
                files.append(
                    ArchiveFile(key=f"{directory_index}/{name}", size=4, last_modified=stamp)
                )
        symbols.append(SymbolListFilesResult(symbol=str(directory_index), files=files))
    symbols.insert(1, SymbolListFilesResult(symbol="failed2", files=[], error="second"))
    symbols.append(SymbolListFilesResult(symbol="failed1", files=[], error="first"))
    return ListFilesResult(per_symbol=symbols)


def classification(result: DiffResult) -> tuple:
    """Include the complete ordered plan, metadata, paths, reasons and failures."""
    return (
        [(entry.remote, entry.local_path, entry.reason) for entry in result.to_download],
        result.skipped,
        result.total_remote,
        [(error.symbol, error.error) for error in result.listing_errors],
    )


def measure(functions: dict[str, Callable[[], DiffResult]], repeats: int) -> None:
    """Warm once, check every timed classification, then measure separate memory peaks."""
    expected = classification(functions["baseline"]())
    for name, function in functions.items():
        # The baseline call above is its single warm-up.
        if name != "baseline":
            assert classification(function()) == expected
    timings: dict[str, list[float]] = {name: [] for name in functions}
    names = list(functions)
    for round_index in range(repeats):
        for name in names[:: 1 if round_index % 2 == 0 else -1]:
            start = time.perf_counter()
            result = functions[name]()
            timings[name].append((time.perf_counter() - start) * 1000)
            assert classification(result) == expected
    for name, function in functions.items():
        tracemalloc.start()
        result = function()
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        assert classification(result) == expected
        samples = timings[name]
        print(f"{name}: samples_ms={[round(value, 3) for value in samples]}")
        print(
            f"{name}: median_ms={statistics.median(samples):.3f} "
            f"range_ms={min(samples):.3f}..{max(samples):.3f} peak_python_kib={peak / 1024:.1f}"
        )
    print("complete_ordered_classifications_equal=True")


def main() -> None:
    """Benchmark dense, mixed and sparse comparisons on identical real scratch files."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=BASELINE)
    parser.add_argument("--objects", type=int, default=20000)
    parser.add_argument("--directories", type=int, default=10)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--temp-root", type=Path, default=None)
    args = parser.parse_args()
    if args.objects < 20000 or args.directories < 2 or args.repeats < 5:
        parser.error("require >=20000 objects, >=2 directories and >=5 repetitions")
    if args.objects % args.directories or args.objects // args.directories < 200:
        parser.error("objects must divide directories, with >=200 objects per directory")
    baseline = load_baseline(args.baseline)
    print(f"python={sys.version} platform={platform.platform()} cpus={os.cpu_count()}")
    print(f"current_source={sys.modules[ArchiveDownloadWorkflow.__module__].__file__}")
    print(f"baseline={args.baseline} temp_root={args.temp_root or tempfile.gettempdir()}")
    with tempfile.TemporaryDirectory(
        prefix="download-comparison-", dir=args.temp_root
    ) as temporary:
        root = Path(temporary)
        for workload in ("dense", "mixed", "sparse"):
            home = root / workload
            listing = populate(home, workload, args.objects, args.directories)
            print(
                f"workload={workload} objects={args.objects} directories={args.directories} "
                f"remote_objects={listing.total_remote_files} local_entries={sum(1 for p in home.rglob('*') if p.is_file())}"
            )
            functions = {}
            for name, cls in (("baseline", baseline), ("candidate", ArchiveDownloadWorkflow)):
                workflow = cls(
                    TradeType.um,
                    DataFrequency.monthly,
                    DataType.funding_rate,
                    [],
                    home,
                    dry_run=True,
                )
                functions[name] = lambda workflow=workflow, listing=listing: (
                    workflow._build_diff_result(listing)
                )
            measure(functions, args.repeats)


if __name__ == "__main__":
    main()
