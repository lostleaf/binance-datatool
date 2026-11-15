"""Verification persistence and real process-group interruption regressions."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from binance_datatool.archive import SymbolArchiveDir, create_symbol_archive_dir
from binance_datatool.common import DataFrequency, DataType, TradeType
from binance_datatool.common.progress import LogReporter
from binance_datatool.workflow import ArchiveVerifyWorkflow

# Load the repository-only harness independently of the pytest entrypoint's sys.path.
harness_spec = importlib.util.spec_from_file_location(
    "verify_interrupt_harness", Path(__file__).parents[1] / "benchmarks/verify_interrupt.py"
)
assert harness_spec is not None and harness_spec.loader is not None
harness = importlib.util.module_from_spec(harness_spec)
harness_spec.loader.exec_module(harness)
CHILD, populate, run_cli = harness.CHILD, harness.populate, harness.run_cli


def test_verify_persists_before_progress(tmp_path, monkeypatch):
    """Acknowledged successes survive interruption before the batch completes."""
    directory = create_symbol_archive_dir(
        tmp_path, TradeType.spot, DataFrequency.daily, DataType.trades, "BTCUSDT"
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
        TradeType.spot,
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
        TradeType.spot,
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
            tmp_path, TradeType.spot, DataFrequency.daily, DataType.trades, symbol
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
        TradeType.spot,
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
            TradeType.spot,
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
        TradeType.spot,
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


@pytest.mark.parametrize(
    "option,value",
    [
        ("--size", "-1"),
        ("--count", "0"),
        ("--repeat", "0"),
        ("--deadline", "0"),
        ("--deadline", "nan"),
        ("--deadline", "inf"),
    ],
)
def test_signal_harness_rejects_invalid_workloads_before_creation(tmp_path, option, value):
    """Invalid CLI workloads fail promptly without creating disposable fixtures."""
    result = subprocess.run(
        [sys.executable, str(Path(harness.__file__)), option, value],
        capture_output=True,
        text=True,
        timeout=5,
        env={**os.environ, "TMPDIR": str(tmp_path)},
    )
    assert result.returncode == 2
    assert option in result.stderr
    assert result.stdout == ""
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("count,size", [(0, 1), (-1, 1), (1, -1)])
def test_signal_fixture_rejects_invalid_sizes_without_writing(tmp_path, count, size):
    """Fixture callers cannot create empty workloads or loop on negative sizes."""
    with pytest.raises(ValueError):
        populate(tmp_path, count, size)
    assert list(tmp_path.iterdir()) == []
