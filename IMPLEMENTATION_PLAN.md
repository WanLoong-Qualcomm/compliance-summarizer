# Current Implementation Status

## Version

The current packaged application is version 0.2.0. The implementation described
here is complete for the supported deterministic SIGPATH workflow.

## Outcome

The application reads a configured `.xlsx` or `.xlsm` compliance workbook,
discovers its SIGPATH schema, calculates deterministic statistics for one or
more supported measurements, optionally calculates metadata-grouped analyses,
and writes a self-contained HTML report. Model calls, charts, GUI behavior,
workbook modification, and additional output formats remain outside the
current scope.

## Completed workstreams

### 1. Configuration and CLI

- `JUI.json` is loaded and strictly validated.
- Relative workbook paths resolve against the settings file.
- Only the `SIGPATH` block is accepted.
- The supported measurement registry is validated before processing.
- Measurement-specific finite, non-negative `acceptable_variation` values are
  loaded from `configs/test_definition.json`.
- `group_by` entries are normalized and deduplicated. Entries may be discovered
  metadata fields or named schemes from `configs/groups.json`; custom scheme
  source fields are checked against the source-result/limit exclusions.
- `add_fail_type` is an optional boolean feature flag. Pivot-specific derived
  grouping fields such as `DUT-1_VAR1.FAIL_type` require it to be enabled.
- `include_group_failures` and `include_group_marginal_passes` are validated as
  booleans and default to `false`.
- `bypass_model` must be `true`.
- `--init-settings`, `--settings`, `--output`, `--overwrite`, and `--version`
  are available through the CLI.
- Expected failures return exit code 2 with an actionable message.

### 2. Workbook parsing and normalization

- `.xlsx` and `.xlsm` workbooks are opened read-only with cached values.
- Row 2 pivot names support merged cells.
- Row 3 pivot statistics and row 4 metadata are discovered dynamically.
- `TESTNAME` and `MEASPORT` are required metadata fields.
- Pivots require `wcMargin` and `MEAN` or `NN_25C AVG`.
- Raw source values and normalized numeric values are stored separately.
- Selected measurements are loaded in one worksheet scan.
- Optional filters are loaded from `configs/test_filters.json` beside the
  settings file.
- Named custom grouping schemes are loaded from `configs/groups.json` beside
  the settings file.
- Coverage gaps, malformed values, invalid limits, filtered rows, and duplicate
  identities produce warnings with metric-specific impact.

### 3. Measurement calculations

The definitions in `configs/test_definition.json`, loaded by
`measurements.py`, currently support:

`GAIN`, `GAIN-DNL`, `GCIB`, `GCTX`, `IP2ACS`, `IP2IB`, `IP3ACS`, `IP3IB`,
`IP3TB`, `S11-LOW`, `S11-MID`, `S11-HIGH`, `SSNFWSPURREMOVAL`,
`SSNF-FIRSTRBWSPURREMOVAL`, and `SSNF-LASTRBWSPURREMOVAL`.

The JSON file is the source of truth for signed comparison functions and
measurement-specific tolerances. `delta_fn` is one of the exact constants
`"this - other"`, `"other - this"`, or `"midpoint deviation"`; the application
dispatches these values directly without an expression parser.

The calculator implements:

- `wcMargin`-based failure/pass statistics;
- valid denominators and invalid-margin counts;
- worst margins and complete available failure identities;
- top-20 failure ranking;
- top-5 marginal-pass ranking;
- main-pivot comparisons against every other pivot;
- tolerance-aware degradation, unchanged, and improvement classification;
- signed maximum and average degradation/improvement; and
- `GAIN-DNL` midpoint-deviation comparison using `LL` and `UL`; and
- optional per-pivot `FAIL_type` classification using `MIN - LL` and
  `UL - MAX` with a `1e-9` absolute/relative tolerance.

