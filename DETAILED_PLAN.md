# Detailed Implementation Plan

## 1. Purpose and Source Authority

This document expands `HIGH_LEVEL_PLAN.md` into an implementation-ready plan for version 0.1 of the compliance summarizer.

Source precedence is mandatory:

1. `HIGH_LEVEL_PLAN.md` is the source of truth for business requirements and scope.
2. The `Combined` sheet in `REFERENCE.xlsm` is the reference for workbook structure, terminology, field names, pivot statistics, compliance behavior, and representative data conditions.
3. This document may make an ambiguous requirement executable by stating an implementation assumption, but it must not add a new business capability or override the high-level plan.

If implementation evidence later conflicts with this document, compare it with `HIGH_LEVEL_PLAN.md` first. Do not silently change behavior. Record the conflict and obtain clarification if the source intent cannot be preserved.

## 2. v0.1 Outcome

Implement a UV-managed Python command-line application that:

1. Creates a user-editable `settings.json` file.
2. Waits for the user to complete the file and press Enter.
3. Loads an `.xlsx` or `.xlsm` compliance workbook and a named compliance sheet.
4. Validates the required signal-path columns, pivot fields, and pivot statistics.
5. Collects background information for every discovered pivot field.
6. Performs the required negative-GAIN safety check.
7. Processes only the GAIN test at 25C for the NN split.
8. Computes deterministic compliance summaries, failure analysis, pass analysis, and pairwise pivot comparisons.
9. Bypasses external AI generation.
10. Produces a fixed, self-contained HTML report suitable for direct embedding in an email.

The implementation is complete only when the full workflow can be run against the `Combined` sheet in `REFERENCE.xlsm` and produces a deterministic report without modifying or executing macros in the source workbook.

## 3. Scope Boundaries

### 3.1 Included

- Desktop execution through a command-line application.
- Python managed and executed with `uv`.
- `.xlsx` and `.xlsm` input files.
- A user-selected compliance worksheet.
- RX SIGPATH characterization.
- GAIN only.
- NN split at 25C, represented by the `NN_25C AVG` pivot statistic.
- User-selected pivot field of interest.
- Comparisons between the pivot field of interest and every other discovered pivot field.
- Compliance calculations based on `Result?`, `LL`, `UL`, `MIN`, `MAX`, `NN_25C AVG`, and `wcMargin`.
- User-provided GAIN variation threshold, defaulting to `0.2`.
- Interactive confirmation when negative GAIN `MIN` values are found.
- Deterministic HTML, tables, and required graphics.
- A bypassed or local stub model stage with no external AI call.

### 3.2 Excluded

- A graphical or web user interface.
- AI-generated prose or any external model-provider integration.
- Gain-DNL.
- SSNF, linearity, S11, or any test other than GAIN.
- Temperatures or splits other than the data represented by `NN_25C AVG`.
- Editing the input workbook.
- Executing VBA macros in `.xlsm` files.
- Automatically repairing malformed compliance worksheets.
- Inferring new business rules from unsupported columns.
- Changing compliance limits or recalculating source measurement statistics from raw silicon-test data.

## 4. Reference Workbook Findings

The following facts were verified against the `Combined` sheet in `REFERENCE.xlsm` and must guide implementation and tests.

### 4.1 Sheet Layout

- The sheet contains 44,076 rows and 37 columns in the supplied reference workbook.
- Row 1 contains the title `COMPLIANCE_DASHBOARD`.
- Row 2 contains pivot-field labels.
- Row 3 contains pivot-statistic labels.
- Row 4 contains the Excel table's physical column headers.
- Data begins on row 5.
- The Excel table is named `Dashboard` and spans `A4:AK44076` in the reference workbook.
- Pivot labels are merged across their five statistic columns. A parser must therefore treat a merged row-2 label as applying to all statistic columns in that merged block.

### 4.2 Fixed Signal-Path and Test Columns

Columns `A:Q` contain:

| Column | Header | v0.1 status |
|---|---|---|
| A | `LNAMODE` | Required |
| B | `CAMODE` | Required |
| C | `STD` | Required |
| D | `BAND` | Required |
| E | `BW` | Optional additional context |
| F | `MEASPORT` | Required |
| G | `DLP` | Required |
| H | `DIV` | Required |
| I | `F0_MHZ` | Optional additional context |
| J | `TESTNAME` | Required |
| K | `GAINMODE` | Required |
| L | `BBPATH` | Required |
| M | `FREQ` | Required |
| N | `CHANNEL` | Required |
| O | `Result?` | Required |
| P | `LL` | Required |
| Q | `UL` | Required |

`BW` and `F0_MHZ` are present in the reference but are not minimum v0.1 requirements. When present, retain them as case context and display them in case-detail output. Their absence must not fail structural validation.

### 4.3 Pivot Groups and Statistics

The reference contains these row-2 pivot fields:

- `GF-PROTO`, spanning `R:V`.
- `GF-QMOM`, spanning `W:AA`.
- `SEC-DR5`, spanning `AB:AF`.

Every pivot group uses this row-3 statistic order:

1. `MIN`
2. `MAX`
3. `NN_25C AVG`
4. `wcMargin`
5. `wcValue`

`wcValue` exists in the reference but is not a minimum v0.1 requirement. Preserve and display it when present, but do not reject a workbook solely because `wcValue` is absent.

The implementation must discover pivot names from the selected sheet. It must not hard-code the three reference pivot names.

### 4.4 Additional Reference Columns

The reference contains pairwise delta and fail-type columns after the pivot groups:

- `Δ(QMOM, PROTO)`
- `Δ(QMOM, SEC)`
- `Δ(PROTO, SEC)`
- `QMOM FAIL TYPE`
- `SEC FAIL TYPE`

These are reference evidence, not required v0.1 inputs. The application must calculate its own selected-pivot comparisons from `NN_25C AVG` and must not depend on these optional columns being present.

