"""SIGPATH workbook schema discovery and row normalization."""

from __future__ import annotations

from collections import Counter
from contextlib import closing
from math import isfinite
from pathlib import Path
from typing import Any, Mapping, Sequence

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .errors import WorkbookValidationError
from .measurements import get_measurement_definition, metadata_midpoint
from .models import (
    ComplianceCase,
    CoverageSummary,
    ParsedMeasurement,
    PivotSchema,
    SheetSchema,
)


REQUIRED_METADATA_HEADERS = ("TESTNAME", "MEASPORT")
PATH_EXCLUDED_HEADERS = ("Result?", "LL", "UL")
_PATH_EXCLUDED_CANONICAL = frozenset(
    "RESULT?" if header == "Result?" else header.upper()
    for header in PATH_EXCLUDED_HEADERS
)
REQUIRED_PIVOT_STATISTICS = ("wcMargin",)
ALTERNATIVE_PIVOT_STATISTICS = ("MEAN", "NN_25C AVG")
RECOGNIZED_PIVOT_STATISTICS = (
    "MIN",
    "MAX",
    "MEAN",
    "NN_25C AVG",
    "wcMargin",
    "wcValue",
)


def load_measurement(
    workbook_path: str | Path,
    sheet_name: str,
    measurement: str = "GAIN",
    *,
    test_filters: Mapping[str, Mapping[str, Sequence[object]]] | None = None,
) -> ParsedMeasurement:
    """Load and validate one measurement without modifying the source workbook."""

    return load_measurements(
        workbook_path,
        sheet_name,
        (measurement,),
        test_filters=test_filters,
    )[0]


def load_measurements(
    workbook_path: str | Path,
    sheet_name: str,
    measurements: Sequence[str],
    *,
    test_filters: Mapping[str, Mapping[str, Sequence[object]]] | None = None,
) -> tuple[ParsedMeasurement, ...]:
    """Load and validate multiple measurements from one workbook pass."""

    source = Path(workbook_path)
    try:
        workbook = load_workbook(
            source,
            read_only=True,
            data_only=True,
            keep_links=False,
        )
    except (OSError, InvalidFileException, ValueError) as error:
        raise WorkbookValidationError(
            f"Could not open workbook '{source}': {error}. Check that it is a valid "
            ".xlsx or .xlsm file and is not locked or corrupt."
        ) from error

    with closing(workbook):
        if sheet_name not in workbook.sheetnames:
            available = ", ".join(workbook.sheetnames) or "none"
            raise WorkbookValidationError(
                f"Worksheet '{sheet_name}' was not found in '{source.name}'. "
                f"Available sheets: {available}."
            )
        worksheet = workbook[sheet_name]
        schema = discover_schema(worksheet)
        return parse_measurements_rows(
            worksheet,
            schema,
            measurements,
            test_filters=test_filters,
        )


