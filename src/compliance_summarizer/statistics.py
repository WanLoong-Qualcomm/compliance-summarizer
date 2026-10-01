"""Deterministic GAIN compliance and comparison calculations."""

from __future__ import annotations

from math import isfinite
from statistics import fmean

from .errors import WorkbookValidationError
from .measurements import MeasurementDefinition, get_measurement_definition
from .models import (
    ComplianceCase,
    CALCULATION_ERROR,
    ComparisonStatistics,
    FailureCaseStatistics,
    MeasurementStatistics,
    ParsedMeasurement,
    PivotMainStatistics,
    Rate,
)


def calculate_measurement_statistics(
    parsed: ParsedMeasurement,
    main_pivot: str,
    acceptable_variation: float,
    *,
    include_ranked_cases: bool = True,
) -> MeasurementStatistics:
    """Calculate deterministic statistics without consulting source ``Result?``."""

    definition = get_measurement_definition(parsed.measurement)
    if main_pivot not in parsed.schema.pivot_names:
        available = ", ".join(parsed.schema.pivot_names)
        raise WorkbookValidationError(
            f"Configured main pivot '{main_pivot}' is absent from worksheet "
            f"'{parsed.schema.name}'. Available pivots: {available}."
        )

    pivot_statistics = tuple(
        _pivot_main_statistics(parsed, pivot_name)
        for pivot_name in parsed.schema.pivot_names
    )
    selected = next(item for item in pivot_statistics if item.pivot == main_pivot)
    if selected.failure_rate.denominator == 0:
        raise WorkbookValidationError(
            f"Main pivot '{main_pivot}' has no valid wcMargin values for "
            f"{parsed.measurement}; a compliance conclusion cannot be generated."
        )

    main_failures = tuple(
        case
        for case in parsed.cases
        if _value(case, main_pivot, definition.margin_statistic) is not None
        and _value(case, main_pivot, definition.margin_statistic) < 0
    )
    main_passes = tuple(
        case
        for case in parsed.cases
        if _value(case, main_pivot, definition.margin_statistic) is not None
        and _value(case, main_pivot, definition.margin_statistic) >= 0
    )
    comparison_names = tuple(
        pivot for pivot in parsed.schema.pivot_names if pivot != main_pivot
    )
    if include_ranked_cases:
        ordered_failures = sorted(
            main_failures,
            key=lambda case: (
                _value(case, main_pivot, definition.margin_statistic),
                _identity_sort_key(case.identity),
                case.worksheet_row,
            ),
        )
        top_failure_cases = tuple(
            _case_statistics(case, main_pivot, comparison_names, definition)
            for case in ordered_failures[:20]
        )
        ordered_passes = sorted(
            main_passes,
            key=lambda case: (
                _value(case, main_pivot, definition.margin_statistic),
                _identity_sort_key(case.identity),
                case.worksheet_row,
            ),
        )
        top_pass_cases = tuple(
            _case_statistics(case, main_pivot, comparison_names, definition)
            for case in ordered_passes[:5]
        )
    else:
        top_failure_cases = ()
        top_pass_cases = ()
    comparisons = tuple(
        _comparison_statistics(
            parsed,
            main_pivot,
            comparison_pivot,
            acceptable_variation,
            definition,
        )
        for comparison_pivot in comparison_names
    )

    return MeasurementStatistics(
        measurement=parsed.measurement,
        main_pivot=main_pivot,
        acceptable_variation=acceptable_variation,
        case_count=len(parsed.cases),
        pivot_statistics=pivot_statistics,
        comparisons=comparisons,
        top_failure_cases=top_failure_cases,
        top_pass_cases=top_pass_cases,
    )


def _pivot_main_statistics(
    parsed: ParsedMeasurement,
    pivot_name: str,
) -> PivotMainStatistics:
    valid = [
        (case, value)
        for case in parsed.cases
        if (value := _value(case, pivot_name, "wcMargin")) is not None
    ]
    failures = [(case, value) for case, value in valid if value < 0]
    worst_case, worst_value = min(
        valid,
        key=lambda item: (
            item[1],
            _identity_sort_key(item[0].identity),
            item[0].worksheet_row,
        ),
        default=(None, None),
    )
    return PivotMainStatistics(
        pivot=pivot_name,
        failure_rate=Rate(len(failures), len(valid)),
        invalid_margin_count=len(parsed.cases) - len(valid),
        worst_wc_margin=worst_value,
        worst_failure_path=(
            worst_case.identity
            if worst_case is not None and worst_value is not None and worst_value < 0
            else None
        ),
    )