For GAIN, the reference delta formulas subtract the second named pivot from the first named pivot, for example `Δ(QMOM, PROTO) = QMOM NN_25C AVG - PROTO NN_25C AVG`. This validates the use of signed differences for GAIN comparisons.

### 4.5 Reference Data Conditions That Must Be Supported

- The reference contains 4,256 GAIN rows: 4,160 `PASS` and 96 `FAIL`.
- Some GAIN rows do not contain values for every pivot field. In the reference, 896 GAIN rows contain `SEC-DR5` values while `GF-PROTO` and `GF-QMOM` are blank.
- All 4,256 GAIN rows contain both `LL` and `UL` in the reference, but the implementation must still validate row values rather than assume this always holds.
- For all GAIN rows in the reference, `Result? = FAIL` corresponds to at least one available pivot having a negative `wcMargin`.
- The reference's existing delta formulas can produce misleading values when a pivot is blank because spreadsheet formulas may treat blanks as zero. The application must not reproduce that behavior. It must mark a pairwise comparison unavailable when either required `NN_25C AVG` value is missing.

## 5. Terminology and Calculation Rules

Use the following terms and rules consistently in code, logs, tests, and report labels.

### 5.1 Case

A case is one data row from the compliance sheet after the four header rows. Its identity and context consist of the available signal-path and test-information fields from `A:Q`, plus the original worksheet row number.

The original worksheet row number must be retained for traceability and deterministic tie-breaking.

### 5.2 Pivot Field

A pivot field is a row-2 label spanning a group of row-3 statistics. Each pivot field represents a configuration, split, or other comparison dimension in the compliance table.

A pivot field is structurally valid only when its group contains unique columns for all required statistics:

- `MIN`
- `MAX`
- `NN_25C AVG`
- `wcMargin`

### 5.3 Pivot Field of Interest

The pivot field of interest is the user-selected pivot that anchors ranking and comparisons. It must match one discovered pivot name exactly after trimming leading and trailing whitespace. Do not perform fuzzy matching or silently substitute a pivot.

### 5.4 Compliance and Failure

- The source `Result?` value identifies whether the complete compliance case is `PASS` or `FAIL`.
- A pivot-specific failure occurs when that pivot's numeric `wcMargin` is less than zero.
- A pivot-specific pass occurs when that pivot's numeric `wcMargin` is greater than or equal to zero.
- A missing or nonnumeric `wcMargin` is unavailable, not pass and not fail.
- Do not overwrite `Result?` with a derived value.
- If source `Result?` disagrees with available pivot margins, report a data-validity warning. Continue only if the discrepancy does not prevent the requested calculations; otherwise terminate with a clear error.

### 5.5 Worst-Case Margin and Value

- Lower `wcMargin` is worse.
- A negative `wcMargin` is a failure.
- Among failures, the most negative `wcMargin` is the worst.
- Among passing cases, the smallest positive `wcMargin` is closest to failure.
- `wcValue`, when available, is contextual output and must not replace `wcMargin` for ranking.

### 5.6 GAIN Delta

For every row where both values are numeric, calculate:

```text
delta = pivot_of_interest.NN_25C AVG - comparison_pivot.NN_25C AVG
```

Because higher GAIN is better:

- `delta < -variation_threshold` means degradation for the pivot field of interest.
- `delta > variation_threshold` means improvement for the pivot field of interest.
- `abs(delta) <= variation_threshold` is neutral.
- A delta exactly equal to either threshold boundary is neutral.
- If either value is missing or nonnumeric, the comparison is unavailable and must not enter rate denominators or extrema.

This normalized selected-pivot convention may require negating a pre-existing reference delta whose label uses the opposite pivot order. Calculate from the underlying averages instead of selecting a spreadsheet delta column.

### 5.7 Comparison Rates

For each comparison pivot independently:

```text
degradation_rate = degradation_count / comparable_case_count
improvement_rate = improvement_count / comparable_case_count
neutral_rate = neutral_count / comparable_case_count
```

`comparable_case_count` includes only retained GAIN rows having numeric `NN_25C AVG` values for both pivots.

If `comparable_case_count` is zero, display the rates as unavailable. Never divide by the total number of GAIN rows when one side of the comparison is missing.

### 5.8 Pivot Failure Rate

For each pivot independently:

```text
failure_rate = count(numeric wcMargin < 0) / count(numeric wcMargin)
```

Report the numerator, denominator, percentage, and number of unavailable margins. This makes missing-pivot coverage explicit.

### 5.9 Maximum Degradation and Improvement

For each comparison pivot:

- Maximum degradation is the most negative qualifying delta and its case context.
- Maximum improvement is the largest positive qualifying delta and its case context.
- If no delta exceeds the applicable threshold, report `None` for that category.
- Preserve the signed delta in data and output. A separate absolute magnitude may be displayed, but must not replace the signed value.

### 5.10 Degradation-Led Failure

Evaluate both aggregate and case-level evidence:

- Aggregate signal: the pivot field of interest has a higher pivot-specific failure count or failure rate than a comparison pivot over their comparable cases.
- Case-level candidate: the pivot field of interest has `wcMargin < 0`, the comparison pivot has `wcMargin >= 0`, and the selected-pivot GAIN delta is a degradation under the configured threshold.

Retain case-level candidates with full signal-path context. Do not claim causation; label them `degradation-led failure candidates`.

## 6. Assumptions and Constraints

These assumptions resolve nonblocking ambiguity without changing the approved requirements.

