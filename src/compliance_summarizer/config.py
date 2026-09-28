"""Load and validate the v0.1 ``settings.json`` contract."""

from __future__ import annotations

import json
from copy import deepcopy
from json import JSONDecodeError
from math import isfinite
from pathlib import Path

from .errors import ConfigurationError
from .models import Settings


DEFAULT_SETTINGS: dict[str, object] = {
    "excel_file_path": "./REFERENCE.xlsm",
    "compliance_sheet_name": "Combined",
    "test": "SIGPATH",
    "measurements": ["GAIN"],
    "acceptable_variation": {"GAIN": 0.2},
    "background_information": "",
    "main_pivot": "",
    "group_by": [],
    "aggregate_port_groups": False,
    "bypass_model": True,
}


def default_settings() -> dict[str, object]:
    return deepcopy(DEFAULT_SETTINGS)


def create_settings_template(path: str | Path = "settings.json") -> Path:
    target = Path(path)
    if target.exists():
        raise ConfigurationError(
            f"Settings file '{target}' already exists; it was not overwritten."
        )
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(DEFAULT_SETTINGS, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except OSError as error:
        raise ConfigurationError(
            f"Could not create settings file '{target}': {error}."
        ) from error
    return target


def load_settings(path: str | Path = "settings.json") -> Settings:
    settings_path = Path(path)
    try:
        payload = json.loads(settings_path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigurationError(
            f"Settings file '{settings_path}' does not exist. Run with "
            "--init-settings to create a template."
        ) from error
    except JSONDecodeError as error:
        raise ConfigurationError(
            f"Invalid JSON in '{settings_path}' at line {error.lineno}, "
            f"column {error.colno}: {error.msg}."
        ) from error
    except OSError as error:
        raise ConfigurationError(
            f"Could not read settings file '{settings_path}': {error}."
        ) from error

    if not isinstance(payload, dict):
        raise ConfigurationError("The settings root must be a JSON object.")
    missing = tuple(field for field in DEFAULT_SETTINGS if field not in payload)
    if missing:
        raise ConfigurationError(
            "Missing required settings field(s): " + ", ".join(missing) + "."
        )
    extra = tuple(sorted(set(payload) - set(DEFAULT_SETTINGS)))
    if extra:
        raise ConfigurationError(
            "Unsupported v0.1 settings field(s): " + ", ".join(extra) + "."
        )

    workbook_text = _nonempty_string(payload["excel_file_path"], "excel_file_path")
    workbook_path = Path(workbook_text)
    if not workbook_path.is_absolute():
        workbook_path = settings_path.resolve().parent / workbook_path
    workbook_path = workbook_path.resolve()
    if workbook_path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ConfigurationError(
            "'excel_file_path' must identify an .xlsx or .xlsm workbook."
        )
    if not workbook_path.is_file():
        raise ConfigurationError(
            f"Configured workbook does not exist: '{workbook_path}'."
        )

    sheet = _nonempty_string(payload["compliance_sheet_name"], "compliance_sheet_name")
    test = _nonempty_string(payload["test"], "test").upper()
    if test != "SIGPATH":
        raise ConfigurationError("v0.1 supports only test 'SIGPATH'.")

    measurements_value = payload["measurements"]
    if type(measurements_value) is not list or measurements_value != ["GAIN"]:
        raise ConfigurationError("v0.1 'measurements' must be exactly ['GAIN'].")

    variation_value = payload["acceptable_variation"]
    if type(variation_value) is not dict or set(variation_value) != {"GAIN"}:
        raise ConfigurationError(
            "'acceptable_variation' must contain exactly a GAIN value in v0.1."
        )
    gain_variation = variation_value["GAIN"]
    if (
        isinstance(gain_variation, bool)
        or not isinstance(gain_variation, (int, float))
        or not isfinite(gain_variation)
        or gain_variation < 0
    ):
        raise ConfigurationError(
            "'acceptable_variation.GAIN' must be a finite non-negative number."
        )

    background = payload["background_information"]
    if not isinstance(background, str):
        raise ConfigurationError("'background_information' must be a string.")
    main_pivot = _nonempty_string(payload["main_pivot"], "main_pivot")

    group_by = payload["group_by"]
    if type(group_by) is not list or any(not isinstance(item, str) for item in group_by):
        raise ConfigurationError("'group_by' must be a JSON list of strings.")
    if group_by:
        raise ConfigurationError("'group_by' must be empty because v0.1 has no aggregation.")

    aggregate = payload["aggregate_port_groups"]
    if type(aggregate) is not bool:
        raise ConfigurationError("'aggregate_port_groups' must be a boolean.")
    if aggregate:
        raise ConfigurationError(
            "'aggregate_port_groups' must be false because v0.1 has no aggregation."
        )
    bypass = payload["bypass_model"]
    if bypass is not True:
        raise ConfigurationError("'bypass_model' must be true in v0.1.")

    return Settings(
        excel_file_path=workbook_path,
        compliance_sheet_name=sheet,
        test=test,
        measurements=("GAIN",),
        acceptable_variation={"GAIN": float(gain_variation)},
        background_information=background,
        main_pivot=main_pivot,
        group_by=(),
        aggregate_port_groups=False,
        bypass_model=True,
    )


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"'{field}' must be a non-empty string.")
    return value.strip()
