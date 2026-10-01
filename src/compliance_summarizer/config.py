"""Load and validate the v0.2 ``JUI.json`` contract."""

from __future__ import annotations

import json
from copy import deepcopy
from json import JSONDecodeError
from pathlib import Path

from .errors import ConfigurationError
from .measurements import MEASUREMENTS
from .models import CustomGroupDefinition, Settings
from .workbook import canonical_metadata_header, is_path_excluded_header


DEFAULT_SETTINGS: dict[str, object] = {
    "excel_file_path": "./REFERENCE.xlsm",
    "compliance_sheet_name": "Combined",
    "block": "SIGPATH",
    "testnames": ["GAIN"],
    "background_information": "",
    "main_pivot": "",
    "group_by": [],
    "include_group_failures": False,
    "include_group_marginal_passes": False,
    "bypass_model": True,
}
OPTIONAL_SETTINGS = frozenset(
    {"include_group_failures", "include_group_marginal_passes"}
)


def default_settings() -> dict[str, object]:
    return deepcopy(DEFAULT_SETTINGS)


def load_test_filters(
    settings_path: str | Path,
) -> dict[str, dict[str, tuple[object, ...]]]:
    """Load optional per-testname row filters beside the settings file."""

    filter_path = Path(settings_path).resolve().parent / "configs" / "test_filters.json"
    if not filter_path.is_file():
        return {}
    try:
        payload = json.loads(filter_path.read_text(encoding="utf-8"))
    except JSONDecodeError as error:
        raise ConfigurationError(
            f"Invalid JSON in '{filter_path}' at line {error.lineno}, "
            f"column {error.colno}: {error.msg}."
        ) from error
    except OSError as error:
        raise ConfigurationError(
            f"Could not read test filter file '{filter_path}': {error}."
        ) from error

    if not isinstance(payload, dict):
        raise ConfigurationError("The test filter root must be a JSON object.")

    filters: dict[str, dict[str, tuple[object, ...]]] = {}
    for raw_measurement, raw_rules in payload.items():
        measurement = _nonempty_string(raw_measurement, "test filter testname").upper()
        if measurement not in MEASUREMENTS:
            raise ConfigurationError(
                f"Unsupported test filter testname '{raw_measurement}'. Supported "
                f"values: {', '.join(MEASUREMENTS)}."
            )
        if not isinstance(raw_rules, dict):
            raise ConfigurationError(
                f"Test filter '{measurement}' must contain a JSON object of fields."
            )
        normalized_rules: dict[str, tuple[object, ...]] = {}
        for raw_field, raw_values in raw_rules.items():
            field = canonical_metadata_header(raw_field)
            if not field:
                raise ConfigurationError(
                    f"Test filter '{measurement}' contains a blank field name."
                )
            if type(raw_values) is not list or not raw_values:
                raise ConfigurationError(
                    f"Test filter '{measurement}.{field}' must be a non-empty list."
                )
            normalized_rules[field] = tuple(raw_values)
        filters[measurement] = normalized_rules
    return filters


def load_custom_groups(
    settings_path: str | Path,
) -> dict[str, CustomGroupDefinition]:
    """Load named metadata grouping schemes beside the settings file."""

    group_path = Path(settings_path).resolve().parent / "configs" / "groups.json"
    if not group_path.is_file():
        return {}
    try:
        payload = json.loads(group_path.read_text(encoding="utf-8"))
    except JSONDecodeError as error:
        raise ConfigurationError(
            f"Invalid JSON in '{group_path}' at line {error.lineno}, "
            f"column {error.colno}: {error.msg}."
        ) from error
    except OSError as error:
        raise ConfigurationError(
            f"Could not read custom group file '{group_path}': {error}."
        ) from error

    if not isinstance(payload, dict):
        raise ConfigurationError("The custom group root must be a JSON object.")

    definitions: dict[str, CustomGroupDefinition] = {}
    for raw_name, raw_definition in payload.items():
        name = _nonempty_string(raw_name, "custom group name")
        lookup_name = canonical_metadata_header(name)
        if lookup_name in definitions:
            raise ConfigurationError(
                f"Custom group name '{raw_name}' duplicates another name after "
                "normalization."
            )
        if not isinstance(raw_definition, dict):
            raise ConfigurationError(
                f"Custom group '{name}' must contain a JSON object definition."
            )
        required = {"field", "groups", "default"}
        missing = tuple(sorted(required - set(raw_definition)))
        if missing:
            raise ConfigurationError(
                f"Custom group '{name}' is missing required field(s): "
                + ", ".join(missing)
                + "."
            )

        field = canonical_metadata_header(raw_definition["field"])
        if not field:
            raise ConfigurationError(f"Custom group '{name}' has a blank field.")
        if is_path_excluded_header(field):
            raise ConfigurationError(
                f"Custom group '{name}' cannot use source-result or limit field "
                f"'{field}'."
            )

        raw_groups = raw_definition["groups"]
        if not isinstance(raw_groups, dict) or not raw_groups:
            raise ConfigurationError(
                f"Custom group '{name}.groups' must be a non-empty JSON object."
            )
        groups: list[tuple[str, tuple[object, ...]]] = []
        seen_labels: set[str] = set()
        for raw_label, raw_values in raw_groups.items():
            label = _nonempty_string(raw_label, f"custom group '{name}' label")
            label_key = label.casefold()
            if label_key in seen_labels:
                raise ConfigurationError(
                    f"Custom group '{name}' contains duplicate label '{label}'."
                )
            if type(raw_values) is not list or not raw_values:
                raise ConfigurationError(
                    f"Custom group '{name}.{label}' must contain a non-empty list."
                )
            seen_labels.add(label_key)
            groups.append((label, tuple(raw_values)))

        definitions[lookup_name] = CustomGroupDefinition(
            name=name,
            field=field,
            groups=tuple(groups),
            default=raw_definition["default"],
        )
    return definitions


