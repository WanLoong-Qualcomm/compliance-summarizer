from __future__ import annotations

import pytest

from compliance_summarizer.errors import WorkbookValidationError
from compliance_summarizer.workbook import load_measurement


def test_discovers_pivots_filters_measurement_and_reports_coverage(
    workbook_factory, sample_rows
):
    workbook = workbook_factory(sample_rows)

    parsed = load_measurement(workbook, "Combined")

    assert parsed.schema.pivot_names == ("DUT-1_VAR1", "DUT-2_VAR1")
    assert len(parsed.cases) == 3
    assert parsed.cases[0].identity[-1] == ("CHANNEL", 1)
    assert parsed.coverage[0].gaps_by_field["NN_25C AVG"] == 1
    assert parsed.coverage[0].malformed_by_field["NN_25C AVG"] == 1
    assert parsed.coverage[1].rows_with_gaps == 2


def test_mean_can_replace_legacy_average_statistic(workbook_factory, sample_rows):
    rows = [
        {
            **row,
            "DUT-1_VAR1": {
                **row["DUT-1_VAR1"],
                "MEAN": row["DUT-1_VAR1"]["NN_25c AVG"],
            },
            "DUT-2_VAR1": {
                **row["DUT-2_VAR1"],
                "MEAN": row["DUT-2_VAR1"]["NN_25c AVG"],
            },
        }
        for row in sample_rows[:1]
    ]
    workbook = workbook_factory(
        rows,
        pivot_stats=("MIN", "MAX", "MEAN", "wcMargin", "wcValue"),
    )

    parsed = load_measurement(workbook, "Combined")

    assert parsed.coverage[0].gaps_by_field["MEAN"] == 0
    assert parsed.cases[0].pivot_values["DUT-1_VAR1"]["MEAN"] == 10.0


def test_test_filters_exclude_non_matching_rows(workbook_factory, sample_rows):
    rows = [
        {**row, "TESTNAME": "IP2ACS", "CHANNEL": channel}
        for row, channel in zip(sample_rows[:3], ("IQ", "TX", " iq "), strict=True)
    ]
    workbook = workbook_factory(rows)

    parsed = load_measurement(
        workbook,
        "Combined",
        "IP2ACS",
        test_filters={"IP2ACS": {"CHANNEL": ("IQ",)}},
    )

    assert [case.metadata_values["CHANNEL"] for case in parsed.cases] == [
        "IQ",
        " iq ",
    ]
    assert any("1 row(s) were excluded" in warning for warning in parsed.warnings)


def test_pivot_requires_one_of_the_two_comparison_statistics(
    workbook_factory, sample_rows
):
    workbook = workbook_factory(
        sample_rows[:1],
        pivot_stats=("MIN", "MAX", "wcMargin", "wcValue"),
    )

    with pytest.raises(WorkbookValidationError, match="MEAN or NN_25C AVG"):
        load_measurement(workbook, "Combined")


def test_missing_required_header_is_actionable(workbook_factory, sample_rows):
    workbook = workbook_factory(sample_rows, omit_header="TESTNAME")

    with pytest.raises(WorkbookValidationError, match="TESTNAME.*missing"):
        load_measurement(workbook, "Combined")


@pytest.mark.parametrize("required_header", ["TESTNAME", "MEASPORT"])
def test_only_testname_and_measport_are_required(
    workbook_factory, sample_rows, required_header
):
    workbook = workbook_factory(sample_rows, omit_header=required_header)

    with pytest.raises(WorkbookValidationError, match=f"{required_header}.*missing"):
        load_measurement(workbook, "Combined")


def test_discovers_arbitrary_metadata_and_uses_it_for_identity(
    workbook_factory, sample_rows
):
    rows = [
        {**row, "TEMP": temperature}
        for row, temperature in zip(sample_rows[:3], (-50, 25, 110), strict=True)
    ]
    workbook = workbook_factory(
        rows,
        omit_header="LNAMODE",
        extra_headers=("TEMP",),
    )

    parsed = load_measurement(workbook, "Combined")

    assert "LNAMODE" not in parsed.schema.metadata_columns
    assert "TEMP" in parsed.schema.metadata_columns
    assert all(("TEMP", value) in case.identity for case, value in zip(
        parsed.cases, (-50, 25, 110), strict=True
    ))
    assert all(
        header not in {"Result?", "LL", "UL"}
        for case in parsed.cases
        for header, _ in case.identity
    )


def test_absent_measurement_stops_processing(workbook_factory, sample_rows):
    rows = [{**row, "TESTNAME": "SSNF"} for row in sample_rows]
    workbook = workbook_factory(rows)

    with pytest.raises(WorkbookValidationError, match="no rows.*GAIN"):
        load_measurement(workbook, "Combined")
