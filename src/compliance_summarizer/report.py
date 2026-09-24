"""Fixed, self-contained HTML report rendering for v0.1."""

from __future__ import annotations

import html
import os
from collections.abc import Sequence
from enum import Enum
from os import PathLike
from pathlib import Path
import tempfile
from typing import Any

from .analytics import FailureAnalysisResult
from .contracts import (
    CaseAnalysis,
    CompleteAnalysisResult,
    PivotMarginStatus,
    Rate,
    ValidationFinding,
)
from .model import MODEL_BYPASS_STATEMENT
from .report_images import TopFailureTableImage, render_top_failure_table_image


DEFAULT_REPORT_FILENAME = "compliance-summary.html"


def render_html_report(analysis: CompleteAnalysisResult) -> str:
    """Render one complete deterministic report from an analysis result."""

    if not isinstance(analysis, CompleteAnalysisResult):
        raise TypeError("analysis must be CompleteAnalysisResult")

    selected_pivot = analysis.settings.pivot_field_of_interest
    top_image = _render_top_image(analysis)
    sections = (
        _section(
            "1",
            "Report title and generation metadata",
            _render_metadata(analysis),
        ),
        _section(
            "2",
            "User inputs and global background information",
            _render_user_inputs(analysis),
        ),
        _section(
            "3",
            "Pivot fields and per-pivot background information",
            _render_pivots(analysis),
        ),
        _section(
            "4",
            "Validation summary and warnings",
            _render_validation(analysis),
        ),
        _section(
            "5",
            "Dataset summary and GAIN PASS/FAIL counts",
            _render_dataset_summary(analysis),
        ),
        _section(
            "6",
            "Per-pivot failure rates",
            _render_failure_rates(analysis),
        ),
        _section(
            "7",
            "Selected-pivot failure analysis",
            _render_selected_failure_analysis(analysis),
        ),
        _section(
            "8",
            "Top-50 failure-case screenshot and equivalent accessible HTML table",
            _render_top_failures(analysis, top_image),
        ),
        _section(
            "9",
            "Five worst failure cases with all-pivot context",
            _render_case_group(analysis, analysis.worst_failure_cases, "worst"),
        ),
        _section(
            "10",
            "Five closest-to-failure pass cases",
            _render_case_group(analysis, analysis.closest_pass_cases, "closest"),
        ),
        _section(
            "11",
            "Overall pairwise degradation/improvement analysis",
            _render_pairwise_summary(analysis),
        ),
        _section(
            "12",
            "Maximum degradation and improvement cases",
            _render_pairwise_extrema(analysis),
        ),
        _section(
            "13",
            "Degradation-led failure candidates",
            _render_degradation_candidates(analysis),
        ),
        _section(
            "14",
            "Model-bypass statement",
            _render_model_bypass(analysis),
        ),
    )

    title = "RX SIGPATH GAIN Compliance Summary"
    return "<!doctype html>\n" + _html_document(title, sections)


def write_html_report(
    analysis: CompleteAnalysisResult,
    output_path: str | PathLike[str] = DEFAULT_REPORT_FILENAME,
    *,
    overwrite: bool = False,
) -> Path:
    """Render and atomically write a complete HTML report.

    The temporary file is created beside the destination, so a failed render
    or write cannot replace an existing completed report with partial output.
    Existing reports require explicit ``overwrite=True``.
    """

    destination = Path(output_path)
    if destination.exists() and not overwrite:
        raise FileExistsError(
            f"Report already exists: {destination}. Set overwrite=True to replace it."
        )
    if not destination.parent.is_dir():
        raise FileNotFoundError(
            f"Report output directory does not exist: {destination.parent}"
        )

    document = render_html_report(analysis)
    temporary_path: Path | None = None
    try:
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.",
            suffix=".tmp",
            dir=destination.parent,
        )
        temporary_path = Path(temporary_name)
        with os.fdopen(file_descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(document)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, destination)
        temporary_path = None
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
    return destination


