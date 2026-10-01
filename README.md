# Compliance Summarizer

Compliance Summarizer v0.2 reads a SIGPATH compliance workbook, calculates
deterministic compliance statistics for each selected measurement, and creates
a standalone HTML report.
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

Edit `JUI.json`, especially `excel_file_path` and `main_pivot`, then run:

```powershell
uv run compliance-summarizer
```

By default, the report is written to `compliance-summary.html`. To select paths
or replace an existing report:

```powershell
uv run compliance-summarizer --settings .\JUI.json `
  --output .\reports\summary.html --overwrite
```

The current settings fields are:

| Field | Requirement |
| --- | --- |
| `excel_file_path` | Existing `.xlsx` or `.xlsm`, relative to the settings file or absolute. |
| `compliance_sheet_name` | Worksheet containing the compliance table. |
| `block` | Must be `SIGPATH`. |
| `testnames` | Non-empty list selected from `GAIN`, `GAIN-DNL`, `GCIB`, `IP2ACS`, `IP2IB`, `IP3ACS`, `IP3IB`, `S11-LOW`, `S11-MID`, and `S11-HIGH`. |
| `acceptable_variation` | One finite, non-negative value for every selected measurement. |
| `background_information` | Optional report context string. |
| `main_pivot` | Exact pivot name discovered in row 2. |
| `group_by` | Optional row-4 metadata columns used for grouped analysis. Field names are discovered from the selected workbook; `Result?`, `LL`, and `UL` are excluded. Empty preserves the overall-only report. |
| `bypass_model` | Must be `true` in the current scope. |

The active local configuration is `JUI.json`.

Optional per-testname row filters are read from `configs/test_filters.json`
beside `JUI.json`. The current structure maps each testname to metadata fields
and their allowed values, for example:

```json
{
  "IP2ACS": {"CHANNEL": ["IQ"]}
}
```

Rows must match every configured field filter to be included in that
testname's coverage and statistics. Filtered rows are reported as a coverage
note.

## Workbook contract

- Row 2 contains pivot names (merged pivot cells are supported).
- Row 3 contains pivot statistics.
- Row 4 contains workbook-defined metadata headers and pivot display columns.
- Data starts at row 5.
- Every pivot must contain `wcMargin` and at least one of `MEAN` or
  `NN_25c AVG`. When both are present, calculations use `MEAN`; otherwise
  they use whichever one is available. `MIN`, `MAX`, and `wcValue` are
  retained when present.
- `TESTNAME` and `MEASPORT` are the only required row-4 metadata fields. Every
  other row-4 metadata field is optional and is discovered dynamically, so
  fields such as `TEMP` can be added or omitted without changing the parser.
  All discovered metadata fields are retained in report tables and signal-path
  identity, except `Result?`, `LL`, and `UL`, which remain source context or
  limit fields and are excluded from identity/grouping.

Missing or invalid required numeric pivot values are reported as coverage gaps.
They remain blank in the HTML report and are excluded only from the affected
metrics. Main pivot statistics use every valid main-pivot value even when
another pivot is missing. Pairwise summary metrics include only rows where
both selected comparison values are valid. Rates are calculated with their denominators
internally but displayed as percentages only; a rate with no valid pairs is
blank.

`GAIN-DNL` compares each pivot's absolute deviation from the row's `LL`/`UL`
midpoint. It uses `other deviation - main deviation`, because smaller
deviation is better. Rows with missing or invalid `LL`/`UL` values generate a
coverage warning and are excluded from affected comparisons. `GCIB` and the
three `S11` measurements use `other - main` because lower is better. `IP2ACS`,
`IP2IB`, `IP3ACS`, and `IP3IB` use `main - other` because higher is better.

The report is a standalone HTML file. Each selected measurement receives the
following complete summary:

- coverage and validation warnings;
- per-pivot compliance statistics based on `wcMargin`;
- main-pivot comparisons using signed degradation and improvement values;
- an Excel-style top-20 main-pivot failure table;
- an Excel-style top-5 main-pivot pass-case table, ordered by ascending `wcMargin`;
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

The current scope excludes external model calls, a graphical UI, and workbook
modification.
