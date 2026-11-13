# Coding standards

Project-specific Python and testing conventions. Language, runtime compatibility, and commit
boundaries live in [AGENTS.md](../../AGENTS.md).

## Toolchain

Before changing Python or tool configuration, read [pyproject.toml](../../pyproject.toml) for
supported runtimes, dependencies, Ruff, and pytest settings. Use modern syntax within the
supported range. Keep [uv.lock](../../uv.lock) synchronized with dependency declarations.

## Code

- Keep imports at module level. Explain technically necessary local imports with a brief comment.
- Use Google-style docstrings for public modules, classes, and functions. Add comments where
  they explain a reason the code does not make clear.
- Prefer explicit types, descriptive names, and focused modules with composable responsibilities.
- Use mature project dependencies for standard infrastructure.
- Keep CLI functions focused on arguments, workflow construction, and presentation. Put business
  logic in importable workflows. Follow the package boundaries in [architecture](../architecture.md).
- Export only version metadata from `binance_datatool.__init__`.

## Failure and inference

Expose failures explicitly. Add recovery only for a known failure mode with a defined outcome.
Inference rules need evidence, a defined applicability range, and representative tests. Return
an unrecognized result when supported rules cannot determine an answer; guesses, silent
fallbacks, and ad hoc patches are not substitutes for a supported rule.

## Test contracts

- Cover meaningful behavior changes at the smallest existing public seam that proves them.
  Test results, input rejection, exception types, structured data, and filesystem effects.
- Keep exact contracts for machine output: symbol lines, relative paths, TSV columns and values,
  checksum selection, dry-run plans, and clean stdout.
- For human help, summaries, warnings, and errors, test emission, routing, and the underlying
  data. Human wording and logging-library rendering are not contracts. Check command and option
  availability through invocation or registration, with help smoke coverage.
- Preserve diagnostic payloads and their associated symbols or paths independently of punctuation.
  Protect summary counts through result data. Reuse existing seams rather than adding production
  interfaces solely for tests.
- Exercise representative inference inputs and unrecognized outcomes. For data processing,
  include representative fixtures or focused regression coverage.

For fixtures, test placement, and network-test opt-in, see [test organization](../reference/testing.md).

## Validation

Run affected test files during iteration. Before completion, run:

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest
```

Read the checked-in CI workflows before changing CI checks or release gates; see
[test organization](../reference/testing.md#continuous-integration).
