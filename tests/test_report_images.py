from __future__ import annotations

import base64
from io import BytesIO

from PIL import Image

from compliance_summarizer.analytics import FailureAnalysisResult
from compliance_summarizer.contracts import CaseAnalysis, ParsedCase, SourceResult
from compliance_summarizer.report_images import render_top_failure_table_image


SELECTED_PIVOT = "SELECTED"


def make_failure_analysis(row_numbers: tuple[int, ...]) -> FailureAnalysisResult:
    cases = tuple(make_case(row_number) for row_number in row_numbers)
    return FailureAnalysisResult(
        source_fail_cases=cases,
        top_failure_cases=cases[:50],
        worst_failure_cases=cases[:5],
        unrankable_failure_cases=(),
    )


def make_case(row_number: int) -> CaseAnalysis:
    case = ParsedCase(
        worksheet_row_number=row_number,
        source_values={
            "LNAMODE": f"LNA-{row_number}",
            "CAMODE": "CA0",
            "STD": "5G",
            "BAND": "n78",
            "BW": 100,
            "MEASPORT": f"PORT-{row_number}",
            "DLP": "DLP0",
            "DIV": 2,
            "F0_MHZ": 3600,
            "TESTNAME": "GAIN",
            "GAINMODE": row_number,
            "BBPATH": "BB0",
            "FREQ": 3600.0,
            "CHANNEL": row_number,
            "Result?": "FAIL",
            "LL": -1.0,
            "UL": 1.0,
        },
        fixed_values={"TESTNAME": "GAIN"},
        pivot_values={"SELECTED": {"wcMargin": -float(row_number)}},
        source_result=SourceResult.FAIL,
    )
    return CaseAnalysis(
        case=case,
        selected_pivot=SELECTED_PIVOT,
        selected_margin=-float(row_number),
        pivot_statuses={},
        comparisons={},
    )


def test_empty_failure_analysis_renders_explicit_empty_state():
    asset = render_top_failure_table_image(make_failure_analysis(()), SELECTED_PIVOT)

    assert asset.is_empty
    assert asset.rows == ()
    assert asset.empty_state_message == (
        "No rankable failure cases for selected pivot 'SELECTED'."
    )
    assert "file:" not in asset.data_uri


def test_one_row_preserves_identifying_values_and_inline_encoding():
    asset = render_top_failure_table_image(make_failure_analysis((17,)), SELECTED_PIVOT)

    assert not asset.is_empty
    assert asset.rows[0][0] == "17"
    assert asset.rows[0][1] == "LNA-17"
    assert asset.rows[0][5] == "100"
    assert asset.rows[0][-1] == "-17.0"
    image = _decode_image(asset.data_uri)
    assert image.width > 0
    assert image.height > 0


def test_identical_input_produces_identical_png_data_uri():
    failure_analysis = make_failure_analysis((17, 18))

    first = render_top_failure_table_image(failure_analysis, SELECTED_PIVOT)
    second = render_top_failure_table_image(failure_analysis, SELECTED_PIVOT)

    assert first.data_uri == second.data_uri


def test_exactly_fifty_rows_keep_ranked_order():
    row_numbers = tuple(range(5, 55))
    asset = render_top_failure_table_image(make_failure_analysis(row_numbers), SELECTED_PIVOT)

    assert len(asset.rows) == 50
    assert [int(row[0]) for row in asset.rows] == list(row_numbers)


def test_more_than_fifty_source_rows_are_capped_without_reordering():
    row_numbers = tuple(range(100, 161))
    asset = render_top_failure_table_image(make_failure_analysis(row_numbers), SELECTED_PIVOT)

    assert len(asset.rows) == 50
    assert [int(row[0]) for row in asset.rows] == list(row_numbers[:50])


def _decode_image(data_uri: str) -> Image.Image:
    encoded = data_uri.removeprefix("data:image/png;base64,")
    return Image.open(BytesIO(base64.b64decode(encoded)))
