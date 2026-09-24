import json

from compliance_summarizer.cli import main


def test_cli_starts(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")

    assert main([]) == 0

    captured = capsys.readouterr()
    assert "compliance-summarizer 0.1.0 (baseline)" in captured.out
    assert "Model stage: AI generation is bypassed in v0.1." in captured.out
    assert (tmp_path / "settings.json").is_file()


def test_cli_loads_existing_valid_settings(capsys, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    workbook_path = tmp_path / "input.xlsx"
    workbook_path.write_bytes(b"placeholder")
    (tmp_path / "settings.json").write_text(
        json.dumps(
            {
                "excel_file_path": str(workbook_path),
                "compliance_sheet_name": "Combined",
                "tests_to_report": ["GAIN"],
                "acceptable_variation": {"GAIN": 0.2},
                "background_information": "",
                "pivot_field_of_interest": "GF-PROTO",
                "bypass_model": True,
            }
        ),
        encoding="utf-8",
    )

    assert main([]) == 0
    assert "Settings loaded successfully." in capsys.readouterr().out


def test_cli_reports_invalid_existing_settings_without_stack_trace(
    capsys, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("builtins.input", lambda _prompt: "")
    (tmp_path / "settings.json").write_text("{}", encoding="utf-8")

    assert main([]) == 2
    captured = capsys.readouterr()
    assert "Settings error:" in captured.err
    assert "Traceback" not in captured.err


def test_cli_aborts_before_completion_when_settings_pause_reaches_eof(
    capsys, monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)

    def raise_eof(_prompt):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)

    assert main([]) == 2
    captured = capsys.readouterr()
    assert "Input aborted:" in captured.err
    assert "Model stage:" not in captured.out
