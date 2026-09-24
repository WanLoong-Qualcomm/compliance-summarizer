"""Content validation and calculation eligibility for parsed compliance rows."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Mapping

from .contracts import (
    FindingSeverity,
    NegativeGainDecision,
    ParsedCase,
    SheetSchema,
    SourceResult,
    ValidationFinding,
)
from .prompts import InputFunction, OutputFunction, prompt_negative_gain_decision
from .rows import RowParsingResult


@dataclass(frozen=True, slots=True)
class NegativeGainFinding:
    """One numeric negative GAIN ``MIN`` with traceable context."""

    worksheet_row_number: int
    pivot_name: str
    minimum: float
    context: Mapping[str, object]

    def __post_init__(self) -> None:
        if type(self.worksheet_row_number) is not int or self.worksheet_row_number < 5:
            raise ValueError("worksheet_row_number must be a data row number")
        if not self.pivot_name.strip():
            raise ValueError("pivot_name must be nonempty")
        if not _is_finite_number(self.minimum) or self.minimum >= 0:
            raise ValueError("minimum must be a finite negative number")
        context = dict(self.context)
        if any(not isinstance(name, str) or not name for name in context):
            raise TypeError("context keys must be nonempty strings")
        object.__setattr__(self, "context", context)

    @property
    def validation_finding(self) -> ValidationFinding:
        """Return the shared warning representation used by the report contract."""

        return ValidationFinding(
            code="negative_gain_min",
            message=(
                f"GAIN row has numeric negative MIN {self.minimum} for pivot "
                f"'{self.pivot_name}'."
            ),
            severity=FindingSeverity.WARNING,
            blocking=False,
            worksheet_row_number=self.worksheet_row_number,
            field_name="MIN",
            pivot_name=self.pivot_name,
            count=1,
            sample_rows=(self.worksheet_row_number,),
        )


@dataclass(frozen=True, slots=True)
class NegativeGainCheckResult:
    """Negative-GAIN findings and the user's continuation decision."""

    findings: tuple[NegativeGainFinding, ...]
    decision: NegativeGainDecision
    validation_findings: tuple[ValidationFinding, ...] = ()

    def __post_init__(self) -> None:
        findings = tuple(self.findings)
        if any(not isinstance(finding, NegativeGainFinding) for finding in findings):
            raise TypeError("findings must contain NegativeGainFinding instances")
        validation_findings = tuple(self.validation_findings)
        if any(
            not isinstance(finding, ValidationFinding)
            for finding in validation_findings
        ):
            raise TypeError("validation_findings must contain ValidationFinding instances")
        expected = tuple(finding.validation_finding for finding in findings)
        if validation_findings != expected:
            raise ValueError("validation_findings must match findings")
        if type(self.decision) is not NegativeGainDecision:
            raise TypeError("decision must be NegativeGainDecision")
        if not findings and self.decision is not NegativeGainDecision.NOT_REQUIRED:
            raise ValueError("no findings require a NOT_REQUIRED decision")
        if findings and self.decision is NegativeGainDecision.NOT_REQUIRED:
            raise ValueError("findings require an explicit continuation decision")
        object.__setattr__(self, "findings", findings)
        object.__setattr__(self, "validation_findings", validation_findings)

    @property
    def should_continue(self) -> bool:
        """Whether the caller may continue to analytics and report generation."""

        return self.decision in {
            NegativeGainDecision.NOT_REQUIRED,
            NegativeGainDecision.PROCEED,
        }


@dataclass(frozen=True, slots=True)
class ContentValidationResult:
    """Eligibility sets, exclusions, warnings, and blocking findings."""

    selected_pivot: str
    gain_cases: tuple[ParsedCase, ...]
    valid_gain_cases: tuple[ParsedCase, ...]
    selected_ranking_cases: tuple[ParsedCase, ...]
    pairwise_cases: Mapping[str, tuple[ParsedCase, ...]]
    findings: tuple[ValidationFinding, ...]
    exclusion_counts: Mapping[str, int]

    def __post_init__(self) -> None:
        if not isinstance(self.selected_pivot, str) or not self.selected_pivot.strip():
            raise ValueError("selected_pivot must be a nonempty string")
        for name in (
            "gain_cases",
            "valid_gain_cases",
            "selected_ranking_cases",
        ):
            cases = tuple(getattr(self, name))
            if any(not isinstance(case, ParsedCase) for case in cases):
                raise TypeError(f"{name} must contain ParsedCase instances")
            object.__setattr__(self, name, cases)

        pairwise = {
            pivot: tuple(cases) for pivot, cases in self.pairwise_cases.items()
        }
        if any(not isinstance(pivot, str) for pivot in pairwise):
            raise TypeError("pairwise_cases keys must be strings")
        if any(
            not isinstance(case, ParsedCase)
            for cases in pairwise.values()
            for case in cases
        ):
            raise TypeError("pairwise_cases values must contain ParsedCase instances")
        object.__setattr__(self, "pairwise_cases", pairwise)

        findings = tuple(self.findings)
        if any(not isinstance(finding, ValidationFinding) for finding in findings):
            raise TypeError("findings must contain ValidationFinding instances")
        object.__setattr__(self, "findings", findings)

        exclusions = dict(self.exclusion_counts)
        if any(
            not isinstance(reason, str) or type(count) is not int or count < 0
            for reason, count in exclusions.items()
        ):
            raise ValueError("exclusion_counts must map strings to nonnegative integers")
        object.__setattr__(self, "exclusion_counts", exclusions)

    @property
    def is_blocked(self) -> bool:
        return any(finding.blocking for finding in self.findings)

    @property
    def blocking_findings(self) -> tuple[ValidationFinding, ...]:
        return tuple(finding for finding in self.findings if finding.blocking)


