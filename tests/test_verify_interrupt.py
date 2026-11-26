"""Verification persistence and real process-group interruption regressions."""

from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from binance_datatool.archive import SymbolArchiveDir, create_symbol_archive_dir
from binance_datatool.common import DataFrequency, DataType, MarketType
from binance_datatool.common.progress import LogReporter
from binance_datatool.workflow import ArchiveVerifyWorkflow

# Four reported CPUs select two workers through the existing default.
CHILD = """
import os
os.cpu_count = lambda: 4
from binance_datatool.cli import app
app()
"""

# Forces cleanup on harness failure; this is not a product shutdown limit.
SIGNAL_DEADLINE = 60


def populate(home: Path, count: int, size: int) -> Path:
    """Create independent small pairs; hard-link larger finite hashing payloads."""
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


def run_cli(home: Path, *, interrupt=True, json_output=False, child=CHILD) -> dict:
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
    signaled = False
    acknowledged = 0
    survivors = []
    try:
        while process.poll() is None and time.monotonic() - start < SIGNAL_DEADLINE:
            try:
                line = events.get(timeout=0.05)
            except queue.Empty:
                line = ""
            match = re.search(r"\[Verify\].*?\((\d+)/(\d+)\).*?ok=(\d+)", line)
            if match:
                acknowledged = max(acknowledged, int(match[3]))
            ready = match and 0 < int(match[1]) < int(match[2])
            if interrupt and not signaled and (ready or "SIGNAL_READY" in line):
                signaled = True
                os.killpg(process.pid, signal.SIGINT)
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
        signaled=signaled,
        acknowledged=acknowledged,
        stdout="".join(output["stdout"]),
        stderr="".join(output["stderr"]),
        survivors=survivors,
        timed_out=timed_out,
    )


def test_verify_persists_before_progress(tmp_path, monkeypatch):
    """Acknowledged successes survive interruption before the batch completes."""
    directory = create_symbol_archive_dir(
        tmp_path, MarketType.spot, DataFrequency.daily, DataType.trades, "BTCUSDT"
    )
    directory.path.mkdir(parents=True)
    for index in range(3):
        path = directory.path / f"{index}.zip"
        path.write_bytes(b"payload")
        path.with_suffix(".zip.CHECKSUM").write_text(hashlib.sha256(b"payload").hexdigest())

    original_tick = LogReporter.tick

    def interrupt_after_success(self, event):
        if event.name.endswith(".zip"):
            assert directory.scan().skipped == 1
            raise KeyboardInterrupt
        original_tick(self, event)

    monkeypatch.setattr(LogReporter, "tick", interrupt_after_success)
    workflow = ArchiveVerifyWorkflow(
        MarketType.spot,
        DataFrequency.daily,
        DataType.trades,
        ["BTCUSDT"],
        tmp_path,
        n_workers=1,
    )
    with pytest.raises(KeyboardInterrupt):
        workflow.run()
    assert directory.scan().skipped == 1
    assert len(directory.scan().to_verify) == 2


@pytest.mark.skipif(sys.platform != "linux", reason="requires POSIX groups and /proc")
@pytest.mark.parametrize("json_output", [False, True])
def test_cli_one_sigint_retains_successes_and_resumes(tmp_path, json_output):
    """A real group signal preserves acknowledged work and leaves no workers."""
    directory = populate(tmp_path, 120, 32 * 1024 * 1024)
    result = run_cli(tmp_path, json_output=json_output)
    assert result["signaled"], result
    assert not result["timed_out"], result
    assert result["code"] == 130, result
    assert result["stdout"] == ""
    assert result["stderr"]
    assert "Traceback" not in result["stderr"]
    assert not result["survivors"]
    scan = SymbolArchiveDir(directory).scan()
    assert 0 < result["acknowledged"] <= scan.skipped < 120
    pending_names = {path.name for path in scan.to_verify}
    acknowledged_names = re.findall(r"last=(\S+\.zip)", result["stderr"])
    assert acknowledged_names
    assert not pending_names.intersection(acknowledged_names)
    workflow = ArchiveVerifyWorkflow(
        MarketType.spot,
        DataFrequency.daily,
        DataType.trades,
        ["BTCUSDT"],
        tmp_path,
        dry_run=True,
    )
    remaining = workflow.run()
    assert remaining.skipped == scan.skipped
    assert remaining.to_verify == scan.to_verify
    assert len(remaining.to_verify) == 120 - scan.skipped
    rerun = run_cli(tmp_path, interrupt=False, json_output=True)
    assert rerun["code"] == 0, rerun
    summary = json.loads(rerun["stdout"])["summary"]
    assert summary["skipped"] == scan.skipped
    assert summary["verified"] == 120 - scan.skipped
    assert SymbolArchiveDir(directory).scan().skipped == 120
    assert not rerun["survivors"]