1. A single worksheet row already aligns corresponding pivot values. No cross-row join is required.
2. Comparisons are valid only when both pivot values required by the calculation are numeric.
3. Missing pivot data is expected because it exists in the reference. It is not automatically a workbook-level error.
4. Missing required structural headers or statistics is a blocking validation error.
5. Numeric zero is a valid measurement or margin and must not be treated as missing.
6. `PASS` and `FAIL` matching is case-insensitive after trimming whitespace, but the report uses uppercase canonical labels.
7. Unknown nonblank `Result?` values are validation errors for affected rows.
8. The GAIN variation threshold is a nonnegative finite number in the same unit as GAIN, expected to be dB.
9. The default threshold is `0.2`.
10. The default and only supported test list is `['GAIN']`. Any other requested test is rejected in v0.1 rather than silently ignored.
11. `bypass_model` defaults to `true` and must be `true` in v0.1. A false value produces an unsupported-feature error; it must not trigger a network call.
12. Background information can be empty, but the user must be given an explicit opportunity to provide global and per-pivot background.
13. The workbook is opened read-only and with formulas evaluated from cached workbook values. Macros are never executed.
14. If a required formula-backed cell has no cached value, treat it as unavailable and report the problem; do not calculate arbitrary replacement values unless the calculation is explicitly defined in this plan.
15. Rows remain in original worksheet order unless a required sort is being performed.
16. Sort ties are broken by original worksheet row number in ascending order.
17. Percentages must expose their numerator and denominator and use one consistent report-wide rounding rule.
18. The report must be self-contained: CSS and generated graphics are embedded in the HTML rather than referenced through machine-local paths.
19. No workbook-specific pivot names, row counts, cell ranges, test counts, or result counts may be hard-coded.

## 7. Settings Contract

### 7.1 Required JSON Shape

Create `settings.json` with this initial structure and defaults:

```json
{
  "excel_file_path": "",
  "compliance_sheet_name": "Combined",
  "tests_to_report": ["GAIN"],
  "acceptable_variation": {
    "GAIN": 0.2
  },
  "background_information": "",
  "pivot_field_of_interest": "",
  "bypass_model": true
}
```

The generated file must be valid JSON and must not contain comments.

### 7.2 Field Validation

| Field | Validation | Failure behavior |
|---|---|---|
| `excel_file_path` | Nonempty path; file exists; extension is `.xlsx` or `.xlsm` | Stop with actionable error |
| `compliance_sheet_name` | Nonempty string; exact sheet exists | Stop and list available sheet names |
| `tests_to_report` | Nonempty list containing only `GAIN` | Stop and state v0.1 supports only GAIN |
| `acceptable_variation.GAIN` | Numeric, finite, and `>= 0` | Stop and show expected value |
| `background_information` | String; empty allowed | Stop only for wrong type |
| `pivot_field_of_interest` | Nonempty and matches a discovered pivot | Stop and list discovered pivots |
| `bypass_model` | Boolean and `true` | Stop if false because AI is unavailable in v0.1 |

Do not place user-entered secrets in the settings template. v0.1 requires no API key.

### 7.3 Interactive Sequence

1. Start the application.
2. Create `settings.json` if it does not exist.
3. If it already exists, do not overwrite user content without explicit confirmation.
4. Print the settings path and short completion instructions.
5. Wait for Enter.
6. Parse and validate JSON syntax and fields.
7. Load and structurally validate the workbook.
8. Discover pivot fields and validate the selected pivot.
9. Prompt once for background information for each discovered pivot field, in worksheet order.
10. Run the negative-GAIN check.
11. If negative values exist, show them and request an explicit proceed/abort decision.
12. Run deterministic analysis.
13. Run the bypassed model stage.
14. Generate the HTML report.
15. Print the report location and a concise processing summary.

End-of-file or invalid input at a required confirmation prompt must abort safely rather than assume consent.

## 8. Workbook Parsing Contract

### 8.1 Header Parsing

Read rows 2 through 4 independently:

- Row 2 defines pivot-field labels.
- Row 3 defines pivot-statistic labels.
- Row 4 defines physical table columns and fixed case fields.

For columns after the fixed signal-path section:

1. Identify a pivot group from a nonblank row-2 label.
2. Apply that label across its merged range. If merge metadata is unavailable, carry the label across consecutive recognized pivot-statistic columns until the next nonblank row-2 label or the statistic sequence ends.
3. Map each recognized row-3 statistic to its physical column index.
4. Stop treating columns as pivot statistics when row 3 no longer contains recognized pivot-statistic names.
5. Allow unrecognized trailing columns without using them as required inputs.

Do not use row-4 names such as `Column1`, `Column2`, and `Column3` as semantic statistic names. They are Excel table implementation names in the reference.

### 8.2 Required Structure

The selected sheet is structurally valid only if:

- All required fixed headers are present exactly once.
- At least one pivot field is discovered.
- Every discovered pivot field used by v0.1 has exactly one `MIN`, `MAX`, `NN_25C AVG`, and `wcMargin` column.
- The selected pivot field of interest is present.
- A data region exists below row 4.

Reject duplicate required headers, duplicate required statistics within a pivot, orphaned row-3 statistics without a pivot label, or overlapping pivot definitions.

### 8.3 Row Parsing

For each row beginning at row 5:

- Retain original worksheet row number.
- Read fixed context fields by mapped header, not assumed column number.
- Read pivot statistics by discovered pivot/statistic mapping.
- Preserve optional `BW`, `F0_MHZ`, and `wcValue` when available.
- Normalize only superficial text whitespace and canonical PASS/FAIL case.
- Do not coerce arbitrary text to numbers.
- Treat blank cells as missing.
- Reject or warn on nonnumeric values in fields required by a calculation, as defined in the validation matrix.

### 8.4 Workbook Safety

- Never save the source workbook.
- Never execute macros.
- Do not require Excel to be installed.
- Close workbook resources after parsing.
- Include source filename, sheet name, and processing timestamp in the report, but do not expose unrelated filesystem information.

## 9. Validation and User Decisions

### 9.1 Structural Validation

Blocking errors:

- File missing or unsupported extension.
- Workbook cannot be opened.
- Sheet missing.
- Required fixed header missing or duplicated.
- No valid pivot field.
- Required statistic missing or duplicated in a pivot group.
- Selected pivot field absent.
- No data rows.

### 9.2 Content Validation

Evaluate GAIN rows for:

