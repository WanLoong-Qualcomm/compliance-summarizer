from __future__ import annotations

import json

import pytest

from compliance_summarizer.app import analyze
from compliance_summarizer.errors import WorkbookValidationError
from compliance_summarizer.grouping import calculate_grouped_analyses
from compliance_summarizer.models import CustomGroupDefinition
from compliance_summarizer.report import render_html
from compliance_summarizer.workbook import load_measurement

from conftest import write_settings


def test_grouping_partitions_rows_and_reuses_statistics(
    workbook_factory, sample_rows
):
    parsed = load_measurement(workbook_factory(sample_rows[:3]), "Combined")

    grouped, warnings = calculate_grouped_analyses(
        parsed,
        ("CHANNEL",),
        "DUT-1_VAR1",
        0.2,
    )

    assert warnings == ()
    assert [item.group_key for item in grouped] == [
        (("CHANNEL", 1),),
        (("CHANNEL", 2),),
        (("CHANNEL", 3),),
    ]
    assert [item.statistics.case_count for item in grouped] == [1, 1, 1]
    assert all(item.statistics.top_failure_cases == () for item in grouped)
    assert all(item.statistics.top_pass_cases == () for item in grouped)
    assert [
        item.statistics.pivot_statistics[0].failure_rate.numerator
        for item in grouped
    ] == [1, 0, 1]


def test_grouping_field_order_does_not_change_membership(
    workbook_factory, sample_rows
):
    rows = sample_rows[:3]
    rows[1]["MEASPORT"] = "P2"
    parsed = load_measurement(workbook_factory(rows), "Combined")

    first, first_warnings = calculate_grouped_analyses(
        parsed, ("MEASPORT", "CHANNEL"), "DUT-1_VAR1", 0.2
    )
    second, second_warnings = calculate_grouped_analyses(
        parsed, ("CHANNEL", "MEASPORT"), "DUT-1_VAR1", 0.2
    )

    assert first_warnings == second_warnings == ()
    assert {
        frozenset(item.group_key)
        for item in first
    } == {
        frozenset(item.group_key)
        for item in second
    }


def test_grouping_accepts_arbitrary_metadata_field(workbook_factory, sample_rows):
    rows = [
        {**row, "TEMP": temperature}
        for row, temperature in zip(sample_rows[:3], (-50, 25, -50), strict=True)
    ]
    parsed = load_measurement(
        workbook_factory(rows, extra_headers=("TEMP",)),
        "Combined",
    )

    grouped, warnings = calculate_grouped_analyses(
        parsed, ("TEMP",), "DUT-1_VAR1", 0.2
    )

    assert warnings == ()
    assert [item.group_key for item in grouped] == [
        (("TEMP", -50),),
        (("TEMP", 25),),
    ]
    assert [item.statistics.case_count for item in grouped] == [2, 1]


def test_custom_grouping_maps_values_and_unmatched_values_to_default(
    workbook_factory, sample_rows
):
    rows = sample_rows[:3]
    rows[0]["MEASPORT"] = " l1 "
    rows[1]["MEASPORT"] = "MH1"
    rows[2]["MEASPORT"] = "unknown"
    parsed = load_measurement(workbook_factory(rows), "Combined")
    definition = CustomGroupDefinition(
        name="sigpath-block",
        field="MEASPORT",
        groups=(
            ("LB", ("L1",)),
            ("MHB", ("MH1",)),
        ),
        default="OTHER",
    )

    grouped, warnings = calculate_grouped_analyses(
        parsed,
        ("sigpath-block",),
        "DUT-1_VAR1",
        0.2,
        custom_groups={"SIGPATH-BLOCK": definition},
    )

    assert warnings == ()
    assert [item.group_key for item in grouped] == [
        (("sigpath-block", "LB"),),
        (("sigpath-block", "MHB"),),
        (("sigpath-block", "OTHER"),),
    ]


