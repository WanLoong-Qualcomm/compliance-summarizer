# Compliance Summarizer

This document describes the current implementation in version 0.2.0. The
source code and automated tests are authoritative for behavior; this document
records the supported workflow, data contract, calculation rules, and current
limits.

## 1. Product objective

Compliance Summarizer reads a SIGPATH RF transceiver compliance workbook and
produces a high-level standalone HTML report. The current implementation is
fully deterministic and bypasses AI/model calls. It keeps structured
intermediate data so model-backed explanations, additional report formats, or
charts can be added later without changing the compliance calculations.

The application must:

1. calculate pass/fail statistics from workbook values, never from the source
   `Result?` field;
2. expose coverage gaps and validation warnings instead of turning missing
   data into failures;
3. compare every selected pivot with the configured anchor pivot using the
   measurement-specific direction rules; and
4. produce useful HTML output without external assets or model access.

## 2. Terminology

- **Measurement:** A supported SIGPATH value in `TESTNAME`, such as `GAIN` or
  `IP3ACS`.
- **Pivot:** A DUT/variant result group named in row 2, such as `GF-QMOM`.
- **Anchor pivot:** The configured reference pivot used for all comparisons.
- **Comparison pivot:** Every other discovered pivot; comparisons are not
  restricted by DUT or variant naming.
- **Case:** One normalized worksheet data row for one selected measurement.
- **Case identity:** Every discovered row-4 metadata field except `Result?`,
  `LL`, and `UL`.
- **Coverage gap:** A missing, malformed, or non-finite required value. It is
  reported and excluded only from affected metrics; it is not a compliance
  failure.
- **`wcMargin`:** The authoritative compliance margin. A negative valid value
  is a failure and a non-negative valid value is a pass.
- **Acceptable variation:** The inclusive tolerance used to classify an
  oriented comparison delta as unchanged.

## 3. Application workflow

The implementation is staged across the following modules:

1. `config.py` loads and strictly validates `JUI.json`. It resolves relative
   workbook and output-directory paths against the settings file and enforces
   the current SIGPATH, supported-measurement, grouping, and model-bypass
   contract.
2. Measurement definitions provide signed comparison rules, tolerances, and
   optional per-measurement filters; `config.py` loads named custom grouping
   schemes from `configs/groups.json` in the settings-file directory.
3. `workbook.py` opens the configured worksheet read-only, discovers the row
   2–4 schema, and scans the data once for all selected measurements.
4. The workbook layer creates normalized `ComplianceCase` objects, preserving
   raw pivot values separately from finite numeric values and collecting
   coverage, filtering, limit, and duplicate-identity warnings.
5. `statistics.py` calculates independent per-pivot compliance statistics,
   ranked cases, and anchor-pivot comparisons.
6. `grouping.py` optionally partitions the same normalized cases by unique
   combinations of configured metadata fields and reuses the statistics
   calculator for each valid group.
7. `report.py` renders the structured result as escaped inline HTML. The
   report contains no charts or external assets.

An unexpected application error is reported as an actionable CLI error. An
unexpected calculation value represented by the internal `ERROR` sentinel is
rendered as bold red `ERROR`; expected unavailable values are rendered blank.

## 4. Workbook data contract

The configured compliance worksheet has this layout:

- **row 2:** pivot names; merged pivot cells are supported because a pivot name
  remains active across subsequent columns;
- **row 3:** pivot statistics;
- **row 4:** workbook-defined metadata headers and pivot display columns; and
- **row 5 onward:** data rows.

The parser recognizes these row-3 statistics, case-insensitively where
applicable:

`MIN`, `MAX`, `MEAN`, `NN_25C AVG`, `wcMargin`, and `wcValue`.

Every pivot must define `wcMargin` and at least one comparison statistic:
`MEAN` or `NN_25C AVG`. `MEAN` is preferred when its column exists; otherwise
`NN_25C AVG` is used. `MIN`, `MAX`, and `wcValue` are retained when present but
are not required for compliance calculations.

