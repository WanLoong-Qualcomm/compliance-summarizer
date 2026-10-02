# Compliance Summarizer

Compliance Summarizer 0.2.0 is a deterministic Python command-line tool for
processing a SIGPATH compliance workbook and producing a standalone HTML
report. It currently bypasses model calls: all pass/fail decisions,
comparisons, warnings, and report values come from application code.

Pass/fail calculations use `wcMargin`. The workbook's `Result?` field is
retained as source context only and is never used in a calculation.

## Setup

Python 3.12 or newer is required. Install the locked application and test
dependencies with `uv`:

```powershell
uv sync --dev
```

On a network that uses a custom certificate authority:

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

The default output is `compliance-summary.html`. To select a different path or
replace an existing report:

```powershell
uv run compliance-summarizer --settings .\JUI.json `
  --output .\reports\summary.html --overwrite
```

The settings file may be named differently. Relative workbook paths are
resolved relative to the settings file; absolute `.xlsx` and `.xlsm` paths are
also accepted. The supported fields are:

| Field | Behavior |
| --- | --- |
| `excel_file_path` | Existing `.xlsx` or `.xlsm` workbook. |
| `compliance_sheet_name` | Worksheet containing the SIGPATH compliance table. |
| `block` | Must be `SIGPATH`. |
| `testnames` | Non-empty list selected from `GAIN`, `GAIN-DNL`, `GCIB`, `GCTX`, `IP2ACS`, `IP2IB`, `IP3ACS`, `IP3IB`, `IP3TB`, `S11-LOW`, `S11-MID`, `S11-HIGH`, `SSNFWSPURREMOVAL`, `SSNF-FIRSTRBWSPURREMOVAL`, and `SSNF-LASTRBWSPURREMOVAL`. |
| `background_information` | Optional text rendered in the run configuration. It is not sent to a model in the current scope. |
| `main_pivot` | Exact pivot name discovered in row 2. It is the baseline for every comparison. |
| `add_fail_type` | Boolean. When `true`, each pivot exposes a derived `FAIL_type` field for failures. Defaults to `false`. |
| `group_by` | Optional row-4 metadata fields or named schemes from `configs/groups.json`. `Result?`, `LL`, and `UL` cannot be used as source fields. Empty means overall analysis only. |
| `include_group_failures` | Boolean. When `true`, each valid group includes its top-20 failure table. Defaults to `false`. |
| `include_group_marginal_passes` | Boolean. When `true`, each valid group includes its top-5 marginal-pass table. Defaults to `false`. |
| `bypass_model` | Must be `true` in version 0.2.0. |

Optional per-measurement row filters are loaded from
`configs/test_filters.json` under the settings file's directory. Every field
in a measurement's filter must match for a row to be included. String matches
are trimmed and case-insensitive; non-string values use normal equality.

For example:

```json
{
  "IP2ACS": {"CHANNEL": ["IQ"]}
}
```

Excluded rows are reported as a coverage note.

Measurement definitions are loaded from `configs/test_definition.json`. Each
definition contains a `delta_fn` and its finite, non-negative
`acceptable_variation`:

```json
{
  "GAIN-DNL": {
    "delta_fn": "midpoint deviation",
    "acceptable_variation": 0.2
  }
}
```

`delta_fn` accepts only `"main - other"`, `"other - main"`, or
`"midpoint deviation"`. The latter uses the row's LL/UL midpoint and the same
signed comparison convention. There is no expression parser or arbitrary code
execution. Tolerances are defined alongside their measurements in this file,
not in `JUI.json`.

Named custom grouping schemes are loaded from `configs/groups.json`. Each
scheme names a source metadata field, maps allowed values to group labels, and
provides a default for blank or unmatched values:

```json
{
  "sigpath-block": {
    "field": "MEASPORT",
    "groups": {
      "LB": ["L1", "L2"]
    },
    "default": "OTHER"
  }
}
```

Reference a scheme by name in `group_by`, and combine it with raw metadata
fields when needed:

```json
"group_by": ["sigpath-block", "TEMP"]
```

Custom group matching trims and compares strings case-insensitively, supports
numeric/string equivalence, and supports valid JSON scalar, list, and object
values. Blank source values and values that match no configured group use the
scheme's `default` label. Scheme names are normalized like metadata headers.

## Workbook contract

The configured worksheet uses this layout:

- row 2 contains pivot names; merged pivot cells are supported;
- row 3 contains recognized pivot statistics;
- row 4 contains workbook-defined metadata headers and pivot display columns;
- row 5 onward contains data.

`TESTNAME` and `MEASPORT` are the only required row-4 metadata fields. All
other row-4 metadata fields are discovered dynamically and retained in case
identity and ranked report tables. `Result?`, `LL`, and `UL` are retained as
source context or limits but are excluded from case identity and grouping.

When `add_fail_type` is enabled, each pivot also exposes a derived `FAIL_type`
value. It is `LL`, `UL`, or `TIE` for classified negative `wcMargin` failures,
`UNDEF` when a failure cannot be matched to either limit direction, and blank
for non-failures. `UNDEF` is rendered in bold red. The derived value is not a
workbook source column.

Each pivot must contain `wcMargin` and at least one of `MEAN` or `NN_25C AVG`.
When both comparison-statistic columns exist, `MEAN` is preferred. The parser
also retains `MIN`, `MAX`, and `wcValue` when present. Recognized statistic
names are case-insensitive for `MIN`, `MAX`, `MEAN`, `NN_25C AVG`, `wcMargin`,
and `wcValue`.

The workbook is opened read-only with cached values. It is not modified and
macros are not executed.

## Calculations and coverage

- Negative valid `wcMargin` values are failures; non-negative values are passes.
- Blank, malformed, and non-finite required numeric values are coverage gaps,
  not failures.
- Per-pivot failure statistics use every valid `wcMargin` for that pivot,
  independently of other pivots.
- Pairwise comparison statistics use only rows where both selected comparison
  values are valid. A missing comparison value leaves the corresponding ranked
  table cell blank.
- Rates use their valid-pair denominators internally and are displayed as
  percentages. A rate with no valid pairs is blank.
- `GAIN-DNL` compares absolute deviation from the row's `LL`/`UL` midpoint.
  Missing or invalid limits produce a warning and exclude that row only from
  affected comparisons.
- When enabled, `FAIL_type` compares `MIN - LL` and `UL - MAX` with the pivot's
  negative `wcMargin` using a deterministic `1e-9` absolute/relative
  tolerance. Matching both directions produces `TIE`; matching neither
  produces `UNDEF`.

Comparison values use `MEAN` when that column is available for the pivot and
otherwise use `NN_25C AVG`. The report-oriented delta is signed so degradation
is negative and improvement is positive:

| Measurements | Better direction | Report-oriented delta |
| --- | --- | --- |
| `GAIN`, `IP2ACS`, `IP2IB`, `IP3ACS`, `IP3IB`, `IP3TB` | Higher | main value − comparison value |
| `GCIB`, `GCTX`, `S11-LOW`, `S11-MID`, `S11-HIGH`, `SSNFWSPURREMOVAL`, `SSNF-FIRSTRBWSPURREMOVAL`, `SSNF-LASTRBWSPURREMOVAL` | Lower | comparison value − main value |
| `GAIN-DNL` | Smaller midpoint deviation | comparison deviation − main deviation |

An absolute signed delta within the inclusive measurement-specific
`acceptable_variation` is classified as unchanged.

## Grouped analysis

With `group_by: []`, the report contains only the overall analysis. With one or
more raw metadata fields or named custom schemes, rows are partitioned by the
unique combination of those grouping dimensions and the same deterministic
calculations are run independently for each group.

Blank, empty, and whitespace-only group values are displayed as `(blank)`.
Reordering `group_by` changes label order only, not group membership. A custom
scheme displays its scheme name and resolved label, for example
`sigpath-block=LB`. A group with no valid main-pivot `wcMargin` is skipped and
reported as a coverage warning.

When `add_fail_type` is enabled, pivot-specific derived fields may also be used
in `group_by`, for example `DUT-1_VAR1.FAIL_type`. Referencing such a field
while `add_fail_type` is disabled is rejected.

Grouped sections always include pivot compliance and pivot comparisons. Their
top-20 failure and top-5 marginal-pass tables are controlled independently by
`include_group_failures` and `include_group_marginal_passes`.

## Report contents

The standalone HTML report contains no external assets or charts. It includes:

- run configuration;
- one complete overall summary for each selected measurement;
- coverage and validation warnings;
- per-pivot compliance statistics;
- main-pivot comparisons against every other pivot;
- an overall top-20 main-pivot failure table;
- an overall top-5 main-pivot marginal-pass table;
- grouped analysis sections when `group_by` is non-empty; and
- methodology and assumptions.

In pivot compliance tables, the worst `wcMargin` is highlighted red for a
failure and green when it is a valid pass.

The ranked tables retain worksheet row, discovered metadata, source pivot
fields, derived `FAIL type` columns when enabled, `Result?`, limits, and signed
comparison deltas. The internal grouping field remains `FAIL_type`, so a
pivot-specific grouping entry uses `DUT-1_VAR1.FAIL_type`. Expected unavailable
values render blank. Unexpected calculation failures render as bold red
`ERROR`; unclassifiable fail types render as bold red `UNDEF`.
Negative `wcMargin` and displayed `FAIL type` values use failure-red text.
Within pivot fields, each of `MIN`, `MAX`, `NN_25C AVG`, and `MEAN` is checked
independently against the row's valid limits and is red when outside them.
`wcValue` retains its normal styling.
Ranked compliance tables use separate header lines for pivot group names, pivot
field names, and worksheet/test metadata fields, mirroring the workbook's
header-row structure.

## Test

```powershell
uv run pytest
```

The current scope excludes external model calls, a graphical user interface,
workbook modification, charts, and additional report formats.