def _html_document(title: str, sections: Sequence[str]) -> str:
    style = """
      :root { color-scheme: light; font-family: Arial, sans-serif; }
      body { color: #1f2933; background: #ffffff; margin: 0 auto; max-width: 1280px; padding: 24px; line-height: 1.4; }
      h1 { color: #123b5d; margin: 0 0 4px; }
      h2 { color: #123b5d; border-bottom: 2px solid #d7e2eb; padding-bottom: 6px; }
      h3 { color: #285b7f; }
      section { margin: 0 0 28px; }
      table { border-collapse: collapse; margin: 12px 0 18px; max-width: 100%; width: 100%; }
      caption { font-weight: 700; text-align: left; padding: 6px 0; }
      th, td { border: 1px solid #b8c5cf; padding: 6px 8px; text-align: left; vertical-align: top; word-break: break-word; }
      th { background: #1f4e79; color: #ffffff; }
      tr:nth-child(even) td { background: #eff5fb; }
      .metadata { color: #52606d; margin: 0 0 20px; }
      .empty-state { background: #f8f9fb; border: 1px solid #b8c5cf; padding: 10px; }
      .report-image { max-width: 100%; height: auto; border: 1px solid #b8c5cf; }
      .small { color: #52606d; font-size: 0.92em; }
      .warning { color: #7c4a03; }
      .pass { color: #176b3a; }
      .fail { color: #a12a2a; }
      details { margin: 8px 0; }
    """
    return (
        '<html lang="en"><head><meta charset="utf-8">'
        f"<title>{_escape(title)}</title><style>{style}</style></head><body>"
        + "".join(sections)
        + "</body></html>\n"
    )


def _section(number: str, title: str, body: str) -> str:
    return f'<section id="section-{number}"><h2>{number}. {_escape(title)}</h2>{body}</section>'


def _render_metadata(analysis: CompleteAnalysisResult) -> str:
    metadata = analysis.source_metadata
    rows = (
        ("Source workbook", metadata.source_filename),
        ("Compliance sheet", metadata.sheet_name),
        ("Generation timestamp", metadata.processed_at.isoformat()),
    )
    return '<h1>RX SIGPATH GAIN Compliance Summary</h1>' + _table(
        ("Field", "Value"), rows, caption="Report metadata"
    )


def _render_user_inputs(analysis: CompleteAnalysisResult) -> str:
    settings = analysis.settings
    rows = (
        ("Excel file path", settings.excel_file_path),
        ("Compliance sheet name", settings.compliance_sheet_name),
        ("Tests to report", ", ".join(settings.tests_to_report)),
        ("GAIN acceptable variation", settings.acceptable_variation["GAIN"]),
        ("Pivot field of interest", settings.pivot_field_of_interest),
        ("Bypass model", settings.bypass_model),
        ("Global background information", _or_unavailable(analysis.global_background_information)),
    )
    return _table(("Input", "Value"), rows, caption="Validated user inputs")


def _render_pivots(analysis: CompleteAnalysisResult) -> str:
    rows = []
    for pivot in analysis.sheet_schema.pivots:
        statistics = ", ".join(
            f"{name}={column}" for name, column in pivot.statistics.items()
        )
        if pivot.unknown_statistics:
            statistics += "; unknown=" + ", ".join(pivot.unknown_statistics)
        rows.append(
            (
                pivot.name,
                statistics,
                _or_unavailable(analysis.pivot_background_information.get(pivot.name)),
            )
        )
    return _table(
        ("Pivot field", "Statistic columns", "Background information"),
        rows,
        caption="Discovered pivot fields",
    )


