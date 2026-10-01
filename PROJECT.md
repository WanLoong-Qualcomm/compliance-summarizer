# Compliance Summarizer

## 1. Product objective

Build an AI-assisted application that reads an Excel compliance workbook and produces a high-level HTML report for RF transceiver measurement compliance.

The application should combine deterministic calculations with AI-generated explanations:

- Deterministic code validates the input workbook and calculates all compliance statistics.
- The AI client turns those statistics, prompts, templates, and supporting resources into readable measurement-level and overall summaries.
- The report must remain useful when AI generation is disabled. In that mode, the deterministic statistics are rendered directly into the HTML output.

## 2. Design principles

1. **Statistics are deterministic.** Pass/fail decisions and numerical metrics must be calculated by application code, not inferred by the AI model.
2. **The workbook is the source of measurement values.** The `Result?` column must never be used to calculate pass/fail statistics.
3. **The application should fail clearly.** Invalid or irrecoverable input must produce an actionable error rather than a partially misleading report.
4. **Optional data must be handled explicitly.** Missing pivot values are coverage gaps, not automatically failures.
5. **The design should be extensible.** New tests, measurements, aggregation strategies, report sections, and model providers should be addable without rewriting the overall workflow.
6. **Configuration belongs outside the implementation.** Runtime choices such as the workbook path, test, measurements, main pivot, grouping, and model bypass should be controlled through configuration.

## 3. Terminology

- **Test:** A test family or test mode, such as `SIGPATH`.
- **Measurement:** A metric within a test, such as `GAIN`.
- **Pivot:** A DUT/variant result column or logical result set, such as `DUT-1_VAR1`.
- **Main pivot:** The pivot selected as the baseline for comparison.
- **Comparison pivot:** Any other pivot compared with the main pivot. The default comparison set includes every other pivot in the selected measurement, including pivots from different DUTs or variants.
- **Measurement statistics:** Statistics calculated directly from the rows belonging to a measurement.
- **Overall analysis:** The v0.1 analysis calculated across all rows for the selected measurement.
- **Grouped analysis:** An independent analysis calculated for the rows sharing one unique combination of the configured `group_by` fields. Grouped analysis reuses the v0.1 calculation rules with the explicitly documented grouped-report exclusions.
- **Group key:** The values corresponding to the configured `group_by` fields that identify a grouped analysis. Field order affects only label presentation, not group membership. Blank grouping values are represented as `(blank)`.
- **Coverage gap:** A row or field for which a pivot has no usable value while another relevant pivot has a value. A coverage gap is reported to the user and excluded according to the metric-specific rules below; it is not itself a compliance failure.
- **`wcMargin`:** The authoritative compliance margin. A negative value indicates failure; a non-negative value indicates pass, subject to any explicitly configured handling for missing or invalid values.
- **Acceptable variation:** The configured tolerance used when classifying a comparison as degradation, unchanged, or improvement.

## 4. Application workflow

The workflow is intentionally staged so that validation, calculation, and report generation remain separate concerns.

1. **Load configuration and inputs**
   - Read the runtime configuration.
   - Load the workbook selected by the user through `excel_file_path` and open the configured compliance sheet.
   - Identify the test, measurements, main pivot, optional grouping, and acceptable variation.

2. **Validate application inputs**
   - Confirm that the workbook exists and can be opened.
   - Confirm that the configured sheet, test, measurements, main pivot, and required columns exist.
   - Confirm that the workbook structure is compatible with the selected test and measurements.
   - If application inputs are invalid, stop and report the specific validation errors.

3. **Validate the compliance sheet**
   - Check the required header and pivot rows.
   - Check that required column headers are present.
   - Identify missing, blank, malformed, or otherwise unusable pivot values.
   - Report coverage gaps at a high level, for example: `DUT-1_VAR1: 12 gaps`.
   - If a problem is recoverable, state its impact and request user approval before continuing.
   - If a problem is irrecoverable, stop without generating a compliance conclusion.

