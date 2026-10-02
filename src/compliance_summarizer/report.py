"""Self-contained deterministic HTML rendering."""

from __future__ import annotations

import html
import os
import tempfile
from enum import Enum
from pathlib import Path
from typing import Iterable, Sequence

from .errors import ReportError
from .grouping import format_group_key
from .measurements import (
    ANCHOR_MINUS_OTHER,
    MIDPOINT_DEVIATION,
    OTHER_MINUS_ANCHOR,
    get_measurement_definition,
)
from .workbook import (
    FAIL_TYPE_DISPLAY_NAME,
    FAIL_TYPE_UNDEFINED,
    SPECIFICATION_STATISTICS,
    value_outside_limits,
)
from .models import (
    CALCULATION_ERROR,
    AnalysisResult,
    FailureCaseStatistics,
    GroupedAnalysis,
    MeasurementAnalysis,
    MeasurementStatistics,
    PivotMainStatistics,
    Rate,
    SheetSchema,
)


def write_html_report(
    analysis: AnalysisResult,
    output_path: str | Path,
    *,
    overwrite: bool = False,
) -> Path:
    target = Path(output_path).resolve()
    if target.exists() and not overwrite:
        raise ReportError(
            f"Output report '{target}' already exists. Choose another path or pass "
            "--overwrite."
        )
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        rendered = render_html(analysis)
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
            delete=False,
        )
        temporary = Path(handle.name)
        try:
            with handle:
                handle.write(rendered)
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
    except OSError as error:
        raise ReportError(f"Could not write report '{target}': {error}.") from error
    return target


