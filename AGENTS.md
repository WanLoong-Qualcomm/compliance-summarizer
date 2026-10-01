# Agent Guidelines

## Before changing code

- Read the relevant documentation, source modules, tests, and configuration before editing.
- Plan the smallest change that satisfies the request; state important assumptions when they affect behavior.
- Check `git status` first and preserve unrelated user changes.

## While implementing

- Keep compliance calculations deterministic. Never use the workbook's `Result?` field for pass/fail decisions.
- Preserve the separation between workbook parsing, normalized models, statistics, grouping, and report rendering.
- Treat missing, malformed, and non-finite workbook values as explicit coverage gaps unless the contract says otherwise.
- Use existing project patterns and focused changes. Avoid adding dependencies or abstractions without a clear need.
- Use `apply_patch` for file edits. Do not use destructive Git or filesystem commands.

## Documentation and tests

- Update documentation whenever behavior, configuration, scope, or user-facing output changes.
- Add or update tests with every behavioral change, including edge cases and validation failures.
- Run the relevant focused tests during development and the full suite before handoff:

  ```powershell
  uv run pytest
  ```

- Also run `git diff --check` and inspect the final diff for accidental changes.

## Handoff

- Report what changed, what was verified, and any remaining limitations or assumptions.
- Do not claim a feature is implemented unless the code, tests, and documentation agree.