def test_custom_and_raw_grouping_can_be_combined(
    workbook_factory, sample_rows
):
    rows = [
        {**row, "TEMP": temperature}
        for row, temperature in zip(sample_rows[:3], ("25", " 25 ", 110), strict=True)
    ]
    parsed = load_measurement(
        workbook_factory(rows, extra_headers=("TEMP",)),
        "Combined",
    )
    definition = CustomGroupDefinition(
        name="over-voltage-temperature",
        field="TEMP",
        groups=(("25c", ("25",)),),
        default="OVT",
    )

    grouped, warnings = calculate_grouped_analyses(
        parsed,
        ("over-voltage-temperature", "CHANNEL"),
        "DUT-1_VAR1",
        0.2,
        custom_groups={"OVER-VOLTAGE-TEMPERATURE": definition},
    )

    assert warnings == ()
    assert [item.statistics.case_count for item in grouped] == [1, 1, 1]
    assert {
        item.group_key[0][1]
        for item in grouped
    } == {"25c", "OVT"}


def test_analyze_loads_named_custom_groups_from_settings_directory(
    tmp_path, workbook_factory, sample_rows
):
    rows = sample_rows[:3]
    rows[0]["MEASPORT"] = "L1"
    rows[1]["MEASPORT"] = "unmatched"
    workbook = workbook_factory(rows)
    settings = write_settings(
        tmp_path / "JUI.json",
        workbook,
        group_by=["sigpath-block"],
    )
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "groups.json").write_text(
        json.dumps(
            {
                "sigpath-block": {
                    "field": "MEASPORT",
                    "groups": {"LB": ["L1"]},
                    "default": "OTHER",
                }
            }
        ),
        encoding="utf-8",
    )

    analysis = analyze(settings)

    assert [item.group_key[0][1] for item in analysis.grouped_analyses] == [
        "LB",
        "OTHER",
    ]


def test_grouping_reports_metadata_field_absent_from_workbook(
    workbook_factory, sample_rows
):
    parsed = load_measurement(workbook_factory(sample_rows[:3]), "Combined")

    with pytest.raises(WorkbookValidationError, match="absent from worksheet"):
        calculate_grouped_analyses(
            parsed, ("CUSTOM_FIELD",), "DUT-1_VAR1", 0.2
        )


def test_grouping_missing_field_lists_available_custom_groups(
    workbook_factory, sample_rows
):
    parsed = load_measurement(workbook_factory(sample_rows[:3]), "Combined")
    definition = CustomGroupDefinition(
        name="sigpath-block",
        field="MEASPORT",
        groups=(("LB", ("L1",)),),
        default="OTHER",
    )

    with pytest.raises(
        WorkbookValidationError,
        match="Available custom groups: SIGPATH-BLOCK",
    ):
        calculate_grouped_analyses(
            parsed,
            ("CUSTOM_FIELD",),
            "DUT-1_VAR1",
            0.2,
            custom_groups={"SIGPATH-BLOCK": definition},
        )


def test_grouping_can_use_pivot_specific_fail_type(
    workbook_factory, sample_rows
):
    rows = sample_rows[:3]
    rows[0]["DUT-1_VAR1"]["MIN"] = 7.0
    rows[1]["UL"] = 10.0
    rows[1]["DUT-1_VAR1"]["wcMargin"] = -1.0
    rows[1]["DUT-1_VAR1"]["MIN"] = 9.0
    rows[1]["DUT-1_VAR1"]["MAX"] = 11.0
    rows[2]["DUT-1_VAR1"]["wcMargin"] = 0.0
    parsed = load_measurement(
        workbook_factory(rows),
        "Combined",
        add_fail_type=True,
    )

    grouped, warnings = calculate_grouped_analyses(
        parsed,
        ("DUT-1_VAR1.FAIL_type",),
        "DUT-1_VAR1",
        0.2,
        add_fail_type=True,
    )

    assert warnings == ()
    assert {
        item.group_key[0][1]
        for item in grouped
    } == {"LL", "UL", "(blank)"}


