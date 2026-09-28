from __future__ import annotations

import pytest

from compliance_summarizer.errors import WorkbookValidationError
from compliance_summarizer.statistics import calculate_measurement_statistics
from compliance_summarizer.workbook import load_measurement


def test_compliance_uses_margin_and_comparison_uses_paired_averages(
    workbook_factory, sample_rows
):
    parsed = load_measurement(workbook_factory(sample_rows), "Combined")

    result = calculate_measurement_statistics(parsed, "DUT-1_VAR1", 0.2)

    main = result.pivot_statistics[0]
    other = result.pivot_statistics[1]
    assert (main.failure_rate.numerator, main.failure_rate.denominator) == (2, 3)
    assert (other.failure_rate.numerator, other.failure_rate.denominator) == (1, 2)
    assert main.worst_wc_margin == -1.0
    assert dict(main.worst_failure_path)["CHANNEL"] == 1
    comparison = result.comparisons[0]
    assert comparison.paired_count == 1
    assert comparison.main_only_count == 1
    assert comparison.improvement_rate.numerator == 1
    assert comparison.degradation_rate.numerator == 0
    assert comparison.maximum_improvement == 0.5
    assert len(result.top_failure_cases) == 2
    assert result.top_failure_cases[1].deltas["DUT-2_VAR1"] is None


def test_tolerance_boundaries_are_unchanged(workbook_factory, sample_rows):
    rows = sample_rows[:1]
    rows[0]["DUT-1_VAR1"]["NN_25c AVG"] = 10.0
    rows[0]["DUT-2_VAR1"]["NN_25c AVG"] = 9.8
    parsed = load_measurement(workbook_factory(rows), "Combined")

    comparison = calculate_measurement_statistics(
        parsed, "DUT-1_VAR1", 0.2
    ).comparisons[0]

    assert comparison.unchanged_rate.numerator == 1
    assert comparison.improvement_rate.numerator == 0


def test_top_twenty_is_exact_and_ties_are_stable(workbook_factory, sample_rows):
    template = sample_rows[0]
    rows = []
    for channel in range(22, 0, -1):
        row = {
            **template,
            "CHANNEL": channel,
            "DUT-1_VAR1": {**template["DUT-1_VAR1"], "wcMargin": -1.0},
            "DUT-2_VAR1": dict(template["DUT-2_VAR1"]),
        }
        rows.append(row)
    parsed = load_measurement(workbook_factory(rows), "Combined")

    result = calculate_measurement_statistics(parsed, "DUT-1_VAR1", 0.2)

    assert len(result.top_failure_cases) == 20
    assert [item.case.fixed_values["CHANNEL"] for item in result.top_failure_cases] == [
        1,
        10,
        11,
        12,
        13,
        14,
        15,
        16,
        17,
        18,
        19,
        2,
        20,
        21,
        22,
        3,
        4,
        5,
        6,
        7,
    ]


def test_main_pivot_without_valid_margin_is_irrecoverable(
    workbook_factory, sample_rows
):
    rows = sample_rows[:1]
    rows[0]["DUT-1_VAR1"]["wcMargin"] = None
    parsed = load_measurement(workbook_factory(rows), "Combined")

    with pytest.raises(WorkbookValidationError, match="no valid wcMargin"):
        calculate_measurement_statistics(parsed, "DUT-1_VAR1", 0.2)


def test_malformed_wc_margin_is_excluded_not_interpreted_as_result(
    workbook_factory, sample_rows
):
    rows = sample_rows[:2]
    rows[1]["DUT-1_VAR1"]["wcMargin"] = "not-a-number"
    rows[1]["Result?"] = "FAIL"
    parsed = load_measurement(workbook_factory(rows), "Combined")

    result = calculate_measurement_statistics(parsed, "DUT-1_VAR1", 0.2)

    main = result.pivot_statistics[0]
    assert (main.failure_rate.numerator, main.failure_rate.denominator) == (1, 1)
    assert main.invalid_margin_count == 1
    assert parsed.coverage[0].malformed_by_field["wcMargin"] == 1


def test_empty_failure_and_pair_sets_are_reportable(workbook_factory, sample_rows):
    row = sample_rows[0]
    row["DUT-1_VAR1"]["wcMargin"] = 1.0
    row["DUT-1_VAR1"]["NN_25c AVG"] = None
    row["DUT-2_VAR1"]["NN_25c AVG"] = 9.5
    parsed = load_measurement(workbook_factory([row]), "Combined")

    result = calculate_measurement_statistics(parsed, "DUT-1_VAR1", 0.2)

    assert result.top_failure_cases == ()
    assert result.comparisons[0].paired_count == 0
    assert result.comparisons[0].degradation_rate.percentage is None


def test_degradation_extreme_and_failure_average_use_gain_direction(
    workbook_factory, sample_rows
):
    first = sample_rows[0]
    first["DUT-1_VAR1"]["NN_25c AVG"] = 9.0
    first["DUT-2_VAR1"]["NN_25c AVG"] = 10.0
    second = {
        **sample_rows[2],
        "DUT-1_VAR1": {
            **sample_rows[2]["DUT-1_VAR1"],
            "NN_25c AVG": 8.0,
            "wcMargin": -0.2,
        },
        "DUT-2_VAR1": {
            **sample_rows[2]["DUT-2_VAR1"],
            "NN_25c AVG": 10.0,
            "wcMargin": 1.0,
        },
    }
    parsed = load_measurement(workbook_factory([first, second]), "Combined")

    comparison = calculate_measurement_statistics(
        parsed, "DUT-1_VAR1", 0.2
    ).comparisons[0]

    assert comparison.maximum_degradation == -2.0
    assert comparison.degradation_rate.numerator == 2
    assert comparison.average_degradation_on_main_failures == pytest.approx(1.5)