4. **Calculate measurement results**
   For each configured measurement:

   1. Filter the input rows to the measurement.
   2. Calculate main statistics independently for every pivot.
   3. Calculate comparison statistics between the main pivot and every other pivot.
   4. Reduce low-level statistics to report-ready key statistics.
   5. When grouped analysis is enabled, partition the measurement rows by each
      unique combination of the configured `group_by` fields.
   6. For each group, calculate the same main-pivot and comparison statistics as
      the measurement analysis, except for the grouped-report exclusions defined
      below. A group without a valid main-pivot `wcMargin` is skipped after its
      coverage warning is recorded.
   7. Reserve group-centric charts for a later version; v0.1 and v0.2 have no
      chart output.
   8. Combine the prompt, input/output templates, calculated statistics, and supporting resources.
   9. Generate the measurement report or summary through the AI client, unless model usage is bypassed.

5. **Generate the overall report**
   - Combine the overall prompt, templates, resources, and per-measurement reports.
   - Generate the overall compliance report or summary through the AI client, unless model usage is bypassed.
   - Render the result as a standalone HTML file with the calculated statistics.

The pipeline should expose structured intermediate results between stages. This allows later versions to add report formats, charts, validation rules, or model providers without coupling them to Excel parsing.

## 5. Workbook data contract

### 5.1 Expected layout

The sample/reference workbook uses the `Combined` sheet with the following layout:

- **Row 2:** Pivot names, such as `DUT-1_VAR1`, `DUT-2_VAR1`, and `DUT-3_VAR2`.
- **Row 3:** Pivot fields, such as `MIN`, `MAX`, `MEAN`, and `NN_25c AVG`.
- **Row 4:** Workbook-defined metadata/input column headers, such as `LNAMODE`,
  `CAMODE`, or `TEMP`.

`TESTNAME` and `MEASPORT` are the only required row-4 metadata fields. Every
other metadata field is optional and discovered from the workbook. All
discovered metadata fields are retained in report tables and case identity;
`Result?`, `LL`, and `UL` are retained as source context/limits but excluded
from case identity and grouping. Pivot statistics must include `wcMargin` and
at least one of `MEAN` or `NN_25c AVG`. If both are present, calculations use
`MEAN`; otherwise they use the available alternative. `MIN`, `MAX`, and
`wcValue` are retained when present.

The parser should treat the header locations and required fields as part of a test-specific data contract rather than scattering row numbers throughout the implementation.

### 5.2 Required metric fields

- `wcMargin` is the authoritative field for compliance pass/fail.
- `MEAN` is preferred for degradation or improvement comparisons; `NN_25c AVG`
  is the fallback when `MEAN` is unavailable.
- The `Result?` column is display-only for compliance calculations and must not determine pass/fail rates or other compliance metrics.

### 5.3 Coverage gaps

Coverage gaps are expected in the current workbook: for example, `VAR1` pivots may contain blank fields where the corresponding `VAR2` pivot has a value.

Coverage gaps must be:

- detected during compliance-sheet validation;
- summarized for the user without overwhelming them with row-level detail;
- excluded from per-pivot statistics when the relevant pivot value is missing; and
- handled according to the comparison metric rather than through one universal join rule.

For comparisons based on paired values:

- **Per-row comparison tables:** use a left join from the main pivot's relevant rows. Preserve a main-pivot row when the comparison pivot is missing, and render the comparison value and delta as blank rather than dropping the row.
- **Paired summary metrics:** use an inner join on rows where both pivots have valid values. Exclude incomplete pairs from the mean, maximum, and rate calculations.
- **Main-pivot failure metrics:** calculate them from valid main-pivot values even when a comparison pivot has a coverage gap.

The exact row key used to pair pivots must be stable and derived from the
available metadata identity. It must not rely on incidental Excel row order.

## 6. Statistics and reporting requirements

### 6.1 Measurement main statistics

Calculate independently for each pivot:

- failure rate, using negative `wcMargin` values as failures;
- worst `wcMargin`;
- the failure path, meaning the complete available metadata identity for the
  main pivot's worst failure;
