"""Tests for the aria2 archive downloader."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest
from loguru import logger
from tqdm import tqdm

from binance_datatool.archive.downloader import (
    Aria2NotFoundError,
    DownloadRequest,
    _find_missing_requests,
    _is_download_complete,
    download_archive_files,
)
from binance_datatool.common.progress import make_reporter

if TYPE_CHECKING:
    from pathlib import Path


def test_download_archive_files_raises_when_aria2_is_missing(monkeypatch, tmp_path) -> None:
    """A dedicated error should be raised when aria2c is unavailable."""
    monkeypatch.setattr("shutil.which", lambda name: None)

    def unexpected_run(*args, **kwargs):
        pytest.fail("Missing aria2c must be reported before starting a download process.")

    monkeypatch.setattr("subprocess.run", unexpected_run)

    with pytest.raises(Aria2NotFoundError):
        download_archive_files(
            [
                DownloadRequest(
                    url="https://data.binance.vision/data/a.zip", local_path=tmp_path / "a.zip"
                )
            ],
            inherit_proxy=False,
        )


def test_download_archive_files_strips_proxy_env_by_default(monkeypatch, tmp_path) -> None:
    """Default aria2 runs should remove proxy-related environment variables."""
    commands: list[tuple[list[str], dict[str, str] | None]] = []

    monkeypatch.setenv("HTTP_PROXY", "http://proxy.example")
    monkeypatch.setenv("HTTPS_PROXY", "https://proxy.example")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/aria2c")

    def fake_run(cmd, check, env):  # noqa: ANN001
        commands.append((cmd, env))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)

    result = download_archive_files(
        [
            DownloadRequest(
                url="https://data.binance.vision/data/spot/file.zip",
                local_path=tmp_path / "nested" / "file.zip",
            )
        ],
        inherit_proxy=False,
    )

    assert result.succeeded == 1
    assert commands
    cmd, env = commands[0]
    assert "-j64" in cmd
    assert "--allow-overwrite=true" in cmd
    assert "--auto-file-renaming=false" in cmd
    assert env is not None
    assert "HTTP_PROXY" not in env
    assert "HTTPS_PROXY" not in env
    assert (tmp_path / "nested").exists()


def test_download_archive_files_can_inherit_proxy_env(monkeypatch, tmp_path) -> None:
    """The proxy flag should allow aria2 to inherit the process environment."""
    seen_envs: list[dict[str, str] | None] = []

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/aria2c")

    def fake_run(cmd, check, env):  # noqa: ANN001
        del cmd, check
        seen_envs.append(env)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)

    download_archive_files(
        [
            DownloadRequest(
                url="https://data.binance.vision/data/spot/file.zip",
                local_path=tmp_path / "file.zip",
            )
        ],
        inherit_proxy=True,
    )

    assert seen_envs == [None]


def test_download_archive_files_retries_only_missing_files(monkeypatch, tmp_path) -> None:
    """When aria2 fails but some files land on disk, only missing files are retried."""
    call_count = 0

    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/aria2c")

    def fake_run(cmd, check, env):  # noqa: ANN001
        nonlocal call_count
        del cmd, check, env
        call_count += 1
        if call_count == 1:
            # Simulate: first batch fails but file-0 lands on disk.
            (tmp_path / "file-0.zip").write_bytes(b"ok")
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)

    requests = [
        DownloadRequest(
            url=f"https://data.binance.vision/data/spot/file-{i}.zip",
            local_path=tmp_path / f"file-{i}.zip",
        )
        for i in range(3)
    ]
    result = download_archive_files(
        requests,
        inherit_proxy=False,
        batch_size=2,
        max_tries=3,
    )

    # Batch 1 (file-0, file-1) fails; file-0 exists, only file-1 retried.
    # Batch 2 (file-2) succeeds.
    # Retry round: file-1 only → succeeds.
    assert call_count == 3
    assert result.succeeded == 3
    assert result.failed_requests == []


def test_download_archive_files_partial_download_detected(monkeypatch, tmp_path) -> None:
    """A file with a leftover .aria2 control file is treated as incomplete."""
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/aria2c")

    call_count = 0

    def fake_run(cmd, check, env):  # noqa: ANN001
        nonlocal call_count
        del cmd, check, env
        call_count += 1
        if call_count == 1:
            # file-0 downloaded fully; file-1 is partial (has .aria2 control file).
            (tmp_path / "file-0.zip").write_bytes(b"ok")
            (tmp_path / "file-1.zip").write_bytes(b"partial")
            (tmp_path / "file-1.zip.aria2").write_bytes(b"ctrl")
            return SimpleNamespace(returncode=1)
        # Retry succeeds; clean up the control file.
        (tmp_path / "file-1.zip.aria2").unlink(missing_ok=True)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)

    requests = [
        DownloadRequest(
            url=f"https://data.binance.vision/data/spot/file-{i}.zip",
            local_path=tmp_path / f"file-{i}.zip",
        )
        for i in range(2)
    ]
    result = download_archive_files(requests, inherit_proxy=False, max_tries=3)

    assert call_count == 2
    assert result.succeeded == 2
    assert result.failed_requests == []


# --- Unit tests for helper functions ---


def test_is_download_complete_missing_file(tmp_path: Path) -> None:
    """A file that does not exist is not complete."""
    req = DownloadRequest(url="https://example.com/a.zip", local_path=tmp_path / "a.zip")
    assert _is_download_complete(req) is False


def test_is_download_complete_full_file(tmp_path: Path) -> None:
    """A file that exists without a control file is complete."""
    target = tmp_path / "a.zip"
    target.write_bytes(b"data")
    req = DownloadRequest(url="https://example.com/a.zip", local_path=target)
    assert _is_download_complete(req) is True


def test_is_download_complete_partial_file(tmp_path: Path) -> None:
    """A file with a sibling .aria2 control file is not complete."""
    target = tmp_path / "a.zip"
    target.write_bytes(b"partial")
    (tmp_path / "a.zip.aria2").write_bytes(b"ctrl")
    req = DownloadRequest(url="https://example.com/a.zip", local_path=target)
    assert _is_download_complete(req) is False


def test_find_missing_requests_filters_correctly(tmp_path: Path) -> None:
    """Only requests with missing or incomplete files should be returned."""
    (tmp_path / "exists.zip").write_bytes(b"ok")
    (tmp_path / "partial.zip").write_bytes(b"partial")
    (tmp_path / "partial.zip.aria2").write_bytes(b"ctrl")

    requests = [
        DownloadRequest(url="https://example.com/exists.zip", local_path=tmp_path / "exists.zip"),
        DownloadRequest(url="https://example.com/missing.zip", local_path=tmp_path / "missing.zip"),
        DownloadRequest(url="https://example.com/partial.zip", local_path=tmp_path / "partial.zip"),
    ]
    missing = _find_missing_requests(requests)
    assert len(missing) == 2
    assert missing[0].local_path.name == "missing.zip"
    assert missing[1].local_path.name == "partial.zip"


@pytest.mark.parametrize("progress_bar", [False, True])
@pytest.mark.parametrize("batch_options", [{}, {"batch_size": 4096}, {"batch_size": 128}])
def test_download_progress_advances_within_512_files(
    monkeypatch, tmp_path, capsys, progress_bar, batch_options
) -> None:
    """Large downloads should expose every batch through logs and the bar."""
    batch_lengths = []
    visible_counts = []
    reporters = []
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/aria2c")

    def capture_reporter(*args, **kwargs):
        reporter = make_reporter(*args, **kwargs)
        reporters.append(reporter)
        return reporter

    def capture_log(message):
        visible_counts.append(reporters[-1].done)

    original_update = tqdm.update

    def capture_bar_update(bar, count):
        original_update(bar, count)
        visible_counts.append(bar.n)

    monkeypatch.setattr("binance_datatool.archive.downloader.make_reporter", capture_reporter)
    monkeypatch.setattr(tqdm, "update", capture_bar_update)

    def fake_run(cmd, **kwargs):
        with open(cmd[cmd.index("-i") + 1], encoding="utf-8") as input_file:
            batch_lengths.append(sum(line.startswith("https://") for line in input_file))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr("subprocess.run", fake_run)
    requests = [
        DownloadRequest(
            url=f"https://example.com/{index}.zip", local_path=tmp_path / f"{index}.zip"
        )
        for index in range(12289)
    ]
    sink_id = logger.add(
        capture_log,
        filter=lambda record: record["name"] == "binance_datatool.common.progress",
    )
    try:
        result = download_archive_files(
            requests, inherit_proxy=False, progress_bar=progress_bar, **batch_options
        )
    finally:
        logger.remove(sink_id)

    output = capsys.readouterr()
    gaps = [
        current - previous
        for previous, current in zip([0, *visible_counts], visible_counts, strict=False)
    ]
    assert result.succeeded == 12289
    assert result.failed_requests == []
    assert sum(batch_lengths) == 12289
    assert max(batch_lengths) <= 512
    assert (reporters[0].done, reporters[0].ok, reporters[0].fail) == (12289, 12289, 0)
    assert visible_counts[-1] == 12289
    assert max(gaps) <= 512
    assert output.out == ""
    if progress_bar:
        assert output.err.strip()


@pytest.mark.parametrize("concurrency", [0, -1])
def test_download_rejects_invalid_concurrency(concurrency) -> None:
    """Importable downloads reject invalid concurrency even for an empty plan."""
    with pytest.raises(ValueError):
        download_archive_files([], inherit_proxy=False, concurrency=concurrency)


def test_download_preserves_failed_counts_after_per_file_retries(monkeypatch, tmp_path) -> None:
    """Retry exhaustion preserves successes and retries only incomplete files."""
    inputs = []
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/aria2c")

    def fake_run(cmd, **kwargs):
        with open(cmd[cmd.index("-i") + 1], encoding="utf-8") as input_file:
            inputs.append([line.strip() for line in input_file if line.startswith("https://")])
        (tmp_path / "ok.zip").write_bytes(b"complete")
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr("subprocess.run", fake_run)
    requests = [
        DownloadRequest(url="https://example.com/ok.zip", local_path=tmp_path / "ok.zip"),
        DownloadRequest(url="https://example.com/fail.zip", local_path=tmp_path / "fail.zip"),
    ]
    result = download_archive_files(requests, inherit_proxy=False, max_tries=3)
    assert inputs == [
        ["https://example.com/ok.zip", "https://example.com/fail.zip"],
        ["https://example.com/fail.zip"],
        ["https://example.com/fail.zip"],
    ]
    assert result.requested == 2
    assert result.succeeded == 1
    assert result.failed_requests == requests[1:]
