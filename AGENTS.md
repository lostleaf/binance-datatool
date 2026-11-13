# AGENTS.md

## Project boundaries

- Before making changes, read `.AGENTS.local.md` at the repository root if it exists.
- This package manages historical archive discovery, downloading, local storage, and SHA256
  verification. Checked-in source, tests, and configuration establish current behavior when
  documentation conflicts with them.
- Use English for documentation, comments, docstrings, logs, CLI text, and developer-facing text.
  Keep Python code compatible with Python 3.11.
- Keep `temp/` materials outside the public package surface and project documentation.
- Update the relevant documentation when behavior, public interfaces, or contributor workflows
  change. Commit code before the corresponding documentation, in separate commits unless the
  user explicitly requests otherwise.

## Task guidance

- Before changing Python code or tests, read [coding standards](docs/agents/coding-standards.md).
- Before structural or cross-layer changes, read [architecture](docs/architecture.md).
- Before adding a command, workflow, enum member, or command group, read
  [extending the project](docs/extending.md).
- Before changing tests, fixtures, or test layout, read [test organization](docs/reference/testing.md).
- For module and CLI behavior, start at the [reference index](docs/reference/README.md).
- When creating or editing Markdown, use the installed
  [writing-for-agents skill](.agents/skills/writing-for-agents/SKILL.md).
- When defining or changing domain terminology or recording architectural decisions, use the
  installed [domain-modeling skill](.agents/skills/domain-modeling/SKILL.md).
  Before domain work, read the [domain guide](docs/agents/domain.md) and its glossary/ADR pointers.
- When reading or updating issues and specs, follow the [issue tracker guide](docs/agents/issue-tracker.md).
- When triaging issues, use the [triage label mapping](docs/agents/triage-labels.md).

For agent skill setup in a fresh checkout, see [agent development](README.md#agent-development).