def render_html(analysis: AnalysisResult) -> str:
    body = (
        _section("Run configuration", _configuration_table(analysis))
        + "".join(
            _measurement_sections(analysis, item)
            for item in analysis.measurement_analyses
        )
        + _section("Methodology and assumptions", _notes(analysis))
    )
    measurement_title = ", ".join(
        item.measurement for item in analysis.measurement_analyses
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Compliance Summary — {_escape(measurement_title)}</title>
<style>
:root {{ color-scheme: light; --ink:#172033; --muted:#5d6778; --line:#d9dfeb;
--panel:#fff; --wash:#f4f7fb; --brand:#3157d5; --bad:#FF0000; --good:#006100; }}
* {{ box-sizing:border-box; }} body {{ margin:0; background:var(--wash); color:var(--ink);
font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }}
main {{ width:min(1480px,calc(100% - 32px)); margin:28px auto 64px; }}
.hero {{ color:white; background:linear-gradient(125deg,#172554,#3157d5); border-radius:18px;
padding:28px; box-shadow:0 10px 30px #23387622; }} h1 {{ margin:0 0 8px; font-size:30px; }}
h2 {{ margin:0 0 14px; font-size:20px; }} .subtitle {{ opacity:.84; margin:0; }}
.cards {{ display:flex; flex-wrap:wrap; gap:12px; margin-top:22px; }}
.card {{ min-width:150px; padding:12px 15px; border:1px solid #ffffff32; border-radius:12px;
background:#ffffff13; }} .card strong {{ display:block; font-size:21px; }}
section {{ margin-top:18px; padding:22px; border:1px solid var(--line); border-radius:14px;
background:var(--panel); box-shadow:0 3px 14px #1720330b; }} .method,.muted {{ color:var(--muted); }}
.measurement-summary {{ margin-top:24px; }}
.measurement-summary + .measurement-summary {{ margin-top:42px; padding-top:28px;
border-top:2px solid var(--line); }}
.scroll {{ overflow:auto; }} table {{ width:100%; border:1px solid #7F7F7F; border-collapse:collapse; font-size:13px; }}
caption {{ text-align:left; font-weight:700; margin-bottom:8px; }} th {{ background:#eef2fb;
position:sticky; top:0; text-align:left; }} th,td {{ border:1px solid #7F7F7F; padding:8px 9px;
vertical-align:top; white-space:nowrap; }} tr:nth-child(even) td {{ background:#fafbfe; }}
.grouped-table thead tr:nth-child(2) th {{ top:34px; }}
.grouped-table thead tr:nth-child(3) th {{ top:68px; }}
.grouped-table .header-spacer {{ background:var(--panel); }}
.grouped-table .pivot-group {{ text-align:center; }}
.excel-summary-table thead th,
.excel-compliance-table thead th {{ background:#FCE4D6; color:#000000; text-align:center; }}
.excel-compliance-table thead th.header-spacer {{ background:var(--panel); border:0; }}
.excel-compliance-table thead th.worksheet-spacer {{ background:var(--panel); border:0; }}
.excel-compliance-table thead th.pivot-spacer {{ background:var(--panel);
border-top:0; border-bottom:1px solid #7F7F7F; border-left:1px solid #7F7F7F;
border-right:1px solid #7F7F7F; }}
.excel-compliance-table thead th.worksheet-header {{ background:var(--panel); }}
.excel-compliance-table tbody td {{ text-align:center; }}
.excel-compliance-table tbody td.excel-metadata-value {{ background:#E2F0D9; }}
.excel-compliance-table tbody td.excel-bound-value {{ color:#0000FF; }}
.excel-compliance-table tbody td.excel-column-shade-1 {{ background:#D9E2F3; }}
.excel-compliance-table tbody td.excel-column-shade-2 {{ background:#E6DDF3; }}
.excel-compliance-table tbody tr:nth-child(even) td.excel-column-shade-1,
.excel-compliance-table tbody tr:nth-child(even) td.excel-column-shade-2 {{ background:#FFFFFF; }}
.excel-compliance-table tbody td.excel-pivot-failure {{ color:#FF0000; }}
.excel-compliance-table tbody td.excel-result-pass {{ background:#C6EFCE; color:#006100; }}
.excel-compliance-table tbody td.excel-result-fail {{ background:#FFC7CE; color:#9C0006; }}
.calculation-error {{ color:#C00000; font-weight:700; }}
.fail-type-undef {{ color:#FF0000; font-weight:700; }}
.comparison-degradation {{ color:var(--bad); font-weight:400; }}
.comparison-improvement {{ color:var(--good); font-weight:400; }}
.compliance-failure {{ color:var(--bad); }}
.compliance-clear {{ color:var(--good); }}
.compliance-worst-failure {{ color:var(--bad); }}
.anchor-pivot-row {{ font-weight:700; }}
.group-divider {{ border:0; border-top:1px solid var(--line); margin:24px 0; }}
h3 {{ margin:0 0 10px; font-size:16px; }}
code {{ background:#edf0f6; padding:1px 4px; border-radius:4px; }} ul {{ margin-bottom:0; }}
</style>
</head>
<body><main>{body}</main></body>
</html>
"""


def _measurement_sections(
    analysis: AnalysisResult,
    item: MeasurementAnalysis,
) -> str:
    stats = item.statistics
    main = next(
        pivot for pivot in stats.pivot_statistics if pivot.pivot == stats.anchor_pivot
    )
    return (
        '<article class="measurement-summary">'
        + "".join(
            (
            _hero(analysis, item, main.failure_rate),
            _section("Coverage and validation", _coverage(item)),
            _section(
                "Overall pivot compliance",
                _pivot_compliance_content(stats),
            ),
            _section(
                f"Overall {stats.anchor_pivot} comparisons",
                _comparison_content(stats),
            ),
            _section(
                f"Overall {stats.anchor_pivot} failures",
                f'<p class="method">The top 20 failures are ordered by ascending '
                f'{_escape(stats.anchor_pivot)} '
                "<code>wcMargin</code>. Missing comparison operands remain blank.</p>"
                + _top_failure_table(analysis, item),
            ),
            _section(
                f"Overall {stats.anchor_pivot} marginal passes",
                f'<p class="method">The top 5 marginal passes are ordered by ascending '
                f'{_escape(stats.anchor_pivot)} '
                "<code>wcMargin</code>. Missing comparison operands remain blank.</p>"
                + _top_pass_table(analysis, item),
            ),
            _grouped_sections(analysis, item),
            )
        )
        + "</article>"
    )


def _hero(
    analysis: AnalysisResult,
    item: MeasurementAnalysis,
    failure_rate: Rate,
) -> str:
    stats = item.statistics
    anchor_pivot = _escape(stats.anchor_pivot)
    failure_label = _format_rate(failure_rate)
    return f"""<header class="hero">
<h1>{_escape(stats.measurement)} compliance summary</h1>
<p class="subtitle">{_escape(analysis.settings.excel_file_path.name)} ·
{_escape(analysis.settings.compliance_sheet_name)} · generated {_escape(analysis.generated_at)}</p>
<div class="cards">
<div class="card"><span>Anchor</span><strong>{anchor_pivot}</strong></div>
<div class="card"><span>Measurement rows</span><strong>{stats.case_count}</strong></div>
<div class="card"><span>{anchor_pivot} failures</span><strong>{failure_rate.numerator}</strong></div>
<div class="card"><span>{anchor_pivot} failure rate</span><strong>{_render_cell(failure_label)}</strong></div>
</div></header>"""


def _configuration_table(analysis: AnalysisResult) -> str:
    settings = analysis.settings
    rows = (
        ("Workbook", settings.excel_file_path),
        ("Outputs directory", settings.outputs_directory),
        ("Sheet", settings.compliance_sheet_name),
        ("Block", settings.block),
        ("Testnames", ", ".join(settings.testnames)),
        ("Anchor pivot", settings.anchor_pivot),
        ("Add fail type", settings.add_fail_type),
        (
            "Acceptable variation",
            "; ".join(
                f"{measurement}: "
                f"{get_measurement_definition(measurement).acceptable_variation}"
                for measurement in settings.testnames
            ),
        ),
        ("Group by", ", ".join(settings.group_by) or "(none)"),
        ("Include group failures", settings.include_group_failures),
        (
            "Include group marginal passes",
            settings.include_group_marginal_passes,
        ),
        ("Model bypass", settings.bypass_model),
        ("Background information", settings.background_information or ""),
    )
    return _table(
        ("Setting", "Value"),
        rows,
        "Settings",
        table_class="excel-summary-table",
    )


def _coverage(item: MeasurementAnalysis) -> str:
    rows = []
    coverage_items = tuple(
        coverage
        for coverage in item.parsed.coverage
        if coverage.pivot == item.statistics.anchor_pivot
    ) + tuple(
        coverage
        for coverage in item.parsed.coverage
        if coverage.pivot != item.statistics.anchor_pivot
    )
    for coverage in coverage_items:
        rows.append(
            (
                coverage.pivot,
                coverage.rows_with_gaps,
                sum(coverage.malformed_by_field.values()),
            )
        )
    content = _table(
        (
            "Pivot",
            "Coverage gaps",
            "Malformed/non-finite values",
        ),
        rows,
        "Coverage gaps",
        table_class="excel-summary-table",
    )
    warnings = (*item.parsed.warnings, *item.group_warnings)
    if warnings:
        content += "<h3>Warnings</h3><ul>" + "".join(
            f"<li>{_escape(warning)}</li>" for warning in warnings
        ) + "</ul>"
    else:
        content += '<p class="muted">No coverage or parsing warnings were recorded.</p>'
    return content


def _pivot_table(
    stats: MeasurementStatistics,
    *,
    highlight_pivot: str | None = None,
) -> str:
    pivot_statistics = _anchor_pivot_first(stats.pivot_statistics, stats.anchor_pivot)
    rows = []
    for item in pivot_statistics:
        rows.append(
            (
                item.pivot,
                item.failure_rate.denominator,
                item.failure_rate.numerator,
                _format_rate(item.failure_rate),
                _format_number(item.worst_wc_margin),
                _format_identity(item.worst_failure_path),
            )
        )
    cell_classes = []
    for item, row in zip(pivot_statistics, rows, strict=True):
        classes = [
            "anchor-pivot-row" if item.pivot == highlight_pivot else ""
            for _ in row
        ]
        classes[2] = _append_class(
            classes[2],
            "compliance-clear" if item.failure_rate.numerator == 0 else "compliance-failure",
        )
        if item.failure_rate.percentage is not None:
            classes[3] = _append_class(
                classes[3],
                "compliance-clear"
                if item.failure_rate.percentage == 0
                else "compliance-failure",
            )
        if item.worst_wc_margin is not None:
            classes[4] = _append_class(
                classes[4],
                "compliance-worst-failure"
                if item.worst_wc_margin < 0
                else "compliance-clear",
            )
        cell_classes.append(tuple(classes))

    return _table(
        (
            "Pivot",
            "Cases",
            "Failures",
            "Failure rate",
            "Worst wcMargin",
            "Worst failure path",
        ),
        rows,
        "Pivot compliance",
        cell_classes=tuple(cell_classes),
        table_class="excel-summary-table",
    )


def _anchor_pivot_first(
    pivot_statistics: Sequence[PivotMainStatistics],
    anchor_pivot: str,
) -> tuple[PivotMainStatistics, ...]:
    return tuple(
        item
        for item in pivot_statistics
        if item.pivot == anchor_pivot
    ) + tuple(
        item
        for item in pivot_statistics
        if item.pivot != anchor_pivot
    )


def _comparison_table(stats: MeasurementStatistics) -> str:
    rows = []
    for item in stats.comparisons:
        rows.append(
            (
                item.comparison_pivot,
                _format_rate(item.degradation_rate),
                _format_rate(item.unchanged_rate),
                _format_rate(item.improvement_rate),
                _format_number(item.maximum_degradation),
                _format_number(item.maximum_improvement),
                _format_average(item.average_degradation),
                _format_average(item.average_improvement),
            )
        )
    return _table(
        (
            "Comparison pivot",
            "Degradation rate",
            "Unchanged rate",
            "Improvement rate",
            "Maximum degradation",
            "Maximum improvement",
            "Average degradation",
            "Average improvement",
        ),
        rows,
        "Pivot comparisons",
        empty="No comparison pivots were discovered.",
        cell_classes=tuple(
            (
                "",
                "comparison-degradation",
                "",
                "comparison-improvement",
                "comparison-degradation",
                "comparison-improvement",
                "comparison-degradation",
                "comparison-improvement",
            )
            for _ in rows
        ),
        table_class="excel-summary-table",
    )


def _pivot_compliance_content(stats: MeasurementStatistics) -> str:
    return (
        '<p class="method">A negative <code>wcMargin</code> is a failure. '
        "Blank or invalid values are excluded from each pivot's failure-rate calculation.</p>"
        + _pivot_table(stats, highlight_pivot=stats.anchor_pivot)
    )


def _comparison_content(stats: MeasurementStatistics) -> str:
    definition = get_measurement_definition(stats.measurement)
    formula = definition.formula_text
    if definition.delta_fn == MIDPOINT_DEVIATION:
        explanation = (
            "Each deviation is the absolute distance from the row's LL/UL midpoint; "
            "smaller deviation is better."
        )
    elif definition.delta_fn == ANCHOR_MINUS_OTHER:
        explanation = "Higher values are better."
    else:
        explanation = "Lower values are better."
    return (
        f'<p class="method"><code>delta = {_escape(formula)}</code>. '
        "<code>MEAN</code> is used when available; otherwise <code>NN_25C AVG</code> "
        f"is used. {_escape(explanation)} Negative is degradation and positive is "
        "improvement. Values within the inclusive tolerance are unchanged.</p>"
        + _comparison_table(stats)
    )


def _grouped_sections(
    analysis: AnalysisResult,
    item: MeasurementAnalysis,
) -> str:
    return "".join(
        _grouped_section(analysis, item, grouped)
        for grouped in item.grouped_analyses
    )


def _grouped_section(
    analysis: AnalysisResult,
    item: MeasurementAnalysis,
    grouped: GroupedAnalysis,
) -> str:
    stats = grouped.statistics
    group_label = format_group_key(grouped.group_key)
    content = (
        "<h3>Pivot compliance</h3>"
        + _pivot_compliance_content(stats)
        + '<hr class="group-divider">'
        + f"<h3>{_escape(stats.anchor_pivot)} comparisons</h3>"
        + _comparison_content(stats)
    )
    if grouped.include_failures:
        content += (
            '<hr class="group-divider">'
            + f"<h3>{_escape(stats.anchor_pivot)} failures</h3>"
            + '<p class="method">The top 20 failures are ordered by ascending '
            + f'{_escape(stats.anchor_pivot)} '
            + "<code>wcMargin</code>. Missing comparison operands remain blank.</p>"
            + _ranked_case_table(
                analysis,
                item.parsed.schema,
                stats,
                stats.top_failure_cases,
                caption="Failure cases",
                empty=f"{stats.anchor_pivot} has no negative wcMargin values.",
            )
        )
    if grouped.include_marginal_passes:
        content += (
            '<hr class="group-divider">'
            + f"<h3>{_escape(stats.anchor_pivot)} marginal passes</h3>"
            + '<p class="method">The top 5 marginal passes are ordered by ascending '
            + f'{_escape(stats.anchor_pivot)} '
            + "<code>wcMargin</code>. Missing comparison operands remain blank.</p>"
            + _ranked_case_table(
                analysis,
                item.parsed.schema,
                stats,
                stats.top_pass_cases,
                caption="Marginal pass cases",
                empty=f"{stats.anchor_pivot} has no non-negative wcMargin values.",
            )
        )
    return _section(f"Group: {group_label}", content)


def _top_failure_table(
    analysis: AnalysisResult,
    item: MeasurementAnalysis,
) -> str:
    return _ranked_case_table(
        analysis,
        item.parsed.schema,
        item.statistics,
        item.statistics.top_failure_cases,
        caption="Failure cases",
        empty=f"{item.statistics.anchor_pivot} has no negative wcMargin values.",
    )


def _top_pass_table(
    analysis: AnalysisResult,
    item: MeasurementAnalysis,
) -> str:
    return _ranked_case_table(
        analysis,
        item.parsed.schema,
        item.statistics,
        item.statistics.top_pass_cases,
        caption="Marginal pass cases",
        empty=f"{item.statistics.anchor_pivot} has no non-negative wcMargin values.",
    )


def _ranked_case_table(
    analysis: AnalysisResult,
    schema: SheetSchema,
    stats: MeasurementStatistics,
    cases: Sequence[FailureCaseStatistics],
    *,
    caption: str,
    empty: str,
) -> str:
    all_metadata_headers = tuple(
        header for header, _ in sorted(schema.metadata_columns.items(), key=lambda item: item[1])
    )
    last_pivot_column = max(
        column
        for pivot in schema.pivots
        for column in pivot.statistics.values()
    )
    metadata_headers = tuple(
        header
        for header in all_metadata_headers
        if schema.metadata_columns[header] <= last_pivot_column
    )
    user_defined_headers = tuple(
        header
        for header in all_metadata_headers
        if schema.metadata_columns[header] > last_pivot_column
    )
    pivot_groups = tuple(
        (
            pivot.name,
            tuple(
                statistic
                for statistic, _ in sorted(
                    pivot.statistics.items(), key=lambda item: item[1]
                )
            )
            + (
                (FAIL_TYPE_DISPLAY_NAME,)
                if analysis.settings.add_fail_type
                else ()
            ),
        )
        for pivot in schema.pivots
    )
    comparison_headers = tuple(
        _comparison_header(stats, comparison.comparison_pivot)
        for comparison in stats.comparisons
    )
    groups = pivot_groups
    if user_defined_headers:
        groups += (("User defined", user_defined_headers),)
    groups += (("Comparison Deltas", comparison_headers),)
    rows: list[tuple[object, ...]] = []
    cell_classes: list[tuple[str, ...]] = []
    for case_statistics in cases:
        case = case_statistics.case
        row: list[object] = [case.worksheet_row]
        classes: list[str] = ["excel-worksheet-row"]
        for header in metadata_headers:
            value = case.metadata_values.get(header)
            row.append(value)
            if header == "Result?":
                status = str(value).strip().upper()
                classes.append(
                    "excel-result-pass" if status == "PASS" else "excel-result-fail"
                )
            elif header in {"LL", "UL"}:
                classes.append("excel-bound-value excel-column-shade-1")
            else:
                classes.append("excel-metadata-value")
        for pivot_index, pivot in enumerate(schema.pivots):
            margin = case.pivot_values[pivot.name].get("wcMargin")
            fail_type = case.pivot_fail_types.get(pivot.name)
            pivot_shade = _column_shade_class(pivot_index)
            for statistic, _ in sorted(
                pivot.statistics.items(), key=lambda field: field[1]
            ):
                row.append(case.pivot_raw_values[pivot.name].get(statistic))
                statistic_class = f"excel-pivot-value {pivot_shade}"
                if statistic == "wcMargin" and margin is not None and margin < 0:
                    statistic_class += " excel-pivot-failure"
                elif statistic in SPECIFICATION_STATISTICS and value_outside_limits(
                    case.pivot_values[pivot.name].get(statistic),
                    case.metadata_values,
                ):
                    statistic_class += " excel-pivot-failure"
                classes.append(statistic_class)
            if analysis.settings.add_fail_type:
                row.append(fail_type)
                fail_type_class = f"excel-fail-type {pivot_shade}"
                if fail_type is not None:
                    fail_type_class += " excel-pivot-failure"
                if fail_type == FAIL_TYPE_UNDEFINED:
                    fail_type_class += " fail-type-undef"
                classes.append(fail_type_class)
        for header in user_defined_headers:
            row.append(case.metadata_values.get(header))
            classes.append(
                f"excel-pivot-value {_column_shade_class(len(schema.pivots))}"
            )
        for comparison in stats.comparisons:
            delta = case_statistics.deltas[comparison.comparison_pivot]
            row.append(delta)
            semantic_class = _comparison_class(delta)
            classes.append(
                "excel-delta "
                + _column_shade_class(
                    len(schema.pivots) + bool(user_defined_headers)
                )
                + (f" {semantic_class}" if semantic_class else "")
            )
        rows.append(tuple(row))
        cell_classes.append(tuple(classes))
    return _grouped_table(
        ("Worksheet row",) + metadata_headers,
        groups,
        rows,
        caption,
        empty=empty,
        cell_classes=cell_classes,
        table_class="grouped-table excel-compliance-table",
    )


def _notes(analysis: AnalysisResult) -> str:
    return "<ul>" + "".join(f"<li>{_escape(note)}</li>" for note in analysis.notes) + "</ul>"


def _section(title: str, content: str) -> str:
    return f"<section><h2>{_escape(title)}</h2>{content}</section>"


def _table(
    headers: Sequence[object],
    rows: Iterable[Sequence[object]],
    caption: str,
    *,
    empty: str = "No data available.",
    cell_classes: Sequence[Sequence[str]] | None = None,
    header_classes: Sequence[str] | None = None,
    table_class: str = "",
) -> str:
    materialized = tuple(tuple(row) for row in rows)
    head = "".join(
        f'<th{class_attribute} scope="col">{_escape(value)}</th>'
        for index, value in enumerate(headers)
        for class_attribute in (
            (
                f' class="{_escape(header_classes[index])}"'
                if header_classes is not None
                and index < len(header_classes)
                and header_classes[index]
                else ""
            ),
        )
    )
    if materialized:
        body_rows = []
        for index, row in enumerate(materialized):
            classes = cell_classes[index] if cell_classes is not None else ()
            cells = "".join(
                f'<td{class_attribute}>{_render_cell(value)}</td>'
                for column, value in enumerate(row)
                for class_attribute in (
                    (
                        f' class="{_escape(classes[column])}"'
                        if column < len(classes) and classes[column]
                        else ""
                    ),
                )
            )
            body_rows.append(f"<tr>{cells}</tr>")
        body = "".join(body_rows)
    else:
        body = f'<tr><td colspan="{len(headers)}">{_escape(empty)}</td></tr>'
    class_attribute = f' class="{_escape(table_class)}"' if table_class else ""
    return (
        f'<div class="scroll"><table{class_attribute}><caption>{_escape(caption)}</caption>'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _grouped_table(
    leading_headers: Sequence[object],
    groups: Sequence[tuple[object, Sequence[object]]],
    rows: Iterable[Sequence[object]],
    caption: str,
    *,
    empty: str = "No data available.",
    cell_classes: Sequence[Sequence[str]] | None = None,
    table_class: str = "grouped-table",
) -> str:
    materialized = tuple(tuple(row) for row in rows)
    fixed_head = "".join(
        (
            '<th class="worksheet-spacer" aria-hidden="true"></th>'
            if index == 0
            else '<th class="header-spacer" aria-hidden="true"></th>'
        )
        for index, _ in enumerate(leading_headers)
    )
    group_head = "".join(
        f'<th class="pivot-group" scope="colgroup" colspan="{len(headers)}">'
        f'{_escape(label)}</th>'
        for label, headers in groups
        if headers
    )
    group_detail_head = "".join(
        f'<th scope="col">{_escape(header)}</th>'
        for _, headers in groups
        for header in headers
    )
    metadata_head = "".join(
        (
            f'<th class="worksheet-header" scope="col">{_escape(header)}</th>'
            if header == "Worksheet row"
            else f'<th scope="col">{_escape(header)}</th>'
        )
        for header in leading_headers
    )
    leading_spacers = "".join(
        '<th class="header-spacer" aria-hidden="true"></th>'
        for _ in leading_headers
    )
    group_spacers = "".join(
        '<th class="pivot-spacer" aria-hidden="true"></th>'
        for _, headers in groups
        for header in headers
    )
    total_columns = len(leading_headers) + sum(len(headers) for _, headers in groups)
    if materialized:
        body_rows = []
        for index, row in enumerate(materialized):
            classes = cell_classes[index] if cell_classes is not None else ()
            cell_values = []
            for column, value in enumerate(row):
                class_attribute = (
                    f' class="{_escape(classes[column])}"'
                    if column < len(classes) and classes[column]
                    else ""
                )
                cell_values.append(f'<td{class_attribute}>{_render_cell(value)}</td>')
            cells = "".join(cell_values)
            body_rows.append(f"<tr>{cells}</tr>")
        body = "".join(body_rows)
    else:
        body = f'<tr><td colspan="{total_columns}">{_escape(empty)}</td></tr>'
    return (
        f'<div class="scroll"><table class="{_escape(table_class)}"><caption>{_escape(caption)}</caption>'
        f"<thead><tr>{fixed_head}{group_head}</tr>"
        f"<tr>{leading_spacers}{group_detail_head}</tr>"
        f"<tr>{metadata_head}{group_spacers}</tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
    )


def _comparison_header(stats: MeasurementStatistics, comparison_pivot: str) -> str:
    definition = get_measurement_definition(stats.measurement)
    if definition.delta_fn == ANCHOR_MINUS_OTHER:
        return f"{stats.anchor_pivot} - {comparison_pivot}"
    if definition.delta_fn == OTHER_MINUS_ANCHOR:
        return f"{comparison_pivot} - {stats.anchor_pivot}"
    if definition.delta_fn == MIDPOINT_DEVIATION:
        return f"{comparison_pivot} deviation - {stats.anchor_pivot} deviation"
    raise ValueError(f"Unsupported measurement delta function '{definition.delta_fn}'.")


def _column_shade_class(group_index: int) -> str:
    shade = 2 if group_index % 2 == 0 else 1
    return f"excel-column-shade-{shade}"


def _comparison_class(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value < 0:
            return "comparison-degradation"
        if value > 0:
            return "comparison-improvement"
    return ""


def _append_class(existing: str, additional: str) -> str:
    return f"{existing} {additional}".strip()


def _format_rate(rate: Rate) -> str:
    if rate.error:
        return CALCULATION_ERROR
    if rate.percentage is None:
        return ""
    return f"{rate.percentage:.1f}%"


def _format_identity(identity: tuple[tuple[str, object], ...] | None) -> str:
    if identity is None:
        return ""
    return "; ".join(f"{name}={_format_number(value)}" for name, value in identity)


def _format_number(value: object) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, str) and value.strip().upper() == "N/A":
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _format_average(value: object) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.2f}"
    return _format_number(value)


def _render_cell(value: object) -> str:
    formatted = _format_number(value)
    if formatted == CALCULATION_ERROR:
        return '<strong class="calculation-error">ERROR</strong>'
    return html.escape(formatted, quote=True)


def _escape(value: object) -> str:
    return html.escape(_format_number(value), quote=True)
