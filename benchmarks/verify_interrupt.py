"""Disposable archive and real CLI signal harness; run with --help for workloads."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import queue
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from binance_datatool.archive import SymbolArchiveDir

CHILD = """
import faulthandler, os, signal
faulthandler.register(signal.SIGUSR1, all_threads=True)
os.cpu_count = lambda: 4
from binance_datatool.cli import app
app()
"""


def populate(home: Path, count: int, size: int) -> Path:
    """Create independent small pairs; hard-link larger finite hashing payloads."""
    if count <= 0 or size < 0:
        raise ValueError("count must be positive and size must be nonnegative")
    directory = home / "data/spot/daily/trades/BTCUSDT"
    directory.mkdir(parents=True)
    payload = home / "payload"
    digest = hashlib.sha256()
    block = b"x" * min(size, 1024 * 1024)
    with payload.open("wb") as stream:
        remaining = size
        while remaining:
            chunk = block[:remaining]
            stream.write(chunk)
            digest.update(chunk)
            remaining -= len(chunk)
    for index in range(count):
        path = directory / f"{index:06}.zip"
        if size <= 8192:
            path.write_bytes(block)
        else:
            os.link(payload, path)
        path.with_suffix(".zip.CHECKSUM").write_text(digest.hexdigest())
    return directory


def group_members(group: int) -> list[int]:
    """List living group members on Linux, excluding already-exited zombies."""
    members = []
    for path in Path("/proc").glob("[0-9]*/stat"):
        try:
            fields = path.read_text().rsplit(")", 1)[1].split()
            if fields[0] != "Z" and int(fields[2]) == group:
                members.append(int(path.parent.name))
        except (FileNotFoundError, ProcessLookupError):
            pass
    return members


def group_io(group: int) -> dict:
    """Read per-process character counts to distinguish active backlog drainage."""
    counts = {}
    for pid in group_members(group):
        try:
            values = dict(
                line.split(": ") for line in Path(f"/proc/{pid}/io").read_text().splitlines()
            )
            counts[pid] = int(values["rchar"])
        except FileNotFoundError:
            pass
    return counts


def run_cli(
    home: Path, *, interrupt=True, json_output=False, trace=False, deadline=60, child=CHILD
) -> dict:
    """Drain both streams and signal after observable unfinished verification."""
    command = [
        sys.executable,
        "-c",
        child,
        "-v",
        "--archive-home",
        str(home),
        "verify",
        "spot",
        "BTCUSDT",
        "--type",
        "trades",
    ]
    if json_output:
        command.append("--json")
    process = subprocess.Popen(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True
    )
    events = queue.Queue()
    output = {"stdout": [], "stderr": []}

    def drain(name, stream):
        for line in stream:
            output[name].append(line)
            events.put(line)
        stream.close()

    threads = [
        threading.Thread(target=drain, args=(name, stream), daemon=True)
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr))
    ]
    for thread in threads:
        thread.start()
    start = time.monotonic()
    signaled = None
    acknowledged = 0
    io_at_signal = {}
    io_after_signal = {}
    survivors = []
    try:
        while process.poll() is None and time.monotonic() - start < deadline:
            try:
                line = events.get(timeout=0.05)
            except queue.Empty:
                line = ""
            match = re.search(r"\[Verify\].*?\((\d+)/(\d+)\).*?ok=(\d+)", line)
            if match:
                acknowledged = max(acknowledged, int(match[3]))
            ready = match and 0 < int(match[1]) < int(match[2])
            if interrupt and signaled is None and (ready or "SIGNAL_READY" in line):
                io_at_signal = group_io(process.pid)
                signaled = time.monotonic()
                os.killpg(process.pid, signal.SIGINT)
            if trace and signaled and time.monotonic() - signaled > 2:
                io_after_signal = group_io(process.pid)
                os.kill(process.pid, signal.SIGUSR1)
                trace = False
        timed_out = process.poll() is None
        if timed_out:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=10)
        cleanup_deadline = time.monotonic() + 3
        while group_members(process.pid) and time.monotonic() < cleanup_deadline:
            time.sleep(0.01)
        survivors = group_members(process.pid)
    finally:
        if group_members(process.pid):
            os.killpg(process.pid, signal.SIGKILL)
        for thread in threads:
            thread.join(timeout=5)
    reported_successes = re.findall(r"\[Verify\].*?ok=(\d+)", "".join(output["stderr"]))
    acknowledged = max([acknowledged, *(int(count) for count in reported_successes)])
    return dict(
        code=process.returncode,
        signaled=signaled is not None,
        exit_latency=None if signaled is None else time.monotonic() - signaled,
        elapsed=time.monotonic() - start,
        acknowledged=acknowledged,
        stdout="".join(output["stdout"]),
        stderr="".join(output["stderr"]),
        survivors=survivors,
        timed_out=timed_out,
        io_at_signal=io_at_signal,
        io_after_signal=io_after_signal,
    )


def main():
    """Repeat an interrupted workload and report marker/rescan evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=60000)
    parser.add_argument("--size", type=int, default=8192)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--trace", action="store_true")
    parser.add_argument("--deadline", type=float, default=60)
    parser.add_argument("--control", action="store_true")
    args = parser.parse_args()
    if args.count <= 0:
        parser.error("--count must be positive")
    if args.size < 0:
        parser.error("--size must be nonnegative")
    if args.repeat <= 0:
        parser.error("--repeat must be positive")
    if not math.isfinite(args.deadline) or args.deadline <= 0:
        parser.error("--deadline must be finite and positive")
    for repetition in range(args.repeat):
        with tempfile.TemporaryDirectory(prefix="verify-signal-") as temporary:
            home = Path(temporary)
            directory = populate(home, args.count, args.size)
            result = run_cli(
                home, interrupt=not args.control, trace=args.trace, deadline=args.deadline
            )
            scan = SymbolArchiveDir(directory).scan()
            result.update(
                repetition=repetition + 1,
                count=args.count,
                size=args.size,
                retained=scan.skipped,
                remaining=len(scan.to_verify),
                python=sys.version.split()[0],
            )
            print(json.dumps(result), flush=True)


if __name__ == "__main__":
    main()