def _case_statistics(
    case: ComplianceCase,
    main_pivot: str,
    comparison_names: tuple[str, ...],
    definition: MeasurementDefinition,
) -> FailureCaseStatistics:
    main_average = _comparison_value(case, main_pivot, definition)
    comparison_values: dict[str, float | None] = {}
    deltas: dict[str, float | None] = {}
    for pivot in comparison_names:
        comparison = _comparison_value(case, pivot, definition)
        comparison_values[pivot] = comparison
        if main_average is None or comparison is None:
            deltas[pivot] = None
        else:
            try:
                delta = definition.delta(main_average, comparison)
                oriented_delta = definition.oriented_delta(delta)
                if not isfinite(delta) or not isfinite(oriented_delta):
                    raise ValueError("non-finite comparison delta")
                deltas[pivot] = oriented_delta
            except Exception:
                deltas[pivot] = CALCULATION_ERROR
    margin = _value(case, main_pivot, definition.margin_statistic)
    assert margin is not None
    return FailureCaseStatistics(
        case=case,
        main_wc_margin=margin,
        comparison_values=comparison_values,
        deltas=deltas,
    )


def _comparison_statistics(
    parsed: ParsedMeasurement,
    main_pivot: str,
    comparison_pivot: str,
    tolerance: float,
    definition: MeasurementDefinition,
) -> ComparisonStatistics:
    paired: list[tuple[float, float, str]] = []
    main_only_count = 0
    calculation_error = False
    for case in parsed.cases:
        main = _comparison_value(case, main_pivot, definition)
        comparison = _comparison_value(case, comparison_pivot, definition)
        if main is not None and comparison is None:
            main_only_count += 1
        if main is not None and comparison is not None:
            try:
                delta = definition.delta(main, comparison)
                oriented_delta = definition.oriented_delta(delta)
                if not isfinite(delta) or not isfinite(oriented_delta):
                    raise ValueError("non-finite comparison delta")
                paired.append(
                    (delta, oriented_delta, definition.classify(delta, tolerance))
                )
            except Exception:
                calculation_error = True

    degradation = [
        delta
        for _, delta, classification in paired
        if classification == "degradation"
    ]
    unchanged = [
        delta
        for _, delta, classification in paired
        if classification == "unchanged"
    ]
    improvement = [
        delta
        for _, delta, classification in paired
        if classification == "improvement"
    ]

    denominator = len(paired)
    if calculation_error:
        return ComparisonStatistics(
            comparison_pivot=comparison_pivot,
            paired_count=denominator,
            main_only_count=main_only_count,
            degradation_rate=Rate(0, denominator, error=True),
            unchanged_rate=Rate(0, denominator, error=True),
            improvement_rate=Rate(0, denominator, error=True),
            maximum_degradation=CALCULATION_ERROR,
            maximum_improvement=CALCULATION_ERROR,
            average_degradation=CALCULATION_ERROR,
            average_improvement=CALCULATION_ERROR,
        )

    return ComparisonStatistics(
        comparison_pivot=comparison_pivot,
        paired_count=denominator,
        main_only_count=main_only_count,
        degradation_rate=Rate(len(degradation), denominator),
        unchanged_rate=Rate(len(unchanged), denominator),
        improvement_rate=Rate(len(improvement), denominator),
        maximum_degradation=min(degradation) if degradation else None,
        maximum_improvement=max(improvement) if improvement else None,
        average_degradation=fmean(degradation) if degradation else None,
        average_improvement=fmean(improvement) if improvement else None,
    )


def _value(case: ComplianceCase, pivot: str, statistic: str) -> float | None:
    return case.pivot_values[pivot].get(statistic)


def _comparison_value(
    case: ComplianceCase,
    pivot: str,
    definition: MeasurementDefinition,
) -> float | None:
    values = case.pivot_values[pivot]
    for statistic in definition.comparison_statistics:
        if statistic in values:
            return definition.transform_comparison_value(
                values[statistic], case.metadata_values
            )
    return None


def _identity_sort_key(identity: tuple[tuple[str, object], ...]) -> tuple[str, ...]:
    return tuple(f"{name}={value!s}" for name, value in identity)
