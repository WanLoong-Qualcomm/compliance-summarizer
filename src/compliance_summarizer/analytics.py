"""Deterministic analytical dataset preparation."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite

from .contracts import (
    ParsedCase,
    PivotFailureSummary,
    SheetSchema,
    SourceResult,
)
from .validation import ContentValidationResult


class DatasetError(ValueError):
    """Raised when the requested GAIN dataset cannot be produced."""


@dataclass(frozen=True, slots=True)
class GainDatasetSummary:
    """All exact GAIN rows partitioned by source compliance result."""

    gain_cases: tuple[ParsedCase, ...]
    pass_cases: tuple[ParsedCase, ...] = field(init=False)
    fail_cases: tuple[ParsedCase, ...] = field(init=False)
    invalid_result_cases: tuple[ParsedCase, ...] = field(init=False)

    def __post_init__(self) -> None:
        gain_cases = tuple(self.gain_cases)
        if not gain_cases:
            raise DatasetError("No rows with normalized TESTNAME == 'GAIN' remain.")
        if any(not isinstance(case, ParsedCase) for case in gain_cases):
            raise TypeError("gain_cases must contain ParsedCase instances")
        if any(case.fixed_values.get("TESTNAME") != "GAIN" for case in gain_cases):
            raise ValueError("gain_cases must contain only exact normalized GAIN rows")

        pass_cases = tuple(
            case for case in gain_cases if case.source_result is SourceResult.PASS
        )
        fail_cases = tuple(
            case for case in gain_cases if case.source_result is SourceResult.FAIL
        )
        invalid_result_cases = tuple(
            case
            for case in gain_cases
            if case.source_result not in {SourceResult.PASS, SourceResult.FAIL}
        )
        object.__setattr__(self, "gain_cases", gain_cases)
        object.__setattr__(self, "pass_cases", pass_cases)
        object.__setattr__(self, "fail_cases", fail_cases)
        object.__setattr__(self, "invalid_result_cases", invalid_result_cases)

    @property
    def total_gain_rows(self) -> int:
        return len(self.gain_cases)

    @property
    def pass_count(self) -> int:
        return len(self.pass_cases)

    @property
    def fail_count(self) -> int:
        return len(self.fail_cases)

    @property
    def invalid_result_count(self) -> int:
        return len(self.invalid_result_cases)


def summarize_gain_dataset(content: ContentValidationResult) -> GainDatasetSummary:
    """Select exact GAIN rows and produce deterministic source-result counts."""

    if not isinstance(content, ContentValidationResult):
        raise TypeError("content must be ContentValidationResult")
    gain_cases = tuple(
        case
        for case in content.gain_cases
        if case.fixed_values.get("TESTNAME") == "GAIN"
    )
    return GainDatasetSummary(gain_cases=gain_cases)


def calculate_pivot_failure_rates(
    dataset: GainDatasetSummary,
    schema: SheetSchema,
) -> tuple[PivotFailureSummary, ...]:
    """Calculate independent ``wcMargin`` failure rates in schema order.

    Only GAIN rows with a valid source PASS or FAIL result contribute to the
    calculation.  A pivot's denominator contains finite numeric margins only;
    missing and nonnumeric margins are counted as unavailable instead of being
    treated as passes.
    """

    if not isinstance(dataset, GainDatasetSummary):
        raise TypeError("dataset must be GainDatasetSummary")
    if not isinstance(schema, SheetSchema):
        raise TypeError("schema must be SheetSchema")

    valid_cases = dataset.pass_cases + dataset.fail_cases
    summaries: list[PivotFailureSummary] = []
    for pivot_name in schema.pivot_names:
        failure_count = 0
        numeric_margin_count = 0
        for case in valid_cases:
            margin = case.pivot_values.get(pivot_name, {}).get("wcMargin")
            if not _is_finite_number(margin):
                continue
            numeric_margin_count += 1
            if margin < 0:
                failure_count += 1

        summaries.append(
            PivotFailureSummary(
                pivot_name=pivot_name,
                failure_count=failure_count,
                numeric_margin_count=numeric_margin_count,
                unavailable_margin_count=len(valid_cases) - numeric_margin_count,
            )
        )
    return tuple(summaries)


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
    )
