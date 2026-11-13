# Binance DataTool - Built for Agents, Data Delivered.

[![PyPI](https://img.shields.io/pypi/v/binance-datatool?logo=pypi&logoColor=white)](https://pypi.org/project/binance-datatool/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![License: BSD-3-Clause](https://img.shields.io/badge/license-BSD--3--Clause-green)](LICENSE)
[![Ruff](https://img.shields.io/badge/code%20style-ruff-d4aa00?logo=ruff&logoColor=white)](https://docs.astral.sh/ruff/)
[![uv](https://img.shields.io/badge/package%20manager-uv-de5fe9?logo=uv&logoColor=white)](https://docs.astral.sh/uv/)

A non-official Python toolkit for managing historical market data from
[data.binance.vision](https://data.binance.vision/) — designed
from the ground up for AI agents and quantitative workflows.

**binance-datatool** is designed to make every command equally easy to call for AI agents and humans:

- **Composable CLI** — stdin/stdout pipelines let agents chain
  commands without glue code
- **Atomic operations** — each command does one thing well; agents
  can inspect, decide, and act step by step
- **Deterministic output** — structured, parseable results that
  agents can reason about
- **Zero interaction** — no prompts, no confirmations; dry-run mode
  for safe previews

## Agent Skill

A packaged [Agent Skill](skills/binance-datatool/SKILL.md) is included in this repository.

It teaches agents how to use `binance-datatool` to discover, download, and
verify Binance historical market data — no manual command lookup required.

## Features

- **Multi-market coverage** — Spot, USD-M Futures, and COIN-M Futures
- **Smart symbol filtering** — filter by quote asset, exclude stablecoins
  and leveraged tokens, select contract types
- **Resumable batch downloads** — diff-based sync via
  [aria2](https://aria2.github.io/) that only fetches new or updated files
- **Data integrity verification** — SHA256 checksum validation with
  timestamped marker caching
- **Composable pipelines** — Unix-friendly design; commands read from
  stdin and write to stdout
- **Async I/O** — concurrent S3 listing and parallel checksum verification

## Quick Start

### Prerequisites

- [Python](https://www.python.org/) 3.11+
- [pipx](https://pipx.pypa.io/) — installs the CLI in an isolated environment
- [aria2](https://aria2.github.io/) — required for the `download` command

### Install

```bash
# install the CLI
pipx install binance-datatool
# run `pipx ensurepath` if the command isn't found immediately

# system dependency for download command
# macOS
brew install aria2
# Ubuntu/Debian
sudo apt install aria2

export BINANCE_DATATOOL_ARCHIVE_HOME="$HOME/crypto_data/binance_archive"

binance-datatool --help
```

### Try it

```bash
# List USDT-quoted spot symbols, excluding stablecoins
binance-datatool list-symbols spot --quote USDT --exclude-stables

# Download daily 1m klines
binance-datatool list-symbols spot --quote USDT --exclude-stables \
  | binance-datatool download spot --type klines --interval 1m

# Verify integrity
binance-datatool verify spot --type klines --interval 1m BTCUSDT
```

## Supported Data Types

| Category | Types |
|----------|-------|
| Trade data | `klines`, `aggTrades`, `trades` |
| Derivatives | `fundingRate`, `liquidationSnapshot`, `metrics` |
| Order book | `bookDepth`, `bookTicker` |
| Index data | `indexPriceKlines`, `markPriceKlines`, `premiumIndexKlines` |

The CLI accepts **daily** and **monthly** archive partitions. Availability depends on
the market and dataset; for example, futures funding rates use monthly archives.
Kline types require `--interval` (such as `1m`), independently of partition frequency.
Use `list-files` to discover what Binance publishes for a selection. See
[archive paths](docs/reference/archive/path-structure.md) and the [glossary](GLOSSARY.md).

## CLI Overview

The entry point is `binance-datatool`. All data commands are available
directly on the root app:

| Command | Description |
|---------|-------------|
| `list-symbols` | List available symbols on the remote archive |
| `list-files` | List archive files for given symbols |
| `download` | Download new or updated archive files |
| `verify` | Verify local ZIP files against sibling SHA256 checksums; no network access |

> [!TIP]
> `list-files`, `download`, and `verify` accept symbols from **stdin** or as
> **positional args**, so they can consume `list-symbols` output:
>
> ```bash
> binance-datatool list-symbols um --quote USDT \
>   | binance-datatool download um --type klines --interval 1m
> ```

Run `binance-datatool --help` for the full option reference.

Downloads count individual objects, including ZIP and checksum files. Successful transfer
or an up-to-date local copy does not establish SHA256 verification. Verification counts ZIPs
and distinguishes newly verified files from those skipped using cached verification. See
[command outcomes](docs/reference/cli/archive.md) for counts, cleanup, and exit semantics.

## Architecture

```
CLI Layer        Thin Typer commands (argument parsing, output formatting)
    │
Workflow Layer   Business logic (diff computation, verification protocol)
    │
Archive Layer    Remote listings and downloads, local directories, checksums, markers
    │
Common Layer     Shared types, enums, constants, and utilities
```

See [docs/architecture.md](docs/architecture.md) for a detailed design overview.

## Documentation

| Document | Description |
|----------|-------------|
| [Architecture](docs/architecture.md) | Layered design, data flow, and key decisions |
| [Module Reference](docs/reference/README.md) | Per-subpackage API reference |
| [Extending](docs/extending.md) | How to add commands, enums, workflows, and tests |
| [Testing Guide](docs/reference/testing.md) | Test organization and conventions |
| [Agent Skill](skills/binance-datatool/SKILL.md) | Packaged skill for agents |

## Agent development

Contributors using agents need the [Matt Pocock skills](https://github.com/mattpocock/skills)
collection recorded in [skills-lock.json](skills-lock.json), including `writing-for-agents`
for Markdown and `domain-modeling` for terminology and architectural decisions. These are
development tools; using the Python package or CLI does not require them. The packaged
[binance-datatool skill](skills/binance-datatool/SKILL.md) separately teaches CLI usage.

For a fresh checkout, install [uv](https://docs.astral.sh/uv/) for Python development and
Node.js/npm for the [skills installer](https://github.com/vercel-labs/skills), then run from
the repository root:

```bash
uv sync
npx skills experimental_install --agent codex claude-code --frozen-lockfile
```

Select the agent names you use. The installer restores the recorded collection into
`.agents/skills/` and links agent-specific directories as needed. Its `--dry-run` option
previews restoration without installing. Read [AGENTS.md](AGENTS.md) before working;
[CLAUDE.md](CLAUDE.md) imports that same guide.

The tracked skill record contains source repositories, skill paths, and content hashes.
It does not pin an upstream commit or guarantee reproducible restoration. Frozen installation
fails if fetched content would change the record. If upstream content has moved or changed,
leave updates to the maintainer: manually review the upstream changes, run the installer's
explicit update command when approved, and review the resulting skill-record diff. Skills
are not updated automatically by package setup or CI. Installer options are documented in
`npx skills --help`.

For Python and testing conventions, read [coding standards](docs/agents/coding-standards.md).