- Valid `Result?` value.
- Numeric `LL` and/or `UL` where compliance context requires them.
- Numeric selected-pivot `wcMargin` for rankings.
- Numeric `NN_25C AVG` on both sides of a comparison.
- Numeric `MIN` for the negative-GAIN check.
- Source `Result?` consistency with available pivot `wcMargin` signs.

A missing value should invalidate only the calculation that needs it unless it makes the entire requested report impossible. Record excluded-row counts by reason.

The run is blocked if the selected pivot has no numeric GAIN `wcMargin` values or no numeric GAIN `NN_25C AVG` values, because required ranking or comparison outputs cannot be produced.

### 9.3 Negative-GAIN Check

Run this check whenever any GAIN row is present, regardless of `tests_to_report` contents.

1. Examine `MIN` for every discovered pivot on every GAIN row.
2. Select numeric values less than zero.
3. Display a compact table containing worksheet row, pivot field, `MIN`, and all available signal-path context fields.
4. Ask the user whether to proceed.
5. Continue only on an explicit affirmative response.
6. On rejection, terminate before analytics and report generation.

If no negative values exist, log that the check passed and continue without prompting.

### 9.4 Warning Policy

Warnings must be collected for inclusion in the report. At minimum, warn about:

- Missing optional context columns.
- Missing pivot values.
- Rows excluded from a calculation.
- Source `Result?` and pivot-margin inconsistency.
- Formula cells without cached values.
- Unknown extra columns or statistics.

Warnings must identify counts and representative worksheet rows without overwhelming the report. Full details may be placed in a collapsible HTML section.

## 10. Data Processing Requirements

### 10.1 GAIN Filtering

- Filter by normalized `TESTNAME == 'GAIN'`.
- Do not include `IP3IB-GAIN`; it is a distinct reference test name.
- Do not process any other test in v0.1.
- If no GAIN rows remain, terminate with a clear error.

### 10.2 Case Context

Every retained case table must include, when available:

- Worksheet row number.
- `LNAMODE`
- `CAMODE`
- `STD`
- `BAND`
- `BW`
- `MEASPORT`
- `DLP`
- `DIV`
- `F0_MHZ`
- `TESTNAME`
- `GAINMODE`
- `BBPATH`
- `FREQ`
- `CHANNEL`
- `Result?`
- `LL`
- `UL`
- Selected pivot statistics.
- Relevant comparison-pivot statistics and calculated delta.

Do not drop a signal-path field merely because many rows contain the same value.

### 10.3 Failure-Case Dataset

Build the failure-case dataset from rows whose source `Result?` is `FAIL`.

For selected-pivot ranking:

1. Keep rows with numeric selected-pivot `wcMargin`.
2. Sort ascending by `wcMargin`.
3. Break ties by worksheet row number.
4. Retain the first 50 as `top_failure_cases`.
5. Retain the first 5 as `worst_failure_cases`.
6. If fewer than 50 or 5 qualifying rows exist, retain all available rows.
7. Record source FAIL rows that could not be ranked because the selected pivot margin is unavailable.

For each of the five worst cases:

- Include all other pivots' available `wcMargin` values.
- Classify each comparison margin as fail, pass, or unavailable.
- Include selected-pivot and comparison `NN_25C AVG` values.
- Calculate and classify the delta.
- Identify whether the row is a degradation-led failure candidate.

### 10.4 Pass-Case Dataset

Build the pass-case dataset from rows whose source `Result?` is `PASS`.

1. Keep rows with a numeric selected-pivot `wcMargin` greater than zero.
2. Sort ascending by `wcMargin`.
3. Break ties by worksheet row number.
4. Retain the first five as `closest_pass_cases`.
5. If fewer than five exist, retain all available rows.

For each retained pass case:

- Compare the selected pivot with every other pivot that has a numeric average.
- Show signed delta and classification.
- Keep the source margin visible so that a user can judge whether degradation remains acceptable.
- Do not suppress a degradation merely because the margin is positive. Label it and preserve the margin; the report narrative may state that compliance remains passing.

Rows with exactly zero `wcMargin` do not satisfy the specified smallest-positive selection. Report their count separately as boundary cases.

### 10.5 Pairwise Overall Comparison

For each nonselected pivot:

1. Build the comparable set across all retained GAIN rows.
2. Calculate signed delta.
3. Classify degradation, improvement, or neutral.
4. Count each classification.
5. Calculate rates using the comparable set denominator.
6. Find maximum degradation and maximum improvement.
7. Retain complete context for both extrema.
8. Calculate pivot-specific failure counts and rates over comparable rows for aggregate degradation-led failure checks.
9. Retain all case-level degradation-led failure candidates.

Do not combine all comparison pivots into one denominator. Produce one result per comparison pivot.

## 11. Deterministic Analysis Output Contract

Before HTML rendering, assemble one complete analysis result containing at least:

- Source metadata.
- Validated user settings.
- Global background information.
- Per-pivot background information.
- Discovered fixed columns.
- Discovered optional columns.
- Ordered pivot names and statistic mappings.
- Total worksheet data rows.
- Total GAIN rows.
- PASS and FAIL row counts.
- Negative-GAIN findings and user decision.
- Data-quality warnings and exclusion counts.
- Per-pivot failure counts, denominators, rates, and unavailable counts.
- Top 50 selected-pivot failure cases.
- Five worst selected-pivot failure cases with cross-pivot context.
- Five closest-to-failure pass cases with cross-pivot context.
- Zero-margin pass boundary count.
- Per-comparison degradation, improvement, and neutral counts and rates.
- Per-comparison maximum degradation and improvement cases.
- Aggregate and case-level degradation-led failure evidence.
- Model-bypass status.

All renderers and tests should consume this analysis result rather than recomputing business metrics during HTML generation.

## 12. HTML Report Requirements

### 12.1 General Requirements

