"""Partition normalized measurement rows into independent analyses."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .errors import WorkbookValidationError
from .models import (
    ComplianceCase,
    GroupedAnalysis,
    ParsedMeasurement,
)
from .statistics import calculate_measurement_statistics


_BLANK = object()


def calculate_grouped_analyses(
    parsed: ParsedMeasurement,
    group_by: tuple[str, ...],
    main_pivot: str,
    acceptable_variation: float,
) -> tuple[tuple[GroupedAnalysis, ...], tuple[str, ...]]:
    """Calculate grouped statistics while preserving the overall parsed rows."""

    if not group_by:
        return (), ()

    normalized_fields = tuple(field.strip().upper() for field in group_by)
    missing = tuple(
        field for field in normalized_fields if field not in parsed.schema.fixed_columns
    )
    if missing:
        available = ", ".join(parsed.schema.fixed_columns)
        raise WorkbookValidationError(
            f"Configured group_by field(s) are absent from worksheet "
            f"'{parsed.schema.name}': {', '.join(missing)}. Available fixed "
            f"fields: {available}."
        )

    groups: dict[tuple[object, ...], list[ComplianceCase]] = defaultdict(list)
    display_keys: dict[tuple[object, ...], tuple[tuple[str, Any], ...]] = {}
    for case in parsed.cases:
        raw_values = tuple(case.fixed_values.get(field) for field in normalized_fields)
        group_token = tuple(_group_token(value) for value in raw_values)
        groups[group_token].append(case)
        display_keys[group_token] = tuple(
            (field, _display_group_value(value))
            for field, value in zip(normalized_fields, raw_values, strict=True)
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
            case.pivot_values.get(main_pivot, {}).get("wcMargin") is not None
            for case in cases
        ):
            warnings.append(
                f"Group {_format_group_key(group_key)}: main pivot '{main_pivot}' "
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
        )
        statistics = calculate_measurement_statistics(
            grouped,
            main_pivot,
            acceptable_variation,
            include_ranked_cases=False,
        )
        analyses.append(GroupedAnalysis(group_key=group_key, statistics=statistics))

    return tuple(analyses), tuple(warnings)


def format_group_key(group_key: tuple[tuple[str, Any], ...]) -> str:
    """Return the compact group label used by the HTML report."""

    return _format_group_key(group_key)


def _group_token(value: object) -> object:
    if value is None or (isinstance(value, str) and not value.strip()):
        return _BLANK
    return value


def _display_group_value(value: object) -> object:
    return "(blank)" if _group_token(value) is _BLANK else value


def _group_sort_key(group_key: tuple[tuple[str, Any], ...]) -> tuple[str, ...]:
    return tuple(str(value) for _, value in group_key)


def _format_group_key(group_key: tuple[tuple[str, Any], ...]) -> str:
    return "; ".join(f"{field}={value}" for field, value in group_key)
