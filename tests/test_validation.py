from compliance_summarizer.contracts import (
    REQUIRED_FIXED_HEADERS,
    ParsedCase,
    PivotSchema,
    SheetSchema,
    SourceResult,
)
from compliance_summarizer.rows import RowParsingResult
from compliance_summarizer.validation import validate_compliance_content


def make_schema() -> SheetSchema:
    return SheetSchema(
        sheet_name="Combined",
        fixed_columns={
            "LNAMODE": 1,
            "CAMODE": 2,
            "STD": 3,
            "BAND": 4,
            "MEASPORT": 6,
            "DLP": 7,
            "DIV": 8,
            "TESTNAME": 10,
            "GAINMODE": 11,
            "BBPATH": 12,
            "FREQ": 13,
            "CHANNEL": 14,
            "Result?": 15,
            "LL": 16,
            "UL": 17,
        },
        optional_columns={"BW": 5, "F0_MHZ": 9},
        pivots=(
            PivotSchema(
                name="SELECTED",
                statistics={
                    "MIN": 18,
                    "MAX": 19,
                    "NN_25C AVG": 20,
                    "wcMargin": 21,
                },
            ),
            PivotSchema(
                name="COMPARISON",
                statistics={
                    "MIN": 22,
                    "MAX": 23,
                    "NN_25C AVG": 24,
                    "wcMargin": 25,
                },
            ),
        ),
    )


def make_case(
    row_number: int,
    *,
    result: SourceResult | None,
    test_name: str = "GAIN",
    selected_margin: object = 1.0,
    selected_average: object = 10.0,
    comparison_average: object = 9.0,
    comparison_margin: object = 1.0,
    limits: tuple[object, object] = (-1.0, 1.0),
) -> ParsedCase:
    raw_result = None if result is None else result.value
    fixed_values = {header: "context" for header in REQUIRED_FIXED_HEADERS}
    fixed_values.update(
        {
            "TESTNAME": test_name,
            "Result?": raw_result,
            "LL": limits[0],
            "UL": limits[1],
        }
    )
    source_values = dict(fixed_values)
    return ParsedCase(
        worksheet_row_number=row_number,
        source_values=source_values,
        fixed_values=fixed_values,
        pivot_values={
            "SELECTED": {
                "MIN": 1.0,
                "MAX": 2.0,
                "NN_25C AVG": selected_average,
                "wcMargin": selected_margin,
            },
            "COMPARISON": {
                "MIN": 1.0,
                "MAX": 2.0,
                "NN_25C AVG": comparison_average,
                "wcMargin": comparison_margin,
            },
        },
        source_result=result,
    )


def validate(cases):
    return validate_compliance_content(
        RowParsingResult(cases=tuple(cases), findings=()),
        make_schema(),
        "SELECTED",
    )


def test_invalid_results_and_selected_margins_are_excluded():
    result = validate(
        [
            make_case(5, result=SourceResult.PASS),
            make_case(6, result=None),
            make_case(7, result=SourceResult.FAIL, selected_margin="bad"),
        ]
    )

    assert [case.worksheet_row_number for case in result.gain_cases] == [5, 6, 7]
    assert [case.worksheet_row_number for case in result.valid_gain_cases] == [5, 7]
    assert [case.worksheet_row_number for case in result.selected_ranking_cases] == [5]
    assert result.exclusion_counts["missing_result"] == 1
    assert result.exclusion_counts["selected_margin_nonnumeric"] == 1
    assert not result.is_blocked


def test_missing_comparison_pivot_only_reduces_that_denominator():
    result = validate(
        [
            make_case(5, result=SourceResult.PASS, comparison_average=9.0),
            make_case(6, result=SourceResult.PASS, comparison_average=None),
        ]
    )

    assert [case.worksheet_row_number for case in result.pairwise_cases["COMPARISON"]] == [5]
    assert result.exclusion_counts["comparison_average_unavailable[COMPARISON]"] == 1
    assert not result.is_blocked


def test_source_result_margin_mismatch_is_reported_without_overwriting_source():
    result = validate(
        [
            make_case(5, result=SourceResult.PASS, selected_margin=-1.0),
            make_case(6, result=SourceResult.FAIL, selected_margin=0.0),
        ]
    )

    mismatches = [finding for finding in result.findings if finding.code == "result_margin_mismatch"]
    assert mismatches[0].count == 2
    assert result.valid_gain_cases[0].source_result is SourceResult.PASS


def test_required_selected_analysis_impossibility_blocks_run():
    result = validate(
        [
            make_case(
                5,
                result=SourceResult.PASS,
                selected_margin=None,
                selected_average=None,
            )
        ]
    )

    assert result.is_blocked
    assert {finding.code for finding in result.blocking_findings} == {
        "selected_ranking_impossible",
        "selected_comparison_impossible",
    }