def detect_negative_gain_minima(
    parsed: RowParsingResult,
    schema: SheetSchema,
) -> tuple[NegativeGainFinding, ...]:
    """Find every numeric negative pivot ``MIN`` on an exact GAIN row."""

    if not isinstance(parsed, RowParsingResult):
        raise TypeError("parsed must be RowParsingResult")
    if not isinstance(schema, SheetSchema):
        raise TypeError("schema must be SheetSchema")

    findings: list[NegativeGainFinding] = []
    context_headers = _ordered_context_headers(schema)
    for case in parsed.cases:
        if case.fixed_values.get("TESTNAME") != "GAIN":
            continue
        context = {
            header: _case_value(case, header)
            for header in context_headers
        }
        for pivot in schema.pivots:
            minimum = case.pivot_values.get(pivot.name, {}).get("MIN")
            if not _is_finite_number(minimum) or minimum >= 0:
                continue
            findings.append(
                NegativeGainFinding(
                    worksheet_row_number=case.worksheet_row_number,
                    pivot_name=pivot.name,
                    minimum=float(minimum),
                    context=context,
                )
            )
    return tuple(findings)


def format_negative_gain_findings(
    findings: tuple[NegativeGainFinding, ...],
) -> tuple[str, ...]:
    """Format negative-GAIN findings as deterministic CLI table lines."""

    findings = tuple(findings)
    if any(not isinstance(finding, NegativeGainFinding) for finding in findings):
        raise TypeError("findings must contain NegativeGainFinding instances")
    if not findings:
        return ("Negative-GAIN check passed: no numeric negative MIN values found.",)

    context_headers = tuple(findings[0].context)
    header = ("Worksheet row", "Pivot field", "MIN", *context_headers)
    lines = [" | ".join(header)]
    for finding in findings:
        values = (
            str(finding.worksheet_row_number),
            finding.pivot_name,
            str(finding.minimum),
            *("N/A" if value is None else str(value) for value in finding.context.values()),
        )
        lines.append(" | ".join(values))
    return tuple(lines)


def run_negative_gain_check(
    parsed: RowParsingResult,
    schema: SheetSchema,
    *,
    input_fn: InputFunction | None = None,
    output_fn: OutputFunction | None = None,
) -> NegativeGainCheckResult:
    """Detect negative GAIN minima, display them, and request confirmation."""

    findings = detect_negative_gain_minima(parsed, schema)
    for line in format_negative_gain_findings(findings):
        _write_output(output_fn, line)

    if not findings:
        decision = NegativeGainDecision.NOT_REQUIRED
    else:
        decision = prompt_negative_gain_decision(
            input_fn=input_fn,
            output_fn=output_fn,
        )
        if decision is NegativeGainDecision.ABORT:
            _write_output(
                output_fn,
                "Negative-GAIN check rejected; analytics and report generation must stop.",
            )
    return NegativeGainCheckResult(
        findings=findings,
        decision=decision,
        validation_findings=tuple(finding.validation_finding for finding in findings),
    )


@dataclass(slots=True)
class _FindingAccumulator:
    code: str
    message: str
    field_name: str | None = None
    pivot_name: str | None = None
    severity: FindingSeverity = FindingSeverity.WARNING
    blocking: bool = False
    count: int = 0
    first_row: int | None = None
    sample_rows: list[int] | None = None

    def add(self, row_number: int | None = None) -> None:
        self.count += 1
        if row_number is not None:
            if self.first_row is None:
                self.first_row = row_number
            if self.sample_rows is None:
                self.sample_rows = []
            if row_number not in self.sample_rows and len(self.sample_rows) < 5:
                self.sample_rows.append(row_number)

    def build(self) -> ValidationFinding:
        return ValidationFinding(
            code=self.code,
            message=self.message,
            severity=self.severity,
            blocking=self.blocking,
            worksheet_row_number=self.first_row,
            field_name=self.field_name,
            pivot_name=self.pivot_name,
            count=self.count,
            sample_rows=tuple(self.sample_rows or ()),
        )


