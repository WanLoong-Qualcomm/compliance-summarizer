# v0.1 Implementation Plan and Closeout

This plan implements the current requirements in `PROJECT.md`. It intentionally
does not carry forward behavior from older prototypes where that behavior
conflicts with the current specification.

## Outcome

Deliver a `uv`-managed Python 3.12 command-line application that reads the
configured SIGPATH compliance worksheet, calculates deterministic GAIN
statistics, and writes a self-contained HTML report. AI, aggregation, and
non-GAIN measurements remain outside v0.1.

## Workstreams

1. **Foundation and configuration**
   - Package and lock dependencies with `uv`.
   - Validate every current `settings.json` field.
   - Reject unsupported v0.1 combinations with actionable messages.
2. **Workbook contract and normalization**
   - Read `.xlsx`/`.xlsm` without saving or executing macros.
   - Discover row-2 pivot names, row-3 statistics, and row-4 fixed headers.
   - Retain raw values separately from normalized numeric values.
   - Create stable case identities from SIGPATH identifying columns.
3. **Validation and deterministic statistics**
   - Treat blank, malformed, and non-finite required pivot values as coverage
     gaps and exclude them only from affected denominators.
   - Calculate compliance exclusively from `wcMargin`.
   - Compare every pivot with the main pivot using paired `NN_25C AVG` values.
   - Produce per-pivot failure statistics, worst paths, comparison rates and
     signed extrema, main-failure degradation counts, maximum and average
     degradation on main failures, and the top 20 failures.
4. **Report and CLI**
   - Render escaped, inline-styled standalone HTML without external assets or
     charts.
   - Display configuration, coverage warnings, percentage-only rates,
     statistics, and source fields for the top failures.
   - Expose initialization and report generation through one CLI.
5. **Qualification**
   - Keep coverage gaps, malformed values, tolerance boundaries, ties, empty
     results, HTML escaping, and end-to-end CLI behavior represented in the
     existing test suite.
   - Run the suite as part of a future verification pass.

## Explicit v0.1 decisions

- Blank, non-numeric, and non-finite required pivot cells are reported as
  coverage gaps. Coverage gaps are expected unavailable data: they remain
  blank in the report, are not failures, and do not enter affected metrics.
- An unexpected calculation failure is represented by the literal `ERROR`.
  The HTML renderer displays it in bold red text instead of silently leaving a
  blank.
- Comparison rates use valid paired `NN_25C AVG` values internally, but the
  report shows percentages only. Rates with no valid pairs are blank.
- Comparison deltas are oriented by the measurement definition. Degradation is
  negative, improvement is positive, and unchanged values are within the
  inclusive acceptable variation.
- For GAIN, the raw delta is `main NN_25C AVG - comparison NN_25C AVG`.
- The top-failure table contains exactly 20 rows when at least 20 failures
  exist. Ties use identifying fields and the source row as a final display-only
  tie breaker.
- A case identity uses the available SIGPATH identifying columns. Duplicate
  identities produce a warning; the worksheet row is retained for traceability.
- Main-failure degradation statistics contain the signed maximum degradation
  and signed average degradation. They are calculated only for paired rows
  classified as degradation.
- AI remains a deterministic bypass statement; no prompt or provider call is
  made.

## v0.1 closeout

The v0.1 implementation is complete for the configured SIGPATH GAIN workflow.
A valid configured workbook produces one standalone HTML report, and the
report uses the configured pivot name throughout its headings and labels. The
Excel-style top-failure table keeps pivot names in a group row above the field
headers, includes a separate worksheet-row header cell, and leaves expected
unavailable values blank.

The existing test expectations have been aligned with the v0.1 output. The
test suite was not run during this documentation closeout; the generated
report and `git diff --check` were used for final verification.

The following remain intentionally deferred to the next revision:

- aggregation and port-group reporting;
- non-GAIN measurement definitions;
- model-backed explanations and a defined AI output contract;
- additional report formats and optional visualizations; and
- broader workbook contracts beyond the v0.1 SIGPATH layout.