- the top 20 main-pivot failure cases, ordered by ascending main-pivot `wcMargin` so the most negative value appears first;
- the top 5 main-pivot passing cases, ordered by ascending non-negative main-pivot `wcMargin` so the cases closest to the compliance limit appear first;
- the original compliance fields for each ranked case; and
- the signed delta between the main pivot and every other pivot for each ranked failure and pass case, using the preferred `MEAN`/`NN_25c AVG` comparison statistic and the measurement-specific comparison direction. Degradation is negative and improvement is positive.

### 6.2 Measurement comparison statistics

For every other pivot, calculate the comparison against the main pivot:

- degradation rate;
- unchanged rate;
- improvement rate;
- maximum degradation; and
- maximum improvement;
- average degradation; and
- average improvement.

Average degradation and improvement are calculated across all valid paired
rows classified in the corresponding category. The values are signed, so
degradation is negative and improvement is positive.

Classification must account for the configured acceptable variation. In general, an absolute delta within the tolerance is unchanged; deltas outside the tolerance are classified as degradation or improvement according to the selected measurement's comparison direction.

The comparison direction is defined by the measurement, not globally. The delta is always expressed as the main-pivot value relative to the comparison-pivot value, but the sign's meaning depends on whether higher or lower values are better. For example, for `GAIN`, higher is better and:

```text
delta = main_pivot[comparison statistic] - comparison_pivot[comparison statistic]
```

The comparison statistic is `MEAN` when that pivot provides it; otherwise it
is `NN_25c AVG`.

For `GAIN`, a positive delta means the main pivot has higher gain and is an improvement; a negative delta means the main pivot has lower gain and is a degradation. A delta within the configured acceptable variation is unchanged. Other measurements must define their own direction and formula explicitly.

Comparisons are always anchored on the configured main pivot and run against every other pivot. For example, if `DUT-1_VAR1` is the main pivot, calculate separate comparisons for `DUT-1_VAR1` versus `DUT-2_VAR1` and `DUT-1_VAR1` versus `DUT-3_VAR2`. The application must not omit a pivot merely because its DUT or variant differs from the main pivot.

Rates exclude rows without valid paired values. Denominators are retained in the
structured statistics for traceability, while the HTML report displays rates as
percentages only. A rate with no valid pairs is blank.

### 6.3 Grouped analysis statistics

Grouped analysis uses the same core metrics as measurement main statistics:

- failure rate;
- worst `wcMargin`;
- main-pivot failure path; and
- other applicable key statistics.

Grouped analysis excludes:

- the top-20 failure-case compliance table; and

### 6.4 Grouped comparison statistics

Grouped comparison statistics use exactly the same definitions as measurement
comparison statistics, including acceptable-variation handling and coverage-gap
treatment. The grouped HTML presentation follows the existing v0.1 report:
rates are displayed as percentages only, expected unavailable values are blank,
and unexpected calculation failures are rendered as bold red `ERROR`.

Grouping behavior is defined as follows:

- `group_by: []` produces the existing overall analysis only.
- A non-empty `group_by` partitions rows by unique combinations of the selected
  fields. Reordering the selected fields does not change group membership,
  although report labels may follow the configured field order.
- Blank, empty, and whitespace-only grouping values are represented by the
  explicit value `(blank)` and are not discarded.
- Any discovered metadata field may be selected. `Result?`, `LL`, and `UL` are
  not valid grouping fields.
- A group with no valid main-pivot `wcMargin` values is omitted from grouped
  statistics and contributes a warning in the existing coverage-and-validation
  warning list. It does not prevent other groups from being reported.

### 6.5 Charts

Future charts should be generated from structured statistics rather than
directly from raw workbook cells. Chart types should be registerable by
measurement or aggregate type. v0.1 intentionally emits no chart.

Future chart assets should be embedded when practical so generated reports can
be opened without a separate assets directory.

## 7. Configuration

`JUI.json` is the runtime configuration. Its fields are:

- `excel_file_path`: user-selected input workbook path;
- `compliance_sheet_name`: compliance sheet name;
- `block`: selected test family;
- `testnames`: selected measurements;
- `acceptable_variation`: tolerance per measurement;
- `background_information`: optional context for report generation;
- `main_pivot`: baseline pivot;
- `group_by`: optional discovered row-4 metadata fields for grouped analysis;
  `Result?`, `LL`, and `UL` cannot be used;
