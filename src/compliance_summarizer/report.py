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
from .models import (
    CALCULATION_ERROR,
    AnalysisResult,
    GroupedAnalysis,
    MeasurementStatistics,
    Rate,
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
    settings = analysis.settings
    parsed = analysis.parsed
    stats = analysis.statistics
    main = next(item for item in stats.pivot_statistics if item.pivot == stats.main_pivot)
    body = "".join(
        (
            _hero(analysis, main.failure_rate),
            _section("Run configuration", _configuration_table(analysis)),
            _section("Coverage and validation", _coverage(analysis)),
            _section(
                "Overall pivot compliance",
                _pivot_compliance_content(analysis.statistics),
            ),
            _section(
                f"Overall {stats.main_pivot} comparisons",
                _comparison_content(analysis.statistics),
            ),
            _section(
                f"Overall {stats.main_pivot} failures",
                f'<p class="method">The top 20 failures are ordered by ascending '
                f'{_escape(stats.main_pivot)} '
                "<code>wcMargin</code>. Missing comparison operands remain blank.</p>"
                + _top_failure_table(analysis),
            ),
            _grouped_sections(analysis),
            _section("Methodology and assumptions", _notes(analysis)),
        )
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Compliance Summary — {_escape(stats.measurement)}</title>
<style>
:root {{ color-scheme: light; --ink:#172033; --muted:#5d6778; --line:#d9dfeb;
--panel:#fff; --wash:#f4f7fb; --brand:#3157d5; --bad:#b42318; --good:#18794e; }}
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
.scroll {{ overflow:auto; }} table {{ width:100%; border:1px solid #7F7F7F; border-collapse:collapse; font-size:13px; }}
caption {{ text-align:left; font-weight:700; margin-bottom:8px; }} th {{ background:#eef2fb;
position:sticky; top:0; text-align:left; }} th,td {{ border:1px solid #7F7F7F; padding:8px 9px;
vertical-align:top; white-space:nowrap; }} tr:nth-child(even) td {{ background:#fafbfe; }}
.grouped-table thead tr:nth-child(2) th {{ top:34px; }}
.grouped-table .header-spacer {{ background:var(--panel); }}
.grouped-table .pivot-group {{ text-align:center; }}
.excel-summary-table thead th,
.excel-compliance-table thead th {{ background:#FCE4D6; color:#000000; text-align:center; }}
.excel-compliance-table thead th.header-spacer {{ background:var(--panel); border:0; }}
.excel-compliance-table thead th.worksheet-spacer {{ background:var(--panel); border:1px solid #7F7F7F; }}
.excel-compliance-table thead th.worksheet-header {{ background:var(--panel); }}
.excel-compliance-table tbody td {{ text-align:center; }}
.excel-compliance-table tbody td.excel-fixed-value {{ background:#E2F0D9; }}
.excel-compliance-table tbody td.excel-bound-value {{ background:#D9E2F3; color:#0000FF; }}
.excel-compliance-table tbody td.excel-pivot-value,
.excel-compliance-table tbody td.excel-delta {{ background:#D9E2F3; }}
.excel-compliance-table tbody tr:nth-child(even) td.excel-bound-value,
.excel-compliance-table tbody tr:nth-child(even) td.excel-pivot-value,
.excel-compliance-table tbody tr:nth-child(even) td.excel-delta {{ background:#FFFFFF; }}
.excel-compliance-table tbody td.excel-pivot-failure {{ color:#FF0000; }}
.excel-compliance-table tbody td.excel-result-pass {{ background:#C6EFCE; color:#006100; }}
.excel-compliance-table tbody td.excel-result-fail {{ background:#FFC7CE; color:#9C0006; }}
.calculation-error {{ color:#C00000; font-weight:700; }}
.bad {{ color:var(--bad); font-weight:700; }} .good {{ color:var(--good); font-weight:700; }}
code {{ background:#edf0f6; padding:1px 4px; border-radius:4px; }} ul {{ margin-bottom:0; }}
</style>
</head>
<body><main>{body}</main></body>
</html>
"""


def _hero(analysis: AnalysisResult, failure_rate: Rate) -> str:
    stats = analysis.statistics
    main_pivot = _escape(stats.main_pivot)
    failure_label = _format_rate(failure_rate)
    return f"""<header class="hero">
<h1>{_escape(stats.measurement)} compliance summary</h1>
<p class="subtitle">{_escape(analysis.settings.excel_file_path.name)} ·
{_escape(analysis.settings.compliance_sheet_name)} · generated {_escape(analysis.generated_at)}</p>
<div class="cards">
<div class="card"><span>{main_pivot}</span><strong>Baseline</strong></div>
<div class="card"><span>Measurement rows</span><strong>{stats.case_count}</strong></div>
<div class="card"><span>{main_pivot} failures</span><strong>{failure_rate.numerator}</strong></div>
<div class="card"><span>{main_pivot} failure rate</span><strong>{_render_cell(failure_label)}</strong></div>
</div></header>"""


def _configuration_table(analysis: AnalysisResult) -> str:
    settings = analysis.settings
    rows = (
        ("Workbook", settings.excel_file_path),
        ("Sheet", settings.compliance_sheet_name),
        ("Test", settings.test),
        ("Measurement", ", ".join(settings.measurements)),
        ("Baseline", settings.main_pivot),
        ("GAIN acceptable variation", settings.acceptable_variation["GAIN"]),
        ("Group by", ", ".join(settings.group_by) or "(none)"),
        ("Model bypass", settings.bypass_model),
        ("Background information", settings.background_information or ""),
    )
    return _table(
        ("Setting", "Value"),
        rows,
        "Validated runtime settings",
        table_class="excel-summary-table",
    )


def _coverage(analysis: AnalysisResult) -> str:
    rows = []
    for item in analysis.parsed.coverage:
        rows.append(
            (
                item.pivot,
                item.rows_with_gaps,
                sum(item.malformed_by_field.values()),
            )
        )
    content = _table(
        (
            "Pivot",
            "Coverage gaps",
            "Malformed/non-finite values",
        ),
        rows,
        "Coverage-gap summary",
        table_class="excel-summary-table",
    )
    warnings = (*analysis.parsed.warnings, *analysis.group_warnings)
    if warnings:
        content += "<h3>Warnings</h3><ul>" + "".join(
            f"<li>{_escape(warning)}</li>" for warning in warnings
        ) + "</ul>"
    else:
        content += '<p class="muted">No coverage or parsing warnings were recorded.</p>'
    return content


def _pivot_table(stats: MeasurementStatistics) -> str:
    rows = []
    for item in stats.pivot_statistics:
        rows.append(
            (
                item.pivot,
                item.failure_rate.numerator,
                _format_rate(item.failure_rate),
                _format_number(item.worst_wc_margin),
                _format_identity(item.worst_failure_path),
            )
        )
    return _table(
        (
            "Pivot",
            "Failures",
            "Failure rate",
            "Worst wcMargin",
            "Worst failure path",
        ),
        rows,
        "Per-pivot compliance statistics",
        table_class="excel-summary-table",
    )


def _comparison_table(stats: MeasurementStatistics) -> str:
    main_pivot = stats.main_pivot
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
                item.degraded_main_failure_count,
                _format_number(item.maximum_degradation_on_main_failures),
                _format_number(item.average_degradation_on_main_failures),
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
            f"Degraded {main_pivot} failures",
            f"Maximum degradation on {main_pivot} failures",
            f"Average degradation on {main_pivot} failures",
        ),
        rows,
        f"Comparisons anchored on {stats.main_pivot}",
        empty="No comparison pivots were discovered.",
        table_class="excel-summary-table",
    )


def _pivot_compliance_content(stats: MeasurementStatistics) -> str:
    return (
        '<p class="method">A negative <code>wcMargin</code> is a failure. '
        "Blank or invalid values are excluded from each pivot's failure-rate calculation.</p>"
        + _pivot_table(stats)
    )


def _comparison_content(stats: MeasurementStatistics) -> str:
    return (
        f'<p class="method"><code>delta = {_escape(stats.main_pivot)} NN_25C AVG '
        "− comparison NN_25C AVG</code>. For GAIN, negative is degradation and positive is "
        "improvement. Values within the inclusive tolerance are unchanged.</p>"
        + _comparison_table(stats)
    )


def _grouped_sections(analysis: AnalysisResult) -> str:
    return "".join(
        _grouped_section(grouped)
        for grouped in analysis.grouped_analyses
    )


def _grouped_section(grouped: GroupedAnalysis) -> str:
    stats = grouped.statistics
    group_label = format_group_key(grouped.group_key)
    content = (
        _section("Pivot compliance", _pivot_compliance_content(stats))
        + _section(
            f"{stats.main_pivot} comparisons",
            _comparison_content(stats),
        )
    )
    return _section(f"Group: {group_label}", content)


def _top_failure_table(analysis: AnalysisResult) -> str:
    schema = analysis.parsed.schema
    fixed_headers = tuple(
        header for header, _ in sorted(schema.fixed_columns.items(), key=lambda item: item[1])
    )
    pivot_groups = tuple(
        (
            pivot.name,
            tuple(
                statistic
                for statistic, _ in sorted(
                    pivot.statistics.items(), key=lambda item: item[1]
                )
            ),
        )
        for pivot in schema.pivots
    )
    comparison_headers = tuple(
        f"Δ({analysis.statistics.main_pivot}, {comparison.comparison_pivot})"
        for comparison in analysis.statistics.comparisons
    )
    rows: list[tuple[object, ...]] = []
    cell_classes: list[tuple[str, ...]] = []
    for item in analysis.statistics.top_failure_cases:
        case = item.case
        row: list[object] = [case.worksheet_row]
        classes: list[str] = ["excel-worksheet-row"]
        for header in fixed_headers:
            value = case.fixed_values.get(header)
            row.append(value)
            if header == "Result?":
                status = str(value).strip().upper()
                classes.append(
                    "excel-result-pass" if status == "PASS" else "excel-result-fail"
                )
            elif header in {"LL", "UL"}:
                classes.append("excel-bound-value")
            else:
                classes.append("excel-fixed-value")
        for pivot in schema.pivots:
            margin = case.pivot_values[pivot.name].get("wcMargin")
            pivot_class = "excel-pivot-value"
            if margin is not None and margin < 0:
                pivot_class += " excel-pivot-failure"
            for statistic, _ in sorted(
                pivot.statistics.items(), key=lambda field: field[1]
            ):
                row.append(case.pivot_raw_values[pivot.name].get(statistic))
                classes.append(pivot_class)
        row.extend(
            item.deltas[comparison.comparison_pivot]
            for comparison in analysis.statistics.comparisons
        )
        classes.extend("excel-delta" for _ in analysis.statistics.comparisons)
        rows.append(tuple(row))
        cell_classes.append(tuple(classes))
    return _grouped_table(
        ("Worksheet row",) + fixed_headers,
        pivot_groups + (("Comparison Deltas", comparison_headers),),
        rows,
        f"Worst {min(20, len(rows))} failures for {analysis.statistics.main_pivot}",
        empty=f"{analysis.statistics.main_pivot} has no negative wcMargin values.",
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
    table_class: str = "",
) -> str:
    materialized = tuple(tuple(row) for row in rows)
    head = "".join(f'<th scope="col">{_escape(value)}</th>' for value in headers)
    if materialized:
        body = "".join(
            "<tr>" + "".join(f"<td>{_render_cell(value)}</td>" for value in row) + "</tr>"
            for row in materialized
        )
    else:
        body = f'<tr><td colspan="{len(headers)}">{_escape(empty)}</td></tr>'
    class_attribute = f' class="{_escape(table_class)}"' if table_class else ""
    return (
        f'<div class="scroll"><table{class_attribute}><caption>{_escape(caption)}</caption>'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _grouped_table(
    fixed_headers: Sequence[object],
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
        for index, _ in enumerate(fixed_headers)
    )
    group_head = "".join(
        f'<th class="pivot-group" scope="colgroup" colspan="{len(headers)}">'
        f'{_escape(label)}</th>'
        for label, headers in groups
        if headers
    )
    detail_head = "".join(
        (
            f'<th class="worksheet-header" scope="col">{_escape(header)}</th>'
            if header == "Worksheet row"
            else f'<th scope="col">{_escape(header)}</th>'
        )
        for header in fixed_headers
    ) + "".join(
        f'<th scope="col">{_escape(header)}</th>'
        for _, headers in groups
        for header in headers
    )
    total_columns = len(fixed_headers) + sum(len(headers) for _, headers in groups)
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
        f"<thead><tr>{fixed_head}{group_head}</tr><tr>{detail_head}</tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
    )


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


def _render_cell(value: object) -> str:
    formatted = _format_number(value)
    if formatted == CALCULATION_ERROR:
        return '<strong class="calculation-error">ERROR</strong>'
    return html.escape(formatted, quote=True)


def _escape(value: object) -> str:
    return html.escape(_format_number(value), quote=True)