`TESTNAME` and `MEASPORT` are the only required row-4 metadata headers. All
other non-pivot row-4 headers are discovered dynamically, normalized for
lookup, and retained in case identity and ranked tables. The special source
and limit headers `Result?`, `LL`, and `UL` are retained in the parsed metadata
but excluded from identity and grouping.

The workbook is opened with `openpyxl` in read-only, cached-value mode. The
application does not save or modify the workbook and does not execute macros.

## 5. Configuration

`JUI.json` supports exactly these fields:

- `excel_file_path`: existing `.xlsx` or `.xlsm` path;
- `outputs_directory`: directory for timestamped default reports; relative
  paths are resolved beside the settings file, and blank uses `outputs`;
- `compliance_sheet_name`: worksheet name;
- `block`: currently required to be `SIGPATH`;
- `testnames`: one or more unique supported measurements;
- `background_information`: optional display text;
- `anchor_pivot`: non-empty exact pivot name, validated against the workbook;
- `add_fail_type`: optional boolean that adds derived per-pivot `FAIL_type`
  fields, defaulting to `false`;
- `group_by`: zero or more unique discovered metadata fields or named custom
  grouping schemes from `configs/groups.json`, or pivot-specific derived fields
  such as `DUT-1_VAR1.FAIL_type`; custom scheme source fields cannot be
  `Result?`, `LL`, or `UL`; and
- `include_group_failures`: boolean controlling per-group top-20 failure tables;
- `include_group_marginal_passes`: boolean controlling per-group top-5
  marginal-pass tables; and
- `bypass_model`: currently required to be the JSON value `true`.

The `add_fail_type` and two `include_group_*` fields are optional for
compatibility with older settings files and default to `false` when omitted.

Supported measurements are:

`GAIN`, `GAIN-DNL`, `GCIB`, `GCTX`, `IP2ACS`, `IP2IB`, `IP3ACS`, `IP3IB`,
`IP3TB`, `S11-LOW`, `S11-MID`, `S11-HIGH`, `SSNFWSPURREMOVAL`,
`SSNF-FIRSTRBWSPURREMOVAL`, and `SSNF-LASTRBWSPURREMOVAL`.

Measurement names and configurable metadata fields are normalized for
case/whitespace lookup. Unknown settings fields, missing settings fields,
duplicate measurements, duplicate grouping fields, unsupported measurements,
invalid definition tolerances, and invalid paths are rejected before analysis.

### 5.1 Optional row filters

Measurement-specific filters are defined inside the corresponding entry in
`configs/test_definition.json`:

```json
{
  "IP2ACS": {
    "delta_fn": "anchor - other",
    "acceptable_variation": 0.2,
    "filters": {"CHANNEL": ["IQ"]}
  }
}
```

A row must match every configured field rule for its measurement. String values
are trimmed and compared case-insensitively. Filtered rows remain out of that
measurement's cases and are reported in its warning list. A filter field that
does not exist in the selected workbook is a validation error.

### 5.2 Named custom grouping schemes

The application loads `configs/groups.json` when grouping is configured. Its
root object maps a scheme name to a definition containing:

- `field`: the source row-4 metadata field;
- `groups`: an object mapping output labels to lists of allowed values; and
- `default`: the output label for blank or unmatched source values.

For example:

```json
{
  "sigpath-block": {
    "field": "MEASPORT",
    "groups": {"LB": ["L1", "L2"]},
    "default": "OTHER"
  }
}
```

A scheme is selected by putting its name in `group_by`. Raw fields and custom
schemes may be combined, for example `group_by: ["sigpath-block", "TEMP"]`.
String matching trims whitespace and ignores case. Numeric/string equivalents
match numerically, and valid JSON scalar, list, and object values are accepted.
Blank values and values that match no allowed value use `default`.

## 6. Measurement definitions and statistics

The runtime definitions loaded from `configs/test_definition.json` define the
compliance margin statistic, comparison statistic preference, signed delta
function, and acceptable variation for each measurement.