def validate_compliance_content(
    parsed: RowParsingResult,
    schema: SheetSchema,
    selected_pivot: str,
) -> ContentValidationResult:
    """Validate GAIN rows and partition them by calculation eligibility."""

    if not isinstance(parsed, RowParsingResult):
        raise TypeError("parsed must be RowParsingResult")
    if not isinstance(schema, SheetSchema):
        raise TypeError("schema must be SheetSchema")

    if selected_pivot not in schema.pivot_names:
        raise ValueError(
            f"selected_pivot {selected_pivot!r} is not present in the discovered schema"
        )
    findings: list[ValidationFinding] = list(parsed.findings)
    accumulators: dict[tuple[str, str | None, str | None], _FindingAccumulator] = {}
    exclusions: dict[str, int] = {}
    gain_cases: list[ParsedCase] = []
    valid_gain_cases: list[ParsedCase] = []
    selected_ranking_cases: list[ParsedCase] = []
    pairwise_cases: dict[str, list[ParsedCase]] = {
        pivot: [] for pivot in schema.pivot_names if pivot != selected_pivot
    }

    for case in parsed.cases:
        if case.fixed_values.get("TESTNAME") != "GAIN":
            continue
        gain_cases.append(case)

        if case.source_result is None:
            reason = (
                "missing_result"
                if _is_blank(case.source_values.get("Result?"))
                else "invalid_result"
            )
            _exclude(exclusions, reason)
            _add(
                accumulators,
                code="invalid_gain_result",
                message="GAIN row has no valid PASS or FAIL source Result? value.",
                row_number=case.worksheet_row_number,
                field_name="Result?",
            )
            continue

        valid_gain_cases.append(case)
        _validate_compliance_limits(case, accumulators)
        _validate_result_margin_consistency(case, schema, accumulators)

        selected_values = case.pivot_values.get(selected_pivot, {})
        selected_margin = selected_values.get("wcMargin")
        if _is_finite_number(selected_margin):
            selected_ranking_cases.append(case)
        else:
            reason = (
                "selected_margin_missing"
                if _is_blank(selected_margin)
                else "selected_margin_nonnumeric"
            )
            _exclude(exclusions, reason)
            _add(
                accumulators,
                code="selected_margin_unavailable",
                message=f"GAIN row cannot enter selected-pivot ranking because "
                f"'{selected_pivot}.wcMargin' is unavailable.",
                row_number=case.worksheet_row_number,
                field_name="wcMargin",
                pivot_name=selected_pivot,
            )

        selected_average = selected_values.get("NN_25C AVG")
        for comparison_pivot in pairwise_cases:
            comparison_values = case.pivot_values.get(comparison_pivot, {})
            comparison_average = comparison_values.get("NN_25C AVG")
            if _is_finite_number(selected_average) and _is_finite_number(
                comparison_average
            ):
                pairwise_cases[comparison_pivot].append(case)
            elif not _is_finite_number(comparison_average):
                reason = f"comparison_average_unavailable[{comparison_pivot}]"
                _exclude(exclusions, reason)
                _add(
                    accumulators,
                    code="comparison_average_unavailable",
                    message=f"GAIN row is excluded only from the '{comparison_pivot}' "
                    "comparison because its NN_25C AVG is unavailable.",
                    row_number=case.worksheet_row_number,
                    field_name="NN_25C AVG",
                    pivot_name=comparison_pivot,
                )

        if not _is_finite_number(selected_average):
            _exclude(exclusions, "selected_average_unavailable")
            _add(
                accumulators,
                code="selected_average_unavailable",
                message=f"GAIN row cannot enter pairwise comparisons because "
                f"'{selected_pivot}.NN_25C AVG' is unavailable.",
                row_number=case.worksheet_row_number,
                field_name="NN_25C AVG",
                pivot_name=selected_pivot,
            )

    if not gain_cases:
        _add_blocking(
            accumulators,
            code="no_gain_rows",
            message="No rows with normalized TESTNAME == 'GAIN' were found.",
        )
    if gain_cases and not valid_gain_cases:
        _add_blocking(
            accumulators,
            code="no_valid_gain_results",
            message="No GAIN row has a valid source Result? value for analysis.",
        )
    if valid_gain_cases and not selected_ranking_cases:
        _add_blocking(
            accumulators,
            code="selected_ranking_impossible",
            message=f"No valid GAIN row has a numeric '{selected_pivot}.wcMargin'; "
            "selected-pivot ranking cannot be produced.",
            field_name="wcMargin",
            pivot_name=selected_pivot,
        )
    if valid_gain_cases and not any(
        _is_finite_number(case.pivot_values.get(selected_pivot, {}).get("NN_25C AVG"))
        for case in valid_gain_cases
    ):
        _add_blocking(
            accumulators,
            code="selected_comparison_impossible",
            message=f"No valid GAIN row has a numeric '{selected_pivot}.NN_25C AVG'; "
            "pairwise comparison analysis cannot be produced.",
            field_name="NN_25C AVG",
            pivot_name=selected_pivot,
        )

    findings.extend(accumulator.build() for accumulator in accumulators.values())
    return ContentValidationResult(
        selected_pivot=selected_pivot,
        gain_cases=tuple(gain_cases),
        valid_gain_cases=tuple(valid_gain_cases),
        selected_ranking_cases=tuple(selected_ranking_cases),
        pairwise_cases={pivot: tuple(cases) for pivot, cases in pairwise_cases.items()},
        findings=tuple(findings),
        exclusion_counts=exclusions,
    )


