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


def test_missing_required_header_is_actionable(workbook_factory, sample_rows):
    workbook = workbook_factory(sample_rows, omit_header="TESTNAME")

    with pytest.raises(WorkbookValidationError, match="TESTNAME.*missing"):
        load_measurement(workbook, "Combined")


def test_absent_measurement_stops_processing(workbook_factory, sample_rows):
    rows = [{**row, "TESTNAME": "SSNF"} for row in sample_rows]
    workbook = workbook_factory(rows)

    with pytest.raises(WorkbookValidationError, match="no rows.*GAIN"):
        load_measurement(workbook, "Combined")