- Produce valid HTML with embedded CSS.
- Use a fixed section order.
- Escape all workbook and user-provided text before inserting it into HTML.
- Do not include JavaScript unless required for a simple self-contained presentation feature; the report must remain readable without JavaScript.
- Do not reference local CSS, image, font, or script files.
- Use readable tables with units and explicit denominators.
- Make the report usable when copied or embedded into an email.
- Include a generation timestamp and source workbook/sheet identifiers.
- Do not include AI-generated content in v0.1.

### 12.2 Required Section Order

1. Report title and generation metadata.
2. User inputs and global background information.
3. Pivot fields and per-pivot background information.
4. Validation summary and warnings.
5. Dataset summary and GAIN PASS/FAIL counts.
6. Per-pivot failure rates.
7. Selected-pivot failure analysis.
8. Top-50 failure-case screenshot and equivalent accessible HTML table.
9. Five worst failure cases with all-pivot context.
10. Five closest-to-failure pass cases.
11. Overall pairwise degradation/improvement analysis.
12. Maximum degradation and improvement cases.
13. Degradation-led failure candidates.
14. Model-bypass statement.

### 12.3 Top-50 Screenshot

- Render the sorted `top_failure_cases` dataset as a legible table image.
- Include no more than 50 rows, excluding the header.
- Include the selected pivot name and selected `wcMargin` prominently.
- Include sufficient signal-path fields to identify each case.
- Embed the image in the HTML as a data URI so the report has no local image dependency.
- Also include the same data as an HTML table for accessibility, copying, and exact-value inspection.
- If there are no rankable failure cases for the selected pivot, render an explicit empty-state message instead of a blank image.

### 12.4 Fixed Narrative

Any prose summary must be template-based and derived only from computed facts. It may state counts, rates, extrema, availability, and compliance status. It must not infer root cause, quality disposition, or engineering significance beyond the defined classifications.

### 12.5 Model Stub

Represent the model stage with a deterministic local operation that:

- Records that AI was bypassed.
- Makes no network request.
- Does not alter calculated data.
- Supplies a fixed status statement to the report.

## 13. Workstreams and Detailed Tasks

### Workstream A: Project and Execution Baseline

#### A1. Establish UV-Managed Python Execution

Inputs:

- Existing repository.
- Installed `uv` command.

Tasks:

1. Define the supported Python version in the project configuration.
2. Declare only the dependencies required to read Excel workbooks, calculate summaries, generate the required table image, render HTML, and run tests.
3. Create a documented `uv` command for running the application.
4. Create documented `uv` commands for focused and full tests.
5. Ensure no global Python installation or manually activated virtual environment is required.

Deliverables:

- UV project metadata and lock file.
- Runnable application entry point.
- Test command documentation.

Acceptance criteria:

- A clean checkout can install/synchronize dependencies with `uv`.
- The CLI starts through the documented `uv` command.
- Tests run through `uv`.

Completion criteria:

- Commands are verified on the repository's supported platform.
- Dependency versions are reproducible.

Dependencies: None.

#### A2. Define Shared Data Contracts

Inputs:

- Sections 5, 7, 8, and 11 of this plan.

Tasks:

1. Define explicit structures for settings, sheet schema, pivot schema, parsed case, validation finding, pairwise comparison, and complete analysis result.
2. Keep original worksheet row numbers and source values available for traceability.
3. Distinguish missing values from numeric zero.
4. Represent unavailable rates and extrema explicitly instead of using zero.

Deliverables:

- Typed or otherwise clearly validated internal data contracts.

Acceptance criteria:

- Every required report value has one defined source in the analysis result.
- Missing and unavailable states cannot be confused with pass or zero.

Completion criteria:

- Unit tests construct and validate representative contracts.

Dependencies: A1.

### Workstream B: Settings and CLI Orchestration

#### B1. Generate and Load Settings

Tasks:

1. Generate the exact JSON fields from Section 7.1.
2. Protect an existing settings file from silent overwrite.
3. Parse JSON with actionable syntax errors.
4. Validate every field before opening the workbook where possible.

Acceptance criteria:

- Fresh run produces valid default JSON.
- Valid edited settings load successfully.
- Missing, mistyped, or unsupported fields produce field-specific errors.
- `bypass_model: false` cannot call an external service.

Completion criteria:

- Automated tests cover valid defaults and each invalid field category.

Dependencies: A2.

#### B2. Implement Interactive Prompts

Tasks:

1. Pause after creating or locating settings.
2. Collect per-pivot background in discovered order.
3. Implement strict yes/no handling for negative-GAIN continuation.
4. Handle EOF and keyboard interruption safely.

Acceptance criteria:

- Invalid responses are rejected with a clear retry prompt.
- Negative-GAIN processing continues only after explicit approval.
- Abort paths do not create a misleading completed report.

Completion criteria:

- CLI interaction tests cover proceed, reject, EOF, and interruption paths.

Dependencies: B1, C2.

### Workstream C: Workbook Schema Discovery and Parsing

#### C1. Open Workbook Safely

Tasks:

1. Validate file extension and existence.
2. Open `.xlsx` and `.xlsm` without executing macros.
3. Select the named sheet or report available names.
4. Ensure resources are closed on success and error.

Acceptance criteria:

- Reference workbook opens and `Combined` is selectable.
- Unsupported, corrupt, and missing files fail clearly.
- Source file timestamp and contents remain unchanged.

Completion criteria:

- Tests cover both supported extensions and principal error paths.

Dependencies: A1, B1.

#### C2. Discover and Validate Sheet Schema

Tasks:

1. Read semantic header rows 2, 3, and 4.
2. Map required fixed headers.
3. Discover merged pivot groups.
4. Map required and optional pivot statistics.
5. Isolate optional trailing calculation columns.
6. Validate selected pivot presence.
7. Return ordered schema metadata and validation findings.

Acceptance criteria:

- The reference resolves three pivots in this order: `GF-PROTO`, `GF-QMOM`, `SEC-DR5`.
- Each reference pivot maps to `MIN`, `MAX`, `NN_25C AVG`, `wcMargin`, and optional `wcValue`.
- Physical row-4 names such as `Column1` are never reported as statistic names.
- Missing or duplicate required structure blocks processing.

