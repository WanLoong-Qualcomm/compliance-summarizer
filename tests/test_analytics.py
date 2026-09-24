import pytest

from compliance_summarizer.analytics import (
    DatasetError,
    FailureAnalysisResult,
    GainDatasetSummary,
    PassAnalysisResult,
    analyze_failure_cases,
    analyze_pass_cases,
    calculate_pairwise_deltas,
    calculate_pairwise_comparisons,
    calculate_pivot_failure_rates,
    summarize_gain_dataset,
)
from compliance_summarizer.contracts import (
    DeltaClassification,
    ParsedCase,
    PairwiseComparison,
    PivotMarginStatus,
    PivotSchema,
    SheetSchema,
    SourceResult,
)
from compliance_summarizer.validation import ContentValidationResult


def make_case(row_number: int, test_name: str, result: SourceResult | None) -> ParsedCase:
    raw_result = None if result is None else result.value
    return ParsedCase(
        worksheet_row_number=row_number,
        source_values={"TESTNAME": test_name, "Result?": raw_result},
        fixed_values={"TESTNAME": test_name, "Result?": raw_result},
        pivot_values={},
        source_result=result,
    )


def make_content(cases):
    return ContentValidationResult(
        selected_pivot="SELECTED",
        gain_cases=tuple(cases),
        valid_gain_cases=tuple(
            case for case in cases if case.source_result is not None
        ),
        selected_ranking_cases=(),
        pairwise_cases={},
        findings=(),
        exclusion_counts={},
    )


def test_summary_selects_exact_gain_and_counts_source_results():
    gain_pass = make_case(5, "GAIN", SourceResult.PASS)
    gain_fail = make_case(6, "GAIN", SourceResult.FAIL)
    gain_invalid = make_case(7, "GAIN", None)
    content = make_content(
        [
            gain_pass,
            gain_fail,
            gain_invalid,
            make_case(8, "IP3IB-GAIN", SourceResult.FAIL),
            make_case(9, "SSNF", SourceResult.PASS),
        ]
    )

    summary = summarize_gain_dataset(content)

    assert summary.total_gain_rows == 3
    assert summary.pass_count == 1
    assert summary.fail_count == 1
    assert summary.invalid_result_count == 1
    assert summary.gain_cases == (gain_pass, gain_fail, gain_invalid)
    assert summary.pass_cases == (gain_pass,)
    assert summary.fail_cases == (gain_fail,)
    assert summary.invalid_result_cases == (gain_invalid,)


def test_no_gain_rows_raises_clear_dataset_error():
    content = make_content([make_case(5, "SSNF", SourceResult.PASS)])

    with pytest.raises(DatasetError, match="No rows with normalized TESTNAME == 'GAIN'"):
        summarize_gain_dataset(content)


def make_failure_schema(*pivot_names: str) -> SheetSchema:
    fixed_headers = (
        "LNAMODE",
        "CAMODE",
        "STD",
        "BAND",
        "MEASPORT",
        "DLP",
        "DIV",
        "TESTNAME",
        "GAINMODE",
        "BBPATH",
        "FREQ",
        "CHANNEL",
        "Result?",
        "LL",
        "UL",
    )
    pivots = []
    for pivot_index, pivot_name in enumerate(pivot_names):
        first_column = 16 + pivot_index * 4
        pivots.append(
            PivotSchema(
                name=pivot_name,
                statistics={
                    "MIN": first_column,
                    "MAX": first_column + 1,
                    "NN_25C AVG": first_column + 2,
                    "wcMargin": first_column + 3,
                },
            )
        )
    return SheetSchema(
        sheet_name="Combined",
        fixed_columns={header: index for index, header in enumerate(fixed_headers, 1)},
        optional_columns={},
        pivots=tuple(pivots),
    )


