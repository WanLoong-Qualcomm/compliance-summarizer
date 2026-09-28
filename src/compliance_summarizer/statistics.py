"""Deterministic GAIN compliance and comparison calculations."""

from __future__ import annotations

from statistics import fmean

from .errors import WorkbookValidationError
from .measurements import MeasurementDefinition, get_measurement_definition
from .models import (
    ComplianceCase,
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
) -> MeasurementStatistics:
    """Calculate all v0.1 statistics without consulting source ``Result?``."""

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
    ordered_failures = sorted(
        main_failures,
        key=lambda case: (
            _value(case, main_pivot, definition.margin_statistic),
            _identity_sort_key(case.identity),
            case.worksheet_row,
        ),
    )
    comparison_names = tuple(
        pivot for pivot in parsed.schema.pivot_names if pivot != main_pivot
    )
    top_failure_cases = tuple(
        _failure_case(case, main_pivot, comparison_names, definition)
        for case in ordered_failures[:20]
    )
    comparisons = tuple(
        _comparison_statistics(
            parsed,
            main_pivot,
            comparison_pivot,
            acceptable_variation,
            main_failures,
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


def _failure_case(
    case: ComplianceCase,
    main_pivot: str,
    comparison_names: tuple[str, ...],
    definition: MeasurementDefinition,
) -> FailureCaseStatistics:
    main_average = _value(case, main_pivot, definition.comparison_statistic)
    comparison_values: dict[str, float | None] = {}
    deltas: dict[str, float | None] = {}
    for pivot in comparison_names:
        comparison = _value(case, pivot, definition.comparison_statistic)
        comparison_values[pivot] = comparison
        deltas[pivot] = (
            definition.delta(main_average, comparison)
            if main_average is not None and comparison is not None
            else None
        )
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
    main_failures: tuple[ComplianceCase, ...],
    definition: MeasurementDefinition,
) -> ComparisonStatistics:
    deltas: list[float] = []
    main_only_count = 0
    for case in parsed.cases:
        main = _value(case, main_pivot, definition.comparison_statistic)
        comparison = _value(case, comparison_pivot, definition.comparison_statistic)
        if main is not None and comparison is None:
            main_only_count += 1
        if main is not None and comparison is not None:
            deltas.append(definition.delta(main, comparison))

    degradation = [
        delta for delta in deltas if definition.classify(delta, tolerance) == "degradation"
    ]
    unchanged = [
        delta for delta in deltas if definition.classify(delta, tolerance) == "unchanged"
    ]
    improvement = [
        delta for delta in deltas if definition.classify(delta, tolerance) == "improvement"
    ]

    failure_degradation_magnitudes: list[float] = []
    for case in main_failures:
        main = _value(case, main_pivot, definition.comparison_statistic)
        comparison = _value(case, comparison_pivot, definition.comparison_statistic)
        if main is None or comparison is None:
            continue
        delta = definition.delta(main, comparison)
        if definition.classify(delta, tolerance) == "degradation":
            failure_degradation_magnitudes.append(
                definition.degradation_magnitude(delta)
            )

    denominator = len(deltas)
    return ComparisonStatistics(
        comparison_pivot=comparison_pivot,
        paired_count=denominator,
        main_only_count=main_only_count,
        degradation_rate=Rate(len(degradation), denominator),
        unchanged_rate=Rate(len(unchanged), denominator),
        improvement_rate=Rate(len(improvement), denominator),
        maximum_degradation=_most_degraded(degradation, definition),
        maximum_improvement=_most_improved(improvement, definition),
        average_degradation_on_main_failures=(
            fmean(failure_degradation_magnitudes)
            if failure_degradation_magnitudes
            else None
        ),
        degraded_main_failure_count=len(failure_degradation_magnitudes),
    )


def _value(case: ComplianceCase, pivot: str, statistic: str) -> float | None:
    return case.pivot_values[pivot].get(statistic)


def _identity_sort_key(identity: tuple[tuple[str, object], ...]) -> tuple[str, ...]:
    return tuple(f"{name}={value!s}" for name, value in identity)


def _most_degraded(
    deltas: list[float], definition: MeasurementDefinition
) -> float | None:
    if not deltas:
        return None
    return min(deltas) if definition.higher_is_better else max(deltas)


def _most_improved(
    deltas: list[float], definition: MeasurementDefinition
) -> float | None:
    if not deltas:
        return None
    return max(deltas) if definition.higher_is_better else min(deltas)