`delta_fn` is one of the exact string constants `"anchor - other"`,
`"other - anchor"`, or `"midpoint deviation"`. The latter uses the row's LL/UL
midpoint. The application dispatches these constants directly; it does not
parse or execute arbitrary expressions. Tolerances are defined in the same
measurement-definition file rather than in `JUI.json`.

### 6.1 Compliance statistics

For every discovered pivot, the calculator produces:

- valid-case denominator;
- failure count and rate from negative `wcMargin` values;
- invalid `wcMargin` count;
- the lowest valid `wcMargin`; and
- the complete available case identity for that pivot's worst failure, when
  the lowest margin is negative.

The configured anchor pivot must have at least one valid `wcMargin`; otherwise
analysis stops because a compliance conclusion cannot be generated. Other
pivots may have no valid margins and are represented with unavailable values.

The overall analysis also produces:

- up to 20 anchor-pivot failures, ordered by ascending `wcMargin`;
- up to 5 anchor-pivot marginal passes, ordered by ascending non-negative
  `wcMargin`; and
- signed comparison deltas for every ranked case against every comparison
  pivot.

Stable identity fields and then worksheet row resolve ranking ties. Grouped
analyses intentionally omit the ranked case tables.

### 6.2 Comparison statistics

Comparisons are anchored on the configured anchor pivot and include every other
pivot. The report-oriented delta is signed so degradation is negative and
improvement is positive:

| Measurements | Better direction | Report-oriented delta |
| --- | --- | --- |
| `GAIN`, `IP2ACS`, `IP2IB`, `IP3ACS`, `IP3IB`, `IP3TB` | Higher | anchor value − comparison value |
| `GCIB`, `GCTX`, `S11-LOW`, `S11-MID`, `S11-HIGH`, `SSNFWSPURREMOVAL`, `SSNF-FIRSTRBWSPURREMOVAL`, `SSNF-LASTRBWSPURREMOVAL` | Lower | comparison value − anchor value |
| `GAIN-DNL` | Smaller midpoint deviation | comparison deviation − anchor deviation |

For `GAIN-DNL`, each comparison value is transformed to the absolute distance
from the row's `(LL + UL) / 2` midpoint. Rows with missing or invalid limits
are excluded from affected comparisons and produce a warning.

For every comparison pivot, the structured result contains:

- degradation, unchanged, and improvement rates;
- maximum degradation and maximum improvement;
- average degradation and average improvement;
- valid paired-row count; and
- anchor-only count, where the anchor comparison value is valid but the other
  comparison value is not.

Only valid pairs enter comparison metrics. An absolute signed delta less than
or equal to the configured tolerance is unchanged. Rates with no valid pairs
have no percentage value and render blank in HTML. The HTML report displays
percentages only; pair counts remain available in the structured result.

When enabled, each pivot's derived `FAIL_type` is calculated only for negative
valid `wcMargin` values. `MIN - LL` and `UL - MAX` are compared against
`wcMargin` using `math.isclose` with `rel_tol=1e-9` and `abs_tol=1e-9`.
Matching one direction returns `LL` or `UL`; matching both returns `TIE`; and
matching neither, or lacking enough values to classify the failure, returns
`UNDEF`. Non-failures return blank.

In ranked report tables, negative `wcMargin` and displayed `FAIL_type` values
remain red. Each of `MIN`, `MAX`, `NN_25C AVG`, and `MEAN` is independently
highlighted when outside the row's valid limits. `wcValue` retains its normal
styling. Ranked tables place pivot group names, pivot field names, and
worksheet/test metadata headers on separate lines to mirror the workbook.
LL/UL, pivot, user-defined, and delta cells retain row-wise blue/white
alternation, with the blue shade alternating by column group.

## 7. Coverage and validation behavior

Blank, malformed, and non-finite numeric cells are normalized to unavailable
values. The parser records coverage for the required `wcMargin` and selected
comparison statistic for each pivot. Raw values remain available for the
ranked source tables.

Coverage handling is metric-specific:

- a missing anchor-pivot `wcMargin` is excluded from that pivot's compliance
  denominator;
- a missing comparison-pivot value does not remove the anchor case from ranked
  tables, but its comparison value and delta render blank;