- `bypass_model`: whether AI generation is bypassed.

Configuration validation should catch incompatible combinations, such as a configured measurement without an acceptable variation or a main pivot that is not present in the user-selected workbook.

## 8. v0.1 (Status: Complete)

### Scope

- Implement the end-to-end application workflow.
- Use `JUI.json` as the runtime configuration interface.
- Support the `SIGPATH` test only.
- Support the `GAIN` measurement only.
- Do not implement aggregation or aggregate-centric charts yet.
- Bypass model usage. The deterministic compiled output is used directly as the report input/output.
- Generate a standalone HTML report containing the compiled statistics. No
  chart is included in v0.1.
- Keep prompt construction minimal or stubbed until model usage is enabled.

### v0.1 acceptance criteria

1. A valid configured workbook can be loaded and processed.
2. Invalid configuration and irrecoverable workbook errors stop processing with actionable messages.
3. Coverage gaps are detected, summarized, and excluded according to the metric-specific rules.
4. Pass/fail statistics use `wcMargin`, never `Result?`.
5. Degradation and improvement use preferred `MEAN`/`NN_25c AVG` values and
   the configured acceptable variation.
6. The report includes the required measurement statistics and top-20 main-pivot failure table.
7. The output is a self-contained HTML file with no external assets.
8. Expected unavailable values render as blank, while unexpected calculation
   failures render as bold red `ERROR`.
9. Comparison degradation is negative and improvement is positive, with the
   measurement definition controlling the direction.

## 9. Extensibility requirements

Future versions should be appended below this section using the template in Section 10. Existing sections should remain stable unless a requirement is intentionally changed; changes should be recorded under the relevant version.

The implementation should isolate these extension points:

- workbook parsing and test-specific data contracts;
- measurement definitions and required fields;
- pivot pairing and coverage-gap policies;
- statistic calculators;
- aggregate/grouping strategies;
- chart builders;
- prompt and report templates;
- AI client/model providers; and
- output renderers.

Each new version should state its scope, changed behavior, acceptance criteria, and compatibility impact. A later version may supersede an earlier rule, but it should not silently change the interpretation of existing reports.

## 10. Future milestone template

Copy and append the following section for each future version:

```markdown
## vX.Y (Status: Planned|In progress|Complete)

### Objective

<!-- One paragraph describing the outcome of this version. -->

### Scope

-

### Behavior changes

-

### Acceptance criteria

1.

### Compatibility and migration notes

-

### Open questions

-
```

## 11. Implementation guidance

- Follow standard coding and testing practices.
- Prefer established packages such as pandas, NumPy, Plotly, or dataframe-to-image tools when they reduce implementation risk.
- Avoid large, brittle validation frameworks or custom boilerplate when a maintained package or a small focused validator is sufficient.
- Keep raw workbook data, normalized data, calculated statistics, AI prompts, and rendered report output as separate representations.
- Use stable field names and explicit schemas for intermediate results.
- Include tests for missing values, coverage gaps, ties in the top-20 list, invalid `wcMargin`, invalid comparison values, and empty result sets.
- Log enough context to diagnose a failed run without exposing sensitive workbook data unnecessarily.

## 12. Resolved v0.1 decisions and next-revision questions

The original open questions are resolved for v0.1 as follows:

1. **Sample filename:** Runtime configuration controls the workbook path. The
   repository sample is `EXAMPLE.xlsm`; the generated template uses the
   placeholder path `./REFERENCE.xlsm`, which must be edited before running.
2. **Measurement definitions:** Each measurement owns its comparison direction
   and delta orientation. GAIN uses the main-pivot comparison statistic minus
   the comparison-pivot comparison statistic, preferring `MEAN` and falling
   back to `NN_25c AVG`, with negative values meaning degradation and positive
   values meaning improvement.
3. **Missing and invalid values:** Blank, malformed, and non-finite required
   pivot values are expected coverage gaps. They remain blank, are not
   compliance failures, and are excluded only from affected metrics.
4. **Calculation errors:** An unexpected calculation error is rendered as bold
   red `ERROR`; it must never be silently converted to a blank.