def _validate_compliance_limits(
    case: ParsedCase,
    accumulators: dict[tuple[str, str | None, str | None], _FindingAccumulator],
) -> None:
    for field_name in ("LL", "UL"):
        value = case.fixed_values.get(field_name)
        if _is_blank(value):
            _add(
                accumulators,
                code="missing_compliance_limit",
                message=f"GAIN row has blank {field_name}; compliance context is incomplete.",
                row_number=case.worksheet_row_number,
                field_name=field_name,
            )
        elif not _is_finite_number(value):
            _add(
                accumulators,
                code="invalid_compliance_limit",
                message=f"GAIN row has nonnumeric {field_name}; compliance context is invalid.",
                row_number=case.worksheet_row_number,
                field_name=field_name,
            )


def _validate_result_margin_consistency(
    case: ParsedCase,
    schema: SheetSchema,
    accumulators: dict[tuple[str, str | None, str | None], _FindingAccumulator],
) -> None:
    statuses = [
        _margin_status(case, pivot_name)
        for pivot_name in schema.pivot_names
    ]
    numeric_statuses = [status for status in statuses if status is not None]
    if not numeric_statuses:
        return
    has_failure = any(status < 0 for status in numeric_statuses)
    mismatch = (
        case.source_result is SourceResult.PASS and has_failure
    ) or (
        case.source_result is SourceResult.FAIL and not has_failure
    )
    if mismatch:
        _add(
            accumulators,
            code="result_margin_mismatch",
            message="Source Result? disagrees with the signs of available pivot wcMargin values; "
            "both source and derived values are preserved.",
            row_number=case.worksheet_row_number,
            field_name="Result?",
        )


def _margin_status(case: ParsedCase, pivot_name: str) -> float | None:
    margin = case.pivot_values.get(pivot_name, {}).get("wcMargin")
    return float(margin) if _is_finite_number(margin) else None


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _exclude(exclusions: dict[str, int], reason: str) -> None:
    exclusions[reason] = exclusions.get(reason, 0) + 1


def _add(
    accumulators: dict[tuple[str, str | None, str | None], _FindingAccumulator],
    *,
    code: str,
    message: str,
    row_number: int | None = None,
    field_name: str | None = None,
    pivot_name: str | None = None,
) -> None:
    key = (code, field_name, pivot_name)
    if key not in accumulators:
        accumulators[key] = _FindingAccumulator(
            code=code,
            message=message,
            field_name=field_name,
            pivot_name=pivot_name,
        )
    accumulators[key].add(row_number)


def _add_blocking(
    accumulators: dict[tuple[str, str | None, str | None], _FindingAccumulator],
    *,
    code: str,
    message: str,
    field_name: str | None = None,
    pivot_name: str | None = None,
) -> None:
    key = (code, field_name, pivot_name)
    if key not in accumulators:
        accumulators[key] = _FindingAccumulator(
            code=code,
            message=message,
            field_name=field_name,
            pivot_name=pivot_name,
            severity=FindingSeverity.ERROR,
            blocking=True,
        )
    accumulators[key].add()


def _ordered_context_headers(schema: SheetSchema) -> tuple[str, ...]:
    columns = (
        *schema.fixed_columns.items(),
        *schema.optional_columns.items(),
    )
    return tuple(name for name, _ in sorted(columns, key=lambda item: item[1]))


def _case_value(case: ParsedCase, header: str) -> object:
    if header in case.source_values:
        return case.source_values[header]
    return case.fixed_values.get(header)


def _write_output(output_fn: OutputFunction | None, message: str) -> None:
    writer = print if output_fn is None else output_fn
    writer(message)
