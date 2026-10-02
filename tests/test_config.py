from __future__ import annotations

import json

import pytest

from compliance_summarizer.config import (
    create_settings_template,
    load_custom_groups,
    load_settings,
)
from compliance_summarizer.errors import ConfigurationError

from conftest import write_settings


def test_load_settings_resolves_workbook_relative_to_settings(
    tmp_path, workbook_factory, sample_rows
):
    workbook = workbook_factory(sample_rows)
    path = write_settings(tmp_path / "JUI.json", workbook)

    settings = load_settings(path)

    assert settings.excel_file_path == workbook.resolve()
    assert settings.testnames == ("GAIN",)
    assert settings.add_fail_type is False
    assert settings.include_group_failures is False
    assert settings.include_group_marginal_passes is False


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"block": "OTHER"}, "SIGPATH"),
        ({"testnames": []}, "testnames.*GAIN"),
        ({"acceptable_variation": {"GAIN": 0.2}}, "Unsupported.*acceptable_variation"),
        ({"group_by": ["Result?"]}, "Unsupported.*group_by"),
        ({"add_fail_type": "yes"}, "add_fail_type.*boolean"),
        ({"include_group_failures": "yes"}, "include_group_failures.*boolean"),
        (
            {"include_group_marginal_passes": 1},
            "include_group_marginal_passes.*boolean",
        ),
        ({"bypass_model": False}, "must be true"),
    ],
)
def test_rejects_invalid_configuration(
    tmp_path, workbook_factory, sample_rows, override, message
):
    workbook = workbook_factory(sample_rows)
    path = write_settings(tmp_path / "JUI.json", workbook, **override)

    with pytest.raises(ConfigurationError, match=message):
        load_settings(path)


def test_load_settings_accepts_and_normalizes_group_by(
    tmp_path, workbook_factory, sample_rows
):
    workbook = workbook_factory(sample_rows)
    path = write_settings(
        tmp_path / "JUI.json",
        workbook,
        group_by=[" custom_field ", "CHANNEL"],
    )

    settings = load_settings(path)

    assert settings.group_by == ("CUSTOM_FIELD", "CHANNEL")


def test_load_custom_groups_normalizes_names_and_fields(tmp_path):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "groups.json").write_text(
        json.dumps(
            {
                " sigpath-block ": {
                    "field": " measport ",
                    "groups": {"LB": ["L1", " l2 "]},
                    "default": "OTHER",
                }
            }
        ),
        encoding="utf-8",
    )

    definitions = load_custom_groups(tmp_path / "JUI.json")

    assert tuple(definitions) == ("SIGPATH-BLOCK",)
    definition = definitions["SIGPATH-BLOCK"]
    assert definition.name == "sigpath-block"
    assert definition.field == "MEASPORT"
    assert definition.groups == (("LB", ("L1", " l2 ")),)
    assert definition.default == "OTHER"


def test_load_custom_groups_rejects_excluded_source_fields(tmp_path):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "groups.json").write_text(
        json.dumps(
            {
                "bad": {
                    "field": "Result?",
                    "groups": {"FAIL": ["FAIL"]},
                    "default": "OTHER",
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="source-result or limit"):
        load_custom_groups(tmp_path / "JUI.json")


def test_load_settings_accepts_multiple_supported_measurements(
    tmp_path, workbook_factory, sample_rows
):
    workbook = workbook_factory(sample_rows)
    path = write_settings(
        tmp_path / "JUI.json",
        workbook,
        testnames=["gain", "GCIB", "S11-low"],
    )

    settings = load_settings(path)

    assert settings.testnames == ("GAIN", "GCIB", "S11-LOW")


def test_group_by_rejects_duplicate_fields(tmp_path, workbook_factory, sample_rows):
    workbook = workbook_factory(sample_rows)
    path = write_settings(
        tmp_path / "JUI.json",
        workbook,
        group_by=["MEASPORT", " measport "],
    )

    with pytest.raises(ConfigurationError, match="duplicate"):
        load_settings(path)


def test_fail_type_grouping_requires_feature_flag(
    tmp_path, workbook_factory, sample_rows
):
    workbook = workbook_factory(sample_rows)
    path = write_settings(
        tmp_path / "JUI.json",
        workbook,
        group_by=["DUT-1_VAR1.FAIL_type"],
    )

    with pytest.raises(ConfigurationError, match="requires 'add_fail_type'"):
        load_settings(path)


def test_fail_type_grouping_normalizes_field_when_enabled(
    tmp_path, workbook_factory, sample_rows
):
    workbook = workbook_factory(sample_rows)
    path = write_settings(
        tmp_path / "JUI.json",
        workbook,
        add_fail_type=True,
        group_by=["DUT-1_VAR1.FAIL_type"],
    )

    settings = load_settings(path)

    assert settings.add_fail_type is True
    assert settings.group_by == ("DUT-1_VAR1.FAIL_TYPE",)


def test_create_template_does_not_overwrite(tmp_path):
    path = tmp_path / "JUI.json"
    create_settings_template(path)
    original = path.read_text(encoding="utf-8")

    with pytest.raises(ConfigurationError, match="not overwritten"):
        create_settings_template(path)

    assert path.read_text(encoding="utf-8") == original
    assert json.loads(original)["bypass_model"] is True