Completion criteria:

- Tests include merged headers, unmerged equivalent headers, missing statistics, duplicate headers, and trailing unknown columns.

Dependencies: C1, A2.

#### C3. Parse Data Rows

Tasks:

1. Iterate from row 5 through the used data region.
2. Create case records using schema mappings.
3. Preserve optional context and original row number.
4. Normalize supported text fields.
5. Record data-type and missing-value findings.

Acceptance criteria:

- Reference row counts and GAIN counts can be reproduced without hard-coded totals.
- Blank pivot groups remain missing rather than becoming zero.
- Numeric zero remains numeric zero.

Completion criteria:

- Tests cover complete rows, partially populated pivot rows, formula-cached values, blanks, and invalid numeric text.

Dependencies: C2.

### Workstream D: Preliminary Checks

#### D1. Implement Negative-GAIN Detection

Tasks:

1. Find GAIN rows before final requested-test processing.
2. Inspect every available pivot `MIN`.
3. Build a context-rich finding table.
4. Integrate with the confirmation flow.

Acceptance criteria:

- Every numeric negative `MIN` is reported once with pivot and row.
- Blank and non-GAIN values do not trigger false findings.
- A rejection stops the run.

Completion criteria:

- Tests cover no findings, one finding, multiple pivots, proceed, and abort.

Dependencies: C3, B2.

#### D2. Validate Compliance Content

Tasks:

1. Validate `Result?` values.
2. Validate inputs required for selected-pivot rankings.
3. Validate inputs required for pairwise deltas.
4. Compare source result with available margin signs.
5. Aggregate exclusions and warnings by reason.

Acceptance criteria:

- Invalid rows never enter calculations that require their invalid values.
- Missing comparison pivots reduce only the affected comparison denominator.
- The run blocks when required selected-pivot analysis is impossible.

Completion criteria:

- Validation matrix is covered by automated tests.

Dependencies: C3.

### Workstream E: Analytics

#### E1. Filter GAIN Cases and Produce Dataset Summary

Tasks:

1. Select exact GAIN test rows.
2. Count total, PASS, FAIL, and invalid-result rows.
3. Preserve all case context.

Acceptance criteria:

- `IP3IB-GAIN` and all non-GAIN tests are excluded.
- The supplied reference produces 4,256 GAIN rows, 4,160 PASS, and 96 FAIL.

Completion criteria:

- Counts are covered by reference integration testing and small unit fixtures.

Dependencies: D2.

#### E2. Calculate Per-Pivot Failure Rates

Tasks:

1. Count numeric margins per pivot.
2. Count negative margins per pivot.
3. Calculate rates and unavailable counts.

Acceptance criteria:

- Denominators include only numeric margins for that pivot.
- Reference missing-pivot rows do not count as passes.
- Each rate includes numerator and denominator.

Completion criteria:

- Tests cover complete, missing, all-pass, all-fail, and zero-denominator pivots.

Dependencies: E1.

#### E3. Analyze Failure Cases

Tasks:

1. Build source FAIL dataset.
2. Rank selected-pivot failures by ascending margin.
3. Retain top 50 and worst five.
4. Add all-pivot margins and pairwise deltas to the worst five.
5. Track unrankable source FAIL rows.

Acceptance criteria:

- Ordering is deterministic.
- The top five are the first five of the top 50 when at least five exist.
- No source FAIL row with missing selected margin is silently presented as a pass.

Completion criteria:

- Tests cover more than 50, fewer than 50, ties, missing selected margins, and mixed comparison availability.

Dependencies: E1, E4.

#### E4. Calculate Pairwise Deltas and Classifications

Tasks:

1. Compare selected pivot with each other pivot.
2. Calculate signed GAIN deltas.
3. Apply inclusive neutral threshold boundaries.
4. Preserve unavailable comparisons.

Acceptance criteria:

- For threshold `0.2`, deltas `-0.2`, `0`, and `0.2` are neutral.
- A delta below `-0.2` is degradation.
- A delta above `0.2` is improvement.
- Missing values do not create artificial deltas.

Completion criteria:

- Boundary, sign, missing-value, and multiple-pivot tests pass.

Dependencies: E1.

#### E5. Analyze Closest Pass Cases

Tasks:

1. Select source PASS rows with selected margin greater than zero.
2. Rank by ascending selected margin.
3. Retain five.
4. Attach pairwise delta classifications and all relevant margins.
5. Count zero-margin boundary cases separately.

Acceptance criteria:

- Exactly the five smallest positive margins are retained when available.
- Positive-margin degradation remains visible.
- Zero margins are not mixed into the smallest-positive list.

Completion criteria:

- Tests cover ties, zero margin, fewer than five, and degradation with acceptable positive margin.

Dependencies: E4.

#### E6. Calculate Overall Comparisons and Extrema

Tasks:

1. Aggregate degradation, improvement, neutral, and unavailable counts per comparison pivot.
2. Calculate per-comparison rates.
3. Retain maximum degradation and improvement cases.
4. Evaluate aggregate and case-level degradation-led failure evidence.

Acceptance criteria:

- Every rate uses its pairwise comparable denominator.
- Extrema include full case context.
- No qualifying extrema are represented as unavailable, not zero.
- Candidate failures meet every criterion in Section 5.10.

Completion criteria:

- Tests cover mixed classifications, no comparable rows, no qualifying extrema, and candidate/noncandidate failures.

Dependencies: E2, E4.

### Workstream F: Report Generation

#### F1. Implement Deterministic Model Bypass

Tasks:

1. Add the explicit no-AI stage.
2. Return a fixed bypass status.
3. Ensure no provider credentials or network access are required.

Acceptance criteria:

- The stage is visible in execution and report output.
- Repeated runs return identical model-stage content.

Completion criteria:

- A test verifies that no external client is invoked.

Dependencies: B1.