- a comparison pair with either invalid operand is excluded from paired
  summaries; and
- a missing or invalid `LL`/`UL` excludes only the affected `GAIN-DNL`
  comparisons.

Duplicate case identities generate a warning, while worksheet row numbers are
retained for traceability and tie-breaking.

## 8. Grouped analysis

`group_by: []` preserves overall-only behavior. A non-empty `group_by` list can
contain raw discovered row-4 metadata fields, named custom schemes, or both.
When `add_fail_type` is enabled it can also contain pivot-specific derived
fields such as `DUT-1_VAR1.FAIL_type`; those fields are rejected when the
feature is disabled.
Raw fields and custom scheme source fields are validated against the discovered
worksheet metadata. Cases are partitioned by the unique combination of the
resolved grouping dimensions.

Blank, empty, and whitespace-only raw grouping values are represented as
`(blank)`. For custom schemes, blank and unmatched values resolve to the
scheme's configured `default`. Changing the order of selected dimensions
changes display order only, not group membership. Groups are displayed in a
deterministic string order. A group with no valid anchor-pivot `wcMargin` values
is skipped and adds a warning to the measurement's existing warning list; other
groups continue to render.

Each valid group reuses the same compliance, comparison, tolerance, and
coverage rules as the overall analysis. Grouped sections always contain pivot
compliance and comparisons. The per-group top-20 failure and top-5
marginal-pass tables are independently enabled by
`include_group_failures` and `include_group_marginal_passes`.

## 9. HTML report and CLI

The HTML report contains one run-configuration section, followed by a complete
overall measurement section for each selected measurement. Each measurement
section contains:

1. coverage and validation warnings;
2. per-pivot compliance statistics;
3. anchor-pivot comparisons;
4. overall top-20 failures; and
5. overall top-5 marginal passes.

The worst valid `wcMargin` is rendered green when non-negative and red when
negative.
Row-4 fields physically located after the final pivot block are rendered after
all pivot fields under a `User defined` group header with pivot-style value
formatting.

Grouped sections follow the overall section when grouping is enabled. A single
methodology-and-assumptions section appears at the end.

All user/workbook text is HTML-escaped. Default reports are written atomically
to the configured output directory with timestamped names. An explicitly
selected output path is rejected if it exists unless `--overwrite` is supplied.

The CLI supports:

```powershell
uv run compliance-summarizer --init-settings
uv run compliance-summarizer --settings .\JUI.json
uv run compliance-summarizer --settings .\JUI.json --output .\report.html --overwrite
uv run compliance-summarizer --version
```

Expected application errors are printed to stderr and return exit code 2.

## 10. Current repository configuration

The checked-in `JUI.json` is a machine-specific working configuration. It
points to `references/QMOM_OVT_v2.xlsm`, selects the `Combined` sheet, uses
`GF-QMOM` as the anchor pivot, selects all currently supported measurements, and
groups by `TEMP`. Its absolute workbook path must be changed on another
machine. The repository also contains `references/FULL_COVERAGE.xlsm` as a
second reference workbook.

## 11. Scope and future extensions

Implemented now:

- deterministic SIGPATH workbook parsing;
- dynamic metadata discovery;
- multi-measurement processing in one workbook scan;
- measurement-specific comparison directions;
- coverage-gap and validation warnings;
- optional raw-field and named custom grouping;
- optional per-measurement row filters;
- optional per-pivot `FAIL_type` classification;
- standalone escaped HTML; and
- CLI initialization, processing, overwrite protection, and version output.

Not implemented in version 0.2.0:

- external model/provider calls or AI-generated prose;
- graphical UI;
- workbook modification;
- charts;
- additional output formats; and

Potential extension points are workbook/test contracts, measurement
definitions, pairing and coverage policies, aggregation, report templates,
model providers, chart builders, and output renderers.

## 12. Verification

Run the complete test suite with:

```powershell
uv run pytest
```

The suite covers configuration, workbook schema discovery and normalization,
filters, coverage gaps, measurement directions, midpoint deviation, ranking,
grouping, HTML escaping, and CLI behavior.
