# Architecture

`binance-datatool` discovers historical archives on `data.binance.vision`, downloads archive
objects into local storage, and verifies ZIP files against SHA256 checksums. Domain meanings
are defined in the root [glossary](../GLOSSARY.md).

## Package boundaries

Dependencies point inward: CLI → Workflow → Archive → Common. A layer can also use shared
facilities from lower layers directly; lower layers do not import higher ones.

| Layer | Package | Responsibility |
|-------|---------|----------------|
| Common | `binance_datatool.common` | Shared enums, symbol inference and filters, archive layout and interval validation, archive-home resolution, logging, and progress reporting. |
| Archive | `binance_datatool.archive` | S3 listings, archive-object metadata, aria2 transfers, SHA256 helpers, local symbol directories, and verification markers. |
| Workflow | `binance_datatool.workflow` | Symbol classification, file listing and failure isolation, remote/local download comparison, local scanning, verification, and cleanup. |
| CLI | `binance_datatool.cli` | Argument validation, workflow construction, output formatting, and exit status. |

The root package exports only version metadata. Workflows are importable independently of
Typer. The [module reference](reference/README.md) documents public interfaces and re-exports;
[coding standards](agents/coding-standards.md) owns Python and testing conventions.

## Operations and data flow

| Commands | Workflow operations | External boundary |
|----------|---------------------|-------------------|
| `list-symbols`, `list-files` | Discover symbols or objects, classify/filter results, isolate listing failures. | Remote S3 XML listings through `ArchiveClient`. |
| `download` | List remote objects, compare local files, transfer selected objects, invalidate affected verification markers. | Remote listings, aria2 subprocess, local filesystem. |
| `verify` | Scan local symbol directories, reuse fresh verification markers, compare SHA256, clean orphan or failed artifacts. | Local filesystem and verification worker processes; no remote listing or download. |

Download dry-runs still list remote objects but do not write local files. Verification dry-runs
scan local files without hashing or cleanup. Download completion and eligibility to skip a
transfer do not establish checksum verification.

The [workflow reference](reference/workflow/README.md) owns download comparison and verification
cache rules. The [CLI reference](reference/cli/archive.md) describes output units and outcomes.
Stdout carries machine-consumable results; summaries, diagnostics, and progress go to stderr.
