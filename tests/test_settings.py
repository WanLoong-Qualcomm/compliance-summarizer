import json

import pytest

from compliance_summarizer.settings import (
    DEFAULT_SETTINGS,
    SettingsError,
    create_default_settings,
    load_settings,
)


def write_settings(path, values):
    path.write_text(json.dumps(values), encoding="utf-8")


def valid_settings(workbook_path):
    return {
        "excel_file_path": str(workbook_path),
        "compliance_sheet_name": "Combined",
        "tests_to_report": ["GAIN"],
        "acceptable_variation": {"GAIN": 0.2},
        "background_information": "Bench run",
        "pivot_field_of_interest": "GF-PROTO",
        "bypass_model": True,
    }


def test_fresh_settings_file_has_exact_default_json_and_is_not_overwritten(tmp_path):
    settings_path = tmp_path / "settings.json"

    assert create_default_settings(settings_path) is True
    assert json.loads(settings_path.read_text(encoding="utf-8")) == DEFAULT_SETTINGS

    original = settings_path.read_text(encoding="utf-8")
    settings_path.write_text(original.replace('"Combined"', '"Edited"'), encoding="utf-8")
    assert create_default_settings(settings_path) is False
    assert settings_path.read_text(encoding="utf-8") != original


def test_valid_edited_settings_load_successfully(tmp_path):
    workbook_path = tmp_path / "input.XLSX"
    workbook_path.write_bytes(b"placeholder")
    settings_path = tmp_path / "settings.json"
    write_settings(settings_path, valid_settings(workbook_path))

    settings = load_settings(settings_path, available_pivots=("GF-PROTO", "GF-QMOM"))

    assert settings.excel_file_path == str(workbook_path)
    assert settings.tests_to_report == ("GAIN",)
    assert settings.acceptable_variation["GAIN"] == 0.2
    assert settings.bypass_model is True


def test_invalid_json_has_location_and_actionable_message(tmp_path):
    settings_path = tmp_path / "settings.json"
    settings_path.write_text('{"excel_file_path": ', encoding="utf-8")

    with pytest.raises(SettingsError, match="line 1, column"):
        load_settings(settings_path)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("excel_file_path", "", "nonempty"),
        ("excel_file_path", "missing.csv", "xlsx or .xlsm"),
        ("compliance_sheet_name", 42, "string"),
        ("tests_to_report", ["SSNF"], "only the nonempty list"),
        ("acceptable_variation", {"GAIN": -1}, "greater than or equal to zero"),
        ("background_information", [], "string"),
        ("pivot_field_of_interest", "", "nonempty"),
        ("bypass_model", False, "must be true"),
    ],
)
def test_each_invalid_field_category_is_reported(tmp_path, field, value, message):
    workbook_path = tmp_path / "input.xlsx"
    workbook_path.write_bytes(b"placeholder")
    values = valid_settings(workbook_path)
    values[field] = value
    settings_path = tmp_path / "settings.json"
    write_settings(settings_path, values)

    with pytest.raises(SettingsError, match=message):
        load_settings(settings_path)


def test_missing_and_unsupported_fields_are_reported(tmp_path):
    workbook_path = tmp_path / "input.xlsx"
    workbook_path.write_bytes(b"placeholder")
    values = valid_settings(workbook_path)
    values.pop("background_information")
    values["unsupported"] = True
    settings_path = tmp_path / "settings.json"
    write_settings(settings_path, values)

    with pytest.raises(SettingsError, match="Missing required settings field"):
        load_settings(settings_path)

    values = valid_settings(workbook_path)
    values["unsupported"] = True
    write_settings(settings_path, values)
    with pytest.raises(SettingsError, match="Unsupported settings field"):
        load_settings(settings_path)


def test_selected_pivot_must_match_discovered_names_when_available(tmp_path):
    workbook_path = tmp_path / "input.xlsx"
    workbook_path.write_bytes(b"placeholder")
    values = valid_settings(workbook_path)
    values["pivot_field_of_interest"] = "gf-proto"
    settings_path = tmp_path / "settings.json"
    write_settings(settings_path, values)

    with pytest.raises(SettingsError, match="Available pivots: 'GF-PROTO'"):
        load_settings(settings_path, available_pivots=("GF-PROTO",))