def _render_validation(analysis: CompleteAnalysisResult) -> str:
    diagnostics = [
        ("Negative-GAIN decision", analysis.negative_gain_decision.value),
        ("Unknown columns", _or_unavailable(", ".join(analysis.sheet_schema.unknown_columns))),
        (
            "Optional context columns",
            _or_unavailable(", ".join(analysis.sheet_schema.optional_columns)),
        ),
    ]
    body = _table(("Diagnostic", "Value"), diagnostics, caption="Validation decisions")

    findings = [
        ("Negative-GAIN", finding)
        for finding in analysis.negative_gain_findings
    ] + [("Warning", finding) for finding in analysis.warnings]
    finding_rows = [
        (
            kind,
            finding.code,
            finding.message,
            finding.count,
            _finding_rows(finding),
            _or_unavailable(finding.field_name),
            _or_unavailable(finding.pivot_name),
        )
        for kind, finding in findings
    ]
    body += _table(
        ("Type", "Code", "Message", "Count", "Worksheet rows", "Field", "Pivot"),
        finding_rows,
        caption="Data-quality warnings and findings",
        empty_message="No warnings or findings were recorded.",
    )
    exclusion_rows = tuple(analysis.exclusion_counts.items())
    body += _table(
        ("Exclusion reason", "Count"),
        exclusion_rows,
        caption="Exclusion counts",
        empty_message="No rows were excluded.",
    )
    return body


def _render_dataset_summary(analysis: CompleteAnalysisResult) -> str:
    other_count = analysis.total_gain_rows - analysis.pass_row_count - analysis.fail_row_count
    rows = (
        ("Worksheet data rows", analysis.total_worksheet_data_rows),
        ("GAIN rows", analysis.total_gain_rows),
        ("GAIN PASS rows", analysis.pass_row_count),
        ("GAIN FAIL rows", analysis.fail_row_count),
        ("GAIN rows with another/invalid source result", other_count),
    )
    return _table(("Metric", "Count"), rows, caption="GAIN dataset summary")


def _render_failure_rates(analysis: CompleteAnalysisResult) -> str:
    rows = [
        (
            summary.pivot_name,
            summary.failure_count,
            summary.numeric_margin_count,
            summary.unavailable_margin_count,
            _format_rate(summary.failure_rate),
        )
        for summary in analysis.pivot_failure_summaries
    ]
    return _table(
        ("Pivot field", "Failures", "Numeric wcMargin denominator", "Unavailable wcMargin", "Failure rate"),
        rows,
        caption="Pivot-specific wcMargin failure rates",
        empty_message="No pivot failure-rate results are available.",
    )


def _render_selected_failure_analysis(analysis: CompleteAnalysisResult) -> str:
    rows = (
        ("Selected pivot", analysis.settings.pivot_field_of_interest),
        ("Source GAIN FAIL rows", analysis.fail_row_count),
        ("Ranked failure cases retained", len(analysis.top_failure_cases)),
        ("Worst failure cases retained", len(analysis.worst_failure_cases)),
        ("Closest PASS cases retained", len(analysis.closest_pass_cases)),
        ("Zero-margin PASS boundary count", analysis.zero_margin_pass_boundary_count),
    )
    return _table(("Metric", "Value"), rows, caption="Selected-pivot analysis")


def _render_top_failures(
    analysis: CompleteAnalysisResult,
    image: TopFailureTableImage,
) -> str:
    image_alt = image.empty_state_message or (
        f"Top {len(image.rows)} GAIN failure cases for {image.selected_pivot}, "
        "ordered by selected wcMargin"
    )
    body = (
        '<figure><figcaption>Top selected-pivot failure cases</figcaption>'
        f'<img class="report-image" src="{_escape(image.data_uri)}" '
        f'alt="{_escape(image_alt)}"></figure>'
    )
    body += _table(
        image.columns,
        image.rows,
        caption="Accessible top-50 failure-case table",
        empty_message=image.empty_state_message
        or "No rankable failure cases are available.",
    )
    return body


def _render_case_group(
    analysis: CompleteAnalysisResult,
    cases: Sequence[CaseAnalysis],
    group_name: str,
) -> str:
    headers = _case_context_headers(analysis)
    rows = tuple(_case_context_row(analysis, case_analysis, headers) for case_analysis in cases)
    label = "worst failure" if group_name == "worst" else "closest-to-failure PASS"
    return _table(
        headers,
        rows,
        caption=f"Five {label} cases with all-pivot context",
        empty_message=f"No {label} cases are available.",
    )