def discover_schema(worksheet: Any) -> SheetSchema:
    """Discover dynamic metadata columns and pivot groups from header rows 2-4."""

    header_rows = list(
        worksheet.iter_rows(min_row=2, max_row=4, values_only=True)
    )
    while len(header_rows) < 3:
        header_rows.append(())
    pivot_labels, statistic_labels, column_labels = (tuple(row) for row in header_rows)
    width = max(map(len, (pivot_labels, statistic_labels, column_labels)), default=0)
    if width == 0:
        raise WorkbookValidationError(
            f"Worksheet '{worksheet.title}' has no usable headers in rows 2 through 4."
        )

    errors: list[str] = []
    pivot_blocks: dict[str, dict[str, int]] = {}
    pivot_order: list[str] = []
    pivot_stat_columns: set[int] = set()
    active_pivot: str | None = None
    for column in range(1, width + 1):
        label = _text(_cell(pivot_labels, column))
        if label:
            active_pivot = label
        statistic = _canonical_statistic(_cell(statistic_labels, column))
        if statistic is None:
            continue
        if active_pivot is None:
            errors.append(
                f"pivot statistic '{statistic}' at column {column} has no pivot name "
                "in row 2"
            )
            continue
        if active_pivot not in pivot_blocks:
            pivot_blocks[active_pivot] = {}
            pivot_order.append(active_pivot)
        if statistic in pivot_blocks[active_pivot]:
            errors.append(
                f"pivot '{active_pivot}' defines '{statistic}' more than once"
            )
        else:
            pivot_blocks[active_pivot][statistic] = column
            pivot_stat_columns.add(column)

    metadata_positions: dict[str, list[int]] = {}
    for column in range(1, width + 1):
        if column in pivot_stat_columns:
            continue
        header = canonical_metadata_header(_cell(column_labels, column))
        if header:
            metadata_positions.setdefault(header, []).append(column)

    metadata_columns: dict[str, int] = {}
    for header, positions in metadata_positions.items():
        if len(positions) > 1:
            errors.append(
                f"row-4 metadata header '{header}' appears more than once at columns "
                f"{positions}"
            )
        else:
            metadata_columns[header] = positions[0]

    for header in REQUIRED_METADATA_HEADERS:
        if header not in metadata_columns:
            errors.append(f"required row-4 metadata header '{header}' is missing")

    if not pivot_blocks:
        errors.append("no pivot groups were found from row-2 names and row-3 statistics")
    for pivot_name in pivot_order:
        missing = [
            statistic
            for statistic in REQUIRED_PIVOT_STATISTICS
            if statistic not in pivot_blocks[pivot_name]
        ]
        if not any(
            statistic in pivot_blocks[pivot_name]
            for statistic in ALTERNATIVE_PIVOT_STATISTICS
        ):
            missing.append("MEAN or NN_25C AVG")
        if missing:
            errors.append(
                f"pivot '{pivot_name}' is missing required statistic(s): "
                + ", ".join(missing)
            )
    if errors:
        raise WorkbookValidationError(
            f"Worksheet '{worksheet.title}' has an incompatible SIGPATH layout: "
            + "; ".join(errors)
            + ". Correct rows 2-4 and retry."
        )
    if getattr(worksheet, "max_row", 0) < 5:
        raise WorkbookValidationError(
            f"Worksheet '{worksheet.title}' contains no data below header row 4."
        )

    return SheetSchema(
        name=worksheet.title,
        metadata_columns=metadata_columns,
        pivots=tuple(
            PivotSchema(name=name, statistics=pivot_blocks[name])
            for name in pivot_order
        ),
    )


def parse_measurement_rows(
    worksheet: Any,
    schema: SheetSchema,
    measurement: str,
) -> ParsedMeasurement:
    """Normalize one measurement and summarize unusable numeric cells."""

    return parse_measurements_rows(worksheet, schema, (measurement,))[0]