@pytest.mark.skipif(sys.platform != "linux", reason="requires POSIX groups and /proc")
@pytest.mark.parametrize("phase", ["submission", "startup"])
def test_cli_interrupt_during_pool_start_and_submission(tmp_path, phase):
    """Real workers are reclaimed even while pool ownership is being established."""
    populate(tmp_path, 50, 1024 * 1024)
    if phase == "submission":
        setup = """
from concurrent.futures import ProcessPoolExecutor
import time
original_submit = ProcessPoolExecutor.submit
submitted = 0
def submit(self, *args, **kwargs):
    global submitted
    future = original_submit(self, *args, **kwargs)
    submitted += 1
    if submitted == 3:
        print("SIGNAL_READY", file=__import__("sys").stderr, flush=True)
        time.sleep(.2)
    return future
ProcessPoolExecutor.submit = submit
"""
    else:
        setup = """
from multiprocessing.process import BaseProcess
import time
original_start = BaseProcess.start
def start(self):
    original_start(self)
    print("SIGNAL_READY", file=__import__("sys").stderr, flush=True)
    time.sleep(.2)
BaseProcess.start = start
"""
    child = CHILD.replace(
        "from binance_datatool.cli import app", setup + "\nfrom binance_datatool.cli import app"
    )
    result = run_cli(tmp_path, child=child)
    assert result["signaled"], result
    assert not result["timed_out"], result
    assert result["code"] == 130, result
    assert not result["survivors"]
    assert "Traceback" not in result["stderr"]
    assert result["stdout"] == ""


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="requires a FIFO completion gate")
@pytest.mark.parametrize("keep_failed", [False, True])
def test_verify_mixed_outcomes_use_scan_markers_and_order_failures(
    tmp_path, monkeypatch, keep_failed
):
    """Completion order applies effects; failure output retains original path order."""
    paths = []
    old_markers = []
    for symbol, names in (
        ("ETHUSDT", ["a-slow.zip", "z-failed.zip"]),
        ("BTCUSDT", ["a-failed.zip", "z-passed.zip"]),
    ):
        directory = create_symbol_archive_dir(
            tmp_path, MarketType.spot, DataFrequency.daily, DataType.trades, symbol
        ).path
        directory.mkdir(parents=True)
        for name in names:
            path = directory / name
            payload = b"xxxx"
            path.write_bytes(payload)
            checksum = "0" * 64 if "failed" in name else hashlib.sha256(payload).hexdigest()
            checksum_path = path.with_suffix(".zip.CHECKSUM")
            if "slow" in name:
                os.mkfifo(checksum_path)
            else:
                checksum_path.write_text(checksum)
            paths.append(path)
            for suffix in (".verified", ".1.verified", ".bad.verified"):
                marker = path.with_name(path.name + suffix)
                marker.touch()
                old_markers.append(marker)
    events = []
    original_tick = LogReporter.tick

    def observe(self, event):
        if event.name.endswith(".zip"):
            if event.name == "z-failed.zip":
                # Release the earlier pending path only after a later path completed.
                paths[0].with_suffix(".zip.CHECKSUM").write_text(
                    hashlib.sha256(b"xxxx").hexdigest()
                )
            path = next(path for path in paths if path.name == event.name)
            assert not any(
                marker.exists() for marker in old_markers if marker.name.startswith(path.name)
            )
            if event.ok:
                assert SymbolArchiveDir(path.parent).scan().skipped >= 1
            else:
                assert path.exists() is keep_failed
                assert path.with_suffix(".zip.CHECKSUM").exists() is keep_failed
            events.append(event.name)
        original_tick(self, event)

    def forbidden_glob(*args, **kwargs):
        raise AssertionError("verification must reuse scanned marker names")

    monkeypatch.setattr(LogReporter, "tick", observe)
    monkeypatch.setattr(Path, "glob", forbidden_glob)
    result = ArchiveVerifyWorkflow(
        MarketType.spot,
        DataFrequency.daily,
        DataType.trades,
        ["ETHUSDT", "BTCUSDT"],
        tmp_path,
        keep_failed=keep_failed,
        n_workers=2,
    ).run()
    assert events.index("z-failed.zip") < events.index("a-slow.zip")
    assert list(result.failed_details) == [paths[1], paths[2]]
    assert list(result.failed_details.values()) == ["checksum mismatch", "checksum mismatch"]
    assert result.verified == result.failed == 2
    assert not any(marker.exists() for marker in old_markers)


def test_verify_failed_marker_write_does_not_advance_progress(tmp_path, monkeypatch):
    """Filesystem errors propagate before a result is acknowledged."""
    populate(tmp_path, 1, 32)
    events = []
    original_tick = LogReporter.tick

    def observe(self, event):
        if event.name.endswith(".zip"):
            events.append(event)
        original_tick(self, event)

    def failed_write(self, zip_name):
        raise OSError("marker creation failed")

    monkeypatch.setattr(LogReporter, "tick", observe)
    monkeypatch.setattr(SymbolArchiveDir, "write_marker", failed_write)
    with pytest.raises(OSError, match="marker creation failed"):
        ArchiveVerifyWorkflow(
            MarketType.spot,
            DataFrequency.daily,
            DataType.trades,
            ["BTCUSDT"],
            tmp_path,
            n_workers=1,
        ).run()
    assert events == []


def test_verify_dry_run_never_starts_workers_or_changes_files(tmp_path, monkeypatch):
    """A dry scan preserves stale markers and orphans without hashing or workers."""
    directory = populate(tmp_path, 2, 64)
    (directory / "000000.zip.verified").touch()
    (directory / "orphan.zip").write_bytes(b"orphan")
    (directory / "orphan.zip.bad.verified").touch()
    (directory / "missing.zip.CHECKSUM").write_text("bad")
    before = {path: path.read_bytes() for path in directory.iterdir()}

    def forbidden(*args, **kwargs):
        raise AssertionError("dry-run must not start workers or hash")

    monkeypatch.setattr("binance_datatool.workflow.verify.ProcessPoolExecutor", forbidden)
    monkeypatch.setattr("binance_datatool.workflow.verify.verify_single_file", forbidden)
    result = ArchiveVerifyWorkflow(
        MarketType.spot,
        DataFrequency.daily,
        DataType.trades,
        ["BTCUSDT"],
        tmp_path,
        dry_run=True,
    ).run()
    assert len(result.to_verify) == 2
    assert result.orphan_zips == [directory / "orphan.zip"]
    assert result.orphan_checksums == [directory / "missing.zip.CHECKSUM"]
    assert {path: path.read_bytes() for path in directory.iterdir()} == before