def _render_pairwise_summary(analysis: CompleteAnalysisResult) -> str:
    rows = [
        (
            comparison.comparison_pivot,
            comparison.comparable_case_count,
            comparison.degradation_count,
            _format_rate(comparison.degradation_rate),
            comparison.improvement_count,
            _format_rate(comparison.improvement_rate),
            comparison.neutral_count,
            _format_rate(comparison.neutral_rate),
        )
        for comparison in analysis.pairwise_comparisons
    ]
    return _table(
        (
            "Comparison pivot",
            "Comparable cases",
            "Degradation count",
            "Degradation rate",
            "Improvement count",
            "Improvement rate",
            "Neutral count",
            "Neutral rate",
        ),
        rows,
        caption=f"Pairwise GAIN comparisons against {analysis.settings.pivot_field_of_interest}",
        empty_message="No comparison pivots are available.",
    )


def _render_pairwise_extrema(analysis: CompleteAnalysisResult) -> str:
    rows = []
    for comparison in analysis.pairwise_comparisons:
        rows.append(
            (
                comparison.comparison_pivot,
                _format_extremum(comparison.maximum_degradation),
                _format_extremum(comparison.maximum_improvement),
            )
        )
    return _table(
        ("Comparison pivot", "Maximum degradation", "Maximum improvement"),
        rows,
        caption="Qualifying signed delta extrema with case context",
        empty_message="No qualifying pairwise extrema are available.",
    )


def _render_degradation_candidates(analysis: CompleteAnalysisResult) -> str:
    aggregate_rows = [
        (
            comparison.comparison_pivot,
            _yes_no(comparison.degradation_led_failure.aggregate_signal),
            len(comparison.degradation_led_failure.candidates),
        )
        for comparison in analysis.pairwise_comparisons
    ]
    body = _table(
        ("Comparison pivot", "Aggregate signal", "Candidate count"),
        aggregate_rows,
        caption="Aggregate degradation-led failure evidence",
        empty_message="No pairwise degradation evidence is available.",
    )

    candidate_rows = []
    for comparison in analysis.pairwise_comparisons:
        for candidate in comparison.degradation_led_failure.candidates:
            candidate_rows.append(
                (
                    comparison.comparison_pivot,
                    candidate.case.worksheet_row_number,
                    _format_number(candidate.selected_margin),
                    _format_number(
                        candidate.case.pivot_values.get(comparison.comparison_pivot, {}).get(
                            "wcMargin"
                        )
                    ),
                    _case_identity(analysis, candidate),
                )
            )
    body += _table(
        (
            "Comparison pivot",
            "Worksheet row",
            f"{analysis.settings.pivot_field_of_interest} wcMargin",
            "Comparison wcMargin",
            "Case context",
        ),
        candidate_rows,
        caption="Case-level degradation-led failure candidates",
        empty_message="No degradation-led failure candidates are available.",
    )
    body += '<p class="small">Candidates are defined evidence for the configured classifications and are not causal findings.</p>'
    return body


def _render_model_bypass(analysis: CompleteAnalysisResult) -> str:
    return _table(
        ("Model stage", "Status", "Statement"),
        (("AI generation", analysis.model_bypass_status.value, MODEL_BYPASS_STATEMENT),),
        caption="Deterministic model-stage status",
    )


def _render_top_image(analysis: CompleteAnalysisResult) -> TopFailureTableImage:
    """Adapt the complete-result top cases to the F2 image contract."""

    failure_analysis = FailureAnalysisResult(
        source_fail_cases=analysis.top_failure_cases,
        top_failure_cases=analysis.top_failure_cases,
        worst_failure_cases=analysis.top_failure_cases[:5],
        unrankable_failure_cases=(),
    )
    return render_top_failure_table_image(
        failure_analysis,
        analysis.settings.pivot_field_of_interest,
    )


def _case_context_headers(analysis: CompleteAnalysisResult) -> tuple[str, ...]:
    selected_pivot = analysis.settings.pivot_field_of_interest
    fixed_names = tuple(
        name
        for name, _ in sorted(
            (
                *analysis.sheet_schema.fixed_columns.items(),
                *analysis.sheet_schema.optional_columns.items(),
            ),
            key=lambda item: item[1],
        )
    )
    pivot_headers = tuple(
        header
        for pivot in analysis.sheet_schema.pivots
        for header in (f"{pivot.name} wcMargin", f"{pivot.name} status")
    )
    return ("Worksheet row", f"{selected_pivot} selected wcMargin") + fixed_names + pivot_headers