def parse_measurements_rows(
    worksheet: Any,
    schema: SheetSchema,
    measurements: Sequence[str],
    *,
    test_filters: Mapping[str, Mapping[str, Sequence[object]]] | None = None,
) -> tuple[ParsedMeasurement, ...]:
    """Normalize multiple measurements in one worksheet row scan."""

    requested_measurements = tuple(measurement.strip().upper() for measurement in measurements)
    definitions = {
        measurement: get_measurement_definition(measurement)
        for measurement in requested_measurements
    }
    max_column = max(
        [*schema.metadata_columns.values()]
        + [
            column
            for pivot in schema.pivots
            for column in pivot.statistics.values()
        ]
    )
    cases_by_measurement: dict[str, list[ComplianceCase]] = {
        measurement: [] for measurement in requested_measurements
    }
    limit_gap_counts = {measurement: 0 for measurement in requested_measurements}
    required_statistics = {
        pivot.name: (*REQUIRED_PIVOT_STATISTICS, _comparison_statistic(pivot))
        for pivot in schema.pivots
    }
    gap_counts = {
        measurement: {
            pivot.name: Counter({field: 0 for field in required_statistics[pivot.name]})
            for pivot in schema.pivots
        }
        for measurement in requested_measurements
    }
    malformed_counts = {
        measurement: {
            pivot.name: Counter({field: 0 for field in required_statistics[pivot.name]})
            for pivot in schema.pivots
        }
        for measurement in requested_measurements
    }
    rows_with_gap = {
        measurement: {pivot.name: 0 for pivot in schema.pivots}
        for measurement in requested_measurements
    }
    filter_rules = {
        measurement: dict((test_filters or {}).get(measurement, {}))
        for measurement in requested_measurements
    }
    for measurement, rules in filter_rules.items():
        missing_filter_fields = tuple(
            field for field in rules if field not in schema.metadata_columns
        )
        if missing_filter_fields:
            available = ", ".join(schema.metadata_columns)
            raise WorkbookValidationError(
                f"Test filter field(s) for '{measurement}' are absent from worksheet "
                f"'{schema.name}': {', '.join(missing_filter_fields)}. Available metadata "
                f"fields: {available}."
            )
    filtered_row_counts = {measurement: 0 for measurement in requested_measurements}
    measurement_row_counts = {measurement: 0 for measurement in requested_measurements}
    duplicate_identity_counts = {measurement: 0 for measurement in requested_measurements}
    seen_identities = {measurement: set() for measurement in requested_measurements}

    for worksheet_row, values in enumerate(
        worksheet.iter_rows(
            min_row=schema.data_start_row,
            max_col=max_column,
            values_only=True,
        ),
        start=schema.data_start_row,
    ):
        requested = _text(_cell(values, schema.metadata_columns["TESTNAME"])).upper()
        if requested not in cases_by_measurement:
            continue
        measurement_row_counts[requested] += 1
        metadata_values = {
            header: _cell(values, column)
            for header, column in schema.metadata_columns.items()
        }
        if not _matches_test_filter(metadata_values, filter_rules[requested]):
            filtered_row_counts[requested] += 1
            continue
        definition = definitions[requested]
        if definition.requires_limits and metadata_midpoint(metadata_values) is None:
            limit_gap_counts[requested] += 1
        identity = tuple(
            (header, metadata_values.get(header))
            for header in schema.metadata_columns
            if not is_path_excluded_header(header)
        )
        if identity in seen_identities[requested]:
            duplicate_identity_counts[requested] += 1
        else:
            seen_identities[requested].add(identity)

        pivot_values: dict[str, dict[str, float | None]] = {}
        pivot_raw_values: dict[str, dict[str, Any]] = {}
        for pivot in schema.pivots:
            normalized: dict[str, float | None] = {}
            raw_values: dict[str, Any] = {}
            row_has_gap = False
            for statistic, column in pivot.statistics.items():
                raw = _cell(values, column)
                raw_values[statistic] = raw
                numeric, malformed = _numeric(raw)
                normalized[statistic] = numeric
                if statistic in required_statistics[pivot.name] and numeric is None:
                    gap_counts[requested][pivot.name][statistic] += 1
                    row_has_gap = True
                    if malformed:
                        malformed_counts[requested][pivot.name][statistic] += 1
            if row_has_gap:
                rows_with_gap[requested][pivot.name] += 1
            pivot_values[pivot.name] = normalized
            pivot_raw_values[pivot.name] = raw_values

        cases_by_measurement[requested].append(
            ComplianceCase(
                worksheet_row=worksheet_row,
                identity=identity,
                metadata_values=metadata_values,
                pivot_values=pivot_values,
                pivot_raw_values=pivot_raw_values,
            )
        )

    results: list[ParsedMeasurement] = []
    for requested in requested_measurements:
        cases = cases_by_measurement[requested]
        if not cases:
            if measurement_row_counts[requested] and filter_rules[requested]:
                raise WorkbookValidationError(
                    f"Worksheet '{schema.name}' contains no rows for '{requested}' "
                    "after applying its configured test filters."
                )
            raise WorkbookValidationError(
                f"Worksheet '{schema.name}' contains no rows whose TESTNAME is exactly "
                f"'{requested}'."
            )

        warnings: list[str] = []
        filtered_row_count = filtered_row_counts[requested]
        if filtered_row_count:
            warnings.append(
                f"{requested}: {filtered_row_count} row(s) were excluded by configured "
                f"test filters ({_format_test_filter(filter_rules[requested])})."
            )
        duplicate_identity_count = duplicate_identity_counts[requested]
        if duplicate_identity_count:
            warnings.append(
                f"{duplicate_identity_count} {requested} row(s) repeat an identifying-field "
                "combination; worksheet row numbers are retained only to make displayed ties "
                "traceable."
            )
        limit_gap_count = limit_gap_counts[requested]
        if limit_gap_count:
            warnings.append(
                f"{requested}: {limit_gap_count} row(s) have missing, malformed, or "
                "non-finite LL/UL limits and are excluded from GAIN-DNL comparisons."
            )
        coverage = tuple(
            CoverageSummary(
                pivot=pivot.name,
                rows_with_gaps=rows_with_gap[requested][pivot.name],
                gaps_by_field=dict(gap_counts[requested][pivot.name]),
                malformed_by_field=dict(malformed_counts[requested][pivot.name]),
            )
            for pivot in schema.pivots
        )
        for item in coverage:
            if item.rows_with_gaps:
                warnings.append(
                    f"{item.pivot}: {item.rows_with_gaps} row(s) have required-value "
                    "coverage gaps and are excluded only from affected metrics."
                )
            malformed = sum(item.malformed_by_field.values())
            if malformed:
                warnings.append(
                    f"{item.pivot}: {malformed} required value(s) are non-numeric or "
                    "non-finite and were treated as coverage gaps."
                )

        results.append(
            ParsedMeasurement(
                schema=schema,
                measurement=requested,
                cases=tuple(cases),
                coverage=coverage,
                warnings=tuple(warnings),
            )
        )
    return tuple(results)


