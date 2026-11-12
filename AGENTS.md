# AGENTS.md

## Purpose
- This repository hosts the `binance_datatool` Python package.
- Treat checked-in source code, tests, configuration, and public documentation as the source of
  truth for current behavior.
- Keep the repository easy for both human developers and AI agents to navigate.

## Local Instructions
- Before making changes, check whether `.AGENTS.local.md` exists at the repository root.
- If `.AGENTS.local.md` exists, read it and follow it as additional local guidance.
- Public instructions in this file apply to everyone; local instructions add developer-specific context.

## Documentation Navigation
- Read `docs/architecture.md` before making structural or cross-layer changes.
- Read `docs/extending.md` before adding a new command, workflow, enum member, or sub-command group.
- Read `docs/reference/testing.md` before changing tests, fixtures, or test layout conventions.
- Use `docs/reference/README.md` as the entry point for module and CLI reference details.
- Treat checked-in code and tests as higher priority than documentation if they conflict.
- When a change alters behavior, public interfaces, or contributor workflows, update the relevant
  `docs/` promptly after the code change is committed.
- Unless explicitly requested otherwise, do not mix code changes and documentation updates in the
  same commit.

## Working Model
- Build the project as a modern Python package named `binance_datatool`.
- Use the intended package layout: shared code under `binance_datatool.common`, archive access
  under `binance_datatool.archive`, CLI entrypoints under `binance_datatool.cli`, and business
  workflows under `binance_datatool.workflow.archive`.
- Prefer clear, composable workflows and thin CLI entrypoints.
- Keep the root package minimal. Export only version metadata from `binance_datatool.__init__`.

## Toolchain
- Package and dependency management: `uv`
- Build backend: `hatchling`
- Linting and formatting: `ruff`
- Testing: `pytest`
- Git hooks: `pre-commit`
- External downloader: `aria2`

## Expected Commands
- Environment setup: `uv sync`
- Lint: `uv run ruff check .`
- Format: `uv run ruff format .`
- Tests: `uv run pytest`
- Targeted tests: `uv run pytest tests/path_to_test.py`
- CLI entrypoint target: `uv run binance-datatool --help`

## Code Standards
- Use written English for code comments, docstrings, logs, CLI text, and developer-facing messages.
- Write clear comments only where they add real value; do not narrate obvious code.
- Use Google-style docstrings for public modules, classes, and functions.
- Use modern Python syntax compatible with Python 3.11, but **MUST NOT** use syntax introduced after 3.11
- Keep Python source line length at 100 characters or less. This limit does not apply to
  Markdown files under `docs/`, where long table rows and wide ASCII diagrams are allowed.
- Keep imports at module top level unless a local import is technically necessary.
- Prefer explicit types and clear names over implicit behavior.
- Prefer small, focused modules with straightforward responsibilities.
- Follow a let-it-crash mindset. Do not add casual fallback logic, silent recovery, or defensive
  branches unless there is a concrete and justified failure mode.
- Replace hand-rolled infrastructure with mature third-party libraries when the design already
  names a standard dependency.

## Architecture Expectations
- Keep CLI modules thin: parse arguments, construct workflows, and present output.
- Put business logic in importable workflow or domain modules, not inside CLI command functions.
- Prefer Polars LazyFrame-based data processing when working with tabular pipelines.
- Preserve a clear separation between shared utilities, archive access, parsing, completion,
  metadata tracking, and holographic kline generation.
- Design commands to be atomic and composable so an agent can inspect state and then choose the
  next step.

## Testing Expectations
- Add or update tests for every meaningful behavior change.
- Prefer the smallest test scope that proves the change.
- Use `pytest` as the test runner and keep tests readable enough for agent-assisted maintenance.
- When adding data-processing behavior, include representative fixtures or focused regression
  coverage.
- Focus tests on functional correctness and observable behavior, not on logging implementation
  details such as how loguru renders or routes messages to stderr.

## Repository Boundaries
- `temp/` is git-ignored and may contain temporary or non-public materials.
- Do not treat `temp/` as part of the public package surface or public project documentation.
- Keep checked-in guidance focused on the package and stable workflows, not on transient working files.

## Agent skills

### Issue tracker

Issues and specs live in this repo's GitHub Issues (via the `gh` CLI). See
`docs/agents/issue-tracker.md`.

### Triage labels

The five default triage roles map to labels of the same name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