def _case_context_row(
    analysis: CompleteAnalysisResult,
    case_analysis: CaseAnalysis,
    headers: Sequence[str],
) -> tuple[str, ...]:
    case = case_analysis.case
    selected_pivot = analysis.settings.pivot_field_of_interest
    values: list[str] = []
    for header in headers:
        if header == "Worksheet row":
            values.append(str(case.worksheet_row_number))
        elif header == f"{selected_pivot} selected wcMargin":
            values.append(_format_number(case_analysis.selected_margin))
        elif header.endswith(" wcMargin") and header[:-9] in analysis.sheet_schema.pivot_names:
            pivot_name = header[:-9]
            values.append(
                _format_number(case.pivot_values.get(pivot_name, {}).get("wcMargin"))
            )
        elif header.endswith(" status") and header[:-7] in analysis.sheet_schema.pivot_names:
            pivot_name = header[:-7]
            status = case_analysis.pivot_statuses.get(pivot_name)
            values.append(status.value if isinstance(status, PivotMarginStatus) else "N/A")
        else:
            values.append(_format_number(_source_value(case_analysis, header)))
    return tuple(values)


def _case_identity(analysis: CompleteAnalysisResult, case_analysis: CaseAnalysis) -> str:
    case = case_analysis.case
    identity_names = (
        "LNAMODE",
        "CAMODE",
        "STD",
        "BAND",
        "MEASPORT",
        "DLP",
        "DIV",
        "GAINMODE",
        "BBPATH",
        "FREQ",
        "CHANNEL",
    )
    values = [f"worksheet row={case.worksheet_row_number}"]
    for name in identity_names:
        if name in analysis.sheet_schema.fixed_columns:
            values.append(f"{name}={_format_number(_source_value(case, name))}")
    return "; ".join(values)


def _source_value(case_or_analysis: CaseAnalysis | Any, name: str) -> object:
    case = case_or_analysis.case if isinstance(case_or_analysis, CaseAnalysis) else case_or_analysis
    if name in case.source_values:
        return case.source_values[name]
    return case.fixed_values.get(name)


def _format_extremum(extremum: object) -> str:
    if extremum is None:
        return "N/A (no qualifying case)"
    case_analysis = extremum.case_analysis
    return (
        f"delta={_format_number(extremum.delta)}; "
        f"worksheet row={case_analysis.case.worksheet_row_number}"
    )


def _finding_rows(finding: ValidationFinding) -> str:
    rows = finding.sample_rows or ((finding.worksheet_row_number,) if finding.worksheet_row_number else ())
    return ", ".join(str(row) for row in rows) if rows else "N/A"


def _format_rate(rate: Rate) -> str:
    if rate.value is None:
        return f"{rate.numerator}/{rate.denominator} (Unavailable)"
    return f"{rate.numerator}/{rate.denominator} ({rate.percentage:.1f}%)"


def _format_number(value: object) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, Enum):
        return value.value
    return str(value)


def _or_unavailable(value: object) -> object:
    if value is None or value == "":
        return "N/A"
    return value


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _escape(value: object) -> str:
    return html.escape(_format_number(value), quote=True)


def _table(
    headers: Sequence[object],
    rows: Sequence[Sequence[object]],
    *,
    caption: str,
    empty_message: str = "No data available.",
) -> str:
    header_values = tuple(headers)
    row_values = tuple(tuple(row) for row in rows)
    head = "".join(f"<th scope=\"col\">{_escape(header)}</th>" for header in header_values)
    body_rows: list[str] = []
    if row_values:
        for row in row_values:
            cells = "".join(f"<td>{_escape(value)}</td>" for value in row)
            body_rows.append(f"<tr>{cells}</tr>")
    else:
        body_rows.append(
            f'<tr><td colspan="{len(header_values)}" class="empty-state">'
            f"{_escape(empty_message)}</td></tr>"
        )
    return (
        f"<table><caption>{_escape(caption)}</caption><thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(body_rows)}</tbody></table>"
    )
