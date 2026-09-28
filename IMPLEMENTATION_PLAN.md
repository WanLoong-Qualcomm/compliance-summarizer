# v0.1 Implementation Plan

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
     extrema, average degradation on main failures, and the top 20 failures.
4. **Report and CLI**
   - Render escaped, inline-styled HTML and an inline SVG failure-rate graphic.
   - Display configuration, warnings, denominators, statistics, and source
     fields for the top failures.
   - Expose initialization and report generation through one CLI.
5. **Qualification**
   - Test schema errors, invalid settings, coverage gaps, malformed values,
     tolerance boundaries, ties, empty results, HTML escaping, and end-to-end
     CLI behavior.
   - Run the complete suite through `uv run pytest`.

## Explicit v0.1 decisions for open questions

- Blank, non-numeric, and non-finite `wcMargin`/`NN_25C AVG` cells are reported
  as coverage gaps. They are not failures and do not enter affected rates.
- The top-failure table contains exactly 20 rows when at least 20 failures
  exist. Ties use identifying fields and the source row as a final display-only
  tie breaker.
- A case identity uses the available SIGPATH identifying columns. Duplicate
  identities produce a warning; the worksheet row is retained for traceability.
- Average degradation on main-pivot failures is the mean magnitude of deltas
  classified as degradation, not an average that can be cancelled by
  improvements.
- AI remains a deterministic bypass statement; no prompt or provider call is
  made.

## Definition of done

- All v0.1 acceptance criteria in `PROJECT.md` are represented in code/tests.
- `uv sync --dev` and `uv run pytest` succeed.
- A valid configured workbook produces one standalone HTML file.
- No calculation uses the source `Result?` field.