#### F2. Generate Top-50 Table Image

Tasks:

1. Select display columns that satisfy Section 12.3.
2. Render a deterministic, legible image.
3. Encode it for inline HTML embedding.
4. Handle zero rows and fewer than 50 rows.

Acceptance criteria:

- Image order exactly matches `top_failure_cases`.
- Values are not truncated in a way that prevents case identification.
- HTML contains no filesystem image path.

Completion criteria:

- Image generation tests cover 0, 1, 50, and more than 50 source rows.

Dependencies: E3.

#### F3. Render Fixed HTML Report

Tasks:

1. Render sections in the exact required order.
2. Include all analysis outputs and warnings.
3. Embed CSS and image data.
4. Escape user/workbook strings.
5. Use fixed factual narrative templates.
6. Write the final HTML atomically so a failed render does not leave a partial report presented as complete.

Acceptance criteria:

- Report opens in a standard browser.
- Required sections and top-50 table are present.
- No external asset path or network dependency exists.
- Special characters in input cannot inject HTML.
- Empty analytical categories show explicit empty states.

Completion criteria:

- Snapshot or structural HTML tests pass.
- Manual inspection confirms readability and email-embedding suitability.

Dependencies: E2, E3, E5, E6, F1, F2.

### Workstream G: End-to-End Verification and Documentation

#### G1. Add Focused Automated Tests

Required test groups:

- Settings defaults and validation.
- Header and merged-pivot discovery.
- Required/optional column handling.
- Missing pivot values.
- Negative-GAIN prompt behavior.
- GAIN-only filtering.
- Failure-rate denominators.
- Delta signs and threshold boundaries.
- Failure and pass ranking.
- Degradation-led failure candidates.
- HTML escaping and section presence.
- Model bypass.

Acceptance criteria:

- Each business rule has at least one direct test.
- Tests use small synthetic workbooks for isolated behavior.

Completion criteria:

- Focused test suite passes through `uv`.

Dependencies: Relevant implementation workstreams.

#### G2. Validate Against `REFERENCE.xlsm`

Tasks:

1. Run the complete application against `Combined`.
2. Select each reference pivot in separate runs where practical.
3. Verify discovered schema and GAIN counts.
4. Verify missing pivot values do not become zero comparisons.
5. Inspect rankings, rates, extrema, warnings, screenshot, and HTML layout.
6. Confirm the source workbook is unchanged.

Acceptance criteria:

- Three reference pivots are discovered correctly.
- GAIN count is 4,256, with 4,160 PASS and 96 FAIL.
- The known 896 GAIN rows missing `GF-PROTO` and `GF-QMOM` are treated as unavailable for those comparisons.
- Report generation completes for a pivot having sufficient selected-pivot data.
- Report is deterministic for identical inputs and prompt answers, except for explicitly variable metadata such as generation time.

Completion criteria:

- Results and any warnings are recorded in implementation test evidence.
- No unresolved discrepancy affects required output.

Dependencies: B2, C3, D1, D2, E6, F3.

#### G3. Document Operation and Limitations

Tasks:

1. Document dependency setup and execution with `uv`.
2. Document the settings fields and defaults.
3. Document the expected worksheet header rows.
4. Document the negative-GAIN decision.
5. Document report output location and interpretation.
6. State v0.1 exclusions and missing-data behavior.

Acceptance criteria:

- A user can run the application without reading source code.
- Documentation does not imply support for AI, UI, Gain-DNL, or non-GAIN tests.

Completion criteria:

- Commands are verified and match the implemented entry point.

Dependencies: G2.

## 14. Phase Plan and Milestones

### Phase 1: Foundation and Contracts

Tasks: A1, A2, B1.

Milestone M1 deliverables:

- Reproducible UV environment.
- CLI entry point.
- Settings template and validation.
- Shared internal data contracts.

Exit criteria:

- Settings workflow runs and unit tests pass.

### Phase 2: Workbook Ingestion and Verification

Tasks: C1, C2, C3, D1, D2, B2.

Milestone M2 deliverables:

- Safe workbook loader.
- Dynamic schema discovery.
- Parsed GAIN case data.
- Preliminary validation and interactive decisions.

Exit criteria:

- The reference `Combined` schema is discovered correctly.
- Missing-pivot rows are represented correctly.
- Negative-GAIN proceed/abort flow is tested.

### Phase 3: Deterministic Analytics

Tasks: E1 through E6.

Milestone M3 deliverables:

- Dataset summary.
- Per-pivot failure rates.
- Top 50 and worst five failure cases.
- Closest five pass cases.
- Pairwise delta rates and extrema.
- Degradation-led failure candidates.

Exit criteria:

- All calculation and boundary tests pass.
- Reference GAIN counts match verified values.

### Phase 4: Report and Model Bypass

Tasks: F1, F2, F3.

Milestone M4 deliverables:

- Deterministic bypass stage.
- Embedded top-50 screenshot.
- Fixed self-contained HTML report.

Exit criteria:

- Required report sections render correctly.
- Report contains no external dependencies.

### Phase 5: End-to-End Qualification

Tasks: G1, G2, G3.

Milestone M5 deliverables:

- Passing automated suite.
- Reference-workbook validation evidence.
- Operating documentation.

Exit criteria:

- All v0.1 acceptance criteria in Section 19 are satisfied.

## 15. Dependency Summary

| Task | Depends on |
|---|---|
| A1 | None |
| A2 | A1 |
| B1 | A2 |
| B2 | B1, C2, D1 |
| C1 | A1, B1 |
| C2 | C1, A2 |
| C3 | C2 |
| D1 | C3, B2 interaction support |
| D2 | C3 |
| E1 | D2 |
| E2 | E1 |
| E3 | E1, E4 |
| E4 | E1 |
| E5 | E4 |
| E6 | E2, E4 |
| F1 | B1 |
| F2 | E3 |
| F3 | E2, E3, E5, E6, F1, F2 |
| G1 | Each implemented component |
| G2 | Complete integrated workflow |
| G3 | G2 |

