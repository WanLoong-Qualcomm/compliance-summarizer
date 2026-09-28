"""SIGPATH workbook schema discovery and row normalization."""

from __future__ import annotations

from collections import Counter
from contextlib import closing
from math import isfinite
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .errors import WorkbookValidationError
from .models import (
    ComplianceCase,
    CoverageSummary,
    ParsedMeasurement,
    PivotSchema,
    SheetSchema,
)


REQUIRED_FIXED_HEADERS = (
    "LNAMODE",
    "CAMODE",
    "STD",
    "BAND",
    "MEASPORT",
    "DLP",
    "DIV",
    "TESTNAME",
    "GAINMODE",
    "BBPATH",
    "FREQ",
    "CHANNEL",
    "Result?",
    "LL",
    "UL",
)
OPTIONAL_FIXED_HEADERS = ("BW", "F0_MHZ")
IDENTIFYING_HEADERS = (
    "LNAMODE",
    "CAMODE",
    "STD",
    "BAND",
    "BW",
    "MEASPORT",
    "DLP",
    "DIV",
    "F0_MHZ",
    "TESTNAME",
    "GAINMODE",
    "BBPATH",
    "FREQ",
    "CHANNEL",
)
REQUIRED_PIVOT_STATISTICS = ("NN_25C AVG", "wcMargin")
RECOGNIZED_PIVOT_STATISTICS = (
    "MIN",
    "MAX",
    "NN_25C AVG",
    "wcMargin",
    "wcValue",
)


def load_measurement(
    workbook_path: str | Path,
    sheet_name: str,
    measurement: str = "GAIN",
) -> ParsedMeasurement:
    """Load and validate one measurement without modifying the source workbook."""

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
        return parse_measurement_rows(worksheet, schema, measurement)


def discover_schema(worksheet: Any) -> SheetSchema:
    """Discover fixed fields and pivot groups from header rows 2, 3, and 4."""

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

    fixed_positions: dict[str, list[int]] = {}
    known_fixed = {*REQUIRED_FIXED_HEADERS, *OPTIONAL_FIXED_HEADERS}
    for column in range(1, width + 1):
        canonical = _canonical_fixed(_cell(column_labels, column))
        if canonical in known_fixed:
            fixed_positions.setdefault(canonical, []).append(column)

    errors: list[str] = []
    fixed_columns: dict[str, int] = {}
    for header in REQUIRED_FIXED_HEADERS:
        positions = fixed_positions.get(header, [])
        if not positions:
            errors.append(f"required row-4 header '{header}' is missing")
        elif len(positions) > 1:
            errors.append(
                f"required row-4 header '{header}' appears more than once at columns "
                f"{positions}"
            )
        else:
            fixed_columns[header] = positions[0]
    for header in OPTIONAL_FIXED_HEADERS:
        positions = fixed_positions.get(header, [])
        if len(positions) > 1:
            errors.append(
                f"optional row-4 header '{header}' appears more than once at columns "
                f"{positions}"
            )
        elif positions:
            fixed_columns[header] = positions[0]

    fixed_end = max(fixed_columns.values(), default=0)
    pivot_blocks: dict[str, dict[str, int]] = {}
    pivot_order: list[str] = []
    active_pivot: str | None = None
    for column in range(fixed_end + 1, width + 1):
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

    if not pivot_blocks:
        errors.append("no pivot groups were found from row-2 names and row-3 statistics")
    for pivot_name in pivot_order:
        missing = set(REQUIRED_PIVOT_STATISTICS) - set(pivot_blocks[pivot_name])
        if missing:
            errors.append(
                f"pivot '{pivot_name}' is missing required statistic(s): "
                + ", ".join(sorted(missing))
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
        fixed_columns=fixed_columns,
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
    """Normalize exact measurement rows and summarize unusable numeric cells."""

    requested = measurement.strip().upper()
    max_column = max(
        [*schema.fixed_columns.values()]
        + [
            column
            for pivot in schema.pivots
            for column in pivot.statistics.values()
        ]
    )
    cases: list[ComplianceCase] = []
    gap_counts = {
        pivot.name: Counter({field: 0 for field in REQUIRED_PIVOT_STATISTICS})
        for pivot in schema.pivots
    }
    malformed_counts = {
        pivot.name: Counter({field: 0 for field in REQUIRED_PIVOT_STATISTICS})
        for pivot in schema.pivots
    }
    rows_with_gap = {pivot.name: 0 for pivot in schema.pivots}
    duplicate_identity_count = 0
    seen_identities: set[tuple[tuple[str, Any], ...]] = set()

    for worksheet_row, values in enumerate(
        worksheet.iter_rows(
            min_row=schema.data_start_row,
            max_col=max_column,
            values_only=True,
        ),
        start=schema.data_start_row,
    ):
        test_name = _cell(values, schema.fixed_columns["TESTNAME"])
        if _text(test_name).upper() != requested:
            continue
        fixed_values = {
            header: _cell(values, column)
            for header, column in schema.fixed_columns.items()
        }
        identity = tuple(
            (header, fixed_values.get(header))
            for header in IDENTIFYING_HEADERS
            if header in fixed_values
        )
        if identity in seen_identities:
            duplicate_identity_count += 1
        else:
            seen_identities.add(identity)

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
                if statistic in REQUIRED_PIVOT_STATISTICS and numeric is None:
                    gap_counts[pivot.name][statistic] += 1
                    row_has_gap = True
                    if malformed:
                        malformed_counts[pivot.name][statistic] += 1
            if row_has_gap:
                rows_with_gap[pivot.name] += 1
            pivot_values[pivot.name] = normalized
            pivot_raw_values[pivot.name] = raw_values

        cases.append(
            ComplianceCase(
                worksheet_row=worksheet_row,
                identity=identity,
                fixed_values=fixed_values,
                pivot_values=pivot_values,
                pivot_raw_values=pivot_raw_values,
            )
        )

    if not cases:
        raise WorkbookValidationError(
            f"Worksheet '{schema.name}' contains no rows whose TESTNAME is exactly "
            f"'{requested}'."
        )

    warnings: list[str] = []
    if duplicate_identity_count:
        warnings.append(
            f"{duplicate_identity_count} {requested} row(s) repeat an identifying-field "
            "combination; worksheet row numbers are retained only to make displayed ties "
            "traceable."
        )
    coverage = tuple(
        CoverageSummary(
            pivot=pivot.name,
            rows_with_gaps=rows_with_gap[pivot.name],
            gaps_by_field=dict(gap_counts[pivot.name]),
            malformed_by_field=dict(malformed_counts[pivot.name]),
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

    return ParsedMeasurement(
        schema=schema,
        measurement=requested,
        cases=tuple(cases),
        coverage=coverage,
        warnings=tuple(warnings),
    )


def _cell(row: tuple[Any, ...], column: int) -> Any:
    return row[column - 1] if column > 0 and column <= len(row) else None


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _canonical_fixed(value: object) -> str:
    text = _text(value)
    if text.upper() == "RESULT?":
        return "Result?"
    return text.upper()


def _canonical_statistic(value: object) -> str | None:
    text = " ".join(_text(value).split())
    upper = text.upper()
    aliases = {
        "MIN": "MIN",
        "MAX": "MAX",
        "NN_25C AVG": "NN_25C AVG",
        "WCMARGIN": "wcMargin",
        "WCVALUE": "wcValue",
    }
    return aliases.get(upper)


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
