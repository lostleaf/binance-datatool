"""Archive checksum helpers."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(slots=True)
class VerifyFileResult:
    """Single-file verification outcome."""

    zip_path: Path
    passed: bool
    detail: str


def calc_sha256(file_path: Path) -> str:
    """Calculate the SHA256 digest for a file."""
    with file_path.open("rb") as file_obj:
        return hashlib.file_digest(file_obj, "sha256").hexdigest()


def read_expected_checksum(zip_path: Path) -> str:
    """Read the expected checksum from a sibling ``.CHECKSUM`` file.

    Raises:
        FileNotFoundError: When the ``.CHECKSUM`` sibling does not exist.
        ValueError: When the checksum file has no valid SHA256 token.
    """
    checksum_path = zip_path.parent / f"{zip_path.name}.CHECKSUM"
    try:
        line = checksum_path.read_text(encoding="utf-8").strip()
    except UnicodeDecodeError as exc:
        msg = f"invalid checksum file: {checksum_path}"
        raise ValueError(msg) from exc
    tokens = line.split()
    if not tokens or re.fullmatch(r"[0-9a-fA-F]{64}", tokens[0]) is None:
        msg = f"invalid checksum file: {checksum_path}"
        raise ValueError(msg)
    return tokens[0]


def verify_single_file(zip_path: Path) -> VerifyFileResult:
    """Verify a single zip file against its sibling checksum file."""
    try:
        expected = read_expected_checksum(zip_path)
        actual = calc_sha256(zip_path)
    except Exception as exc:  # noqa: BLE001
        return VerifyFileResult(zip_path=zip_path, passed=False, detail=str(exc))

    if actual == expected:
        return VerifyFileResult(zip_path=zip_path, passed=True, detail="")

    return VerifyFileResult(zip_path=zip_path, passed=False, detail="checksum mismatch")