5. **Top-20 ties:** The report contains exactly 20 rows when at least 20
   failures exist. Stable identifying fields and then worksheet row resolve
   ties.
6. **Failure-path identity:** The available SIGPATH identifying fields form the
   displayed path. Duplicate combinations generate a warning, and worksheet
   row numbers preserve traceability.
7. **AI output contract:** AI generation is bypassed in v0.1. A future version
   must define whether the model returns structured data for rendering or
   final prose/markup.

The next revision will define the grouped-analysis data contract. The remaining
future decisions are:

- supported non-GAIN measurement definitions and direction rules;
- the model provider and structured AI output schema; and
- whether optional visualizations or additional output formats are needed.

## 13. v0.2 (Status: In progress)

### Objective

Enable grouped compliance analysis using user-selected workbook metadata
columns while preserving the current v0.1 overall report and presentation
conventions.

### Scope

- Accept a non-empty `group_by` list of discovered workbook metadata fields.
- Partition rows by unique combinations of those fields.
- Run the existing deterministic compliance and comparison calculations
  independently for each group.
- Keep the current v0.1 overall analysis as the first report section.
- Render grouped reports after the overall analysis.

### Behavior changes

- `group_by: []` remains the backward-compatible ungrouped behavior.
- Grouped reports contain the existing per-pivot compliance and pivot-comparison
  presentations, with the group key shown as the group context.
- Grouped reports do not contain the top-20 failure table.
- Grouped reports do not introduce denominator columns, a second coverage table,
  or other new statistical presentation elements. Existing percentage, blank,
  and `ERROR` rendering conventions remain authoritative.
- Blank grouping values are shown as `(blank)`.
- Groups without a valid main-pivot `wcMargin` are skipped and reported through
  the existing warning-list presentation.
- The grouped report order is not a statistical property. Any deterministic
  display order is acceptable while visualization and hierarchy are out of
  scope.

### Acceptance criteria

1. A valid `group_by` configuration creates one analysis for every unique group
   key and does not lose rows because of blank grouping values.
2. Each valid group uses the same pass/fail, comparison-direction,
   acceptable-variation, and coverage-gap rules as v0.1.
3. The overall v0.1 report remains first and unchanged in substance.
4. Grouped reports appear after the overall report and exclude the top-20
   failure table.
5. A group without a valid main-pivot `wcMargin` produces a coverage warning,
   is skipped, and does not stop valid groups from being reported.
6. Grouped HTML output uses the existing v0.1 conventions for percentages,
   unavailable values, warnings, and calculation errors.

### Compatibility and migration notes

- Existing `group_by: []` settings retain v0.1 behavior.

### Open questions

- None for the v0.2 grouped-analysis behavior described above.

## Current multi-measurement revision

The workflow supports the following SIGPATH measurements:

- `GAIN`;
- `GAIN-DNL`;
- `GCIB`;
- `IP2ACS` and `IP2IB`;
- `IP3ACS` and `IP3IB`; and
- `S11-LOW`, `S11-MID`, and `S11-HIGH`; and
- `SSNFWSPURREMOVAL`.

The configured measurements are loaded in one workbook pass and each receives
an independent copy of the current report summary. All measurements use the
source `wcMargin` for compliance. Comparison values use `MEAN` when available,
otherwise `NN_25C AVG`.

Optional measurement-specific row filters are loaded from
`configs/test_filters.json` beside `JUI.json`. The structure maps a testname to
metadata fields and allowed values; all fields in a testname's filter must
match for a row to be included. For example, `IP2ACS` can restrict `CHANNEL`
to `IQ` without changing the workbook schema or the main settings contract.

`GAIN-DNL` transforms each pivot comparison value into its absolute deviation
from the row-level `LL`/`UL` midpoint. Because smaller deviation is better,
its oriented comparison is `other deviation - main deviation`. Missing or
invalid `LL`/`UL` values produce a coverage warning and are excluded only from
affected comparisons. `GCIB`, the `S11` measurements, and
`SSNFWSPURREMOVAL` use `other - main`; the `IP2` and `IP3` measurements use
`main - other`.
