"""Command-line entry point for the compliance summarizer."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
import sys

from . import __version__
from .analytics import (
    analyze_failure_cases,
    analyze_pass_cases,
    calculate_pairwise_comparisons,
    calculate_pairwise_deltas,
    calculate_pivot_failure_rates,
    summarize_gain_dataset,
)
from .contracts import CompleteAnalysisResult, Settings, SourceMetadata, ValidationFinding
from .model import MODEL_BYPASS_STATEMENT, run_model_stage
from .prompts import (
    PromptAborted,
    collect_pivot_background_information,
    wait_for_settings_completion,
)
from .report import DEFAULT_REPORT_FILENAME, write_html_report
from .rows import parse_data_rows
from .schema import discover_sheet_schema
from .settings import SettingsError, create_default_settings, load_settings
from .validation import run_negative_gain_check, validate_compliance_content
from .workbook import WorkbookError, open_workbook


def build_parser() -> argparse.ArgumentParser:
    """Build the v0.1 command-line parser."""

    return argparse.ArgumentParser(
        prog="compliance-summarizer",
        description="Generate deterministic compliance summaries.",
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Run the complete deterministic v0.1 workflow."""

    parser = build_parser()
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.parse_args(argv)
    settings_path = Path("settings.json")
    try:
        created = create_default_settings(settings_path)
    except SettingsError as error:
        print(f"Settings error: {error}", file=sys.stderr)
        return 2
    if created:
        print(f"Created settings template at {settings_path}.")
        print("Complete the file before continuing with a compliance run.")
    else:
        print(f"Using existing settings file at {settings_path}.")
    try:
        wait_for_settings_completion(settings_path)
    except PromptAborted as error:
        print(f"Input aborted: {error}", file=sys.stderr)
        return 2

    try:
        settings = load_settings(settings_path)
    except SettingsError as error:
        print(f"Settings error: {error}", file=sys.stderr)
        return 2

    print("Settings loaded successfully.")
    try:
        analysis = _run_analysis(settings)
        output_path = write_html_report(analysis, DEFAULT_REPORT_FILENAME)
    except PromptAborted as error:
        print(f"Input aborted: {error}", file=sys.stderr)
        return 2
    except (SettingsError, WorkbookError, FileExistsError, OSError, ValueError) as error:
        print(f"Run failed: {error}", file=sys.stderr)
        return 2

    print(f"Model stage: {MODEL_BYPASS_STATEMENT}")
    print(f"Source workbook: {analysis.source_metadata.source_filename}")
    print(f"Compliance sheet: {analysis.source_metadata.sheet_name}")
    print(f"Selected pivot: {analysis.settings.pivot_field_of_interest}")
    print(f"GAIN rows: {analysis.total_gain_rows}")
    print(f"GAIN PASS rows: {analysis.pass_row_count}")
    print(f"GAIN FAIL rows: {analysis.fail_row_count}")
    print(f"Warnings: {len(analysis.warnings) + len(analysis.negative_gain_findings)}")
    print(f"Report written to: {output_path}")
    print(f"compliance-summarizer {__version__}")
    return 0


def _run_analysis(settings: Settings) -> CompleteAnalysisResult:
    """Run ingestion, checks, analytics, and deterministic model bypass."""

    with open_workbook(settings.excel_file_path, settings.compliance_sheet_name) as opened:
        discovery = discover_sheet_schema(
            opened.worksheet,
            selected_pivot=settings.pivot_field_of_interest,
        )
        if not discovery.is_valid or discovery.schema is None:
            raise ValueError(_format_findings("Sheet schema validation failed", discovery.findings))
        schema = discovery.schema
        backgrounds = collect_pivot_background_information(schema)
        parsed = parse_data_rows(opened.worksheet, schema)
        negative_gain = run_negative_gain_check(parsed, schema)
        if not negative_gain.should_continue:
            raise ValueError("Negative-GAIN confirmation was not approved.")

        content = validate_compliance_content(
            parsed,
            schema,
            settings.pivot_field_of_interest,
        )
        if content.is_blocked:
            raise ValueError(_format_findings("Compliance content validation failed", content.findings))

        dataset = summarize_gain_dataset(content)
        case_analyses = calculate_pairwise_deltas(
            dataset,
            schema,
            settings.pivot_field_of_interest,
            settings.acceptable_variation["GAIN"],
        )
        failure_analysis = analyze_failure_cases(dataset, case_analyses)
        pass_analysis = analyze_pass_cases(dataset, case_analyses)
        pairwise_comparisons = calculate_pairwise_comparisons(
            dataset,
            schema,
            settings.pivot_field_of_interest,
            case_analyses,
        )
        model_stage = run_model_stage()
        warnings = _unique_nonblocking_findings(
            (*discovery.findings, *content.findings)
        )
        return CompleteAnalysisResult(
            source_metadata=SourceMetadata(
                source_filename=Path(settings.excel_file_path).name,
                sheet_name=settings.compliance_sheet_name,
                processed_at=datetime.now(UTC),
            ),
            settings=settings,
            global_background_information=settings.background_information,
            pivot_background_information=backgrounds,
            sheet_schema=schema,
            total_worksheet_data_rows=len(parsed.cases),
            total_gain_rows=dataset.total_gain_rows,
            pass_row_count=dataset.pass_count,
            fail_row_count=dataset.fail_count,
            negative_gain_findings=negative_gain.validation_findings,
            negative_gain_decision=negative_gain.decision,
            warnings=warnings,
            exclusion_counts=content.exclusion_counts,
            pivot_failure_summaries=calculate_pivot_failure_rates(dataset, schema),
            top_failure_cases=failure_analysis.top_failure_cases,
            worst_failure_cases=failure_analysis.worst_failure_cases,
            closest_pass_cases=pass_analysis.closest_pass_cases,
            zero_margin_pass_boundary_count=pass_analysis.zero_margin_pass_boundary_count,
            pairwise_comparisons=pairwise_comparisons,
            model_bypass_status=model_stage.status,
        )


def _unique_nonblocking_findings(
    findings: tuple[ValidationFinding, ...],
) -> tuple[ValidationFinding, ...]:
    unique: list[ValidationFinding] = []
    for finding in findings:
        if finding.blocking or finding in unique:
            continue
        unique.append(finding)
    return tuple(unique)


def _format_findings(prefix: str, findings: tuple[ValidationFinding, ...]) -> str:
    details = "; ".join(finding.message for finding in findings if finding.blocking)
    return f"{prefix}: {details or 'see the schema diagnostics and correct the workbook.'}"
