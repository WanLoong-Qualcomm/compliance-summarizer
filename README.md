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
settings are never overwritten. Complete these fields before continuing:
workbook path, sheet name, supported test (`GAIN`), GAIN variation, global
background, selected pivot, and `bypass_model: true`. The command pauses after
creating or locating the file; press Enter after completing the settings.

Workbook loading supports `.xlsx` and `.xlsm` files in read-only mode. Macros
are not executed, and the source workbook is not saved or modified.

Sheet schema discovery reads semantic headers from rows 2–4, discovers pivots
without hard-coded reference names, and reports blocking structural findings
before row parsing begins.

Parsed rows retain original worksheet numbers and raw source values. Blank
pivot cells remain unavailable, numeric zero remains zero, and invalid numeric
text is reported without coercion.

Content validation keeps invalid GAIN rows out of affected calculations,
maintains separate comparison denominators for missing pivots, and blocks only
when required selected-pivot analysis has no usable inputs.

Before analysis, the negative-GAIN check scans every exact GAIN row and every
discovered pivot MIN. Numeric negative values are shown with worksheet and
signal-path context and require an explicit `yes` or `no` continuation choice;
blank, zero, nonnumeric, and non-GAIN values do not trigger the prompt.

The dataset summary then retains only exact normalized `GAIN` rows and keeps
PASS, FAIL, and invalid-result counts separate from non-GAIN tests.

Per-pivot failure rates use only numeric `wcMargin` values. Missing or
nonnumeric margins are reported as unavailable and are not counted as passes;
each rate retains its failure numerator and numeric denominator.

Pairwise GAIN comparisons subtract each comparison pivot's `NN_25C AVG` from
the selected pivot's value. Inclusive variation-threshold boundaries are
neutral, and missing or nonnumeric operands remain unavailable.

Failure analysis ranks source `FAIL` cases by selected-pivot `wcMargin`, using
worksheet row number as the deterministic tie-breaker. It retains the top 50
and worst five while tracking FAIL cases whose selected margin is unavailable.

Pass analysis retains the five smallest strictly positive selected-pivot
margins, keeps pairwise context attached, and reports exact-zero PASS margins
as a separate boundary count.

Overall pairwise comparisons use only rows with both numeric averages for each
denominator. They retain signed extrema, pivot-specific failure summaries, and
degradation-led failure candidates without converting unavailable values to
zero.

The model stage is explicit and deterministic in v0.1: `AI generation is
bypassed in v0.1.` No provider credentials, client, or network access is used.

## Run tests

Run the focused CLI smoke test:

```powershell
uv run --group dev pytest tests/test_cli.py
```

Run the complete test suite:

```powershell
uv run --group dev pytest
```
