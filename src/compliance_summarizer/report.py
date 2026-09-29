"""Self-contained deterministic HTML rendering."""

from __future__ import annotations

import html
import os
import tempfile
from enum import Enum
from pathlib import Path
from typing import Iterable, Sequence

from .errors import ReportError
from .models import AnalysisResult, Rate


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
                "Pivot compliance",
                '<p class="method">A negative <code>wcMargin</code> is a failure. '
                "Blank or invalid values are excluded from each pivot's failure-rate calculation.</p>"
                + _pivot_table(analysis)
                + _failure_rate_chart(analysis),
            ),
            _section(
                "Main-pivot comparisons",
                '<p class="method"><code>delta = main NN_25C AVG − comparison '
                "NN_25C AVG</code>. For GAIN, negative is degradation and positive is "
                "improvement. Values within the inclusive tolerance are unchanged.</p>"
                + _comparison_table(analysis),
            ),
            _section(
                "Top 20 main-pivot failures",
                '<p class="method">Ordered by ascending main-pivot '
                '<code>wcMargin</code>. Missing comparison operands remain <code>N/A</code>.</p>'
                + _top_failure_table(analysis),
            ),
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
.scroll {{ overflow:auto; }} table {{ width:100%; border-collapse:collapse; font-size:13px; }}
caption {{ text-align:left; font-weight:700; margin-bottom:8px; }} th {{ background:#eef2fb;
position:sticky; top:0; text-align:left; }} th,td {{ border:1px solid var(--line); padding:8px 9px;
vertical-align:top; white-space:nowrap; }} tr:nth-child(even) td {{ background:#fafbfe; }}
.grouped-table thead tr:nth-child(2) th {{ top:34px; }}
.grouped-table .header-spacer {{ background:var(--panel); }}
.grouped-table .pivot-group {{ text-align:center; }}
.bad {{ color:var(--bad); font-weight:700; }} .good {{ color:var(--good); font-weight:700; }}
code {{ background:#edf0f6; padding:1px 4px; border-radius:4px; }} ul {{ margin-bottom:0; }}
.chart {{ overflow:auto; margin-top:18px; }} svg {{ min-width:620px; max-width:100%; height:auto; }}
</style>
</head>
<body><main>{body}</main></body>
</html>
"""


def _hero(analysis: AnalysisResult, failure_rate: Rate) -> str:
    stats = analysis.statistics
    failure_label = _format_rate(failure_rate)
    return f"""<header class="hero">
<h1>{_escape(stats.measurement)} compliance summary</h1>
<p class="subtitle">{_escape(analysis.settings.excel_file_path.name)} ·
{_escape(analysis.settings.compliance_sheet_name)} · generated {_escape(analysis.generated_at)}</p>
<div class="cards">
<div class="card"><span>Main pivot</span><strong>{_escape(stats.main_pivot)}</strong></div>
<div class="card"><span>Measurement rows</span><strong>{stats.case_count}</strong></div>
<div class="card"><span>Main failures</span><strong>{failure_rate.numerator}</strong></div>
<div class="card"><span>Main failure rate</span><strong>{_escape(failure_label)}</strong></div>
</div></header>"""


def _configuration_table(analysis: AnalysisResult) -> str:
    settings = analysis.settings
    rows = (
        ("Workbook", settings.excel_file_path),
        ("Sheet", settings.compliance_sheet_name),
        ("Test", settings.test),
        ("Measurement", ", ".join(settings.measurements)),
        ("Main pivot", settings.main_pivot),
        ("GAIN acceptable variation", settings.acceptable_variation["GAIN"]),
        ("Aggregate port groups", settings.aggregate_port_groups),
        ("Model bypass", settings.bypass_model),
        ("Background information", settings.background_information or "N/A"),
    )
    return _table(("Setting", "Value"), rows, "Validated runtime settings")


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
    )
    warnings = analysis.parsed.warnings
    if warnings:
        content += "<h3>Warnings</h3><ul>" + "".join(
            f"<li>{_escape(warning)}</li>" for warning in warnings
        ) + "</ul>"
    else:
        content += '<p class="muted">No coverage or parsing warnings were recorded.</p>'
    return content


def _pivot_table(analysis: AnalysisResult) -> str:
    rows = []
    for item in analysis.statistics.pivot_statistics:
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
    )


def _failure_rate_chart(analysis: AnalysisResult) -> str:
    items = analysis.statistics.pivot_statistics
    row_height = 42
    height = 42 + row_height * len(items)
    chart_width = 760
    bar_left = 190
    bar_width = 470
    rows: list[str] = []
    for index, item in enumerate(items):
        y = 28 + index * row_height
        percentage = item.failure_rate.percentage or 0.0
        width = percentage / 100.0 * bar_width
        rows.append(
            f'<text x="0" y="{y + 14}" fill="#172033">{_escape(item.pivot)}</text>'
            f'<rect x="{bar_left}" y="{y}" width="{bar_width}" height="20" rx="4" fill="#e8ecf5"/>'
            f'<rect x="{bar_left}" y="{y}" width="{width:.2f}" height="20" rx="4" fill="#b42318"/>'
            f'<text x="{bar_left + bar_width + 12}" y="{y + 14}" fill="#172033">'
            f'{_escape(_format_rate(item.failure_rate))}</text>'
        )
    return (
        '<div class="chart"><svg role="img" aria-label="Failure rate by pivot" '
        f'viewBox="0 0 {chart_width} {height}">'
        + "".join(rows)
        + "</svg></div>"
    )


def _comparison_table(analysis: AnalysisResult) -> str:
    rows = []
    for item in analysis.statistics.comparisons:
        rows.append(
            (
                item.comparison_pivot,
                _format_rate(item.degradation_rate),
                _format_rate(item.unchanged_rate),
                _format_rate(item.improvement_rate),
                _format_number(item.maximum_degradation),
                _format_number(item.maximum_improvement),
                _format_number(item.average_degradation_on_main_failures),
                item.degraded_main_failure_count,
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
            "Average degradation on main failures",
            "Degraded main failures",
        ),
        rows,
        f"Comparisons anchored on {analysis.statistics.main_pivot}",
        empty="No comparison pivots were discovered.",
    )


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
        f"Delta to {comparison.comparison_pivot}"
        for comparison in analysis.statistics.comparisons
    )
    rows: list[tuple[object, ...]] = []
    for item in analysis.statistics.top_failure_cases:
        case = item.case
        row: list[object] = [case.worksheet_row]
        row.extend(case.fixed_values.get(header) for header in fixed_headers)
        for pivot in schema.pivots:
            for statistic, _ in sorted(
                pivot.statistics.items(), key=lambda field: field[1]
            ):
                row.append(case.pivot_raw_values[pivot.name].get(statistic))
        row.extend(
            item.deltas[comparison.comparison_pivot]
            for comparison in analysis.statistics.comparisons
        )
        rows.append(tuple(row))
    return _grouped_table(
        ("Worksheet row",) + fixed_headers,
        pivot_groups + (("Comparison deltas", comparison_headers),),
        rows,
        f"Worst {min(20, len(rows))} failures for {analysis.statistics.main_pivot}",
        empty="The main pivot has no negative wcMargin values.",
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
) -> str:
    materialized = tuple(tuple(row) for row in rows)
    head = "".join(f'<th scope="col">{_escape(value)}</th>' for value in headers)
    if materialized:
        body = "".join(
            "<tr>" + "".join(f"<td>{_escape(value)}</td>" for value in row) + "</tr>"
            for row in materialized
        )
    else:
        body = f'<tr><td colspan="{len(headers)}">{_escape(empty)}</td></tr>'
    return (
        f'<div class="scroll"><table><caption>{_escape(caption)}</caption>'
        f"<thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _grouped_table(
    fixed_headers: Sequence[object],
    groups: Sequence[tuple[object, Sequence[object]]],
    rows: Iterable[Sequence[object]],
    caption: str,
    *,
    empty: str = "No data available.",
) -> str:
    materialized = tuple(tuple(row) for row in rows)
    fixed_head = "".join(
        '<th class="header-spacer" aria-hidden="true"></th>'
        for _ in fixed_headers
    )
    group_head = "".join(
        f'<th class="pivot-group" scope="colgroup" colspan="{len(headers)}">'
        f'{_escape(label)}</th>'
        for label, headers in groups
        if headers
    )
    detail_head = "".join(
        f'<th scope="col">{_escape(header)}</th>'
        for header in fixed_headers
    ) + "".join(
        f'<th scope="col">{_escape(header)}</th>'
        for _, headers in groups
        for header in headers
    )
    total_columns = len(fixed_headers) + sum(len(headers) for _, headers in groups)
    if materialized:
        body = "".join(
            "<tr>" + "".join(f"<td>{_escape(value)}</td>" for value in row) + "</tr>"
            for row in materialized
        )
    else:
        body = f'<tr><td colspan="{total_columns}">{_escape(empty)}</td></tr>'
    return (
        f'<div class="scroll"><table class="grouped-table"><caption>{_escape(caption)}</caption>'
        f"<thead><tr>{fixed_head}{group_head}</tr><tr>{detail_head}</tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
    )


def _format_rate(rate: Rate) -> str:
    if rate.percentage is None:
        return "N/A"
    return f"{rate.percentage:.1f}%"


def _format_identity(identity: tuple[tuple[str, object], ...] | None) -> str:
    if identity is None:
        return "N/A"
    return "; ".join(f"{name}={_format_number(value)}" for name, value in identity)


def _format_number(value: object) -> str:
    if value is None or value == "":
        return "N/A"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _escape(value: object) -> str:
    return html.escape(_format_number(value), quote=True)
