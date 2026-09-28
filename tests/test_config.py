from __future__ import annotations

import json

import pytest

from compliance_summarizer.config import create_settings_template, load_settings
from compliance_summarizer.errors import ConfigurationError

from conftest import write_settings


def test_load_settings_resolves_workbook_relative_to_settings(
    tmp_path, workbook_factory, sample_rows
):
    workbook = workbook_factory(sample_rows)
    path = write_settings(tmp_path / "settings.json", workbook)

    settings = load_settings(path)

    assert settings.excel_file_path == workbook.resolve()
    assert settings.measurements == ("GAIN",)
    assert settings.acceptable_variation == {"GAIN": 0.2}


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"test": "OTHER"}, "SIGPATH"),
        ({"measurements": []}, "measurements.*GAIN"),
        ({"acceptable_variation": {"GAIN": -0.1}}, "non-negative"),
        ({"group_by": ["MEASPORT"]}, "no aggregation"),
        ({"aggregate_port_groups": True}, "no aggregation"),
        ({"bypass_model": False}, "must be true"),
    ],
)
def test_v01_rejects_out_of_scope_configuration(
    tmp_path, workbook_factory, sample_rows, override, message
):
    workbook = workbook_factory(sample_rows)
    path = write_settings(tmp_path / "settings.json", workbook, **override)

    with pytest.raises(ConfigurationError, match=message):
        load_settings(path)


def test_create_template_does_not_overwrite(tmp_path):
    path = tmp_path / "settings.json"
    create_settings_template(path)
    original = path.read_text(encoding="utf-8")

    with pytest.raises(ConfigurationError, match="not overwritten"):
        create_settings_template(path)

    assert path.read_text(encoding="utf-8") == original
    assert json.loads(original)["bypass_model"] is True
