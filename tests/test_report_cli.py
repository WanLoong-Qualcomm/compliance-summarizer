from __future__ import annotations

from compliance_summarizer.app import analyze
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
    assert "main-pivot-row" in rendered
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
        acceptable_variation={"GAIN": 0.2, "GCIB": 0.2},
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


def test_main_pivot_is_first_in_pivot_compliance_table(
    tmp_path, workbook_factory, sample_rows
):
    workbook = workbook_factory(sample_rows[:3])
    settings = write_settings(
        tmp_path / "JUI.json",
        workbook,
        main_pivot="DUT-2_VAR1",
    )

    rendered = render_html(analyze(settings))
    compliance_table = rendered.split(
        "<caption>Pivot compliance</caption>",
        1,
    )[1]

    assert compliance_table.index(">DUT-2_VAR1</td>") < compliance_table.index(">DUT-1_VAR1</td>")


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


def test_cli_reports_actionable_failure(tmp_path, capsys):
    exit_code = main(["--settings", str(tmp_path / "missing.json")])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--init-settings" in captured.err
