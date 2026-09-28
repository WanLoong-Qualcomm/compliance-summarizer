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
- **Aggregate:** A grouped view of measurement rows, for example a port group. Aggregate statistics use the same core metrics as measurement statistics, with explicitly documented exclusions.
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
   5. For each configured aggregate:
      1. Filter the rows to the aggregate.
      2. Calculate main statistics for every pivot.
      3. Calculate comparison statistics between the main pivot and every other pivot.
      4. Reduce low-level statistics to report-ready key statistics.
   6. Generate aggregate-centric charts when aggregation is enabled.
   7. Combine the prompt, input/output templates, calculated statistics, and supporting resources.
   8. Generate the measurement report or summary through the AI client, unless model usage is bypassed.

5. **Generate the overall report**
   - Combine the overall prompt, templates, resources, and per-measurement reports.
   - Generate the overall compliance report or summary through the AI client, unless model usage is bypassed.
   - Render the result as an HTML file with the calculated statistics and charts.

The pipeline should expose structured intermediate results between stages. This allows later versions to add report formats, charts, validation rules, or model providers without coupling them to Excel parsing.

## 5. Workbook data contract

### 5.1 Expected layout

The sample/reference workbook uses the `Combined` sheet with the following layout:

- **Row 2:** Pivot names, such as `DUT-1_VAR1`, `DUT-2_VAR1`, and `DUT-3_VAR2`.
- **Row 3:** Pivot fields, such as `MIN`, `MAX`, and `NN_25c AVG`.
- **Row 4:** Measurement/input column headers, such as `LNAMODE` and `CAMODE`.

Column headers in the compliance sheet are compulsory unless a future test definition explicitly marks one as optional.

The parser should treat the header locations and required fields as part of a test-specific data contract rather than scattering row numbers throughout the implementation.

### 5.2 Required metric fields

- `wcMargin` is the authoritative field for compliance pass/fail.
- `NN_25c AVG` is the field used to calculate degradation or improvement comparisons.
- The `Result?` column is display-only for compliance calculations and must not determine pass/fail rates or other compliance metrics.

### 5.3 Coverage gaps

Coverage gaps are expected in the current workbook: for example, `VAR1` pivots may contain blank fields where the corresponding `VAR2` pivot has a value.

Coverage gaps must be:

- detected during compliance-sheet validation;
- summarized for the user without overwhelming them with row-level detail;
- excluded from per-pivot statistics when the relevant pivot value is missing; and
- handled according to the comparison metric rather than through one universal join rule.

For comparisons based on paired values:

- **Per-row comparison tables:** use a left join from the main pivot's relevant rows. Preserve a main-pivot row when the comparison pivot is missing, and represent the comparison value and delta as `N/A` rather than dropping the row.
- **Paired summary metrics:** use an inner join on rows where both pivots have valid values. Exclude incomplete pairs from the mean, maximum, and rate calculations.
- **Main-pivot failure metrics:** calculate them from valid main-pivot values even when a comparison pivot has a coverage gap.

The exact row key used to pair pivots must be stable and derived from the measurement's identifying columns. It must not rely on incidental Excel row order.

## 6. Statistics and reporting requirements

### 6.1 Measurement main statistics

Calculate independently for each pivot:

- failure rate, using negative `wcMargin` values as failures;
- worst `wcMargin`;
- the failure path, meaning the complete combination of identifying columns for the main pivot's worst failure;
- the top 20 main-pivot failure cases, ordered by ascending main-pivot `wcMargin` so the most negative value appears first;
- the original compliance fields for each top-20 case; and
- the delta between the main pivot and every other pivot for the top-20 cases, using `NN_25c AVG` and the measurement-specific comparison direction.

For main-pivot failure cases, also calculate the average degradation between the main pivot and every other pivot. The definition of degradation direction is measurement-specific and must be documented in the measurement definition.

### 6.2 Measurement comparison statistics

For every other pivot, calculate the comparison against the main pivot:

- degradation rate;
- unchanged rate;
- improvement rate;
- maximum degradation; and
- maximum improvement.

Classification must account for the configured acceptable variation. In general, an absolute delta within the tolerance is unchanged; deltas outside the tolerance are classified as degradation or improvement according to the selected measurement's comparison direction.

The comparison direction is defined by the measurement, not globally. The delta is always expressed as the main-pivot value relative to the comparison-pivot value, but the sign's meaning depends on whether higher or lower values are better. For example, for `GAIN`, higher is better and:

```text
delta = main_pivot[NN_25c AVG] - comparison_pivot[NN_25c AVG]
```

