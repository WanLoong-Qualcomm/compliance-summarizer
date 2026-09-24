import pytest

from compliance_summarizer.analytics import (
    DatasetError,
    GainDatasetSummary,
    calculate_pivot_failure_rates,
    summarize_gain_dataset,
)
from compliance_summarizer.contracts import (
    ParsedCase,
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