def test_grouping_can_use_anchor_fail_type_display_name(
    workbook_factory, sample_rows
):
    rows = sample_rows[:3]
    rows[0]["DUT-1_VAR1"]["MIN"] = 7.0
    rows[1]["UL"] = 10.0
    rows[1]["DUT-1_VAR1"]["wcMargin"] = -1.0
    rows[1]["DUT-1_VAR1"]["MIN"] = 9.0
    rows[1]["DUT-1_VAR1"]["MAX"] = 11.0
    rows[2]["DUT-1_VAR1"]["wcMargin"] = 0.0
    parsed = load_measurement(
        workbook_factory(rows),
        "Combined",
        add_fail_type=True,
    )

    grouped, warnings = calculate_grouped_analyses(
        parsed,
        ("FAIL type",),
        "DUT-1_VAR1",
        0.2,
        add_fail_type=True,
    )

    assert warnings == ()
    assert {item.group_key[0][1] for item in grouped} == {"LL", "UL", "(blank)"}


def test_blank_group_is_explicit_and_groups_without_margin_are_skipped(
    workbook_factory, sample_rows
):
    rows = sample_rows[:3]
    rows[0]["MEASPORT"] = ""
    rows[1]["MEASPORT"] = "P2"
    rows[1]["DUT-1_VAR1"]["wcMargin"] = None
    parsed = load_measurement(workbook_factory(rows), "Combined")

    grouped, warnings = calculate_grouped_analyses(
        parsed, ("MEASPORT",), "DUT-1_VAR1", 0.2
    )

    assert any(item.group_key == (("MEASPORT", "(blank)"),) for item in grouped)
    assert len(warnings) == 1
    assert "Group MEASPORT=P2" in warnings[0]
    assert "skipped" in warnings[0]


def test_grouped_report_follows_overall_report_and_omits_group_top_twenty(
    tmp_path, workbook_factory, sample_rows
):
    workbook = workbook_factory(sample_rows[:3])
    settings = write_settings(
        tmp_path / "JUI.json",
        workbook,
        group_by=["CHANNEL"],
    )

    rendered = render_html(analyze(settings))

    assert rendered.count("The top 20 failures are ordered") == 1
    assert rendered.index("Overall pivot compliance") < rendered.index(
        "Overall DUT-1_VAR1 failures"
    )
    assert rendered.index("Overall DUT-1_VAR1 failures") < rendered.index(
        "Overall DUT-1_VAR1 marginal passes"
    )
    assert rendered.index("Group: CHANNEL=1") < rendered.index(
        "Group: CHANNEL=2"
    ) < rendered.index("Methodology and assumptions")
    assert rendered.index("Overall DUT-1_VAR1 marginal passes") < rendered.index(
        "Group: CHANNEL=1"
    )
    assert rendered.count("The top 5 marginal passes are ordered") == 1
    assert "Group: CHANNEL=2" in rendered
    assert rendered.count('>Pivot compliance</h3>') == 3
    assert rendered.count('>DUT-1_VAR1 comparisons</h3>') == 3
    assert "Pivot compliance" in rendered
    assert "Pivot comparisons" in rendered
    assert '<hr class="group-divider">' in rendered


def test_skipped_group_warning_uses_existing_warning_list(
    tmp_path, workbook_factory, sample_rows
):
    rows = sample_rows[:3]
    rows[1]["MEASPORT"] = "P2"
    rows[1]["DUT-1_VAR1"]["wcMargin"] = None
    workbook = workbook_factory(rows)
    settings = write_settings(
        tmp_path / "JUI.json",
        workbook,
        group_by=["MEASPORT"],
    )

    rendered = render_html(analyze(settings))

    assert "<h3>Warnings</h3>" in rendered
    assert "Group MEASPORT=P2" in rendered
    assert "grouped analysis was skipped as a coverage gap" in rendered
    assert "Group: MEASPORT=P2" not in rendered


def test_grouped_report_can_include_failure_and_marginal_pass_tables(
    tmp_path, workbook_factory, sample_rows
):
    workbook = workbook_factory(sample_rows[:3])
    settings = write_settings(
        tmp_path / "JUI.json",
        workbook,
        group_by=["CHANNEL"],
        include_group_failures=True,
        include_group_marginal_passes=True,
    )

    rendered = render_html(analyze(settings))

    assert rendered.count("The top 20 failures are ordered") == 4
    assert rendered.count("The top 5 marginal passes are ordered") == 4
    assert rendered.count(">Failure cases</caption>") == 4
    assert rendered.count(">Marginal pass cases</caption>") == 4
