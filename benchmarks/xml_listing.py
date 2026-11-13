"""Compare complete listing-page conversion with the original parser.

Run from the repository root with the optional baseline parser installed only
for this invocation::

    uv run --with xmltodict==1.0.4 python benchmarks/xml_listing.py

The baseline source comes from Git; the installed package remains the current
worktree's implementation. No network requests are measured.
"""

from __future__ import annotations

import argparse
import os
import platform
import statistics
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType
from typing import TYPE_CHECKING
from xml.etree import ElementTree

from binance_datatool.archive.client import ArchiveFile, _extract_files

if TYPE_CHECKING:
    from collections.abc import Callable

BASELINE = "4d8830b87ac00a9e4b33ce4d39ef9761bb448863"


def listing_xml() -> str:
    """Build a representative 1,000-object S3 page with ignored metadata too."""
    entries = "".join(
        "<Contents><Key>data/futures/um/daily/klines/BTCUSDT/1m/"
        f"BTCUSDT-1m-{index:06d}.zip</Key>"
        '<LastModified>2026-11-01T01:02:03.000Z</LastModified><ETag>"abcdef"</ETag>'
        "<Size>45000</Size><StorageClass>STANDARD</StorageClass></Contents>"
        for index in range(1000)
    )
    return (
        '<ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/">'
        "<IsTruncated>false</IsTruncated>" + entries + "</ListBucketResult>"
    )


def load_baseline(ref: str) -> ModuleType:
    """Load the original conversion code from a pinned repository revision."""
    source = subprocess.check_output(
        ["git", "show", f"{ref}:src/binance_datatool/archive/client.py"], text=True
    )
    module = ModuleType("_baseline_archive_client")
    sys.modules[module.__name__] = module
    exec(compile(source, f"{ref}:archive/client.py", "exec"), module.__dict__)
    return module


def milliseconds(function: Callable[[], object], repeats: int, iterations: int) -> float:
    """Return median per-page milliseconds after one unmeasured warmup."""
    function()
    samples = []
    for _ in range(repeats):
        started = time.perf_counter()
        for _ in range(iterations):
            function()
        samples.append((time.perf_counter() - started) * 1000 / iterations)
    return statistics.median(samples)


def main() -> None:
    """Check equivalent output and report old and current conversion medians."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default=BASELINE)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--iterations", type=int, default=30)
    args = parser.parse_args()
    if args.repeats < 1 or args.iterations < 1:
        parser.error("repeats and iterations must be positive")
    baseline = load_baseline(args.baseline)
    xml = listing_xml()

    def old() -> list[ArchiveFile]:
        return baseline._extract_files_from_payload(baseline.xmltodict.parse(xml))

    def current() -> list[ArchiveFile]:
        return _extract_files(ElementTree.fromstring(xml))

    # Different revisions define distinct dataclass types; compare their fields.
    old_records = [(file.key, file.size, file.last_modified) for file in old()]
    current_records = [(file.key, file.size, file.last_modified) for file in current()]
    assert old_records == current_records
    old_ms = milliseconds(old, args.repeats, args.iterations)
    current_ms = milliseconds(current, args.repeats, args.iterations)
    print(
        f"Python={platform.python_version()} platform={platform.platform()} cpus={os.cpu_count()}"
    )
    print(f"Current source={Path(sys.modules[ArchiveFile.__module__].__file__).resolve()}")
    print(f"Baseline={args.baseline} entries=1000 bytes={len(xml.encode())} equivalent=True")
    print(f"Repetitions={args.repeats} iterations/repetition={args.iterations} warmup=1")
    print(
        f"Baseline={old_ms:.3f} ms/page current={current_ms:.3f} ms/page speedup={old_ms / current_ms:.2f}x"
    )


if __name__ == "__main__":
    main()
