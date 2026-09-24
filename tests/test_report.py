from __future__ import annotations

from datetime import UTC, datetime

import pytest

import compliance_summarizer.report as report_module
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
    Settings,
    SheetSchema,
    SourceMetadata,
    SourceResult,
    ValidationFinding,
)
from compliance_summarizer.report import render_html_report, write_html_report


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
                name="GF-PROTO",
                statistics={
                    "MIN": 18,
                    "MAX": 19,
                    "NN_25C AVG": 20,
                    "wcMargin": 21,
                },
            ),
            PivotSchema(
                name="GF-QMOM",
                statistics={
                    "MIN": 22,
                    "MAX": 23,
                    "NN_25C AVG": 24,
                    "wcMargin": 25,
                },
            ),
        ),
    )


def make_case(row_number: int, result: SourceResult, margin: float) -> CaseAnalysis:
    selected_average = 10.0 if result is SourceResult.FAIL else 10.0
    comparison_average = 10.5 if result is SourceResult.FAIL else 10.0
    delta = selected_average - comparison_average
    classification = (
        DeltaClassification.DEGRADATION
        if delta < -0.2
        else DeltaClassification.NEUTRAL
    )
    raw_result = result.value
    parsed = ParsedCase(
        worksheet_row_number=row_number,
        source_values={
            "LNAMODE": "<unsafe>" if row_number == 5 else "LNA0",
            "CAMODE": "CA0",
            "STD": "5G",
            "BAND": "n78",
            "BW": 100,
            "MEASPORT": "PORT0",
            "DLP": "DLP0",
            "DIV": 2,
            "F0_MHZ": 3600,
            "TESTNAME": "GAIN",
            "GAINMODE": 1,
            "BBPATH": "BB0",
            "FREQ": 3600.0,
            "CHANNEL": row_number,
            "Result?": raw_result,
            "LL": -1.0,
            "UL": 1.0,
        },
        fixed_values={"TESTNAME": "GAIN", "Result?": raw_result},
        pivot_values={
            "GF-PROTO": {"NN_25C AVG": selected_average, "wcMargin": margin},
            "GF-QMOM": {"NN_25C AVG": comparison_average, "wcMargin": 0.0},
        },
        source_result=result,
    )
    return CaseAnalysis(
        case=parsed,
        selected_pivot="GF-PROTO",
        selected_margin=margin,
        pivot_statuses={
            "GF-PROTO": (
                PivotMarginStatus.FAIL if margin < 0 else PivotMarginStatus.PASS
            ),
            "GF-QMOM": PivotMarginStatus.PASS,
        },
        comparisons={
            "GF-QMOM": DeltaResult(delta, classification),
        },
    )


def make_analysis() -> CompleteAnalysisResult:
    failure = make_case(5, SourceResult.FAIL, -1.0)
    passing = make_case(6, SourceResult.PASS, 0.1)
    comparison = PairwiseComparison(
        selected_pivot="GF-PROTO",
        comparison_pivot="GF-QMOM",
        comparable_case_count=2,
        degradation_count=1,
        improvement_count=0,
        neutral_count=1,
        selected_failure_summary=PivotFailureSummary("GF-PROTO", 1, 2, 0),
        comparison_failure_summary=PivotFailureSummary("GF-QMOM", 0, 2, 0),
        maximum_degradation=None,
        maximum_improvement=None,
        degradation_led_failure_candidates=(failure,),
    )
    return CompleteAnalysisResult(
        source_metadata=SourceMetadata(
            source_filename="input.xlsm",
            sheet_name="Combined",
            processed_at=datetime(2026, 9, 24, 12, 0, tzinfo=UTC),
        ),
        settings=Settings(
            excel_file_path="C:/data/<unsafe>.xlsm",
            compliance_sheet_name="Combined",
            background_information="<global> background",
            pivot_field_of_interest="GF-PROTO",
        ),
        global_background_information="<global> background",
        pivot_background_information={
            "GF-PROTO": "<pivot> background",
            "GF-QMOM": "QMOM background",
        },
        sheet_schema=make_schema(),
        total_worksheet_data_rows=2,
        total_gain_rows=2,
        pass_row_count=1,
        fail_row_count=1,
        negative_gain_findings=(),
        negative_gain_decision=NegativeGainDecision.NOT_REQUIRED,
        warnings=(
            ValidationFinding(
                code="unsafe_text",
                message="A <warning> needs review",
                severity=FindingSeverity.WARNING,
            ),
        ),
        exclusion_counts={},
        pivot_failure_summaries=(
            PivotFailureSummary("GF-PROTO", 1, 2, 0),
            PivotFailureSummary("GF-QMOM", 0, 2, 0),
        ),
        top_failure_cases=(failure,),
        worst_failure_cases=(failure,),
        closest_pass_cases=(passing,),
        zero_margin_pass_boundary_count=0,
        pairwise_comparisons=(comparison,),
        model_bypass_status=ModelBypassStatus.BYPASSED,
    )