def make_gain_case(
    row_number: int,
    margins: dict[str, object],
    result: SourceResult | None,
) -> ParsedCase:
    raw_result = None if result is None else result.value
    return ParsedCase(
        worksheet_row_number=row_number,
        source_values={"TESTNAME": "GAIN", "Result?": raw_result},
        fixed_values={"TESTNAME": "GAIN", "Result?": raw_result},
        pivot_values={
            pivot_name: {"wcMargin": margin}
            for pivot_name, margin in margins.items()
        },
        source_result=result,
    )


def make_delta_case(
    row_number: int,
    averages: dict[str, object],
    result: SourceResult | None,
    margins: dict[str, object] | None = None,
) -> ParsedCase:
    raw_result = None if result is None else result.value
    margins = margins or {}
    return ParsedCase(
        worksheet_row_number=row_number,
        source_values={"TESTNAME": "GAIN", "Result?": raw_result},
        fixed_values={"TESTNAME": "GAIN", "Result?": raw_result},
        pivot_values={
            pivot_name: {
                "NN_25C AVG": average,
                "wcMargin": margins.get(pivot_name),
            }
            for pivot_name, average in averages.items()
        },
        source_result=result,
    )


def test_pivot_failure_rates_keep_schema_order_and_exclude_invalid_results():
    schema = make_failure_schema("PIVOT-B", "PIVOT-A")
    cases = (
        make_gain_case(
            5,
            {"PIVOT-B": -1.0, "PIVOT-A": 0.0},
            SourceResult.PASS,
        ),
        make_gain_case(
            6,
            {"PIVOT-B": 0.5, "PIVOT-A": None},
            SourceResult.FAIL,
        ),
        make_gain_case(
            7,
            {"PIVOT-B": "not numeric", "PIVOT-A": -2.0},
            None,
        ),
    )

    summaries = calculate_pivot_failure_rates(GainDatasetSummary(cases), schema)

    assert tuple(summary.pivot_name for summary in summaries) == ("PIVOT-B", "PIVOT-A")
    assert summaries[0].failure_count == 1
    assert summaries[0].numeric_margin_count == 2
    assert summaries[0].unavailable_margin_count == 0
    assert summaries[0].failure_rate.numerator == 1
    assert summaries[0].failure_rate.denominator == 2
    assert summaries[0].failure_rate.value == 0.5
    assert summaries[1].failure_count == 0
    assert summaries[1].numeric_margin_count == 1
    assert summaries[1].unavailable_margin_count == 1
    assert summaries[1].failure_rate.value == 0.0


def test_pivot_failure_rates_cover_all_pass_all_fail_and_zero_denominator():
    schema = make_failure_schema("ALL-PASS", "ALL-FAIL", "EMPTY")
    cases = (
        make_gain_case(
            5,
            {"ALL-PASS": 0.0, "ALL-FAIL": -0.1, "EMPTY": None},
            SourceResult.PASS,
        ),
        make_gain_case(
            6,
            {"ALL-PASS": 1.0, "ALL-FAIL": -2.0},
            SourceResult.FAIL,
        ),
    )

    summaries = calculate_pivot_failure_rates(GainDatasetSummary(cases), schema)
    all_pass, all_fail, empty = summaries

    assert (all_pass.failure_count, all_pass.numeric_margin_count) == (0, 2)
    assert all_pass.unavailable_margin_count == 0
    assert all_pass.failure_rate.value == 0.0
    assert (all_fail.failure_count, all_fail.numeric_margin_count) == (2, 2)
    assert all_fail.unavailable_margin_count == 0
    assert all_fail.failure_rate.value == 1.0
    assert (empty.failure_count, empty.numeric_margin_count) == (0, 0)
    assert empty.unavailable_margin_count == 2
    assert empty.failure_rate.numerator == 0
    assert empty.failure_rate.denominator == 0
    assert empty.failure_rate.value is None


