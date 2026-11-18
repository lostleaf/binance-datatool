# Documentation

Developer documentation for contributors, maintainers, and AI agents working on the
`binance-datatool` codebase.

For installation and usage instructions, see the [repository root README](../README.md).

## Core Docs

| Document | Description |
|----------|-------------|
| [Architecture](architecture.md) | Layered design, data flow, S3 protocol, and key decisions. |
| [Module Reference](reference/README.md) | Entry point for per-package API and CLI reference. |

## Contributor Guides

| Document | Description |
|----------|-------------|
| [Extending the Project](extending.md) | How to add commands, enums, workflows, and tests. |
| [Coding standards](agents/coding-standards.md) | Project Python, failure, inference, and test contracts. |
| [Domain guide](agents/domain.md) | Glossary and architectural-decision navigation. |
| [Testing](reference/testing.md) | Test directory layout, conventions, and shared fixtures. |

## Agent development

These skills support work on the codebase. For an agent that runs the CLI, use the
[binance-datatool skill](../skills/binance-datatool/SKILL.md).

For a fresh checkout, install [uv](https://docs.astral.sh/uv/) and Node.js with npm, then run
these commands from the repository root. Set `--agent` to the agents you use.

```bash
uv sync
npx skills experimental_install --agent codex claude-code --frozen-lockfile
```

The [skills installer](https://github.com/vercel-labs/skills) restores the
[Matt Pocock contributor skills](https://github.com/mattpocock/skills) recorded in
[skills-lock.json](../skills-lock.json) to `.agents/skills/` and links them for the selected
agents. Add `--dry-run` to preview the installation. [AGENTS.md](../AGENTS.md) explains when
to use each skill, including `writing-for-agents` and `domain-modeling`.
[CLAUDE.md](../CLAUDE.md) imports the same guide.

The current lockfile records source repositories, skill paths, and content hashes. It leaves
the upstream commit unpinned. Frozen installation stops if fetched content would change the
record. Skill updates are manual and run separately from package installation and CI.
If upstream content changes, the maintainer reviews it, runs the installer's update command
when approved, and reviews the lockfile diff. See `npx skills --help` for installer options.
