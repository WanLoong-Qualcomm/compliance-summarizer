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
        tmp_path / "settings.json",
        workbook,
        background="<script>alert('x')</script>",
    )

    rendered = render_html(analyze(settings))

    assert "<svg" in rendered
    assert "http://" not in rendered
    assert "https://" not in rendered
    assert "<script>alert" not in rendered
    assert "&lt;script&gt;" in rendered
    assert "Result?" in rendered
    assert "Top 20 main-pivot failures" in rendered


def test_cli_runs_end_to_end(tmp_path, workbook_factory, sample_rows, capsys):
    workbook = workbook_factory(sample_rows)
    settings = write_settings(tmp_path / "settings.json", workbook)
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