def test_pairwise_deltas_apply_signed_threshold_and_preserve_multiple_pivots():
    schema = make_failure_schema("SELECTED", "COMPARISON-A", "COMPARISON-B")
    cases = (
        make_delta_case(
            5,
            {"SELECTED": 10.0, "COMPARISON-A": 10.2, "COMPARISON-B": 9.8},
            SourceResult.PASS,
            {"SELECTED": 0.0},
        ),
        make_delta_case(
            6,
            {"SELECTED": 10.0, "COMPARISON-A": 10.21, "COMPARISON-B": 9.79},
            SourceResult.FAIL,
        ),
        make_delta_case(
            7,
            {"SELECTED": None, "COMPARISON-A": 100.0, "COMPARISON-B": "invalid"},
            SourceResult.PASS,
            {"SELECTED": 0.4},
        ),
        make_delta_case(
            8,
            {"SELECTED": 5.0, "COMPARISON-A": 5.0, "COMPARISON-B": 5.0},
            SourceResult.PASS,
        ),
        make_delta_case(
            9,
            {"SELECTED": 100.0, "COMPARISON-A": 0.0, "COMPARISON-B": 0.0},
            None,
        ),
    )

    analyses = calculate_pairwise_deltas(
        GainDatasetSummary(cases),
        schema,
        selected_pivot="SELECTED",
        variation_threshold=0.2,
    )

    assert len(analyses) == 4
    boundary, beyond, unavailable, zero = analyses
    assert boundary.selected_margin == 0.0
    assert boundary.pivot_statuses["SELECTED"] is PivotMarginStatus.PASS
    assert tuple(boundary.comparisons) == ("COMPARISON-A", "COMPARISON-B")
    assert boundary.comparisons["COMPARISON-A"].delta == pytest.approx(-0.2)
    assert (
        boundary.comparisons["COMPARISON-A"].classification
        is DeltaClassification.NEUTRAL
    )
    assert boundary.comparisons["COMPARISON-B"].delta == pytest.approx(0.2)
    assert (
        boundary.comparisons["COMPARISON-B"].classification
        is DeltaClassification.NEUTRAL
    )
    assert (
        beyond.comparisons["COMPARISON-A"].classification
        is DeltaClassification.DEGRADATION
    )
    assert (
        beyond.comparisons["COMPARISON-B"].classification
        is DeltaClassification.IMPROVEMENT
    )
    assert unavailable.comparisons["COMPARISON-A"].delta is None
    assert (
        unavailable.comparisons["COMPARISON-A"].classification
        is DeltaClassification.UNAVAILABLE
    )
    assert unavailable.comparisons["COMPARISON-B"].delta is None
    assert zero.comparisons["COMPARISON-A"].delta == 0.0
    assert (
        zero.comparisons["COMPARISON-A"].classification
        is DeltaClassification.NEUTRAL
    )


def test_pairwise_deltas_validate_selected_pivot_and_threshold():
    schema = make_failure_schema("SELECTED")
    dataset = GainDatasetSummary(
        (
            make_delta_case(5, {"SELECTED": 1.0}, SourceResult.PASS),
        )
    )

    with pytest.raises(ValueError, match="not present"):
        calculate_pairwise_deltas(dataset, schema, "MISSING", 0.2)
    with pytest.raises(ValueError, match="finite and nonnegative"):
        calculate_pairwise_deltas(dataset, schema, "SELECTED", -0.1)


