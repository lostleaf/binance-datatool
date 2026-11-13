"""Compare warm-cache symbol scans with the pre-#30 implementation."""

from __future__ import annotations

import argparse
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import types
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

from binance_datatool.archive import SymbolArchiveDir


def load_baseline(revision: str) -> type:
    """Load the original scan implementation from a Git revision."""
    source = subprocess.run(
        ["git", "show", f"{revision}:src/binance_datatool/archive/symbol_dir.py"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    module = types.ModuleType("scan_benchmark_baseline")
    sys.modules[module.__name__] = module
    exec(compile(source, "<baseline-symbol-dir>", "exec"), module.__dict__)
    return module.SymbolArchiveDir


def populate(directory: Path, pairs: int) -> None:
    """Create fresh marker triples with deterministic fractional source mtimes."""
    directory.mkdir()
    for index in range(pairs):
        name = f"{index:06d}.zip"
        for suffix in ("", ".CHECKSUM"):
            path = directory / f"{name}{suffix}"
            path.touch()
            os.utime(path, (1000.9, 1000.9))
        (directory / f"{name}.1001.verified").touch()


def add_classification_cases(directory: Path) -> None:
    """Add stale, legacy, missing-marker, malformed-marker and orphan cases."""
    for name in ("stale", "legacy", "plain", "malformed"):
        for suffix in (".zip", ".zip.CHECKSUM"):
            path = directory / f"{name}{suffix}"
            path.touch()
            os.utime(path, (1000.9, 1000.9))
    for name in (
        "stale.zip.1000.verified",
        "legacy.zip.verified",
        "malformed.zip.bad.verified",
        "orphan.zip",
        "missing.zip.CHECKSUM",
        "unrelated.txt",
    ):
        (directory / name).touch()


def classification(result) -> tuple:
    """Compare result data independently of the baseline dataclass identity."""
    return (result.to_verify, result.orphan_zips, result.orphan_checksums, result.skipped)


def elapsed_ms(function: Callable) -> float:
    """Time one complete operation in milliseconds."""
    started = time.perf_counter()
    function()
    return (time.perf_counter() - started) * 1000


def compare(functions: dict[str, Callable], repeats: int) -> dict[str, float]:
    """Warm each operation, then alternate timing order across repeated rounds."""
    for function in functions.values():
        function()
    timings: dict[str, list[float]] = {name: [] for name in functions}
    names = list(functions)
    for round_index in range(repeats):
        for name in names[:: 1 if round_index % 2 == 0 else -1]:
            timings[name].append(elapsed_ms(functions[name]))
    medians = {}
    for name, samples in timings.items():
        medians[name] = statistics.median(samples)
        print(f"{name}: samples_ms={[round(value, 3) for value in samples]}")
        print(f"{name}: median_ms={medians[name]:.3f}")
    return medians


def main() -> None:
    """Run classification checks and reproducible warm-cache scan measurements."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="4d8830b87ac00a9e4b33ce4d39ef9761bb448863")
    parser.add_argument("--pairs", type=int, default=10000)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--temp-root", type=Path)
    args = parser.parse_args()
    if args.pairs < 10000 or args.repeats < 3:
        parser.error("use at least 10000 pairs and 3 repeats")

    baseline_class = load_baseline(args.baseline)
    print(f"Python={platform.python_version()} platform={platform.platform()}")
    print(f"cpu_count={os.cpu_count()} baseline={args.baseline}")
    print(f"package={sys.modules['binance_datatool'].__file__}")
    with tempfile.TemporaryDirectory(prefix="scan-benchmark-", dir=args.temp_root) as root_text:
        root = Path(root_text)
        directory = root / "single"
        populate(directory, args.pairs)
        add_classification_cases(directory)
        baseline = baseline_class(directory).scan
        current = SymbolArchiveDir(directory).scan
        expected = classification(baseline())
        assert classification(current()) == expected
        missing = root / "missing"
        assert classification(baseline_class(missing).scan()) == classification(
            SymbolArchiveDir(missing).scan()
        )
        print(f"directory={directory} entries={len(list(directory.iterdir()))}")
        print(
            f"composition={args.pairs} fresh triples + 4 pairs + 3 markers + 2 orphans + 1 ignored"
        )
        print("equal_classification=True (including missing directory)")
        print(
            f"counts: pending={len(expected[0])} orphan_zips=1 orphan_checksums=1 skipped={expected[3]}"
        )

        def checked_current():
            assert classification(current()) == expected

        def checked_baseline():
            assert classification(baseline()) == expected

        medians = compare(
            {"baseline": checked_baseline, "single_pass": checked_current}, args.repeats
        )
        print(f"speedup={medians['baseline'] / medians['single_pass']:.2f}x")

        directories = [root / f"symbol-{index}" for index in range(5)]
        pairs_per_directory, remainder = divmod(args.pairs, len(directories))
        for index, symbol_dir in enumerate(directories):
            populate(symbol_dir, pairs_per_directory + (index < remainder))

        def serial_scan():
            return [SymbolArchiveDir(path).scan() for path in directories]

        def threaded_scan():
            with ThreadPoolExecutor(max_workers=5) as executor:
                return list(executor.map(lambda path: SymbolArchiveDir(path).scan(), directories))

        assert serial_scan() == threaded_scan()
        print("multi-symbol: 5 directories, same total fresh pair count, equal_classification=True")
        compare({"serial": serial_scan, "threads5": threaded_scan}, args.repeats)


if __name__ == "__main__":
    main()
