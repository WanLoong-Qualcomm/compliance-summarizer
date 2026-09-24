# Compliance Summarizer

This project is managed and executed with [`uv`](https://docs.astral.sh/uv/).
No globally installed Python interpreter or manually activated virtual
environment is required.

## Setup

Install the locked application and test dependencies:

```powershell
uv sync --dev
```

The supported Python version is Python 3.12 or newer.

## Run the command-line application

Start the command-line entry point with:

```powershell
uv run compliance-summarizer
```

On the first run, the command creates `settings.json` and never overwrites an
existing settings file. Complete the file and press Enter when prompted. On
later runs, the existing file is loaded and validated after the same pause.

After the settings are loaded, the command discovers the worksheet schema,
asks for background information for each discovered pivot, performs the
negative-GAIN confirmation when needed, calculates the deterministic v0.1
analysis, and writes `compliance-summary.html` in the current directory.
The report is not overwritten automatically; move or remove an existing
report before rerunning.

The settings template contains these fields:

| Field | v0.1 value or behavior |
| --- | --- |
| `excel_file_path` | Existing `.xlsx` or `.xlsm` workbook path. |
| `compliance_sheet_name` | Exact worksheet name; default `Combined`. |
| `tests_to_report` | Exactly `GAIN`; no other test is supported. |
| `acceptable_variation.GAIN` | Finite nonnegative threshold; default `0.2`. |
| `background_information` | Optional global background text. |
| `pivot_field_of_interest` | Exact discovered pivot name. |
| `bypass_model` | Must be `true` in v0.1. |

## Workbook assumptions

Workbook loading accepts `.xlsx` and `.xlsm` files in read-only mode. Macros
are never executed, the source workbook is never saved, and formulas are read
from cached values when available.

Schema discovery reads semantic headers from rows 2, 3, and 4, with data
starting at row 5. It discovers pivot fields and their `MIN`, `MAX`,
`NN_25C AVG`, and `wcMargin` statistics without hard-coded pivot names. The
required fixed fields are:

`LNAMODE`, `CAMODE`, `STD`, `BAND`, `MEASPORT`, `DLP`, `DIV`, `TESTNAME`,
`GAINMODE`, `BBPATH`, `FREQ`, `CHANNEL`, `Result?`, `LL`, and `UL`.

`BW` and `F0_MHZ` are optional context fields. Additional trailing workbook
columns are reported as unknown diagnostics and are not used in calculations.

## Validation and missing data

The negative-GAIN check scans every exact normalized `GAIN` row and every
discovered pivot `MIN`. Numeric negative values are shown with worksheet and
signal-path context and require an explicit full-word `yes` or `no` decision.
Blank, zero, nonnumeric, and non-GAIN values do not trigger the prompt. EOF,
interruptions, or rejection abort safely before analysis and report generation.

Parsed rows retain original worksheet row numbers and raw source values. Blank
pivot cells remain unavailable, numeric zero remains zero, and invalid numeric
text is not coerced. Missing values are excluded only from calculations that
require them and are reported through warnings and exclusion counts.

The source `Result?` value remains separate from derived pivot status. GAIN
failure rates use only numeric `wcMargin` values and expose their numerator and
denominator. Pairwise GAIN comparisons use signed selected-minus-comparison
`NN_25C AVG` deltas; threshold boundaries are neutral, and unavailable
operands do not enter denominators.

## Deterministic report output

The report renderer accepts a complete deterministic analysis result:

```python
from compliance_summarizer.report import write_html_report

write_html_report(analysis, "compliance-summary.html")
```

`write_html_report` writes `compliance-summary.html` atomically by default and
does not overwrite an existing report unless `overwrite=True` is supplied.
The generated HTML embeds its CSS, top-50 failure image, and accessible HTML
tables; it does not reference local assets or network resources. The report
contains the fixed 14-section order, validation warnings, GAIN counts,
failure/pass analysis, pairwise comparisons, degradation-led candidates, and
the model-bypass statement.

Reference-workbook validation is reproducible with:

```powershell
uv run --group dev pytest tests/test_reference_integration.py -q
```

The supplied `REFERENCE.xlsm` `Combined` sheet validates to 4,256 GAIN rows:
4,160 PASS and 96 FAIL. The known 896 rows missing `GF-PROTO` and `GF-QMOM`
values remain unavailable for affected comparisons rather than becoming zero.

## v0.1 limitations

Version 0.1 supports only RX SIGPATH GAIN characterization at the NN split
represented by `NN_25C AVG`. It excludes:

- Graphical or web UI features.
- AI-generated prose and external model-provider calls.
- Gain-DNL, SSNF, linearity, S11, and non-GAIN tests.
- Temperatures or splits other than the represented NN/25C data.
- Editing workbooks or executing VBA macros.
- Automatic repair of malformed worksheets.

## Run tests

Run the focused CLI tests:

```powershell
uv run --group dev pytest tests/test_cli.py
```

Run the complete suite:

```powershell
uv run --group dev pytest
```