def test_failure_analysis_limits_to_50_and_breaks_ties_by_worksheet_row():
    schema = make_failure_schema("SELECTED", "COMPARISON")
    row_numbers = tuple(range(5, 60))
    cases = tuple(
        make_delta_case(
            row_number,
            {"SELECTED": float(row_number), "COMPARISON": 0.0},
            SourceResult.FAIL,
            {
                "SELECTED": -10.0 if row_number in {5, 6} else float(row_number),
                "COMPARISON": 0.0,
            },
        )
        for row_number in reversed(row_numbers)
    )
    pass_case = make_delta_case(
        100,
        {"SELECTED": -100.0, "COMPARISON": 0.0},
        SourceResult.PASS,
        {"SELECTED": -100.0, "COMPARISON": 0.0},
    )
    dataset = GainDatasetSummary(cases + (pass_case,))
    analyses = calculate_pairwise_deltas(dataset, schema, "SELECTED", 0.2)

    result = analyze_failure_cases(dataset, analyses)

    assert isinstance(result, FailureAnalysisResult)
    assert len(result.source_fail_cases) == 55
    assert len(result.top_failure_cases) == 50
    assert len(result.worst_failure_cases) == 5
    assert result.worst_failure_cases == result.top_failure_cases[:5]
    assert [
        case_analysis.case.worksheet_row_number
        for case_analysis in result.top_failure_cases[:2]
    ] == [5, 6]
    assert result.top_failure_cases[-1].case.worksheet_row_number == 54
    assert result.unrankable_failure_cases == ()


def test_failure_analysis_tracks_missing_margins_and_worst_case_context():
    schema = make_failure_schema("SELECTED", "COMPARISON-A", "COMPARISON-B")
    cases = (
        make_delta_case(
            10,
            {"SELECTED": 10.0, "COMPARISON-A": None, "COMPARISON-B": 8.0},
            SourceResult.FAIL,
            {"SELECTED": -0.1, "COMPARISON-A": None, "COMPARISON-B": 0.0},
        ),
        make_delta_case(
            11,
            {"SELECTED": 5.0, "COMPARISON-A": 4.9, "COMPARISON-B": "invalid"},
            SourceResult.FAIL,
            {"SELECTED": -0.2, "COMPARISON-A": 0.0},
        ),
        make_delta_case(
            12,
            {"SELECTED": None, "COMPARISON-A": 1.0, "COMPARISON-B": 1.0},
            SourceResult.FAIL,
        ),
    )
    dataset = GainDatasetSummary(cases)
    analyses = calculate_pairwise_deltas(dataset, schema, "SELECTED", 0.2)

    result = analyze_failure_cases(dataset, analyses)

    assert [
        case_analysis.case.worksheet_row_number
        for case_analysis in result.top_failure_cases
    ] == [11, 10]
    assert [
        case_analysis.case.worksheet_row_number
        for case_analysis in result.unrankable_failure_cases
    ] == [12]
    assert result.worst_failure_cases == result.top_failure_cases
    first = result.worst_failure_cases[0]
    assert first.case.pivot_values["COMPARISON-A"]["wcMargin"] == 0.0
    assert first.pivot_statuses["COMPARISON-A"] is PivotMarginStatus.PASS
    assert first.comparisons["COMPARISON-A"].classification is DeltaClassification.NEUTRAL
    assert (
        first.comparisons["COMPARISON-B"].classification
        is DeltaClassification.UNAVAILABLE
    )
    second = result.worst_failure_cases[1]
    assert second.case.pivot_values["COMPARISON-A"]["wcMargin"] is None
    assert second.pivot_statuses["COMPARISON-A"] is PivotMarginStatus.UNAVAILABLE
    assert second.comparisons["COMPARISON-A"].classification is DeltaClassification.UNAVAILABLE
    assert (
        second.comparisons["COMPARISON-B"].classification
        is DeltaClassification.IMPROVEMENT
    )