def test_report_has_fixed_order_embedded_assets_and_escaped_dynamic_text():
    report = render_html_report(make_analysis())

    section_titles = (
        "Report title and generation metadata",
        "User inputs and global background information",
        "Pivot fields and per-pivot background information",
        "Validation summary and warnings",
        "Dataset summary and GAIN PASS/FAIL counts",
        "Per-pivot failure rates",
        "Selected-pivot failure analysis",
        "Top-50 failure-case screenshot and equivalent accessible HTML table",
        "Five worst failure cases with all-pivot context",
        "Five closest-to-failure pass cases",
        "Overall pairwise degradation/improvement analysis",
        "Maximum degradation and improvement cases",
        "Degradation-led failure candidates",
        "Model-bypass statement",
    )
    positions = [report.index(title) for title in section_titles]

    assert positions == sorted(positions)
    assert report.startswith("<!doctype html>")
    assert '<style>' in report
    assert 'src="data:image/png;base64,' in report
    assert "<script" not in report
    assert "<unsafe>" not in report
    assert "&lt;unsafe&gt;" in report
    assert "&lt;global&gt; background" in report
    assert "&lt;warning&gt;" in report
    assert "AI generation is bypassed in v0.1." in report
    assert "file://" not in report
    assert "http://" not in report
    assert "https://" not in report


def test_report_shows_explicit_empty_states_and_unavailable_rates():
    analysis = make_analysis()
    analysis = CompleteAnalysisResult(
        source_metadata=analysis.source_metadata,
        settings=analysis.settings,
        global_background_information=analysis.global_background_information,
        pivot_background_information=analysis.pivot_background_information,
        sheet_schema=analysis.sheet_schema,
        total_worksheet_data_rows=0,
        total_gain_rows=0,
        pass_row_count=0,
        fail_row_count=0,
        negative_gain_findings=(),
        negative_gain_decision=NegativeGainDecision.NOT_REQUIRED,
        warnings=(),
        exclusion_counts={},
        pivot_failure_summaries=(PivotFailureSummary("GF-PROTO", 0, 0, 0),),
        top_failure_cases=(),
        worst_failure_cases=(),
        closest_pass_cases=(),
        zero_margin_pass_boundary_count=0,
        pairwise_comparisons=(),
        model_bypass_status=ModelBypassStatus.BYPASSED,
    )

    report = render_html_report(analysis)

    assert "No rankable failure cases for selected pivot" in report
    assert "No worst failure cases are available." in report
    assert "No closest-to-failure PASS cases are available." in report
    assert "0/0 (Unavailable)" in report
    assert "No comparison pivots are available." in report


def test_write_html_report_is_atomic_and_requires_explicit_overwrite(tmp_path):
    analysis = make_analysis()
    destination = tmp_path / "summary.html"

    assert write_html_report(analysis, destination) == destination
    first_content = destination.read_text(encoding="utf-8")
    assert first_content.startswith("<!doctype html>")
    with pytest.raises(FileExistsError, match="already exists"):
        write_html_report(analysis, destination)
    assert destination.read_text(encoding="utf-8") == first_content

    write_html_report(analysis, destination, overwrite=True)
    assert destination.read_text(encoding="utf-8") == first_content
    assert not list(tmp_path.glob(".*.tmp"))


def test_failed_render_does_not_replace_existing_report(tmp_path, monkeypatch):
    destination = tmp_path / "summary.html"
    destination.write_text("completed report", encoding="utf-8")

    def fail_render(_analysis):
        raise RuntimeError("render failed")

    monkeypatch.setattr(report_module, "render_html_report", fail_render)
    with pytest.raises(RuntimeError, match="render failed"):
        write_html_report(make_analysis(), destination, overwrite=True)

    assert destination.read_text(encoding="utf-8") == "completed report"
