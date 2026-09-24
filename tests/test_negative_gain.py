from __future__ import annotations

from compliance_summarizer.contracts import (
    NegativeGainDecision,
    ParsedCase,
    PivotSchema,
    SheetSchema,
    SourceResult,
)
from compliance_summarizer.prompts import PromptAborted
from compliance_summarizer.rows import RowParsingResult
from compliance_summarizer.validation import (
    detect_negative_gain_minima,
    format_negative_gain_findings,
    run_negative_gain_check,
)


def make_schema() -> SheetSchema:
    return SheetSchema(
        sheet_name="Combined",
        fixed_columns={
            "LNAMODE": 1,
            "CAMODE": 2,
            "STD": 3,
            "BAND": 4,
            "MEASPORT": 6,
            "DLP": 7,
            "DIV": 8,
            "TESTNAME": 10,
            "GAINMODE": 11,
            "BBPATH": 12,
            "FREQ": 13,
            "CHANNEL": 14,
            "Result?": 15,
            "LL": 16,
            "UL": 17,
        },
        optional_columns={"BW": 5, "F0_MHZ": 9},
        pivots=(
            PivotSchema(
                name="FIRST",
                statistics={
                    "MIN": 18,
                    "MAX": 19,
                    "NN_25C AVG": 20,
                    "wcMargin": 21,
                },
            ),
            PivotSchema(
                name="SECOND",
                statistics={
                    "MIN": 22,
                    "MAX": 23,
                    "NN_25C AVG": 24,
                    "wcMargin": 25,
                },
            ),
        ),
    )


def make_case(
    row_number: int,
    *,
    test_name: str = "GAIN",
    minima: dict[str, object] | None = None,
) -> ParsedCase:
    minima = minima or {"FIRST": 1.0, "SECOND": 1.0}
    fixed_values = {
        "LNAMODE": f"LNA-{row_number}",
        "CAMODE": "CA0",
        "STD": "5G",
        "BAND": "n78",
        "BW": 100,
        "MEASPORT": f"PORT-{row_number}",
        "DLP": "DLP0",
        "DIV": 2,
        "F0_MHZ": 3600,
        "TESTNAME": test_name,
        "GAINMODE": 1,
        "BBPATH": "BB0",
        "FREQ": 3600.0,
        "CHANNEL": row_number,
        "Result?": "PASS",
        "LL": -1.0,
        "UL": 1.0,
    }
    return ParsedCase(
        worksheet_row_number=row_number,
        source_values=dict(fixed_values),
        fixed_values=fixed_values,
        pivot_values={
            pivot_name: {
                "MIN": minimum,
                "MAX": 2.0,
                "NN_25C AVG": 10.0,
                "wcMargin": 1.0,
            }
            for pivot_name, minimum in minima.items()
        },
        source_result=SourceResult.PASS,
    )


def parsed(*cases: ParsedCase) -> RowParsingResult:
    return RowParsingResult(cases=cases, findings=())


def test_no_negative_minima_skips_confirmation_and_reports_passed_check():
    output: list[str] = []
    result = run_negative_gain_check(
        parsed(
            make_case(5, minima={"FIRST": 0.0, "SECOND": None}),
            make_case(6, test_name="IP3IB-GAIN", minima={"FIRST": -1.0, "SECOND": -2.0}),
            make_case(7, minima={"FIRST": "invalid", "SECOND": 2.0}),
        ),
        make_schema(),
        input_fn=lambda _prompt: (_ for _ in ()).throw(AssertionError("no prompt expected")),
        output_fn=output.append,
    )

    assert result.findings == ()
    assert result.decision is NegativeGainDecision.NOT_REQUIRED
    assert result.should_continue
    assert output == [
        "Negative-GAIN check passed: no numeric negative MIN values found."
    ]


def test_single_negative_minimum_retains_row_pivot_value_and_context():
    findings = detect_negative_gain_minima(
        parsed(make_case(8, minima={"FIRST": -0.5, "SECOND": 0.0})),
        make_schema(),
    )

    assert len(findings) == 1
    finding = findings[0]
    assert (finding.worksheet_row_number, finding.pivot_name, finding.minimum) == (
        8,
        "FIRST",
        -0.5,
    )
    assert finding.context["LNAMODE"] == "LNA-8"
    assert finding.context["BW"] == 100
    assert finding.validation_finding.field_name == "MIN"
    assert finding.validation_finding.sample_rows == (8,)
    assert format_negative_gain_findings(findings)[0].startswith(
        "Worksheet row | Pivot field | MIN | LNAMODE"
    )


def test_multiple_pivots_report_once_each_in_schema_order():
    findings = detect_negative_gain_minima(
        parsed(make_case(9, minima={"FIRST": -1.0, "SECOND": -2.0})),
        make_schema(),
    )

    assert [(finding.worksheet_row_number, finding.pivot_name) for finding in findings] == [
        (9, "FIRST"),
        (9, "SECOND"),
    ]
    lines = format_negative_gain_findings(findings)
    assert any("9 | FIRST | -1.0" in line for line in lines)
    assert any("9 | SECOND | -2.0" in line for line in lines)


def test_negative_gain_check_requires_explicit_proceed_or_abort():
    output: list[str] = []
    proceed = run_negative_gain_check(
        parsed(make_case(10, minima={"FIRST": -1.0, "SECOND": 1.0})),
        make_schema(),
        input_fn=lambda _prompt: "yes",
        output_fn=output.append,
    )
    assert proceed.decision is NegativeGainDecision.PROCEED
    assert proceed.should_continue
    assert len(proceed.validation_findings) == 1

    output.clear()
    abort = run_negative_gain_check(
        parsed(make_case(11, minima={"FIRST": -1.0, "SECOND": 1.0})),
        make_schema(),
        input_fn=lambda _prompt: "no",
        output_fn=output.append,
    )
    assert abort.decision is NegativeGainDecision.ABORT
    assert not abort.should_continue
    assert output[-1] == (
        "Negative-GAIN check rejected; analytics and report generation must stop."
    )


def test_negative_gain_check_propagates_safe_prompt_abort():
    def raise_eof(_prompt):
        raise EOFError

    try:
        run_negative_gain_check(
            parsed(make_case(12, minima={"FIRST": -1.0, "SECOND": 1.0})),
            make_schema(),
            input_fn=raise_eof,
            output_fn=lambda _message: None,
        )
    except PromptAborted as error:
        assert "aborted safely" in str(error)
    else:
        raise AssertionError("negative-GAIN EOF must abort the run")
