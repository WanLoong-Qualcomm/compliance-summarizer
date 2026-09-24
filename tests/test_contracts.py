from datetime import UTC, datetime

import pytest

from compliance_summarizer.contracts import (
    CaseAnalysis,
    CompleteAnalysisResult,
    DeltaClassification,
    DeltaResult,
    FindingSeverity,
    ModelBypassStatus,
    NegativeGainDecision,
    PairwiseComparison,
    ParsedCase,
    PivotFailureSummary,
    PivotMarginStatus,
    PivotSchema,
    Rate,
    Settings,
    SheetSchema,
    SourceMetadata,
    SourceResult,
    ValidationFinding,
)


def make_schema() -> SheetSchema:
    fixed_columns = {
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
    }
    return SheetSchema(
        sheet_name="Combined",
        fixed_columns=fixed_columns,
        optional_columns={"BW": 5, "F0_MHZ": 9},
        pivots=(
            PivotSchema(
                name="GF-PROTO",
                statistics={
                    "MIN": 18,
                    "MAX": 19,
                    "NN_25C AVG": 20,
                    "wcMargin": 21,
                },
            ),
        ),
    )


def make_case() -> ParsedCase:
    return ParsedCase(
        worksheet_row_number=5,
        source_values={"TESTNAME": "GAIN", "Result?": "FAIL", "raw": 0},
        fixed_values={"TESTNAME": "GAIN", "Result?": "FAIL"},
        pivot_values={
            "GF-PROTO": {
                "MIN": -1.0,
                "MAX": 2.0,
                "NN_25C AVG": 10.0,
                "wcMargin": 0.0,
            }
        },
        source_result=SourceResult.FAIL,
    )


def test_settings_and_schema_are_explicitly_validated():
    settings = Settings()
    assert settings.tests_to_report == ("GAIN",)
    assert settings.acceptable_variation["GAIN"] == 0.2

    schema = make_schema()
    assert schema.pivot_names == ("GF-PROTO",)
    assert schema.pivots[0].statistics["wcMargin"] == 21

    with pytest.raises(ValueError, match="supports only GAIN"):
        Settings(tests_to_report=("SSNF",))


def test_parsed_case_preserves_zero_missing_and_source_result_separately():
    case = make_case()

    assert case.source_result is SourceResult.FAIL
    assert case.pivot_values["GF-PROTO"]["wcMargin"] == 0.0
    assert case.pivot_margin_status("GF-PROTO") is PivotMarginStatus.PASS
    assert case.pivot_margin_status("MISSING-PIVOT") is PivotMarginStatus.UNAVAILABLE

    missing_case = ParsedCase(
        worksheet_row_number=6,
        source_values={"Result?": "PASS"},
        fixed_values={"Result?": "PASS"},
        pivot_values={"GF-PROTO": {"wcMargin": None}},
        source_result=SourceResult.PASS,
    )
    assert missing_case.pivot_margin_status("GF-PROTO") is PivotMarginStatus.UNAVAILABLE


def test_rates_and_failure_summaries_expose_unavailable_values():
    unavailable = Rate(0, 0)
    zero_rate = Rate(0, 4)

    assert unavailable.value is None
    assert unavailable.percentage is None
    assert not unavailable.is_available
    assert zero_rate.value == 0.0
    assert zero_rate.percentage == 0.0

    summary = PivotFailureSummary(
        pivot_name="GF-PROTO",
        failure_count=0,
        numeric_margin_count=0,
        unavailable_margin_count=1,
    )
    assert summary.failure_rate.value is None


def test_complete_analysis_result_has_one_typed_source_for_required_outputs():
    schema = make_schema()
    case = make_case()
    analyzed = CaseAnalysis(
        case=case,
        selected_pivot="GF-PROTO",
        selected_margin=0.0,
        pivot_statuses={"GF-PROTO": PivotMarginStatus.PASS},
        comparisons={},
    )
    result = CompleteAnalysisResult(
        source_metadata=SourceMetadata(
            source_filename="REFERENCE.xlsm",
            sheet_name="Combined",
            processed_at=datetime.now(UTC),
        ),
        settings=Settings(pivot_field_of_interest="GF-PROTO"),
        global_background_information="",
        pivot_background_information={"GF-PROTO": ""},
        sheet_schema=schema,
        total_worksheet_data_rows=1,
        total_gain_rows=1,
        pass_row_count=1,
        fail_row_count=0,
        negative_gain_findings=(),
        negative_gain_decision=NegativeGainDecision.NOT_REQUIRED,
        warnings=(
            ValidationFinding(
                code="missing_optional",
                message="Optional context is absent",
                severity=FindingSeverity.WARNING,
            ),
        ),
        exclusion_counts={"unavailable_margin": 0},
        pivot_failure_summaries=(
            PivotFailureSummary(
                pivot_name="GF-PROTO",
                failure_count=0,
                numeric_margin_count=1,
                unavailable_margin_count=0,
            ),
        ),
        top_failure_cases=(),
        worst_failure_cases=(),
        closest_pass_cases=(analyzed,),
        zero_margin_pass_boundary_count=1,
        pairwise_comparisons=(),
        model_bypass_status=ModelBypassStatus.BYPASSED,
    )

    assert result.pivot_failure_summaries[0].failure_rate.value == 0.0
    assert result.closest_pass_cases[0].case.worksheet_row_number == 5


def test_delta_result_rejects_missing_delta_with_a_status():
    with pytest.raises(ValueError, match="unavailable"):
        DeltaResult(None, DeltaClassification.NEUTRAL)


def test_pairwise_comparison_keeps_empty_rates_unavailable_and_candidates_typed():
    empty_comparison = PairwiseComparison(
        selected_pivot="GF-PROTO",
        comparison_pivot="GF-QMOM",
        comparable_case_count=0,
        degradation_count=0,
        improvement_count=0,
        neutral_count=0,
        selected_failure_summary=PivotFailureSummary("GF-PROTO", 0, 0, 1),
        comparison_failure_summary=PivotFailureSummary("GF-QMOM", 0, 0, 1),
    )
    assert empty_comparison.degradation_rate.value is None
    assert empty_comparison.degradation_led_failure.aggregate_signal is False

    analyzed = CaseAnalysis(
        case=make_case(),
        selected_pivot="GF-PROTO",
        selected_margin=-1.0,
        pivot_statuses={"GF-PROTO": PivotMarginStatus.FAIL},
        comparisons={
            "GF-QMOM": DeltaResult(-0.5, DeltaClassification.DEGRADATION),
        },
    )
    comparison = PairwiseComparison(
        selected_pivot="GF-PROTO",
        comparison_pivot="GF-QMOM",
        comparable_case_count=1,
        degradation_count=1,
        improvement_count=0,
        neutral_count=0,
        selected_failure_summary=PivotFailureSummary("GF-PROTO", 1, 1, 0),
        comparison_failure_summary=PivotFailureSummary("GF-QMOM", 0, 1, 0),
        degradation_led_failure_candidates=(analyzed,),
    )
    assert comparison.degradation_led_failure.candidates == (analyzed,)
    assert comparison.degradation_led_failure.aggregate_signal is True
