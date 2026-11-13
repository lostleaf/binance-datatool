# Test Organization

```
tests/
├── conftest.py                 # Shared test support (FakeArchiveClient, sample_archive_files)
├── data/                       # Static test fixtures (e.g., sample data files)
├── test_archive_client.py      # Archive client unit and integration tests
├── test_archive_workflow.py    # Workflow unit and integration tests (list + download + verify)
├── test_checksum.py            # checksum module unit tests (calc, read, verify_single_file)
├── test_cli.py                 # CLI smoke tests (list-symbols, list-files, download, verify)
├── test_downloader.py          # aria2 downloader unit tests (proxy, batching, retry)
├── test_enums.py               # common.enums property tests
├── test_filter.py              # Symbol filter unit tests
├── test_path.py                # Archive-home resolution (override, env var, missing)
├── test_progress.py            # Progress-reporting framework (LogReporter, TqdmReporter)
├── test_symbol_dir.py          # SymbolArchiveDir, create_symbol_archive_dir, marker protocol
└── test_symbols.py             # Symbol inference unit and integration tests
```

For behavior assertions, human diagnostics, and machine-output contracts, follow the
[coding standards](../agents/coding-standards.md#test-contracts). This page owns test placement
and shared support.

## Conventions

- **Unit tests** use `monkeypatch` to replace HTTP methods with fake responses.
- **Integration tests** are marked with `@pytest.mark.integration` and skipped by default.
  Run them explicitly with `pytest --run-integration`.
- **CLI tests** use `typer.testing.CliRunner` and monkeypatch the workflow's `run()` method so
  they run without network access. Assert emission and stream routing through the runner;
  the CLI diagnostic fixture can observe `typer.echo` emissions without freezing their wording.
  Keep counts and file effects covered in workflow and component results.

## Shared Test Support in `conftest.py`

- **`FakeArchiveClient`** — a programmable stub configured entirely via constructor
  kwargs (`symbols=`, `files_by_symbol=`, `errors_by_symbol=`). It implements
  `list_symbols`, `list_symbol_files`, and `list_symbol_files_batch`. The batch
  method records `progress_bar` state for assertion in tests. Prefer extending
  this stub over re-implementing per-test fakes when you add new workflows.
- **`sample_archive_files`** — a representative pair of `ArchiveFile` entries
  (`.zip` + `.zip.CHECKSUM`) for list-files-style workflow and CLI tests.
- **`--run-integration`** — a custom pytest option that unlocks the `integration`
  marker. The default run skips every integration test.

## Continuous Integration

Read `.github/workflows/ci.yml` before changing push or pull-request checks, and
`.github/workflows/publish.yml` before changing release test gates.

---

See also: [Extending the Project](../extending.md) | [Architecture](../architecture.md)
