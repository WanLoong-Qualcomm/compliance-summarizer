"""Partition normalized measurement rows into independent analyses."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any

from .errors import WorkbookValidationError
from .models import (
    ComplianceCase,
    CustomGroupDefinition,
    GroupedAnalysis,
    ParsedMeasurement,
)
from .statistics import calculate_measurement_statistics
from .workbook import (
    FAIL_TYPE_FIELD,
    FAIL_TYPE_DISPLAY_NAME,
    canonical_metadata_header,
    fail_type_group_pivot,
    is_fail_type_group_field,
    is_path_excluded_header,
)


_BLANK = object()


@dataclass(frozen=True, slots=True)
class _GroupDimension:
    label: str
    field: str
    definition: CustomGroupDefinition | None = None
    fail_type_pivot: str | None = None


def calculate_grouped_analyses(
    parsed: ParsedMeasurement,
    group_by: tuple[str, ...],
    anchor_pivot: str,
    acceptable_variation: float,
    *,
    custom_groups: Mapping[str, CustomGroupDefinition] | None = None,
    add_fail_type: bool = False,
    include_failures: bool = False,
    include_marginal_passes: bool = False,
) -> tuple[tuple[GroupedAnalysis, ...], tuple[str, ...]]:
    """Calculate grouped statistics while preserving the overall parsed rows."""

    if not group_by:
        return (), ()

    dimensions = _resolve_dimensions(
        parsed,
        group_by,
        anchor_pivot,
        custom_groups or {},
        add_fail_type=add_fail_type,
    )
    groups: dict[tuple[object, ...], list[ComplianceCase]] = defaultdict(list)
    display_keys: dict[tuple[object, ...], tuple[tuple[str, Any], ...]] = {}
    for case in parsed.cases:
        display_values = tuple(
            _dimension_value(case, dimension) for dimension in dimensions
        )
        group_token = tuple(_group_token(value) for value in display_values)
        groups[group_token].append(case)
        display_keys[group_token] = tuple(
            (dimension.label, _display_group_value(value))
            for dimension, value in zip(dimensions, display_values, strict=True)
        )

    analyses: list[GroupedAnalysis] = []
    warnings: list[str] = []
    for group_token in sorted(
        groups,
        key=lambda token: _group_sort_key(display_keys[token]),
    ):
        cases = tuple(groups[group_token])
        group_key = display_keys[group_token]
        if not any(
            case.pivot_values.get(anchor_pivot, {}).get("wcMargin") is not None
            for case in cases
        ):
            warnings.append(
                f"Group {_format_group_key(group_key)}: anchor pivot '{anchor_pivot}' "
                f"has no valid wcMargin values for {parsed.measurement}; "
                "grouped analysis was skipped as a coverage gap."
            )
            continue

        grouped = ParsedMeasurement(
            schema=parsed.schema,
            measurement=parsed.measurement,
            cases=cases,
            coverage=parsed.coverage,
            warnings=(),
            fail_type_enabled=parsed.fail_type_enabled,
        )
        statistics = calculate_measurement_statistics(
            grouped,
            anchor_pivot,
            acceptable_variation,
            include_ranked_cases=include_failures or include_marginal_passes,
            include_failure_cases=include_failures,
            include_pass_cases=include_marginal_passes,
        )
        analyses.append(
            GroupedAnalysis(
                group_key=group_key,
                statistics=statistics,
                include_failures=include_failures,
                include_marginal_passes=include_marginal_passes,
            )
        )

    return tuple(analyses), tuple(warnings)


def format_group_key(group_key: tuple[tuple[str, Any], ...]) -> str:
    """Return the compact group label used by the HTML report."""

    return _format_group_key(group_key)


def _resolve_dimensions(
    parsed: ParsedMeasurement,
    group_by: tuple[str, ...],
    anchor_pivot: str,
    custom_groups: Mapping[str, CustomGroupDefinition],
    *,
    add_fail_type: bool,
) -> tuple[_GroupDimension, ...]:
    dimensions: list[_GroupDimension] = []
    missing: list[str] = []
    excluded: list[str] = []
    for item in group_by:
        requested = canonical_metadata_header(item)
        if is_fail_type_group_field(requested):
            explicit_pivot = fail_type_group_pivot(requested)
            configured_pivot = explicit_pivot or anchor_pivot
            matching_pivot = next(
                (
                    pivot
                    for pivot in parsed.schema.pivot_names
                    if configured_pivot is not None
                    and pivot.casefold() == configured_pivot.casefold()
                ),
                None,
            )
            if not add_fail_type or not parsed.fail_type_enabled:
                raise WorkbookValidationError(
                    f"Configured group_by field '{item}' requires 'add_fail_type' "
                    "to be true."
                )
            if matching_pivot is None:
                missing.append(requested)
                continue
            dimensions.append(
                _GroupDimension(
                    label=(
                        FAIL_TYPE_DISPLAY_NAME
                        if explicit_pivot is None
                        else f"{matching_pivot}.{FAIL_TYPE_FIELD}"
                    ),
                    field=FAIL_TYPE_FIELD,
                    fail_type_pivot=matching_pivot,
                )
            )
            continue
        definition = custom_groups.get(requested)
        if definition is None:
            dimension = _GroupDimension(label=requested, field=requested)
        else:
            dimension = _GroupDimension(
                label=definition.name,
                field=definition.field,
                definition=definition,
            )
        if is_path_excluded_header(dimension.field):
            excluded.append(dimension.field)
        elif dimension.field not in parsed.schema.metadata_columns:
            missing.append(
                f"{dimension.label} (source field {dimension.field})"
                if dimension.definition is not None
                else dimension.field
            )
        dimensions.append(dimension)

    if excluded:
        raise WorkbookValidationError(
            "Configured group_by field(s) cannot be used for grouping: "
            + ", ".join(excluded)
            + "."
        )
    if missing:
        available = ", ".join(parsed.schema.metadata_columns)
        available_groups = ", ".join(sorted(custom_groups))
        group_hint = (
            f" Available custom groups: {available_groups}."
            if available_groups
            else " No custom groups are available from configs/groups.json."
        )
        raise WorkbookValidationError(
            f"Configured group_by field(s) are absent from worksheet "
            f"'{parsed.schema.name}': {', '.join(missing)}. Available metadata "
            f"fields: {available}.{group_hint}"
        )
    return tuple(dimensions)


def _dimension_value(case: ComplianceCase, dimension: _GroupDimension) -> object:
    if dimension.fail_type_pivot is not None:
        return case.pivot_fail_types.get(dimension.fail_type_pivot)
    value = case.metadata_values.get(dimension.field)
    if dimension.definition is None:
        return value
    return _custom_group_value(value, dimension.definition)


def _custom_group_value(
    value: object,
    definition: CustomGroupDefinition,
) -> object:
    if _is_blank(value):
        return definition.default
    for label, allowed_values in definition.groups:
        if any(_group_value_matches(value, allowed) for allowed in allowed_values):
            return label
    return definition.default


def _group_value_matches(actual: object, expected: object) -> bool:
    if _is_blank(actual) or _is_blank(expected):
        return False
    if isinstance(actual, str) and isinstance(expected, str):
        return actual.strip().casefold() == expected.strip().casefold()
    if isinstance(actual, bool) or isinstance(expected, bool):
        return type(actual) is type(expected) and actual == expected

    actual_number = _as_number(actual)
    expected_number = _as_number(expected)
    if actual_number is not None and expected_number is not None:
        return actual_number == expected_number

    if isinstance(actual, (list, tuple)) and isinstance(expected, (list, tuple)):
        return len(actual) == len(expected) and all(
            _group_value_matches(left, right)
            for left, right in zip(actual, expected, strict=True)
        )
    if isinstance(actual, dict) and isinstance(expected, dict):
        if set(actual) != set(expected):
            return False
        return all(_group_value_matches(actual[key], expected[key]) for key in actual)
    return actual == expected


def _as_number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    elif isinstance(value, str):
        try:
            number = float(value.strip())
        except (TypeError, ValueError):
            return None
    else:
        return None
    return number if isfinite(number) else None


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _group_token(value: object) -> object:
    if _is_blank(value):
        return _BLANK
    return _freeze_value(value)


def _freeze_value(value: object) -> object:
    if isinstance(value, dict):
        return tuple(
            sorted((str(key), _freeze_value(item)) for key, item in value.items())
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    try:
        hash(value)
    except TypeError:
        return repr(value)
    return value


def _display_group_value(value: object) -> object:
    return "(blank)" if _is_blank(value) else value


def _group_sort_key(group_key: tuple[tuple[str, Any], ...]) -> tuple[str, ...]:
    return tuple(str(value) for _, value in group_key)


def _format_group_key(group_key: tuple[tuple[str, Any], ...]) -> str:
    return "; ".join(f"{field}={value}" for field, value in group_key)