def test_pass_analysis_excludes_nonpositive_margins_and_counts_zero_boundary():
    schema = make_failure_schema("SELECTED", "COMPARISON")
    cases = (
        make_delta_case(
            5,
            {"SELECTED": 10.0, "COMPARISON": 10.5},
            SourceResult.PASS,
            {"SELECTED": 0.3, "COMPARISON": 0.0},
        ),
        make_delta_case(
            6,
            {"SELECTED": 10.0, "COMPARISON": 10.5},
            SourceResult.PASS,
            {"SELECTED": 0.1, "COMPARISON": 0.0},
        ),
        make_delta_case(
            7,
            {"SELECTED": 10.0, "COMPARISON": 9.9},
            SourceResult.PASS,
            {"SELECTED": 0.1, "COMPARISON": 0.0},
        ),
        make_delta_case(
            8,
            {"SELECTED": 10.0, "COMPARISON": 10.0},
            SourceResult.PASS,
            {"SELECTED": 0.0, "COMPARISON": 0.0},
        ),
        make_delta_case(
            9,
            {"SELECTED": 10.0, "COMPARISON": 10.0},
            SourceResult.PASS,
            {"SELECTED": -0.1, "COMPARISON": 0.0},
        ),
        make_delta_case(
            10,
            {"SELECTED": None, "COMPARISON": 10.0},
            SourceResult.PASS,
        ),
        make_delta_case(
            11,
            {"SELECTED": 10.0, "COMPARISON": 10.0},
            SourceResult.PASS,
            {"SELECTED": 0.5, "COMPARISON": 0.0},
        ),
        make_delta_case(
            12,
            {"SELECTED": 10.0, "COMPARISON": 10.0},
            SourceResult.FAIL,
            {"SELECTED": 0.01, "COMPARISON": 0.0},
        ),
    )
    dataset = GainDatasetSummary(cases)
    analyses = calculate_pairwise_deltas(dataset, schema, "SELECTED", 0.2)

    result = analyze_pass_cases(dataset, analyses)

    assert isinstance(result, PassAnalysisResult)
    assert len(result.source_pass_cases) == 7
    assert [
        case_analysis.case.worksheet_row_number
        for case_analysis in result.closest_pass_cases
    ] == [6, 7, 5, 11]
    assert result.zero_margin_pass_boundary_count == 1
    assert all(
        case_analysis.selected_margin > 0
        for case_analysis in result.closest_pass_cases
    )
    assert (
        result.closest_pass_cases[0].comparisons["COMPARISON"].classification
        is DeltaClassification.DEGRADATION
    )
    assert all(
        case_analysis.case.worksheet_row_number not in {8, 9, 10, 12}
        for case_analysis in result.closest_pass_cases
    )


def test_pass_analysis_retains_exactly_five_and_breaks_margin_ties_by_row():
    schema = make_failure_schema("SELECTED", "COMPARISON")
    margins = {
        20: 0.1,
        21: 0.1,
        22: 0.2,
        23: 0.3,
        24: 0.4,
        25: 0.5,
    }
    cases = tuple(
        make_delta_case(
            row_number,
            {"SELECTED": 1.0, "COMPARISON": 1.0},
            SourceResult.PASS,
            {"SELECTED": margin, "COMPARISON": 0.0},
        )
        for row_number, margin in reversed(tuple(margins.items()))
    )
    dataset = GainDatasetSummary(cases)
    analyses = calculate_pairwise_deltas(dataset, schema, "SELECTED", 0.2)

    result = analyze_pass_cases(dataset, analyses)

    assert len(result.closest_pass_cases) == 5
    assert [
        case_analysis.case.worksheet_row_number
        for case_analysis in result.closest_pass_cases
    ] == [20, 21, 22, 23, 24]
    assert result.zero_margin_pass_boundary_count == 0


