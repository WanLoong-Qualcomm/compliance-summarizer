from __future__ import annotations

import pytest

from compliance_summarizer.contracts import (
    NegativeGainDecision,
    PivotSchema,
    SheetSchema,
)
from compliance_summarizer.prompts import (
    PromptAborted,
    collect_pivot_background_information,
    prompt_negative_gain_decision,
    prompt_yes_no,
    wait_for_settings_completion,
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
        optional_columns={},
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


def test_settings_pause_accepts_enter_and_reports_the_path():
    prompts: list[str] = []
    messages: list[str] = []

    wait_for_settings_completion(
        "settings.json",
        input_fn=lambda prompt: prompts.append(prompt) or "",
        output_fn=messages.append,
    )

    assert prompts == [""]
    assert messages == [
        "Complete the settings file at settings.json, then press Enter to continue."
    ]


def test_pivot_backgrounds_follow_discovered_order_and_allow_empty_values():
    prompts: list[str] = []
    responses = iter(("first context", ""))

    backgrounds = collect_pivot_background_information(
        make_schema(),
        input_fn=lambda prompt: prompts.append(prompt) or next(responses),
    )

    assert tuple(backgrounds) == ("FIRST", "SECOND")
    assert backgrounds == {"FIRST": "first context", "SECOND": ""}
    assert "'FIRST'" in prompts[0]
    assert "'SECOND'" in prompts[1]


def test_yes_no_retries_invalid_input_and_accepts_case_insensitive_full_words():
    responses = iter(("maybe", " YES "))
    messages: list[str] = []

    assert prompt_yes_no(
        "Continue?",
        input_fn=lambda _prompt: next(responses),
        output_fn=messages.append,
    ) is True
    assert messages == ["Please enter exactly 'yes' or 'no'."]


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        ("yes", NegativeGainDecision.PROCEED),
        ("no", NegativeGainDecision.ABORT),
    ],
)
def test_negative_gain_confirmation_requires_explicit_decision(response, expected):
    assert prompt_negative_gain_decision(input_fn=lambda _prompt: response) is expected


@pytest.mark.parametrize("function", [wait_for_settings_completion, prompt_negative_gain_decision])
def test_eof_and_keyboard_interrupt_abort_safely(function):
    def raise_eof(_prompt):
        raise EOFError

    def raise_interrupt(_prompt):
        raise KeyboardInterrupt

    with pytest.raises(PromptAborted, match="aborted safely"):
        if function is wait_for_settings_completion:
            function("settings.json", input_fn=raise_eof)
        else:
            function(input_fn=raise_eof)

    with pytest.raises(PromptAborted, match="aborted safely"):
        if function is wait_for_settings_completion:
            function("settings.json", input_fn=raise_interrupt)
        else:
            function(input_fn=raise_interrupt)
