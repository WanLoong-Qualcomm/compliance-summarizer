# Compliance Summarizer

Compliance Summarizer v0.2 reads a SIGPATH compliance workbook, calculates
deterministic GAIN compliance statistics, and creates a standalone HTML report.
Pass/fail calculations use `wcMargin`; the workbook's `Result?` field is shown
only as source context.

## Setup with uv

Python 3.12 or newer is required. Install the locked application and test
dependencies with:

```powershell
uv sync --dev
```

On a network that uses a custom certificate authority, use:

```powershell
uv --system-certs sync --dev
```

## Configure and run

Create a settings template:

```powershell
uv run compliance-summarizer --init-settings
```

Edit `settings.json`, especially `excel_file_path` and `main_pivot`, then run:

```powershell
uv run compliance-summarizer
```

By default, the report is written to `compliance-summary.html`. To select paths
or replace an existing report:

```powershell
uv run compliance-summarizer --settings .\settings.json `
  --output .\reports\summary.html --overwrite
```

The current settings fields are:

| Field | Requirement |
| --- | --- |
| `excel_file_path` | Existing `.xlsx` or `.xlsm`, relative to the settings file or absolute. |
| `compliance_sheet_name` | Worksheet containing the compliance table. |
| `test` | Must be `SIGPATH`. |
| `measurements` | Must be `["GAIN"]`. |
| `acceptable_variation` | Must contain one finite, non-negative `GAIN` value. |
| `background_information` | Optional report context string. |
| `main_pivot` | Exact pivot name discovered in row 2. |
| `group_by` | Optional identifying/compliance columns used for grouped analysis. Empty preserves the overall-only report. |
| `aggregate_port_groups` | Must be `false`; use `group_by` for grouped analysis. |
| `bypass_model` | Must be `true` in the current scope. |

See `settings.example.json` for a complete example.

## Workbook contract

- Row 2 contains pivot names (merged pivot cells are supported).
- Row 3 contains pivot statistics.
- Row 4 contains fixed compliance headers.
- Data starts at row 5.
- Every pivot must contain `NN_25c AVG` and `wcMargin`; `MIN`, `MAX`, and
  `wcValue` are retained when present.
- Required SIGPATH fields include `LNAMODE`, `CAMODE`, `STD`, `BAND`,
  `MEASPORT`, `DLP`, `DIV`, `TESTNAME`, `GAINMODE`, `BBPATH`, `FREQ`,
  `CHANNEL`, `Result?`, `LL`, and `UL`. `BW` and `F0_MHZ` are optional.

Missing or invalid required numeric pivot values are reported as coverage gaps.
They remain blank in the HTML report and are excluded only from the affected
metrics. Main pivot statistics use every valid main-pivot value even when
another pivot is missing. Pairwise summary metrics include only rows where
both averages are valid. Rates are calculated with their denominators
internally but displayed as percentages only; a rate with no valid pairs is
blank.

The report is a standalone HTML file with these sections:

- coverage and validation warnings;
- per-pivot compliance statistics based on `wcMargin`;
- main-pivot comparisons using signed degradation and improvement values;
- an Excel-style top-20 main-pivot failure table;
- grouped per-pivot statistics and comparisons when `group_by` is non-empty; and
- methodology and assumptions.

Grouped reports use the same compact tables and percentage-only presentation as
the overall report. They exclude the top-20 failure table. Blank grouping values
are shown as `(blank)`, and groups without valid main-pivot `wcMargin` values
are skipped with a validation warning.

Unexpected calculation failures are rendered as bold red `ERROR` text. The
source `Result?` value is retained for context and is never used for a
calculation. The report contains no external assets or charts.

## Test

```powershell
uv run pytest
```

The current scope excludes external model calls, non-GAIN measurements, a
graphical UI, and workbook modification.
