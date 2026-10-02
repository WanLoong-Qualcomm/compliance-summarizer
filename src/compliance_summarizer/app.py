"""End-to-end deterministic v0.2 workflow."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .config import load_custom_groups, load_settings, load_test_filters
from .grouping import calculate_grouped_analyses
from .measurements import get_measurement_definition
from .models import AnalysisResult, MeasurementAnalysis
from .report import write_html_report
from .statistics import calculate_measurement_statistics
from .workbook import load_measurements


def analyze(settings_path: str | Path = "JUI.json") -> AnalysisResult:
    settings = load_settings(settings_path)
    test_filters = load_test_filters(settings_path)
    custom_groups = load_custom_groups(settings_path) if settings.group_by else {}
    parsed_measurements = load_measurements(
        settings.excel_file_path,
        settings.compliance_sheet_name,
        settings.testnames,
        test_filters=test_filters,
        add_fail_type=settings.add_fail_type,
    )
    measurement_analyses = []
    for parsed in parsed_measurements:
        measurement = parsed.measurement
        acceptable_variation = get_measurement_definition(
            measurement
        ).acceptable_variation
        statistics = calculate_measurement_statistics(
            parsed,
            settings.anchor_pivot,
            acceptable_variation,
        )
        grouped_analyses, group_warnings = calculate_grouped_analyses(
            parsed,
            settings.group_by,
            settings.anchor_pivot,
            acceptable_variation,
            custom_groups=custom_groups,
            add_fail_type=settings.add_fail_type,
            include_failures=settings.include_group_failures,
            include_marginal_passes=settings.include_group_marginal_passes,
        )
        measurement_analyses.append(
            MeasurementAnalysis(
                measurement=measurement,
                parsed=parsed,
                statistics=statistics,
                grouped_analyses=grouped_analyses,
                group_warnings=group_warnings,
            )
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
        measurement_analyses=tuple(measurement_analyses),
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        notes=notes,
    )


def run(
    settings_path: str | Path = "JUI.json",
    output_path: str | Path = "compliance-summary.html",
    *,
    overwrite: bool = False,
) -> tuple[AnalysisResult, Path]:
    analysis = analyze(settings_path)
    written = write_html_report(analysis, output_path, overwrite=overwrite)
    return analysis, written
