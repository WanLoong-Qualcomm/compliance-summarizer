from __future__ import annotations

import re

from compliance_summarizer.app import analyze, run
from compliance_summarizer.cli import main
from compliance_summarizer.report import render_html

from conftest import write_settings


def test_report_is_self_contained_and_escapes_user_text(
    tmp_path, workbook_factory, sample_rows
):
    workbook = workbook_factory(sample_rows)
    settings = write_settings(
        tmp_path / "JUI.json",
        workbook,
        background="<script>alert('x')</script>",
    )

    rendered = render_html(analyze(settings))

    assert "<svg" not in rendered
    assert "http://" not in rendered
    assert "https://" not in rendered
    assert "<script>alert" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "Result?" in rendered
    assert "Overall DUT-1_VAR1 failures" in rendered
    assert "Overall DUT-1_VAR1 marginal passes" in rendered
    assert '<div class="card"><span>Anchor</span><strong>DUT-1_VAR1</strong></div>' in rendered
    assert "The top 20 failures are ordered" in rendered
    assert "The top 5 marginal passes are ordered" in rendered
    assert "Cases" in rendered
    assert "Average degradation" in rendered
    assert "Average improvement" in rendered
    assert ">0.50</td>" in rendered
    assert "comparison-degradation" in rendered
    assert "comparison-improvement" in rendered
    assert "compliance-failure" in rendered
    assert "compliance-clear" in rendered
    assert "compliance-worst-failure" in rendered
    assert "anchor-pivot-row" in rendered
    assert "FAIL_type" not in rendered
    assert ">DUT-1_VAR1 - DUT-2_VAR1</th>" in rendered
    assert "Degraded DUT-1_VAR1 failures" not in rendered


def test_report_tables_retain_arbitrary_metadata_fields(
    tmp_path, workbook_factory, sample_rows
):
    rows = [
        {**row, "TEMP": temperature}
        for row, temperature in zip(sample_rows[:3], (-50, 25, 110), strict=True)
    ]
    workbook = workbook_factory(rows, extra_headers=("TEMP",))
    settings = write_settings(tmp_path / "JUI.json", workbook)

    rendered = render_html(analyze(settings))

    assert ">TEMP</th>" in rendered
    assert ">-50</td>" in rendered


def test_trailing_user_defined_columns_follow_pivot_sections(
    tmp_path, workbook_factory, sample_rows
):
    rows = [{**sample_rows[0], "USER_A": "custom", "USER_B": 7}]
    workbook = workbook_factory(
        rows,
        trailing_headers=("USER_A", "USER_B"),
    )
    settings = write_settings(tmp_path / "JUI.json", workbook)

    rendered = render_html(analyze(settings))
    failure_table = rendered.split("<caption>Failure cases</caption>", 1)[1]
    failure_head = failure_table.split("</thead>", 1)[0]

    assert ">User defined</th>" in failure_head
    assert failure_head.index(">DUT-2_VAR1</th>") < failure_head.index(">User defined</th>")
    assert failure_head.index(">USER_A</th>") > failure_head.index(">MAX</th>")
    assert '<td class="excel-pivot-value excel-column-shade-2">custom</td>' in failure_table


def test_compliance_table_alternates_column_group_shades(
    tmp_path, workbook_factory, sample_rows
):
    rows = [{**sample_rows[0], "USER_A": "custom"}]
    workbook = workbook_factory(rows, trailing_headers=("USER_A",))
    settings = write_settings(
        tmp_path / "JUI.json",
        workbook,
        add_fail_type=True,
    )

    rendered = render_html(analyze(settings))
    failure_table = rendered.split("<caption>Failure cases</caption>", 1)[1]

    assert '<td class="excel-bound-value excel-column-shade-1">8</td>' in failure_table
    assert '<td class="excel-bound-value excel-column-shade-1">12</td>' in failure_table
    assert '<td class="excel-pivot-value excel-column-shade-2">9.2</td>' in failure_table
    assert '<td class="excel-pivot-value excel-column-shade-1">8.8</td>' in failure_table
    assert '<td class="excel-pivot-value excel-column-shade-2">custom</td>' in failure_table
    assert '<td class="excel-delta excel-column-shade-1 comparison-improvement">0.5</td>' in failure_table
    assert ".excel-column-shade-2 { background:#E6DDF3; }" in rendered
    assert "tbody tr:nth-child(even) td.excel-column-shade-1" in rendered
    assert "tbody tr:nth-child(even) td.excel-column-shade-2" in rendered


