"""Safe interactive prompts for the v0.1 command-line workflow."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from .contracts import NegativeGainDecision, SheetSchema


class PromptAborted(RuntimeError):
    """Raised when interactive input ends or is interrupted."""


InputFunction = Callable[[str], str]
OutputFunction = Callable[[str], object]


def wait_for_settings_completion(
    settings_path: str | Path,
    *,
    input_fn: InputFunction | None = None,
    output_fn: OutputFunction | None = None,
) -> None:
    """Pause until the user confirms that the settings file is complete."""

    _output(
        output_fn,
        f"Complete the settings file at {settings_path}, then press Enter to continue.",
    )
    _read_input(input_fn, "")


def collect_pivot_background_information(
    schema: SheetSchema,
    *,
    input_fn: InputFunction | None = None,
) -> dict[str, str]:
    """Prompt once for each discovered pivot in worksheet order."""

    if not isinstance(schema, SheetSchema):
        raise TypeError("schema must be SheetSchema")

    backgrounds: dict[str, str] = {}
    for pivot_name in schema.pivot_names:
        prompt = (
            f"Background information for pivot '{pivot_name}' "
            "(optional; press Enter to leave blank): "
        )
        backgrounds[pivot_name] = _read_input(input_fn, prompt)
    return backgrounds


def prompt_yes_no(
    prompt: str,
    *,
    input_fn: InputFunction | None = None,
    output_fn: OutputFunction | None = None,
) -> bool:
    """Return a decision after accepting only full ``yes`` or ``no`` input."""

    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("prompt must be a nonempty string")

    while True:
        response = _read_input(input_fn, prompt).strip().casefold()
        if response == "yes":
            return True
        if response == "no":
            return False
        _output(output_fn, "Please enter exactly 'yes' or 'no'.")


def prompt_negative_gain_decision(
    *,
    input_fn: InputFunction | None = None,
    output_fn: OutputFunction | None = None,
) -> NegativeGainDecision:
    """Request explicit approval before continuing after negative GAIN values."""

    approved = prompt_yes_no(
        "Negative GAIN MIN values were found. Proceed with the run? [yes/no]: ",
        input_fn=input_fn,
        output_fn=output_fn,
    )
    return (
        NegativeGainDecision.PROCEED
        if approved
        else NegativeGainDecision.ABORT
    )


def _read_input(input_fn: InputFunction | None, prompt: str) -> str:
    reader = input if input_fn is None else input_fn
    try:
        response = reader(prompt)
    except (EOFError, KeyboardInterrupt) as error:
        raise PromptAborted(
            "Interactive input ended before the required response; the run was aborted safely."
        ) from error
    if not isinstance(response, str):
        raise PromptAborted(
            "Interactive input did not return text; the run was aborted safely."
        )
    return response


def _output(output_fn: OutputFunction | None, message: str) -> None:
    writer = print if output_fn is None else output_fn
    writer(message)
