"""Shared presentation for structured CLI results."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Annotated, TypeAlias

import typer

if TYPE_CHECKING:
    from pathlib import Path

JsonOutputOption: TypeAlias = Annotated[
    bool,
    typer.Option("--json", help="Print one structured JSON result to stdout."),
]


def absolute_path(path: Path) -> str:
    """Format an absolute local path without requiring existence or resolving symlinks."""
    return str(path.absolute())


def emit_json(
    command: str,
    *,
    dry_run: bool,
    summary: dict[str, int],
    **fields: object,
) -> None:
    """Emit one result document with the common command envelope."""
    typer.echo(json.dumps({"command": command, "dry_run": dry_run, "summary": summary, **fields}))