For `GAIN`, a positive delta means the main pivot has higher gain and is an improvement; a negative delta means the main pivot has lower gain and is a degradation. A delta within the configured acceptable variation is unchanged. Other measurements must define their own direction and formula explicitly.

Comparisons are always anchored on the configured main pivot and run against every other pivot. For example, if `DUT-1_VAR1` is the main pivot, calculate separate comparisons for `DUT-1_VAR1` versus `DUT-2_VAR1` and `DUT-1_VAR1` versus `DUT-3_VAR2`. The application must not omit a pivot merely because its DUT or variant differs from the main pivot.

Rates must state their denominator and exclude rows without valid paired values.

### 6.3 Aggregate statistics

Aggregate main statistics use the same core metrics as measurement main statistics:

- failure rate;
- worst `wcMargin`;
- main-pivot failure path; and
- other applicable key statistics.

Aggregate statistics exclude:

- the top-20 failure-case compliance table; and
- average degradation between the main pivot and comparison pivots.

### 6.4 Aggregate comparison statistics

Aggregate comparison statistics use exactly the same definitions as measurement comparison statistics, including acceptable-variation handling, denominators, and coverage-gap treatment.

### 6.5 Charts

Charts should be generated from structured statistics rather than directly from raw workbook cells. In the current milestone, charts are limited to the capabilities explicitly enabled by the configuration. Future chart types should be registerable by measurement or aggregate type.

The HTML report should embed chart assets when practical so the generated report can be opened without access to a separate assets directory. If embedding is not supported by the selected chart library, the output contract must document the required asset files.

## 7. Configuration

`settings.json` is the current v0.1 runtime configuration. Its fields are:

- `excel_file_path`: user-selected input workbook path;
- `compliance_sheet_name`: compliance sheet name;
- `test`: selected test family;
- `measurements`: selected measurements;
- `acceptable_variation`: tolerance per measurement;
- `background_information`: optional context for report generation;
- `main_pivot`: baseline pivot;
- `group_by`: optional grouping fields for aggregates;
- `aggregate_port_groups`: whether port-group aggregation is enabled; and
- `bypass_model`: whether AI generation is bypassed.

Configuration validation should catch incompatible combinations, such as a configured measurement without an acceptable variation or a main pivot that is not present in the user-selected workbook.

## 8. Current milestone: v0.1

### Scope

- Implement the end-to-end application workflow.
- Use `settings.json` as the runtime configuration interface.
- Support the `SIGPATH` test only.
- Support the `GAIN` measurement only.
- Do not implement aggregation or aggregate-centric charts yet.
- Bypass model usage. The deterministic compiled output is used directly as the report input/output.
- Generate an HTML report containing the compiled statistics and embedded graphics where supported.
- Keep prompt construction minimal or stubbed until model usage is enabled.

### v0.1 acceptance criteria

1. A valid configured workbook can be loaded and processed.
2. Invalid configuration and irrecoverable workbook errors stop processing with actionable messages.
3. Coverage gaps are detected, summarized, and excluded according to the metric-specific rules.
4. Pass/fail statistics use `wcMargin`, never `Result?`.
5. Degradation and improvement use `NN_25c AVG` and the configured acceptable variation.
6. The report includes the required measurement statistics and top-20 main-pivot failure table.
7. The output is a self-contained HTML file whenever the selected chart implementation permits it.

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

## 12. Open questions and assumptions to confirm

The following items were ambiguous in the original project description. This version uses the stated assumptions until they are confirmed:

1. **Sample filename:** The workbook path is supplied by the user through `excel_file_path`; the filename mismatch only affects which repository workbook should be used as the sample/default value. The original text names `./EXMAPLE.xlsm`, the repository contains `EXAMPLE.xlsm`, and `settings.json` points to `./REFERENCE.xlsm`.
2. **Measurement definitions:** Each measurement should specify whether higher or lower values are better and how to calculate the main-versus-other delta. For `GAIN`, the current rule is `main - other`, where a positive value means the main pivot has higher gain and is improved.
3. **Missing and invalid values:** Should `wcMargin` values that are blank, non-numeric, or non-finite be treated as coverage gaps, validation errors, or excluded data warnings?
4. **Top-20 ties:** If multiple rows have the same `wcMargin` at rank 20, should the report include exactly 20 rows or all tied rows?
5. **Failure-path identity:** The document assumes that the identifying columns are the required measurement columns and that their combined values uniquely identify a row. If they do not, what additional row key should be used?
6. **AI output contract:** When model usage is enabled, should the AI return structured JSON that is rendered by the application, or may it return final HTML/Markdown directly?
