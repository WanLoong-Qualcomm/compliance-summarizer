# Implementation Agent Guide

## Priority
1. Follow current user instructions.
2. Use this file for operating behavior.
3. Use `HIGH_LEVEL_PLAN.md` as the business-requirement source of truth.
4. Use `DETAILED_PLAN.md` for tasks, dependencies, calculations, and acceptance criteria.
5. Use `REFERENCE.xlsm` `Combined` only to validate terminology, structure, and representative compliance behavior.
6. Treat existing code as implementation evidence, never authority over the plans.

If the plans conflict materially, follow `HIGH_LEVEL_PLAN.md` and ask before implementing. Never modify either plan or the reference workbook unless explicitly requested.

## Progressive Context
1. Start by reading this file plus only the overview and scope sections of both plans.
2. Inspect the repository tree, project metadata, tests, and `git status`.
3. Identify one current goal from the user request or earliest dependency-ready detailed-plan task.
4. Search for that task identifier and read only its task body, criteria, and dependencies.
5. Open supporting sections only when required: parsing for ingestion, calculations for analytics, report rules for rendering, and relevant risks for tests.
6. Follow cross-references only when they affect the next decision; avoid unrelated sections and full-file reads.
7. Keep brief notes: task, files, dependencies, controlling sections, assumptions, validation, and unresolved risks.
8. Re-open authoritative sections instead of relying on uncertain memory.

## Execution
1. Verify dependencies in code and tests before editing.
2. Inspect existing patterns and preserve unrelated user changes.
3. Implement the smallest complete, reversible change satisfying the current task.
4. Work on one coherent task at a time; do not begin speculative downstream work.
5. Fix defects at their originating layer and update directly affected consumers only.
6. Use `uv` for Python execution, dependencies, tests, formatting, and analysis.
7. Open workbooks read-only; never execute macros, save the source, or hard-code reference-specific pivots, positions, or counts.

## Requirement Control
- Do not add features, inputs, tests, output modes, or abstractions unsupported by the plans.
- Preserve exact compliance terminology and keep source `Result?` separate from derived pivot status.
- Preserve missing values separately from zero; calculate only with valid operands and denominators.
- Preserve worksheet row numbers and required signal-path context for traceability.
- Classify with unrounded values and round only for presentation.
- Report unavailable calculations and excluded rows; never silently discard them.

## Escalation
Stop and ask one concise question when sources conflict, two plausible interpretations change compliance results, a required rule or dependency is missing, scope would expand, user changes cannot be preserved, or required analysis is impossible. State the exact issue, affected task, supported alternatives, and smallest decision needed.

## Validation
1. Add focused tests for changed behavior, including applicable sign, boundary, missing, zero, tie, denominator, and empty cases.
2. Run focused tests first, then component and dependent tests, then the full suite at milestone completion.
3. Use small synthetic workbooks for unit tests and `REFERENCE.xlsm` for integration validation.
4. Verify source workbooks remain unchanged, AI is not called in v0.1, and HTML is escaped and self-contained when those areas change.
5. Do not fix unrelated failures; confirm and report them separately.

## Documentation and Done
Update documentation only for implemented setup, CLI, settings, workbook assumptions, output behavior, or limitations. Do not duplicate plan text or rewrite plans to justify implementation shortcuts.

A task is done when dependencies, acceptance criteria, completion criteria, focused tests, affected tests, documentation, traceability, and diff review all pass. A milestone additionally requires the full suite, required reference-workbook validation, and its detailed-plan exit criteria.

## Avoid
Avoid loading all plans upfront, implementing from memory, hard-coding the reference schema, converting blanks to zero, mixing source and derived compliance states, placing business logic in templates, silent exclusions, unrelated cleanup, overengineering, and declaring completion before validation.