def _matches_test_filter(
    metadata_values: Mapping[str, object],
    rules: Mapping[str, Sequence[object]],
) -> bool:
    return all(
        any(_filter_value_matches(metadata_values.get(field), allowed) for allowed in values)
        for field, values in rules.items()
    )


def _filter_value_matches(actual: object, expected: object) -> bool:
    if isinstance(actual, str) and isinstance(expected, str):
        return actual.strip().casefold() == expected.strip().casefold()
    return actual == expected


def _format_test_filter(rules: Mapping[str, Sequence[object]]) -> str:
    return "; ".join(
        f"{field} in ({', '.join(str(value) for value in values)})"
        for field, values in rules.items()
    )


def _cell(row: tuple[Any, ...], column: int) -> Any:
    return row[column - 1] if column > 0 and column <= len(row) else None


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def canonical_metadata_header(value: object) -> str:
    """Normalize a workbook metadata header for lookup and configuration."""

    text = " ".join(_text(value).split())
    if text.upper() == "RESULT?":
        return "Result?"
    return text.upper()


def is_path_excluded_header(value: object) -> bool:
    """Return whether a metadata header is excluded from path identity/grouping."""

    return canonical_metadata_header(value).upper() in _PATH_EXCLUDED_CANONICAL


def _canonical_statistic(value: object) -> str | None:
    text = " ".join(_text(value).split())
    upper = text.upper()
    aliases = {
        "MIN": "MIN",
        "MAX": "MAX",
        "MEAN": "MEAN",
        "NN_25C AVG": "NN_25C AVG",
        "WCMARGIN": "wcMargin",
        "WCVALUE": "wcValue",
    }
    return aliases.get(upper)


def _comparison_statistic(pivot: PivotSchema) -> str:
    for statistic in ALTERNATIVE_PIVOT_STATISTICS:
        if statistic in pivot.statistics:
            return statistic
    raise WorkbookValidationError(
        f"Pivot '{pivot.name}' has no MEAN or NN_25C AVG statistic."
    )


def _numeric(value: object) -> tuple[float | None, bool]:
    if value is None or (isinstance(value, str) and not value.strip()):
        return None, False
    if isinstance(value, bool):
        return None, True
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None, True
    if not isfinite(numeric):
        return None, True
    return numeric, False
