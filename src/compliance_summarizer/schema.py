"""Dynamic discovery and structural validation of compliance sheet schemas."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .contracts import (
    FindingSeverity,
    OPTIONAL_CONTEXT_HEADERS,
    OPTIONAL_PIVOT_STATISTICS,
    REQUIRED_FIXED_HEADERS,
    REQUIRED_PIVOT_STATISTICS,
    PivotSchema,
    SheetSchema,
    ValidationFinding,
)


RECOGNIZED_PIVOT_STATISTICS = frozenset(
    {*REQUIRED_PIVOT_STATISTICS, *OPTIONAL_PIVOT_STATISTICS}
)


@dataclass(frozen=True, slots=True)
class SchemaDiscoveryResult:
    """A usable schema, or blocking findings explaining why one is unavailable."""

    schema: SheetSchema | None
    findings: tuple[ValidationFinding, ...]

    def __post_init__(self) -> None:
        findings = tuple(self.findings)
        if any(not isinstance(finding, ValidationFinding) for finding in findings):
            raise TypeError("findings must contain ValidationFinding instances")
        if self.schema is not None and not isinstance(self.schema, SheetSchema):
            raise TypeError("schema must be SheetSchema or None")
        if self.schema is not None and any(finding.blocking for finding in findings):
            raise ValueError("a schema cannot be returned with blocking findings")
        object.__setattr__(self, "findings", findings)

    @property
    def is_valid(self) -> bool:
        return self.schema is not None and not any(
            finding.blocking for finding in self.findings
        )

    @property
    def blocking_findings(self) -> tuple[ValidationFinding, ...]:
        return tuple(finding for finding in self.findings if finding.blocking)


@dataclass(slots=True)
class _PivotBlock:
    name: str
    statistics: dict[str, int]
    columns: set[int]
    invalid: bool = False


def discover_sheet_schema(
    worksheet: Any,
    selected_pivot: str | None = None,
) -> SchemaDiscoveryResult:
    """Discover fixed columns and ordered pivot groups from one worksheet.

    ``worksheet`` is expected to be the read-only worksheet yielded by
    :func:`compliance_summarizer.workbook.open_workbook`, though any object
    implementing the small ``iter_rows``/``max_row`` interface is sufficient
    for focused tests.
    """

    header_rows = _read_header_rows(worksheet)
    row_two = header_rows[2]
    row_three = header_rows[3]
    row_four = header_rows[4]
    width = max(len(row_two), len(row_three), len(row_four), 1)

    findings: list[ValidationFinding] = []
    fixed_columns, optional_columns, fixed_section_end = _discover_fixed_columns(
        row_four, findings
    )
    pivot_blocks, pivot_columns = _discover_pivot_blocks(
        row_two,
        row_three,
        start_column=fixed_section_end + 1,
        end_column=width,
        findings=findings,
    )

    valid_pivots: list[PivotSchema] = []
    discovered_pivot_names: list[str] = []
    for block in pivot_blocks:
        if block.name not in discovered_pivot_names:
            discovered_pivot_names.append(block.name)
        missing = set(REQUIRED_PIVOT_STATISTICS) - set(block.statistics)
        if missing:
            findings.append(
                _error(
                    "missing_pivot_statistics",
                    f"Pivot '{block.name}' is missing required statistic(s): "
                    f"{', '.join(sorted(missing))}.",
                    field=block.name,
                )
            )
            block.invalid = True
        if not block.invalid:
            valid_pivots.append(
                PivotSchema(name=block.name, statistics=block.statistics)
            )

    all_pivot_names = [block.name for block in pivot_blocks]
    duplicate_pivot_names = list(
        dict.fromkeys(
            name
            for index, name in enumerate(all_pivot_names)
            if name in all_pivot_names[:index]
        )
    )
    if duplicate_pivot_names:
        findings.append(
            _error(
                "duplicate_pivot_field",
                "A pivot field is defined in more than one noncontiguous group: "
                + ", ".join(duplicate_pivot_names),
            )
        )

    if not pivot_blocks:
        findings.append(
            _error("no_pivot_fields", "No pivot field with recognized statistics was discovered.")
        )
    elif not valid_pivots:
        findings.append(
            _error("no_valid_pivot_fields", "No pivot field has the required statistics.")
        )

    if selected_pivot is not None:
        if not isinstance(selected_pivot, str) or not selected_pivot.strip():
            findings.append(
                _error(
                    "missing_selected_pivot",
                    "The selected pivot field of interest must be a nonempty exact name.",
                    field="pivot_field_of_interest",
                )
            )
        elif selected_pivot not in discovered_pivot_names:
            available = ", ".join(repr(name) for name in discovered_pivot_names) or "none"
            findings.append(
                _error(
                    "selected_pivot_absent",
                    f"Selected pivot '{selected_pivot}' was not discovered. "
                    f"Available pivots: {available}.",
                    field="pivot_field_of_interest",
                )
            )

    unknown_columns = _discover_unknown_columns(
        row_four,
        fixed_columns=fixed_columns,
        optional_columns=optional_columns,
        pivot_columns=pivot_columns,
    )
    if unknown_columns:
        findings.append(
            _warning(
                "unknown_trailing_columns",
                "Ignoring unrecognized trailing column(s): " + ", ".join(unknown_columns) + ".",
            )
        )
    for optional_header in OPTIONAL_CONTEXT_HEADERS:
        if optional_header not in optional_columns:
            findings.append(
                _warning(
                    "missing_optional_column",
                    f"Optional context column '{optional_header}' is not present.",
                    field=optional_header,
                )
            )

    if getattr(worksheet, "max_row", 0) is None or worksheet.max_row < 5:
        findings.append(
            _error("no_data_rows", "The selected sheet has no data rows below header row 4.")
        )

    if any(finding.blocking for finding in findings):
        return SchemaDiscoveryResult(schema=None, findings=tuple(findings))

    schema = SheetSchema(
        sheet_name=worksheet.title,
        fixed_columns=fixed_columns,
        optional_columns=optional_columns,
        pivots=tuple(valid_pivots),
        header_rows=(2, 3, 4),
        data_start_row=5,
        unknown_columns=tuple(unknown_columns),
    )
    return SchemaDiscoveryResult(schema=schema, findings=tuple(findings))


def _read_header_rows(worksheet: Any) -> dict[int, tuple[object, ...]]:
    rows = list(worksheet.iter_rows(min_row=2, max_row=4, values_only=True))
    by_number = {
        row_number: tuple(values)
        for row_number, values in zip((2, 3, 4), rows, strict=False)
    }
    return {row_number: by_number.get(row_number, ()) for row_number in (2, 3, 4)}


def _discover_fixed_columns(
    row_four: tuple[object, ...],
    findings: list[ValidationFinding],
) -> tuple[dict[str, int], dict[str, int], int]:
    positions: dict[str, list[int]] = {}
    known_headers = set(REQUIRED_FIXED_HEADERS) | set(OPTIONAL_CONTEXT_HEADERS)
    for column, value in enumerate(row_four, start=1):
        header = _text(value)
        if header in known_headers:
            positions.setdefault(header, []).append(column)

    fixed_columns: dict[str, int] = {}
    optional_columns: dict[str, int] = {}
    first_positions: list[int] = []
    for header in REQUIRED_FIXED_HEADERS:
        header_positions = positions.get(header, [])
        if not header_positions:
            findings.append(
                _error(
                    "missing_required_header",
                    f"Required fixed header '{header}' is missing from row 4.",
                    field=header,
                )
            )
            continue
        first_positions.append(header_positions[0])
        fixed_columns[header] = header_positions[0]
        if len(header_positions) > 1:
            findings.append(
                _error(
                    "duplicate_required_header",
                    f"Required fixed header '{header}' appears more than once in row 4 "
                    f"at columns {header_positions}.",
                    field=header,
                )
            )

    for header in OPTIONAL_CONTEXT_HEADERS:
        header_positions = positions.get(header, [])
        if header_positions:
            first_positions.append(header_positions[0])
            optional_columns[header] = header_positions[0]
            if len(header_positions) > 1:
                findings.append(
                    _error(
                        "duplicate_optional_header",
                        f"Optional context header '{header}' appears more than once in row 4 "
                        f"at columns {header_positions}.",
                        field=header,
                    )
                )

    return fixed_columns, optional_columns, max(first_positions, default=0)


def _discover_pivot_blocks(
    row_two: tuple[object, ...],
    row_three: tuple[object, ...],
    *,
    start_column: int,
    end_column: int,
    findings: list[ValidationFinding],
) -> tuple[list[_PivotBlock], set[int]]:
    blocks: list[_PivotBlock] = []
    active: _PivotBlock | None = None
    pivot_columns: set[int] = set()

    for column in range(start_column, end_column + 1):
        label = _text(_cell(row_two, column))
        statistic = _text(_cell(row_three, column))
        if statistic not in RECOGNIZED_PIVOT_STATISTICS:
            active = None
            continue

        if label:
            if active is None or active.name != label:
                active = _PivotBlock(name=label, statistics={}, columns=set())
                blocks.append(active)
        elif active is None:
            findings.append(
                _error(
                    "orphan_pivot_statistic",
                    f"Recognized pivot statistic '{statistic}' at column {column} "
                    "has no pivot field label in row 2.",
                )
            )
            continue

        pivot_columns.add(column)
        assert active is not None
        if statistic in active.statistics:
            active.invalid = True
            findings.append(
                _error(
                    "duplicate_pivot_statistic",
                    f"Pivot '{active.name}' contains duplicate statistic '{statistic}' "
                    f"at column {column}.",
                    field=active.name,
                )
            )
            continue
        active.statistics[statistic] = column
        active.columns.add(column)

    return blocks, pivot_columns


def _discover_unknown_columns(
    row_four: tuple[object, ...],
    *,
    fixed_columns: dict[str, int],
    optional_columns: dict[str, int],
    pivot_columns: set[int],
) -> list[str]:
    known_columns = set(fixed_columns.values()) | set(optional_columns.values()) | pivot_columns
    unknown: list[str] = []
    for column, value in enumerate(row_four, start=1):
        if column in known_columns:
            continue
        header = _text(value)
        if header and header not in unknown:
            unknown.append(header)
    return unknown


def _cell(row: tuple[object, ...], column: int) -> object:
    return row[column - 1] if column <= len(row) else None


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _error(code: str, message: str, *, field: str | None = None) -> ValidationFinding:
    return ValidationFinding(
        code=code,
        message=message,
        severity=FindingSeverity.ERROR,
        blocking=True,
        field_name=field,
    )


def _warning(code: str, message: str, *, field: str | None = None) -> ValidationFinding:
    return ValidationFinding(code=code, message=message, field_name=field)