Missing or invalid values are unavailable data, not failures. Comparison
statistics use valid pairs only. A missing comparison operand remains blank in
ranked tables. Rates with no valid pairs render blank.

### 4. Grouped analysis

- Empty `group_by` preserves overall-only behavior.
- Non-empty `group_by` accepts discovered metadata fields, named custom schemes,
  or a combination of both.
- Custom schemes map a source metadata field's allowed values to output labels
  and use their configured default for blank or unmatched values.
- Blank raw-field grouping values are shown as `(blank)`.
- String matching trims whitespace and ignores case; numeric/string equivalents
  match numerically, and valid JSON values are supported.
- Field order affects labels only, not group membership.
- Groups with no valid main-pivot `wcMargin` are skipped with a warning.
- Valid groups reuse the overall calculator. Per-group top-20 failures and
  top-5 marginal passes are independently controlled by the two group-table
  settings.
- Pivot-specific derived `FAIL_type` fields can be used as grouping dimensions
  when enabled.

### 5. HTML report

- The report is standalone and contains inline CSS only.
- User and workbook values are HTML-escaped.
- Configuration appears once at the beginning.
- Each selected measurement receives a complete overall section.
- Grouped sections follow the corresponding overall section.
- Methodology and assumptions appear once at the end.
- Expected unavailable values render blank.
- Unexpected calculation failures render as bold red `ERROR`.
- Derived `FAIL type` columns follow the pivot-field color convention, and
  `UNDEF` values render as bold red `UNDEF`.
- Negative `wcMargin` remains red. `MIN`, `MAX`, `NN_25C AVG`, and `MEAN` are
  independently red when outside the row's valid limits; `wcValue` retains
  its normal styling.
- Existing reports are protected unless `--overwrite` is supplied.
- Writes use a temporary file and atomic replacement.

## Explicit behavior decisions

- `Result?` is source context only and never determines compliance.
- A negative valid `wcMargin` is a failure; zero is a pass.
- `MEAN` is preferred when its pivot column exists; `NN_25C AVG` is the
  alternative when `MEAN` is not defined for that pivot.
- Comparison deltas are oriented so degradation is negative and improvement is
  positive.
- An absolute oriented delta within the inclusive tolerance is unchanged.
- Main-pivot statistics use valid main values even when another pivot is
  missing a value.
- Pairwise summaries use only valid pairs.
- Ranking ties use stable identity fields and worksheet row.
- `GAIN-DNL` uses absolute deviation from the row's `LL`/`UL` midpoint and
  excludes invalid-limit rows only from affected comparisons.
- `FAIL_type` is blank for non-failures, uses tolerance-based matching for
  `MIN - LL` and `UL - MAX`, and reports `UNDEF` when a failure cannot be
  classified.
- Grouped reports include ranked case tables only when their corresponding
  group-table settings are enabled.
- No model/provider call is made in version 0.2.0.

## Runtime configuration notes

The checked-in `JUI.json` is a local working configuration. It points to
`references/QMOM_OVT_v2.xlsm`, selects `Combined`, uses `GF-QMOM` as the main
pivot, selects all supported measurements, and groups by `TEMP`. Its absolute
path is machine-specific and must be edited elsewhere.

`configs/test_filters.json` and `configs/groups.json` are consumed at runtime
when the corresponding features are configured. The latter must contain a JSON
object whose definitions have `field`, `groups`, and `default` properties.

## Verification

Run the complete suite with:

```powershell
uv run pytest
```

The current test suite covers configuration, workbook discovery and
normalization, filters, coverage gaps, comparison direction, midpoint
deviation, ranking, grouping, HTML rendering, and CLI behavior.

## Deferred work

Future work may add:

- a defined structured AI/model output contract and provider integration;
- additional aggregation strategies beyond metadata grouping;
- charts generated from structured statistics;
- additional report formats;
- a graphical interface; and
- safe workbook-independent configuration for reusable group definitions.