def test_report_tables_include_fail_type_for_each_pivot_and_style_undef(
    tmp_path, workbook_factory, sample_rows
):
    workbook = workbook_factory(sample_rows)
    settings = write_settings(
        tmp_path / "JUI.json",
        workbook,
        add_fail_type=True,
    )

    rendered = render_html(analyze(settings))

    assert rendered.count(">FAIL type</th>") == 4
    assert ">UNDEF</td>" in rendered
    assert "excel-fail-type excel-column-shade-2 excel-pivot-failure fail-type-undef" in rendered

    failure_table = rendered.split("<caption>Failure cases</caption>", 1)[1]
    failure_head = failure_table.split("</thead>", 1)[0]
    assert failure_head.count("<tr>") == 3
    assert failure_head.index(">MIN</th>") < failure_head.index(">LNAMODE</th>")
    assert 'th.worksheet-spacer { background:var(--panel); border:0; }' in rendered
    assert 'class="pivot-spacer"' in rendered


def test_report_highlights_each_out_of_spec_pivot_value(
    tmp_path, workbook_factory, sample_rows
):
    template = sample_rows[0]
    rows = [
        {
            **template,
            "CHANNEL": "LL",
            "LL": 0.0,
            "UL": 5.0,
            "DUT-1_VAR1": {
                **template["DUT-1_VAR1"],
                "MIN": -1.0,
                "MAX": 4.0,
                "wcMargin": -1.0,
            },
        },
        {
            **template,
            "CHANNEL": "UL",
            "LL": 0.0,
            "UL": 5.0,
            "DUT-1_VAR1": {
                **template["DUT-1_VAR1"],
                "MIN": 2.0,
                "MAX": 6.0,
                "wcMargin": -1.0,
            },
        },
        {
            **template,
            "CHANNEL": "TIE",
            "LL": 0.0,
            "UL": 5.0,
            "DUT-1_VAR1": {
                **template["DUT-1_VAR1"],
                "MIN": -1.0,
                "MAX": 6.0,
                "wcMargin": -1.0,
            },
        },
    ]
    settings = write_settings(
        tmp_path / "JUI.json",
        workbook_factory(rows),
        add_fail_type=True,
    )

    rendered = render_html(analyze(settings))
    rendered_rows = re.findall(r"<tr>(.*?)</tr>", rendered, flags=re.DOTALL)
    rows_by_channel = {
        channel: next(row for row in rendered_rows if f">{channel}</td>" in row)
        for channel in ("LL", "UL", "TIE")
    }
    red_value = '<td class="excel-pivot-value excel-column-shade-2 excel-pivot-failure">'

    assert rows_by_channel["LL"].count(f"{red_value}-1</td>") == 2
    assert f"{red_value}4</td>" not in rows_by_channel["LL"]
    assert f"{red_value}10</td>" in rows_by_channel["LL"]
    assert '<td class="excel-pivot-value excel-column-shade-2">9.2</td>' in rows_by_channel["LL"]
    assert f'{red_value}2</td>' not in rows_by_channel["UL"]
    assert f"{red_value}6</td>" in rows_by_channel["UL"]
    assert f"{red_value}10</td>" in rows_by_channel["UL"]
    assert f"{red_value}6</td>" in rows_by_channel["TIE"]


def test_report_repeats_the_current_summary_for_each_measurement(
    tmp_path, workbook_factory, sample_rows
):
    rows = [
        {**sample_rows[0], "TESTNAME": "GAIN"},
        {**sample_rows[1], "TESTNAME": "GCIB"},
    ]
    workbook = workbook_factory(rows)
    settings = write_settings(
        tmp_path / "JUI.json",
        workbook,
        testnames=["GAIN", "GCIB"],
    )

    rendered = render_html(analyze(settings))

    assert rendered.count("<h1>GAIN compliance summary</h1>") == 1
    assert rendered.count("<h1>GCIB compliance summary</h1>") == 1
    assert rendered.count(">Run configuration</h2>") == 1
    assert rendered.count(">Methodology and assumptions</h2>") == 1
    assert rendered.count(">Overall pivot compliance</h2>") == 2
    assert rendered.count('<article class="measurement-summary">') == 2
    assert ".measurement-summary { margin-top:24px; }" in rendered
    assert ".measurement-summary + .measurement-summary" in rendered
    assert rendered.index(">Run configuration</h2>") < rendered.index(">GAIN compliance summary</h1>")
    assert rendered.index(">Methodology and assumptions</h2>") > rendered.index(">GCIB compliance summary</h1>")


