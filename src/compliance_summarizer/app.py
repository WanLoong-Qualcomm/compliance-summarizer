"""End-to-end deterministic v0.2 workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .config import load_settings
from .grouping import calculate_grouped_analyses
from .models import AnalysisResult
from .report import write_html_report
from .statistics import calculate_measurement_statistics
from .workbook import load_measurement


def analyze(settings_path: str | Path = "settings.json") -> AnalysisResult:
    settings = load_settings(settings_path)
    measurement = settings.measurements[0]
    parsed = load_measurement(
        settings.excel_file_path,
        settings.compliance_sheet_name,
        measurement,
    )
    statistics = calculate_measurement_statistics(
        parsed,
        settings.main_pivot,
        settings.acceptable_variation[measurement],
    )
    grouped_analyses, group_warnings = calculate_grouped_analyses(
        parsed,
        settings.group_by,
        settings.main_pivot,
        settings.acceptable_variation[measurement],
    )
    notes = (
        "AI generation was bypassed; all report conclusions are deterministic.",
        "Source Result? values are displayed as context only and are never used "
        "for compliance calculations.",
        "Top-20 output contains exactly 20 rows when at least 20 failures exist; "
        "ties are ordered by stable identifying fields and then source row for traceability.",
        "Blank, malformed, and non-finite numeric values are treated as coverage gaps.",
    )
    return AnalysisResult(
        settings=settings,
        parsed=parsed,
        statistics=statistics,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        notes=notes,
        grouped_analyses=grouped_analyses,
        group_warnings=group_warnings,
    )


def run(
    settings_path: str | Path = "settings.json",
    output_path: str | Path = "compliance-summary.html",
    *,
    overwrite: bool = False,
) -> tuple[AnalysisResult, Path]:
    analysis = analyze(settings_path)
    written = write_html_report(analysis, output_path, overwrite=overwrite)
    return analysis, written
