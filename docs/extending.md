# Extending the Project

This guide explains how to add new functionality to `binance-datatool` following the patterns
established in the current codebase.

## Adding a New Enum Member

To support a new dataset type (for example, `"premiumIndex"`):

1. Add the member to the appropriate enum in `common/enums.py`:

   ```python
   class DataType(StrEnum):
       ...
       premium_index = "premiumIndex"
   ```

2. Confirm the archive actually publishes the dataset for the intended market and frequency.
   Review whether the new member needs additional enum-property updates. The new member
   is exposed through the enum in:
   - CLI arguments (Typer picks up `StrEnum` members).
   - S3 path construction (the value is used directly).

3. If the new data type uses an interval directory layer, update
   `DataType.has_interval_layer` and add coverage for the interval validation
   paths exercised by the CLI, workflow, and archive client.

If the new member requires a non-trivial path mapping (like `TradeType.s3_path`), add a property
method to the enum class.

## Adding a New CLI Command

Keep the CLI thin and delegate business logic to a workflow. Use archive helpers when
the operation needs remote or local archive access; local-only operations do not need
an `ArchiveClient`. See [package boundaries](architecture.md#package-boundaries).

### Step 1: Add Archive Access

If the command needs new remote listings, add an `async` method to `ArchiveClient` in
`archive/client.py`. Keep it focused on S3 communication and return plain data structures.
For local archive operations, use or extend the directory and checksum helpers in `archive/`.

```python
async def list_dates(self, trade_type: TradeType, ...) -> list[str]:
    """List available date directories for a symbol."""
    prefix = _build_prefix(trade_type, data_freq, data_type) + f"{symbol}/"
    ...
```

See `list_symbols` and `list_symbol_files` in `archive/client.py` for real examples.

### Step 2: Create a Workflow Class

Create a workflow in `workflow/` (or a new module if the scope warrants it).
For remote workflows, follow the existing optional `client` injection pattern. Return
typed result data. Local-only workflows can be synchronous, as `ArchiveVerifyWorkflow` is.

```python
class ArchiveListDatesWorkflow:
    def __init__(self, trade_type: TradeType, ..., client: ArchiveClient | None = None) -> None:
        ...

    async def run(self) -> list[str]:
        ...
```

See `ArchiveListSymbolsWorkflow`, `ArchiveListFilesWorkflow`, `ArchiveDownloadWorkflow`,
and `ArchiveVerifyWorkflow` in `workflow/` for real examples.

### Step 3: Add a CLI Command

Add a Typer root command in `cli/archive.py`. The command parses arguments,
constructs a workflow, and prints the result.

```python
@app.command("list-dates")
def list_dates_command(
    trade_type: Annotated[TradeType, typer.Argument(...)],
    ...
) -> None:
    """List available dates for a symbol."""
    workflow = ArchiveListDatesWorkflow(trade_type, ...)
    for date in asyncio.run(workflow.run()):
        typer.echo(date)
```

See `list_symbols_command`, `list_files_command`, `download_command`, and
`verify_command` in `cli/archive.py` for real examples.

### Step 4: Add Tests

Choose the smallest existing public seam that proves the new behavior. Follow the
[test contracts](agents/coding-standards.md#test-contracts). See [Test Organization](reference/testing.md) for directory layout,
conventions, and shared fixtures.

## Adding a New Sub-command Group

When a feature needs a group, define a Typer app in `cli/__init__.py` and attach it
with `app.add_typer(...)`. Register its command module through the existing side-effect
import pattern. Keep workflow logic in `workflow/` and archive access in `archive/`.
The current data commands are registered directly on the root app.

## Test Organization

For the test directory layout, conventions, and shared fixtures, see
[Test Organization](reference/testing.md).
