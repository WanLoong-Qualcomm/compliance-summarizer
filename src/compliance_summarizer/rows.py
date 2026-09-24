"""Parsing of worksheet data rows into traceable case records."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from .contracts import (
    FindingSeverity,
    ParsedCase,
    PivotSchema,
    REQUIRED_FIXED_HEADERS,
    REQUIRED_PIVOT_STATISTICS,
    SheetSchema,
    SourceResult,
    ValidationFinding,
    normalize_source_result,
)


@dataclass(frozen=True, slots=True)
class RowParsingResult:
    """Parsed cases and aggregated nonblocking row-quality findings."""

    cases: tuple[ParsedCase, ...]
    findings: tuple[ValidationFinding, ...]

    def __post_init__(self) -> None:
        cases = tuple(self.cases)
        findings = tuple(self.findings)
        if any(not isinstance(case, ParsedCase) for case in cases):
            raise TypeError("cases must contain ParsedCase instances")
        if any(not isinstance(finding, ValidationFinding) for finding in findings):
            raise TypeError("findings must contain ValidationFinding instances")
        if any(finding.blocking for finding in findings):
            raise ValueError("row parsing findings must be nonblocking")
        object.__setattr__(self, "cases", cases)
        object.__setattr__(self, "findings", findings)


@dataclass(slots=True)
class _FindingAccumulator:
    code: str
    message: str
    field_name: str | None = None
    pivot_name: str | None = None
    count: int = 0
    first_row: int | None = None
    sample_rows: list[int] | None = None

    def add(self, row_number: int) -> None:
        self.count += 1
        if self.first_row is None:
            self.first_row = row_number
        if self.sample_rows is None:
            self.sample_rows = []
        if row_number not in self.sample_rows and len(self.sample_rows) < 5:
            self.sample_rows.append(row_number)

    def build(self) -> ValidationFinding:
        assert self.count > 0
        assert self.first_row is not None
        return ValidationFinding(
            code=self.code,
            message=self.message,
            severity=FindingSeverity.WARNING,
            blocking=False,
            worksheet_row_number=self.first_row,
            field_name=self.field_name,
            pivot_name=self.pivot_name,
            count=self.count,
            sample_rows=tuple(self.sample_rows or ()),
        )


def parse_data_rows(worksheet: Any, schema: SheetSchema) -> RowParsingResult:
    """Parse every row from ``schema.data_start_row`` through ``max_row``.

    Source values remain raw in ``ParsedCase.source_values``. Mapped fixed
    text fields are stripped for downstream matching, while numeric pivot
    values are never coerced from arbitrary text. Blank cells become ``None``.
    """

    if not isinstance(schema, SheetSchema):
        raise TypeError("schema must be SheetSchema")

    max_row = getattr(worksheet, "max_row", 0) or 0
    if max_row < schema.data_start_row:
        return RowParsingResult(cases=(), findings=())

    accumulators: dict[tuple[str, str | None, str | None], _FindingAccumulator] = {}
    cases: list[ParsedCase] = []
    for row_number, row in enumerate(
        worksheet.iter_rows(
            min_row=schema.data_start_row,
            max_row=max_row,
            values_only=False,
        ),
        start=schema.data_start_row,
    ):
        cells = tuple(row)
        source_values = {
            f"column_{column}": _cell_value(cells, column)
            for column in range(1, len(cells) + 1)
        }
        fixed_values: dict[str, object] = {}

        for header, column in schema.fixed_columns.items():
            raw_value = _cell_value(cells, column)
            source_values[header] = raw_value
            normalized_value = _normalize_text_value(raw_value)
            fixed_values[header] = normalized_value
            if _is_blank(raw_value):
                _add_finding(
                    accumulators,
                    code="missing_fixed_value",
                    message=f"Required fixed field '{header}' is blank on data rows.",
                    row_number=row_number,
                    field_name=header,
                )

        for header, column in schema.optional_columns.items():
            raw_value = _cell_value(cells, column)
            source_values[header] = raw_value
            fixed_values[header] = _normalize_text_value(raw_value)

        source_result = normalize_source_result(source_values.get("Result?"))
        if not _is_blank(source_values.get("Result?")) and source_result is None:
            _add_finding(
                accumulators,
                code="invalid_source_result",
                message="Result? must be PASS or FAIL after trimming and case normalization.",
                row_number=row_number,
                field_name="Result?",
            )
        elif source_result is not None:
            fixed_values["Result?"] = source_result.value

        for numeric_header in ("LL", "UL"):
            value = source_values.get(numeric_header)
            if not _is_blank(value) and not _is_finite_number(value):
                _add_finding(
                    accumulators,
                    code="invalid_numeric_value",
                    message=f"Fixed field '{numeric_header}' contains nonnumeric text.",
                    row_number=row_number,
                    field_name=numeric_header,
                )

        pivot_values: dict[str, dict[str, object]] = {}
        for pivot in schema.pivots:
            pivot_values[pivot.name] = _parse_pivot_values(
                cells,
                pivot,
                source_values,
                row_number,
                accumulators,
            )

        cases.append(
            ParsedCase(
                worksheet_row_number=row_number,
                source_values=source_values,
                fixed_values=fixed_values,
                pivot_values=pivot_values,
                source_result=source_result,
            )
        )

    findings = tuple(accumulator.build() for accumulator in accumulators.values())
    return RowParsingResult(cases=tuple(cases), findings=findings)


def _parse_pivot_values(
    cells: tuple[Any, ...],
    pivot: PivotSchema,
    source_values: dict[str, object],
    row_number: int,
    accumulators: dict[tuple[str, str | None, str | None], _FindingAccumulator],
) -> dict[str, object]:
    values: dict[str, object] = {}
    for statistic, column in pivot.statistics.items():
        raw_value = _cell_value(cells, column)
        source_values[f"{pivot.name}.{statistic}"] = raw_value
        value = None if _is_blank(raw_value) else raw_value
        values[statistic] = value
        if statistic in REQUIRED_PIVOT_STATISTICS:
            if value is None:
                _add_finding(
                    accumulators,
                    code="missing_pivot_value",
                    message=f"Pivot '{pivot.name}' statistic '{statistic}' is blank; "
                    "the value remains unavailable.",
                    row_number=row_number,
                    field_name=statistic,
                    pivot_name=pivot.name,
                )
            elif not _is_finite_number(value):
                _add_finding(
                    accumulators,
                    code="invalid_numeric_value",
                    message=f"Pivot '{pivot.name}' statistic '{statistic}' is not numeric.",
                    row_number=row_number,
                    field_name=statistic,
                    pivot_name=pivot.name,
                )
        elif statistic == "wcValue" and value is not None and not _is_finite_number(value):
            _add_finding(
                accumulators,
                code="invalid_numeric_value",
                message=f"Pivot '{pivot.name}' statistic 'wcValue' is not numeric.",
                row_number=row_number,
                field_name=statistic,
                pivot_name=pivot.name,
            )
    return values


def _cell_value(cells: tuple[Any, ...], column: int) -> object:
    if column > len(cells):
        return None
    cell = cells[column - 1]
    return getattr(cell, "value", cell)


def _normalize_text_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    return stripped if stripped else None


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _add_finding(
    accumulators: dict[tuple[str, str | None, str | None], _FindingAccumulator],
    *,
    code: str,
    message: str,
    row_number: int,
    field_name: str | None = None,
    pivot_name: str | None = None,
) -> None:
    key = (code, field_name, pivot_name)
    if key not in accumulators:
        accumulators[key] = _FindingAccumulator(
            code=code,
            message=message,
            field_name=field_name,
            pivot_name=pivot_name,
        )
    accumulators[key].add(row_number)
