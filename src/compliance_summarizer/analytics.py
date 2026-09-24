"""Deterministic analytical dataset preparation."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite

from .contracts import (
    CaseAnalysis,
    ComparisonExtremum,
    DeltaClassification,
    DeltaResult,
    ParsedCase,
    PairwiseComparison,
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


@dataclass(frozen=True, slots=True)
class FailureAnalysisResult:
    """Ranked and unrankable source FAIL cases for one selected pivot."""

    source_fail_cases: tuple[CaseAnalysis, ...]
    top_failure_cases: tuple[CaseAnalysis, ...]
    worst_failure_cases: tuple[CaseAnalysis, ...]
    unrankable_failure_cases: tuple[CaseAnalysis, ...]

    def __post_init__(self) -> None:
        source_fail_cases = tuple(self.source_fail_cases)
        top_failure_cases = tuple(self.top_failure_cases)
        worst_failure_cases = tuple(self.worst_failure_cases)
        unrankable_failure_cases = tuple(self.unrankable_failure_cases)
        groups = (
            source_fail_cases,
            top_failure_cases,
            worst_failure_cases,
            unrankable_failure_cases,
        )
        if any(
            not isinstance(case_analysis, CaseAnalysis)
            for group in groups
            for case_analysis in group
        ):
            raise TypeError("failure outputs must contain CaseAnalysis instances")
        if any(
            case_analysis.case.source_result is not SourceResult.FAIL
            for case_analysis in source_fail_cases
        ):
            raise ValueError("source_fail_cases must contain source FAIL cases")
        if len(top_failure_cases) > 50 or len(worst_failure_cases) > 5:
            raise ValueError("failure output limits are 50 and 5 respectively")
        if worst_failure_cases != top_failure_cases[:5]:
            raise ValueError("worst_failure_cases must be the first five top failures")
        source_rows = {
            case_analysis.case.worksheet_row_number
            for case_analysis in source_fail_cases
        }
        if any(
            case_analysis.case.worksheet_row_number not in source_rows
            for group in (top_failure_cases, worst_failure_cases, unrankable_failure_cases)
            for case_analysis in group
        ):
            raise ValueError("failure outputs must come from source_fail_cases")
        if any(
            case_analysis.selected_margin is None
            for case_analysis in top_failure_cases
        ):
            raise ValueError("top_failure_cases must be rankable")
        if any(
            case_analysis.selected_margin is not None
            for case_analysis in unrankable_failure_cases
        ):
            raise ValueError("unrankable_failure_cases must have unavailable margins")
        object.__setattr__(self, "source_fail_cases", source_fail_cases)
        object.__setattr__(self, "top_failure_cases", top_failure_cases)
        object.__setattr__(self, "worst_failure_cases", worst_failure_cases)
        object.__setattr__(
            self,
            "unrankable_failure_cases",
            unrankable_failure_cases,
        )


@dataclass(frozen=True, slots=True)
class PassAnalysisResult:
    """Closest source PASS cases and the zero-margin boundary count."""

    source_pass_cases: tuple[CaseAnalysis, ...]
    closest_pass_cases: tuple[CaseAnalysis, ...]
    zero_margin_pass_boundary_count: int

    def __post_init__(self) -> None:
        source_pass_cases = tuple(self.source_pass_cases)
        closest_pass_cases = tuple(self.closest_pass_cases)
        if any(
            not isinstance(case_analysis, CaseAnalysis)
            for case_analysis in source_pass_cases + closest_pass_cases
        ):
            raise TypeError("pass outputs must contain CaseAnalysis instances")
        if any(
            case_analysis.case.source_result is not SourceResult.PASS
            for case_analysis in source_pass_cases
        ):
            raise ValueError("source_pass_cases must contain source PASS cases")
        if len(closest_pass_cases) > 5:
            raise ValueError("closest_pass_cases cannot contain more than five cases")
        source_rows = {
            case_analysis.case.worksheet_row_number
            for case_analysis in source_pass_cases
        }
        if any(
            case_analysis.case.worksheet_row_number not in source_rows
            for case_analysis in closest_pass_cases
        ):
            raise ValueError("closest_pass_cases must come from source_pass_cases")
        if any(
            case_analysis.selected_margin is None
            or case_analysis.selected_margin <= 0
            for case_analysis in closest_pass_cases
        ):
            raise ValueError("closest_pass_cases must have positive selected margins")
        if (
            type(self.zero_margin_pass_boundary_count) is not int
            or self.zero_margin_pass_boundary_count < 0
        ):
            raise ValueError("zero-margin pass count must be a nonnegative integer")
        expected_zero_count = sum(
            case_analysis.selected_margin == 0
            for case_analysis in source_pass_cases
        )
        if self.zero_margin_pass_boundary_count != expected_zero_count:
            raise ValueError("zero-margin pass count does not match source PASS cases")
        object.__setattr__(self, "source_pass_cases", source_pass_cases)
        object.__setattr__(self, "closest_pass_cases", closest_pass_cases)


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


def analyze_failure_cases(
    dataset: GainDatasetSummary,
    case_analyses: tuple[CaseAnalysis, ...],
) -> FailureAnalysisResult:
    """Rank source FAIL cases and retain explicit unrankable cases.

    ``case_analyses`` is expected to be the complete valid-GAIN output from
    :func:`calculate_pairwise_deltas`, allowing retained worst cases to carry
    all-pivot margin statuses and comparison deltas.
    """

    if not isinstance(dataset, GainDatasetSummary):
        raise TypeError("dataset must be GainDatasetSummary")
    analyses = tuple(case_analyses)
    if any(not isinstance(analysis, CaseAnalysis) for analysis in analyses):
        raise TypeError("case_analyses must contain CaseAnalysis instances")

    analyses_by_row: dict[int, CaseAnalysis] = {}
    for analysis in analyses:
        row_number = analysis.case.worksheet_row_number
        if row_number in analyses_by_row:
            raise ValueError("case_analyses must have unique worksheet row numbers")
        analyses_by_row[row_number] = analysis

    source_fail_cases: list[CaseAnalysis] = []
    for case in dataset.fail_cases:
        analysis = analyses_by_row.get(case.worksheet_row_number)
        if analysis is None or analysis.case != case:
            raise ValueError(
                "case_analyses must include every source FAIL case from the dataset"
            )
        source_fail_cases.append(analysis)

    unrankable = tuple(
        analysis
        for analysis in source_fail_cases
        if analysis.selected_margin is None
    )
    rankable = tuple(
        analysis
        for analysis in source_fail_cases
        if analysis.selected_margin is not None
    )
    ranked = tuple(
        sorted(
            rankable,
            key=lambda analysis: (
                analysis.selected_margin,
                analysis.case.worksheet_row_number,
            ),
        )
    )
    top_failure_cases = ranked[:50]
    return FailureAnalysisResult(
        source_fail_cases=tuple(source_fail_cases),
        top_failure_cases=top_failure_cases,
        worst_failure_cases=top_failure_cases[:5],
        unrankable_failure_cases=unrankable,
    )


def analyze_pass_cases(
    dataset: GainDatasetSummary,
    case_analyses: tuple[CaseAnalysis, ...],
) -> PassAnalysisResult:
    """Rank source PASS cases by the smallest positive selected margin."""

    if not isinstance(dataset, GainDatasetSummary):
        raise TypeError("dataset must be GainDatasetSummary")
    analyses = tuple(case_analyses)
    if any(not isinstance(analysis, CaseAnalysis) for analysis in analyses):
        raise TypeError("case_analyses must contain CaseAnalysis instances")

    analyses_by_row: dict[int, CaseAnalysis] = {}
    for analysis in analyses:
        row_number = analysis.case.worksheet_row_number
        if row_number in analyses_by_row:
            raise ValueError("case_analyses must have unique worksheet row numbers")
        analyses_by_row[row_number] = analysis

    source_pass_cases: list[CaseAnalysis] = []
    for case in dataset.pass_cases:
        analysis = analyses_by_row.get(case.worksheet_row_number)
        if analysis is None or analysis.case != case:
            raise ValueError(
                "case_analyses must include every source PASS case from the dataset"
            )
        source_pass_cases.append(analysis)

    rankable = tuple(
        analysis
        for analysis in source_pass_cases
        if analysis.selected_margin is not None and analysis.selected_margin > 0
    )
    closest_pass_cases = tuple(
        sorted(
            rankable,
            key=lambda analysis: (
                analysis.selected_margin,
                analysis.case.worksheet_row_number,
            ),
        )[:5]
    )
    zero_margin_count = sum(
        analysis.selected_margin == 0 for analysis in source_pass_cases
    )
    return PassAnalysisResult(
        source_pass_cases=tuple(source_pass_cases),
        closest_pass_cases=closest_pass_cases,
        zero_margin_pass_boundary_count=zero_margin_count,
    )


def calculate_pairwise_comparisons(
    dataset: GainDatasetSummary,
    schema: SheetSchema,
    selected_pivot: str,
    case_analyses: tuple[CaseAnalysis, ...],
) -> tuple[PairwiseComparison, ...]:
    """Aggregate pairwise rates, extrema, and degradation-led evidence."""

    if not isinstance(dataset, GainDatasetSummary):
        raise TypeError("dataset must be GainDatasetSummary")
    if not isinstance(schema, SheetSchema):
        raise TypeError("schema must be SheetSchema")
    if not isinstance(selected_pivot, str) or not selected_pivot.strip():
        raise ValueError("selected_pivot must be a nonempty string")
    if selected_pivot not in schema.pivot_names:
        raise ValueError(
            f"selected_pivot {selected_pivot!r} is not present in the discovered schema"
        )
    analyses = tuple(case_analyses)
    if any(not isinstance(analysis, CaseAnalysis) for analysis in analyses):
        raise TypeError("case_analyses must contain CaseAnalysis instances")

    analyses_by_row: dict[int, CaseAnalysis] = {}
    for analysis in analyses:
        row_number = analysis.case.worksheet_row_number
        if row_number in analyses_by_row:
            raise ValueError("case_analyses must have unique worksheet row numbers")
        if analysis.selected_pivot != selected_pivot:
            raise ValueError("case_analyses must use the configured selected pivot")
        analyses_by_row[row_number] = analysis

    valid_cases = tuple(
        case
        for case in dataset.gain_cases
        if case.source_result in {SourceResult.PASS, SourceResult.FAIL}
    )
    ordered_analyses: list[CaseAnalysis] = []
    for case in valid_cases:
        analysis = analyses_by_row.get(case.worksheet_row_number)
        if analysis is None or analysis.case != case:
            raise ValueError(
                "case_analyses must include every valid GAIN case from the dataset"
            )
        ordered_analyses.append(analysis)

    comparisons: list[PairwiseComparison] = []
    for comparison_pivot in schema.pivot_names:
        if comparison_pivot == selected_pivot:
            continue
        comparable: list[tuple[CaseAnalysis, DeltaResult]] = []
        for analysis in ordered_analyses:
            delta_result = analysis.comparisons.get(comparison_pivot)
            if delta_result is not None and delta_result.delta is not None:
                comparable.append((analysis, delta_result))

        degradation_count = sum(
            result.classification is DeltaClassification.DEGRADATION
            for _, result in comparable
        )
        improvement_count = sum(
            result.classification is DeltaClassification.IMPROVEMENT
            for _, result in comparable
        )
        neutral_count = sum(
            result.classification is DeltaClassification.NEUTRAL
            for _, result in comparable
        )
        comparable_analyses = tuple(analysis for analysis, _ in comparable)
        selected_failure_summary = _calculate_failure_summary(
            selected_pivot,
            comparable_analyses,
        )
        comparison_failure_summary = _calculate_failure_summary(
            comparison_pivot,
            comparable_analyses,
        )

        maximum_degradation = _select_comparison_extremum(
            comparable,
            comparison_pivot,
            DeltaClassification.DEGRADATION,
        )
        maximum_improvement = _select_comparison_extremum(
            comparable,
            comparison_pivot,
            DeltaClassification.IMPROVEMENT,
        )
        degradation_candidates = tuple(
            analysis
            for analysis, result in comparable
            if result.classification is DeltaClassification.DEGRADATION
            and _is_failure_margin(analysis, selected_pivot)
            and _is_passing_margin(analysis, comparison_pivot)
        )

        comparisons.append(
            PairwiseComparison(
                selected_pivot=selected_pivot,
                comparison_pivot=comparison_pivot,
                comparable_case_count=len(comparable),
                degradation_count=degradation_count,
                improvement_count=improvement_count,
                neutral_count=neutral_count,
                selected_failure_summary=selected_failure_summary,
                comparison_failure_summary=comparison_failure_summary,
                maximum_degradation=maximum_degradation,
                maximum_improvement=maximum_improvement,
                degradation_led_failure_candidates=degradation_candidates,
            )
        )
    return tuple(comparisons)


def _calculate_failure_summary(
    pivot_name: str,
    analyses: tuple[CaseAnalysis, ...],
) -> PivotFailureSummary:
    numeric_margins = tuple(
        margin
        for analysis in analyses
        for margin in (
            _numeric_or_none(
                analysis.case.pivot_values.get(pivot_name, {}).get("wcMargin")
            ),
        )
        if margin is not None
    )
    return PivotFailureSummary(
        pivot_name=pivot_name,
        failure_count=sum(margin < 0 for margin in numeric_margins),
        numeric_margin_count=len(numeric_margins),
        unavailable_margin_count=len(analyses) - len(numeric_margins),
    )


def _select_comparison_extremum(
    comparable: list[tuple[CaseAnalysis, DeltaResult]],
    comparison_pivot: str,
    classification: DeltaClassification,
) -> ComparisonExtremum | None:
    candidates = tuple(
        (analysis, result)
        for analysis, result in comparable
        if result.classification is classification and result.delta is not None
    )
    if not candidates:
        return None
    if classification is DeltaClassification.DEGRADATION:
        selected = min(
            candidates,
            key=lambda item: (
                item[1].delta,
                item[0].case.worksheet_row_number,
            ),
        )
    else:
        selected = min(
            candidates,
            key=lambda item: (
                -item[1].delta,
                item[0].case.worksheet_row_number,
            ),
        )
    return ComparisonExtremum(
        case_analysis=selected[0],
        comparison_pivot=comparison_pivot,
        delta=selected[1].delta,
    )


def _is_failure_margin(analysis: CaseAnalysis, pivot_name: str) -> bool:
    margin = _numeric_or_none(
        analysis.case.pivot_values.get(pivot_name, {}).get("wcMargin")
    )
    return margin is not None and margin < 0


def _is_passing_margin(analysis: CaseAnalysis, pivot_name: str) -> bool:
    margin = _numeric_or_none(
        analysis.case.pivot_values.get(pivot_name, {}).get("wcMargin")
    )
    return margin is not None and margin >= 0


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


def calculate_pairwise_deltas(
    dataset: GainDatasetSummary,
    schema: SheetSchema,
    selected_pivot: str,
    variation_threshold: float,
) -> tuple[CaseAnalysis, ...]:
    """Calculate selected-pivot GAIN deltas for every valid GAIN case.

    Comparisons use the signed difference between the selected pivot's and
    comparison pivot's ``NN_25C AVG`` values.  Missing or nonnumeric operands
    remain explicit as unavailable comparisons and do not produce a delta.
    """

    if not isinstance(dataset, GainDatasetSummary):
        raise TypeError("dataset must be GainDatasetSummary")
    if not isinstance(schema, SheetSchema):
        raise TypeError("schema must be SheetSchema")
    if not isinstance(selected_pivot, str) or not selected_pivot.strip():
        raise ValueError("selected_pivot must be a nonempty string")
    if selected_pivot not in schema.pivot_names:
        raise ValueError(
            f"selected_pivot {selected_pivot!r} is not present in the discovered schema"
        )
    if not _is_finite_number(variation_threshold) or variation_threshold < 0:
        raise ValueError("variation_threshold must be finite and nonnegative")

    valid_cases = tuple(
        case
        for case in dataset.gain_cases
        if case.source_result in {SourceResult.PASS, SourceResult.FAIL}
    )
    analyses: list[CaseAnalysis] = []
    comparison_pivots = tuple(
        pivot_name for pivot_name in schema.pivot_names if pivot_name != selected_pivot
    )
    for case in valid_cases:
        pivot_statuses = {
            pivot_name: case.pivot_margin_status(pivot_name)
            for pivot_name in schema.pivot_names
        }
        selected_values = case.pivot_values.get(selected_pivot, {})
        selected_margin = _numeric_or_none(selected_values.get("wcMargin"))
        selected_average = _numeric_or_none(selected_values.get("NN_25C AVG"))
        comparisons: dict[str, DeltaResult] = {}
        for comparison_pivot in comparison_pivots:
            comparison_values = case.pivot_values.get(comparison_pivot, {})
            comparison_average = _numeric_or_none(
                comparison_values.get("NN_25C AVG")
            )
            if selected_average is None or comparison_average is None:
                comparisons[comparison_pivot] = DeltaResult(
                    None,
                    DeltaClassification.UNAVAILABLE,
                )
                continue

            delta = selected_average - comparison_average
            if not _is_finite_number(delta):
                comparisons[comparison_pivot] = DeltaResult(
                    None,
                    DeltaClassification.UNAVAILABLE,
                )
                continue
            comparisons[comparison_pivot] = DeltaResult(
                delta,
                _classify_delta(delta, variation_threshold),
            )

        analyses.append(
            CaseAnalysis(
                case=case,
                selected_pivot=selected_pivot,
                selected_margin=selected_margin,
                pivot_statuses=pivot_statuses,
                comparisons=comparisons,
            )
        )
    return tuple(analyses)


def _classify_delta(delta: float, variation_threshold: float) -> DeltaClassification:
    if delta < -variation_threshold:
        return DeltaClassification.DEGRADATION
    if delta > variation_threshold:
        return DeltaClassification.IMPROVEMENT
    return DeltaClassification.NEUTRAL


def _numeric_or_none(value: object) -> float | int | None:
    return value if _is_finite_number(value) else None


def _is_finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
    )