Implementation sequencing note: implement the generic prompt and strict yes/no mechanism in B2 first, then connect D1's negative-GAIN finding table to that mechanism.

## 16. Error Handling and Observability

### 16.1 User-Facing Errors

Every fatal error must state:

- What failed.
- Which file, sheet, setting, header, pivot, statistic, or worksheet row is involved.
- What the user can change to continue.

Do not expose a raw stack trace as the only error. A diagnostic stack trace may be available separately for development.

### 16.2 Processing Summary

At successful completion, print:

- Source workbook and sheet.
- Selected pivot.
- GAIN row count.
- PASS and FAIL counts.
- Number of warnings.
- Report location.
- Confirmation that AI was bypassed.

### 16.3 Determinism

Given the same workbook contents, settings, and prompt responses:

- Case ordering must be identical.
- Counts, rates, deltas, and extrema must be identical.
- HTML structure and content must be identical except for explicitly variable metadata.
- Floating-point output must use consistent rounding while internal classification uses unrounded numeric values.

## 17. Risks and Edge Cases

| Risk or edge case | Required handling |
|---|---|
| Pivot labels are merged in row 2 | Expand merged label across its statistic group |
| Workbook uses generic row-4 pivot headers | Use rows 2 and 3 for semantic mapping |
| A pivot is absent on some rows | Mark unavailable; exclude only affected calculations |
| Spreadsheet delta treats blank as zero | Ignore source delta and calculate only from two numeric averages |
| Selected pivot has insufficient data | Block if required ranking/comparison cannot be produced |
| Duplicate required header/statistic | Block structural validation |
| Extra columns or statistics appear | Preserve when useful, warn, and do not reinterpret them |
| GAIN `MIN` is negative | Display context and require explicit decision |
| `Result?` disagrees with margins | Warn and preserve both source and derived pivot status |
| Threshold boundary equality | Classify as neutral |
| Threshold is negative, NaN, or infinite | Reject settings |
| PASS margin is exactly zero | Count separately; exclude from smallest-positive five |
| More than 50 failure cases | Include only the worst 50 in required screenshot/table |
| Fewer than requested ranked cases | Include all and state the available count |
| Formula has no cached value | Mark unavailable; block only if required output becomes impossible |
| `.xlsm` contains VBA | Never execute it and never save the workbook |
| User text contains HTML | Escape before rendering |
| Very long context values | Wrap in tables; do not silently truncate source identity fields |
| Report image becomes excessively wide | Use a deliberate subset/order of identifying fields while keeping the full HTML table |
| Existing settings file | Do not silently overwrite |
| User aborts or interrupts | Exit cleanly without claiming report completion |

## 18. Nonblocking Open Questions and Defaults

The source documents do not specify the following presentation and persistence details. They do not block v0.1 because the defaults below preserve the required behavior. Do not expand them into new features without approval.

| Open question | v0.1 default |
|---|---|
| Should per-pivot background responses be written back into `settings.json`? | Keep them in the run's analysis result and HTML report; do not rewrite settings automatically. |
| What exact output filename and directory should be used? | Choose one deterministic local default, document it, print the resolved location, and avoid overwriting an existing report without an explicit policy. Do not add an output-management UI. |
| What percentage precision should be displayed? | Use one consistent precision across the report, retain full precision for classification, and always show numerator and denominator. |
| Which email client is the target for embedding? | Produce standards-based self-contained HTML with inline CSS and embedded image data; do not optimize for an unspecified proprietary client. |
| Should unknown optional columns appear in the report? | List them in schema diagnostics, but do not add them to business calculations or primary tables unless they are one of the named optional context fields. |
| Should a source `Result?`/margin mismatch require confirmation? | Warn and continue when required outputs remain calculable; stop only when the mismatch or missing data makes required analysis impossible. |

## 19. Overall v0.1 Acceptance Criteria

The release is accepted only when all of the following are true:

1. The application runs in a reproducible UV-managed Python environment.
2. It creates and validates the required JSON settings.
3. It accepts `.xlsx` and `.xlsm` paths and a worksheet name.
4. It discovers required fixed headers and pivot groups from rows 2 through 4.
5. It rejects missing required columns or statistics with actionable errors.
6. It validates the selected pivot field.
7. It requests background information for every pivot field.
8. It checks every GAIN pivot `MIN` for negative values and requires a decision when found.
9. It processes GAIN only and excludes similarly named tests.
10. It calculates per-pivot failure rates with correct missing-data denominators.
11. It calculates selected-pivot deltas against every other pivot using `NN_25C AVG`.
12. It applies the GAIN variation threshold with inclusive neutral boundaries.
13. It retains the top 50 and worst five rankable source FAIL cases.
14. It retains the five smallest-positive-margin source PASS cases.
15. It calculates per-comparison degradation, improvement, and neutral rates.
16. It identifies maximum degradation and improvement with case context.
17. It identifies degradation-led failure candidates without claiming causation.
18. It handles missing pivot values without converting them to zero.
19. It includes all required user inputs, analysis, warnings, tables, and graphics in fixed-order HTML.
20. It embeds the top-50 screenshot and all styling directly in the report.
21. It bypasses AI deterministically and makes no model-provider request.
22. It does not modify the source workbook or execute macros.
23. Automated tests pass through `uv`.
24. An end-to-end run against `REFERENCE.xlsm` and `Combined` reproduces the verified GAIN row and result counts.

## 20. Definition of Done

Version 0.1 is done when:

- All workstream completion criteria are met.
- All overall acceptance criteria pass.
- The reference workbook has been used for end-to-end validation.
- No unresolved blocker changes a business requirement or calculation rule.
- Known warnings and limitations are documented.
- The generated HTML is complete, readable, self-contained, and suitable for the intended deterministic proof-of-concept review.
- A smaller implementation agent can trace every output metric to a defined input, calculation, and acceptance test in this document.
