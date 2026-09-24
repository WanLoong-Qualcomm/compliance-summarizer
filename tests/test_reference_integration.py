from __future__ import annotations

from datetime import UTC, datetime
import hashlib
from pathlib import Path

import pytest

from compliance_summarizer.analytics import (
    analyze_failure_cases,
    analyze_pass_cases,
    calculate_pairwise_comparisons,
    calculate_pairwise_deltas,
    calculate_pivot_failure_rates,
    summarize_gain_dataset,
)
from compliance_summarizer.contracts import (
    CompleteAnalysisResult,
    ModelBypassStatus,
    NegativeGainDecision,
    Settings,
    SourceMetadata,
)
from compliance_summarizer.model import run_model_stage
from compliance_summarizer.report import render_html_report, write_html_report
from compliance_summarizer.rows import parse_data_rows
from compliance_summarizer.schema import discover_sheet_schema
from compliance_summarizer.validation import (
    run_negative_gain_check,
    validate_compliance_content,
)
from compliance_summarizer.workbook import open_workbook


REFERENCE_PATH = Path(__file__).parents[1] / "REFERENCE.xlsm"
REFERENCE_TIMESTAMP = datetime(2026, 9, 24, 0, 0, tzinfo=UTC)


def _file_fingerprint(path: Path) -> tuple[int, int, str]:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, digest.hexdigest()


def _run_reference_analysis(selected_pivot: str) -> CompleteAnalysisResult:
    with open_workbook(REFERENCE_PATH, "Combined") as opened:
        discovery = discover_sheet_schema(opened.worksheet, selected_pivot=selected_pivot)
        assert discovery.schema is not None
        schema = discovery.schema
        parsed = parse_data_rows(opened.worksheet, schema)
        negative_check = run_negative_gain_check(
            parsed,
            schema,
            output_fn=lambda _message: None,
        )
        assert negative_check.decision is NegativeGainDecision.NOT_REQUIRED
        content = validate_compliance_content(parsed, schema, selected_pivot)
        assert not content.is_blocked
        dataset = summarize_gain_dataset(content)
        case_analyses = calculate_pairwise_deltas(
            dataset,
            schema,
            selected_pivot,
            variation_threshold=0.2,
        )
        failure_analysis = analyze_failure_cases(dataset, case_analyses)
        pass_analysis = analyze_pass_cases(dataset, case_analyses)
        pairwise = calculate_pairwise_comparisons(
            dataset,
            schema,
            selected_pivot,
            case_analyses,
        )
        warnings = tuple(
            finding
            for finding in (*parsed.findings, *content.findings)
            if not finding.blocking
        )
        return CompleteAnalysisResult(
            source_metadata=SourceMetadata(
                source_filename=REFERENCE_PATH.name,
                sheet_name="Combined",
                processed_at=REFERENCE_TIMESTAMP,
            ),
            settings=Settings(
                excel_file_path=str(REFERENCE_PATH),
                compliance_sheet_name="Combined",
                acceptable_variation={"GAIN": 0.2},
                pivot_field_of_interest=selected_pivot,
            ),
            global_background_information="",
            pivot_background_information={
                pivot_name: "" for pivot_name in schema.pivot_names
            },
            sheet_schema=schema,
            total_worksheet_data_rows=len(parsed.cases),
            total_gain_rows=dataset.total_gain_rows,
            pass_row_count=dataset.pass_count,
            fail_row_count=dataset.fail_count,
            negative_gain_findings=negative_check.validation_findings,
            negative_gain_decision=negative_check.decision,
            warnings=warnings,
            exclusion_counts=content.exclusion_counts,
            pivot_failure_summaries=calculate_pivot_failure_rates(dataset, schema),
            top_failure_cases=failure_analysis.top_failure_cases,
            worst_failure_cases=failure_analysis.worst_failure_cases,
            closest_pass_cases=pass_analysis.closest_pass_cases,
            zero_margin_pass_boundary_count=pass_analysis.zero_margin_pass_boundary_count,
            pairwise_comparisons=pairwise,
            model_bypass_status=run_model_stage().status,
        )


@pytest.mark.parametrize("selected_pivot", ("GF-PROTO", "GF-QMOM", "SEC-DR5"))
def test_reference_combined_workflow_and_report_are_deterministic(
    tmp_path,
    selected_pivot,
):
    if not REFERENCE_PATH.is_file():
        pytest.skip("REFERENCE.xlsm is not available in this checkout")

    before = _file_fingerprint(REFERENCE_PATH)
    analysis = _run_reference_analysis(selected_pivot)

    assert analysis.sheet_schema.pivot_names == (
        "GF-PROTO",
        "GF-QMOM",
        "SEC-DR5",
    )
    assert (analysis.total_gain_rows, analysis.pass_row_count, analysis.fail_row_count) == (
        4256,
        4160,
        96,
    )
    if selected_pivot in {"GF-PROTO", "GF-QMOM"}:
        paired_pivot = "GF-QMOM" if selected_pivot == "GF-PROTO" else "GF-PROTO"
        paired_comparison = next(
            comparison
            for comparison in analysis.pairwise_comparisons
            if comparison.comparison_pivot == paired_pivot
        )
        assert paired_comparison.comparable_case_count == 3360
        assert paired_comparison.comparable_case_count < analysis.total_gain_rows
        assert analysis.exclusion_counts["selected_margin_missing"] == 896
        assert (
            analysis.exclusion_counts[
                f"comparison_average_unavailable[{paired_pivot}]"
            ]
            == 896
        )

    first_report = render_html_report(analysis)
    second_report = render_html_report(analysis)
    assert first_report == second_report
    assert 'src="data:image/png;base64,' in first_report
    assert "REFERENCE.xlsm" in first_report
    assert "Combined" in first_report
    assert "file://" not in first_report
    assert "http://" not in first_report
    assert "https://" not in first_report

    output_path = write_html_report(analysis, tmp_path / f"{selected_pivot}.html")
    assert output_path.is_file()
    assert output_path.read_text(encoding="utf-8") == first_report
    assert _file_fingerprint(REFERENCE_PATH) == before