def test_pairwise_comparisons_aggregate_rates_extrema_and_failure_candidates():
    schema = make_failure_schema(
        "SELECTED",
        "COMPARISON-A",
        "COMPARISON-B",
        "EMPTY",
    )
    cases = (
        make_delta_case(
            5,
            {"SELECTED": 10.0, "COMPARISON-A": 10.5, "COMPARISON-B": 9.0},
            SourceResult.FAIL,
            {"SELECTED": -1.0, "COMPARISON-A": 0.0, "COMPARISON-B": -1.0},
        ),
        make_delta_case(
            6,
            {"SELECTED": 10.0, "COMPARISON-A": 10.3, "COMPARISON-B": 10.0},
            SourceResult.FAIL,
            {"SELECTED": -0.5, "COMPARISON-A": 0.0, "COMPARISON-B": 0.0},
        ),
        make_delta_case(
            7,
            {"SELECTED": 10.0, "COMPARISON-A": 9.5, "COMPARISON-B": 11.0},
            SourceResult.PASS,
            {"SELECTED": 0.2, "COMPARISON-A": 0.0, "COMPARISON-B": 0.0},
        ),
        make_delta_case(
            8,
            {"SELECTED": 10.0, "COMPARISON-A": 10.1, "COMPARISON-B": 10.2},
            SourceResult.FAIL,
            {"SELECTED": -0.1, "COMPARISON-A": -1.0, "COMPARISON-B": 0.0},
        ),
        make_delta_case(
            9,
            {"SELECTED": None, "COMPARISON-A": 1.0, "COMPARISON-B": 1.0},
            SourceResult.FAIL,
            {"SELECTED": -0.2, "COMPARISON-A": 0.0, "COMPARISON-B": 0.0},
        ),
        make_delta_case(
            10,
            {"SELECTED": 4.0, "COMPARISON-A": None, "COMPARISON-B": 3.0},
            SourceResult.PASS,
            {"SELECTED": 0.1, "COMPARISON-A": 0.0, "COMPARISON-B": 0.0},
        ),
    )
    dataset = GainDatasetSummary(cases)
    analyses = calculate_pairwise_deltas(dataset, schema, "SELECTED", 0.2)

    comparisons = calculate_pairwise_comparisons(
        dataset,
        schema,
        "SELECTED",
        analyses,
    )

    assert all(isinstance(comparison, PairwiseComparison) for comparison in comparisons)
    comparison_a, comparison_b, empty = comparisons
    assert tuple(comparison.comparison_pivot for comparison in comparisons) == (
        "COMPARISON-A",
        "COMPARISON-B",
        "EMPTY",
    )
    assert (
        comparison_a.comparable_case_count,
        comparison_a.degradation_count,
        comparison_a.improvement_count,
        comparison_a.neutral_count,
    ) == (4, 2, 1, 1)
    assert comparison_a.degradation_rate.value == 0.5
    assert comparison_a.improvement_rate.value == 0.25
    assert comparison_a.neutral_rate.value == 0.25
    assert comparison_a.maximum_degradation.delta == -0.5
    assert comparison_a.maximum_degradation.case_analysis.case.worksheet_row_number == 5
    assert comparison_a.maximum_improvement.delta == 0.5
    assert comparison_a.maximum_improvement.case_analysis.case.worksheet_row_number == 7
    assert [
        candidate.case.worksheet_row_number
        for candidate in comparison_a.degradation_led_failure_candidates
    ] == [5, 6]
    assert comparison_a.degradation_led_failure.aggregate_signal is True
    assert comparison_a.selected_failure_summary.failure_rate.value == 0.75
    assert comparison_a.comparison_failure_summary.failure_rate.value == 0.25

    assert (
        comparison_b.comparable_case_count,
        comparison_b.degradation_count,
        comparison_b.improvement_count,
        comparison_b.neutral_count,
    ) == (5, 1, 2, 2)
    assert comparison_b.degradation_rate.value == 0.2
    assert comparison_b.improvement_rate.value == 0.4
    assert comparison_b.neutral_rate.value == 0.4
    assert comparison_b.maximum_degradation.case_analysis.case.worksheet_row_number == 7
    assert comparison_b.maximum_improvement.case_analysis.case.worksheet_row_number == 5
    assert comparison_b.degradation_led_failure_candidates == ()

    assert empty.comparable_case_count == 0
    assert empty.degradation_rate.value is None
    assert empty.improvement_rate.value is None
    assert empty.neutral_rate.value is None
    assert empty.maximum_degradation is None
    assert empty.maximum_improvement is None
    assert empty.degradation_led_failure.aggregate_signal is False
    assert empty.degradation_led_failure.candidates == ()