def create_settings_template(path: str | Path = "JUI.json") -> Path:
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


def load_settings(path: str | Path = "JUI.json") -> Settings:
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
    missing = tuple(
        field
        for field in DEFAULT_SETTINGS
        if field not in payload and field not in OPTIONAL_SETTINGS
    )
    if missing:
        raise ConfigurationError(
            "Missing required settings field(s): " + ", ".join(missing) + "."
        )
    extra = tuple(sorted(set(payload) - set(DEFAULT_SETTINGS)))
    if extra:
        raise ConfigurationError(
            "Unsupported v0.2 settings field(s): " + ", ".join(extra) + "."
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
    block = _nonempty_string(payload["block"], "block").upper()
    if block != "SIGPATH":
        raise ConfigurationError("v0.2 supports only block 'SIGPATH'.")

    testnames_value = payload["testnames"]
    supported_measurements = tuple(MEASUREMENTS)
    if type(testnames_value) is not list or not testnames_value:
        raise ConfigurationError(
            "'testnames' must be a non-empty list of supported values: "
            + ", ".join(supported_measurements)
            + "."
        )
    normalized_measurements: list[str] = []
    for item in testnames_value:
        if not isinstance(item, str) or not item.strip():
            raise ConfigurationError(
                "'testnames' must contain non-empty supported measurement names."
            )
        measurement = item.strip().upper()
        if measurement not in MEASUREMENTS:
            raise ConfigurationError(
                f"Unsupported measurement '{item}'. Supported values: "
                + ", ".join(supported_measurements)
                + "."
            )
        if measurement in normalized_measurements:
            raise ConfigurationError(
                f"'testnames' contains duplicate measurement '{measurement}'."
            )
        normalized_measurements.append(measurement)
    normalized_measurements_tuple = tuple(normalized_measurements)

    background = payload["background_information"]
    if not isinstance(background, str):
        raise ConfigurationError("'background_information' must be a string.")
    main_pivot = _nonempty_string(payload["main_pivot"], "main_pivot")

    group_by = payload["group_by"]
    if type(group_by) is not list or any(not isinstance(item, str) for item in group_by):
        raise ConfigurationError("'group_by' must be a JSON list of strings.")
    normalized_group_by: list[str] = []
    for item in group_by:
        field = canonical_metadata_header(item)
        if not field:
            raise ConfigurationError("'group_by' cannot contain blank field names.")
        if is_path_excluded_header(field):
            raise ConfigurationError(
                f"Unsupported 'group_by' field '{item}': source-result and limit "
                "fields cannot be used for grouping."
            )
        if field in normalized_group_by:
            raise ConfigurationError(
                f"'group_by' contains duplicate field '{field}'."
            )
        normalized_group_by.append(field)

    include_group_failures = payload.get(
        "include_group_failures",
        DEFAULT_SETTINGS["include_group_failures"],
    )
    if type(include_group_failures) is not bool:
        raise ConfigurationError("'include_group_failures' must be a boolean.")
    include_group_marginal_passes = payload.get(
        "include_group_marginal_passes",
        DEFAULT_SETTINGS["include_group_marginal_passes"],
    )
    if type(include_group_marginal_passes) is not bool:
        raise ConfigurationError(
            "'include_group_marginal_passes' must be a boolean."
        )

    bypass = payload["bypass_model"]
    if bypass is not True:
        raise ConfigurationError("'bypass_model' must be true in v0.2.")

    return Settings(
        excel_file_path=workbook_path,
        compliance_sheet_name=sheet,
        block=block,
        testnames=normalized_measurements_tuple,
        background_information=background,
        main_pivot=main_pivot,
        group_by=tuple(normalized_group_by),
        include_group_failures=include_group_failures,
        include_group_marginal_passes=include_group_marginal_passes,
        bypass_model=True,
    )


def _nonempty_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigurationError(f"'{field}' must be a non-empty string.")
    return value.strip()
