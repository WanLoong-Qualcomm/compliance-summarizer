from __future__ import annotations

from compliance_summarizer.app import analyze
from compliance_summarizer.grouping import calculate_grouped_analyses
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
        tmp_path / "settings.json",
        workbook,
        group_by=["CHANNEL"],
    )

    rendered = render_html(analyze(settings))

    assert rendered.count("The top 20 failures are ordered") == 1
    assert rendered.index("Overall pivot compliance") < rendered.index(
        "Overall DUT-1_VAR1 failures"
    )
    assert rendered.index("Overall DUT-1_VAR1 failures") < rendered.index(
        "Overall DUT-1_VAR1 pass cases"
    )
    assert rendered.index("Group: CHANNEL=1") < rendered.index(
        "Group: CHANNEL=2"
    ) < rendered.index("Methodology and assumptions")
    assert rendered.index("Overall DUT-1_VAR1 pass cases") < rendered.index(
        "Group: CHANNEL=1"
    )
    assert rendered.count("The top 5 passing cases are ordered") == 1
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
        tmp_path / "settings.json",
        workbook,
        group_by=["MEASPORT"],
    )

    rendered = render_html(analyze(settings))

    assert "<h3>Warnings</h3>" in rendered
    assert "Group MEASPORT=P2" in rendered
    assert "grouped analysis was skipped as a coverage gap" in rendered
    assert "Group: MEASPORT=P2" not in rendered
