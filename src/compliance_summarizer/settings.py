"""Generation and validation of the v0.1 settings file."""

from __future__ import annotations

import json
from copy import deepcopy
from json import JSONDecodeError
from math import isfinite
from pathlib import Path
from typing import Iterable

from .contracts import Settings


DEFAULT_SETTINGS: dict[str, object] = {
    "excel_file_path": "",
    "compliance_sheet_name": "Combined",
    "tests_to_report": ["GAIN"],
    "acceptable_variation": {"GAIN": 0.2},
    "background_information": "",
    "pivot_field_of_interest": "",
    "bypass_model": True,
}

REQUIRED_SETTINGS_FIELDS = tuple(DEFAULT_SETTINGS)


class SettingsError(ValueError):
    """Actionable error raised for settings generation or validation failures."""

    def __init__(self, message: str, *, field: str | None = None) -> None:
        self.field = field
        super().__init__(message)


def default_settings() -> dict[str, object]:
    """Return a fresh copy of the exact v0.1 settings template."""

    return deepcopy(DEFAULT_SETTINGS)


def create_default_settings(path: str | Path = "settings.json") -> bool:
    """Create the default settings file without overwriting existing content.

    Return ``True`` when a file is created and ``False`` when the path already
    exists.  The exclusive file creation also protects against a concurrent
    process replacing an existing settings file between the existence check
    and the write.
    """

    settings_path = Path(path)
    if settings_path.exists():
        if not settings_path.is_file():
            raise SettingsError(
                f"Cannot create settings file '{settings_path}': the path is not a file."
            )
        return False

    try:
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        with settings_path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(DEFAULT_SETTINGS, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
    except FileExistsError:
        return False
    except OSError as error:
        raise SettingsError(
            f"Could not create settings file '{settings_path}': {error}. "
            "Check the path and write permissions."
        ) from error
    return True


def load_settings(
    path: str | Path = "settings.json",
    *,
    available_pivots: Iterable[str] | None = None,
) -> Settings:
    """Load and validate settings without opening the workbook.

    If ``available_pivots`` is supplied by a later schema-discovery stage,
    the selected pivot is also checked for an exact match.
    """

    settings_path = Path(path)
    try:
        text = settings_path.read_text(encoding="utf-8")
    except OSError as error:
        raise SettingsError(
            f"Could not read settings file '{settings_path}': {error}. "
            "Create the file or check its path and permissions."
        ) from error

    try:
        payload = json.loads(text)
    except JSONDecodeError as error:
        raise SettingsError(
            f"Invalid JSON in settings file '{settings_path}' at line "
            f"{error.lineno}, column {error.colno}: {error.msg}. "
            "Correct the JSON syntax and try again."
        ) from error

    if not isinstance(payload, dict):
        raise SettingsError(
            f"Settings file '{settings_path}' must contain a JSON object, not "
            f"{type(payload).__name__}."
        )

    missing = [field for field in REQUIRED_SETTINGS_FIELDS if field not in payload]
    if missing:
        missing_fields = ", ".join(repr(field) for field in missing)
        raise SettingsError(
            f"Missing required settings field(s): {missing_fields}. "
            "Restore the fields from the default settings template."
        )

    unsupported = sorted(set(payload) - set(REQUIRED_SETTINGS_FIELDS))
    if unsupported:
        unsupported_fields = ", ".join(repr(field) for field in unsupported)
        raise SettingsError(
            f"Unsupported settings field(s): {unsupported_fields}. "
            "Remove them from the v0.1 settings file."
        )

    excel_file_path = _validate_excel_file_path(payload["excel_file_path"])
    compliance_sheet_name = _validate_nonempty_string(
        payload["compliance_sheet_name"], "compliance_sheet_name"
    )
    tests_to_report = _validate_tests(payload["tests_to_report"])
    acceptable_variation = _validate_variation(payload["acceptable_variation"])
    background_information = _validate_string(
        payload["background_information"], "background_information"
    )
    pivot_field_of_interest = _validate_nonempty_string(
        payload["pivot_field_of_interest"], "pivot_field_of_interest"
    )
    bypass_model = _validate_bypass_model(payload["bypass_model"])

    if available_pivots is not None:
        pivots = tuple(available_pivots)
        if pivot_field_of_interest not in pivots:
            discovered = ", ".join(repr(pivot) for pivot in pivots) or "none"
            raise SettingsError(
                f"Invalid settings field 'pivot_field_of_interest': "
                f"{pivot_field_of_interest!r} is not an exact discovered pivot name. "
                f"Available pivots: {discovered}.",
                field="pivot_field_of_interest",
            )

    return Settings(
        excel_file_path=excel_file_path,
        compliance_sheet_name=compliance_sheet_name,
        tests_to_report=tests_to_report,
        acceptable_variation=acceptable_variation,
        background_information=background_information,
        pivot_field_of_interest=pivot_field_of_interest,
        bypass_model=bypass_model,
    )


def _field_error(field: str, message: str) -> SettingsError:
    return SettingsError(f"Invalid settings field '{field}': {message}", field=field)


def _validate_string(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise _field_error(field, "expected a string.")
    return value


def _validate_nonempty_string(value: object, field: str) -> str:
    string_value = _validate_string(value, field)
    if not string_value.strip():
        raise _field_error(field, "must be a nonempty string.")
    return string_value


def _validate_excel_file_path(value: object) -> str:
    field = "excel_file_path"
    path_value = _validate_nonempty_string(value, field)
    workbook_path = Path(path_value)
    if workbook_path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise _field_error(field, "must point to an .xlsx or .xlsm file.")
    if not workbook_path.is_file():
        raise _field_error(
            field,
            f"file does not exist: '{path_value}'. Provide an existing workbook path.",
        )
    return path_value


def _validate_tests(value: object) -> tuple[str, ...]:
    field = "tests_to_report"
    if type(value) is not list:
        raise _field_error(field, "must be a nonempty JSON list containing only 'GAIN'.")
    if value != ["GAIN"]:
        raise _field_error(field, "v0.1 supports only the nonempty list ['GAIN'].")
    return ("GAIN",)


def _validate_variation(value: object) -> dict[str, float]:
    field = "acceptable_variation"
    if type(value) is not dict:
        raise _field_error(field, "must be a JSON object containing only GAIN.")
    if set(value) != {"GAIN"}:
        raise _field_error(field, "must contain exactly the GAIN field.")
    gain_variation = value["GAIN"]
    if (
        isinstance(gain_variation, bool)
        or not isinstance(gain_variation, (int, float))
        or not isfinite(gain_variation)
        or gain_variation < 0
    ):
        raise _field_error(
            f"{field}.GAIN",
            "must be a finite numeric value greater than or equal to zero.",
        )
    return {"GAIN": float(gain_variation)}


def _validate_bypass_model(value: object) -> bool:
    field = "bypass_model"
    if type(value) is not bool:
        raise _field_error(field, "must be the boolean true in v0.1.")
    if value is not True:
        raise _field_error(field, "must be true because external AI is unavailable in v0.1.")
    return True
