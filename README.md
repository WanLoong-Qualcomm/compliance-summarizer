# Compliance Summarizer

This project is managed and executed with [`uv`](https://docs.astral.sh/uv/).
No globally installed Python interpreter or manually activated virtual
environment is required.

## Setup

Install or update the locked application and test dependencies:

```powershell
uv sync --dev
```

The supported Python version is Python 3.12 or newer. `uv` supplies the
environment and resolves the interpreter when needed.

## Run the application

Start the command-line application with:

```powershell
uv run compliance-summarizer
```

The current command is the execution baseline. Workbook ingestion and report
generation are added by later implementation tasks.

On the first run, the command creates a `settings.json` template. Existing
settings are never overwritten. Complete these fields before a later workflow
run: workbook path, sheet name, supported test (`GAIN`), GAIN variation, global
background, selected pivot, and `bypass_model: true`.

Workbook loading supports `.xlsx` and `.xlsm` files in read-only mode. Macros
are not executed, and the source workbook is not saved or modified.

Sheet schema discovery reads semantic headers from rows 2–4, discovers pivots
without hard-coded reference names, and reports blocking structural findings
before row parsing begins.

Parsed rows retain original worksheet numbers and raw source values. Blank
pivot cells remain unavailable, numeric zero remains zero, and invalid numeric
text is reported without coercion.

## Run tests

Run the focused CLI smoke test:

```powershell
uv run --group dev pytest tests/test_cli.py
```

Run the complete test suite:

```powershell
uv run --group dev pytest
```