def test_midpoint_delta_header_describes_deviation_direction(
    tmp_path, workbook_factory, sample_rows
):
    row = {
        **sample_rows[0],
        "TESTNAME": "GAIN-DNL",
        "DUT-1_VAR1": {
            **sample_rows[0]["DUT-1_VAR1"],
            "NN_25c AVG": 10.5,
        },
        "DUT-2_VAR1": {
            **sample_rows[0]["DUT-2_VAR1"],
            "NN_25c AVG": 11.5,
        },
    }
    settings = write_settings(
        tmp_path / "JUI.json",
        workbook_factory([row]),
        testnames=["GAIN-DNL"],
    )

    rendered = render_html(analyze(settings))

    assert ">DUT-2_VAR1 deviation - DUT-1_VAR1 deviation</th>" in rendered


def test_anchor_pivot_is_first_in_pivot_compliance_table(
    tmp_path, workbook_factory, sample_rows
):
    workbook = workbook_factory(sample_rows[:3])
    settings = write_settings(
        tmp_path / "JUI.json",
        workbook,
        anchor_pivot="DUT-2_VAR1",
    )

    rendered = render_html(analyze(settings))
    compliance_table = rendered.split(
        "<caption>Pivot compliance</caption>",
        1,
    )[1]

    assert compliance_table.index(">DUT-2_VAR1</td>") < compliance_table.index(">DUT-1_VAR1</td>")

    coverage_table = rendered.split(
        "<caption>Coverage gaps</caption>",
        1,
    )[1]
    assert coverage_table.index(">DUT-2_VAR1</td>") < coverage_table.index(">DUT-1_VAR1</td>")


def test_passing_worst_wc_margin_is_highlighted_green(
    tmp_path, workbook_factory, sample_rows
):
    row = {
        **sample_rows[0],
        "DUT-1_VAR1": {
            **sample_rows[0]["DUT-1_VAR1"],
            "wcMargin": 0.0,
        },
        "DUT-2_VAR1": {
            **sample_rows[0]["DUT-2_VAR1"],
            "wcMargin": 1.0,
        },
    }
    settings = write_settings(tmp_path / "JUI.json", workbook_factory([row]))

    rendered = render_html(analyze(settings))
    compliance_table = rendered.split(
        "<caption>Pivot compliance</caption>",
        1,
    )[1]

    assert '<td class="anchor-pivot-row compliance-clear">0</td>' in compliance_table


def test_cli_runs_end_to_end(tmp_path, workbook_factory, sample_rows, capsys):
    workbook = workbook_factory(sample_rows)
    settings = write_settings(tmp_path / "JUI.json", workbook)
    output = tmp_path / "report.html"

    exit_code = main(["--settings", str(settings), "--output", str(output)])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert output.is_file()
    assert "Processed 3 GAIN row(s)" in captured.out
    assert "AI generation: bypassed" in captured.out


def test_default_run_writes_timestamped_report_to_outputs_directory(
    tmp_path, workbook_factory, sample_rows
):
    workbook = workbook_factory(sample_rows)
    settings = write_settings(
        tmp_path / "JUI.json",
        workbook,
        outputs_directory="generated-reports",
    )

    _, first = run(settings)
    _, second = run(settings)

    assert first.parent == (tmp_path / "generated-reports").resolve()
    assert second.parent == first.parent
    assert first != second
    assert re.fullmatch(
        r"compliance-summary_\d{8}_\d{6}(?:_\d+)?\.html",
        first.name,
    )
    assert first.is_file()
    assert second.is_file()


def test_cli_reports_actionable_failure(tmp_path, capsys):
    exit_code = main(["--settings", str(tmp_path / "missing.json")])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--init-settings" in captured.err
