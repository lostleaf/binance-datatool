# AGENTS.md

## Project boundaries

- This package manages historical archive discovery, downloading, local storage, and SHA256
  verification. Checked-in source, tests, and configuration establish current behavior when
  documentation conflicts with them.
- Use English for documentation, comments, docstrings, logs, CLI text, and developer-facing text.
  Keep Python code compatible with Python 3.11.
- Keep `temp/` materials outside the public package surface and project documentation.
- Update the relevant documentation when behavior, public interfaces, or contributor workflows
  change.
- Use Conventional Commits. Keep issue numbers out of commit subjects and retain the pull request
  number GitHub adds to squash merges. Use a closing reference in the commit body when the change
  fixes a public issue.

## Task guidance

- Before structural or cross-layer changes, read [architecture](docs/architecture.md).
- Before adding a command, workflow, enum member, or command group, read
  [extending the project](docs/extending.md).
- Before changing tests, fixtures, or test layout, read [test organization](docs/reference/testing.md).
- For module and CLI behavior, start at the [reference index](docs/reference/README.md).
