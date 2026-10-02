"""Typed intermediate representations shared by the v0.2 pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


CALCULATION_ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class Settings:
    excel_file_path: Path
    compliance_sheet_name: str
    block: str
    testnames: tuple[str, ...]
    background_information: str
    anchor_pivot: str
    group_by: tuple[str, ...]
    add_fail_type: bool
    include_group_failures: bool
    include_group_marginal_passes: bool
    bypass_model: bool


@dataclass(frozen=True, slots=True)
class CustomGroupDefinition:
    name: str
    field: str
    groups: tuple[tuple[str, tuple[Any, ...]], ...]
    default: Any


@dataclass(frozen=True, slots=True)
class PivotSchema:
    name: str
    statistics: dict[str, int]


@dataclass(frozen=True, slots=True)
class SheetSchema:
    name: str
    metadata_columns: dict[str, int]
    pivots: tuple[PivotSchema, ...]
    data_start_row: int = 5

    @property
    def pivot_names(self) -> tuple[str, ...]:
        return tuple(pivot.name for pivot in self.pivots)


@dataclass(frozen=True, slots=True)
class ComplianceCase:
    worksheet_row: int
    identity: tuple[tuple[str, Any], ...]
    metadata_values: dict[str, Any]
    pivot_values: dict[str, dict[str, float | None]]
    pivot_raw_values: dict[str, dict[str, Any]]
    pivot_fail_types: dict[str, str | None] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CoverageSummary:
    pivot: str
    rows_with_gaps: int
    gaps_by_field: dict[str, int]
    malformed_by_field: dict[str, int]


@dataclass(frozen=True, slots=True)
class ParsedMeasurement:
    schema: SheetSchema
    measurement: str
    cases: tuple[ComplianceCase, ...]
    coverage: tuple[CoverageSummary, ...]
    warnings: tuple[str, ...] = ()
    fail_type_enabled: bool = False


@dataclass(frozen=True, slots=True)
class Rate:
    numerator: int
    denominator: int
    error: bool = False

    @property
    def percentage(self) -> float | None:
        if self.denominator == 0:
            return None
        return self.numerator / self.denominator * 100.0


@dataclass(frozen=True, slots=True)
class PivotMainStatistics:
    pivot: str
    failure_rate: Rate
    invalid_margin_count: int
    worst_wc_margin: float | None
    worst_failure_path: tuple[tuple[str, Any], ...] | None


@dataclass(frozen=True, slots=True)
class FailureCaseStatistics:
    case: ComplianceCase
    anchor_wc_margin: float
    comparison_values: dict[str, float | None]
    deltas: dict[str, float | str | None]


@dataclass(frozen=True, slots=True)
class ComparisonStatistics:
    comparison_pivot: str
    paired_count: int
    anchor_only_count: int
    degradation_rate: Rate
    unchanged_rate: Rate
    improvement_rate: Rate
    maximum_degradation: float | str | None
    maximum_improvement: float | str | None
    average_degradation: float | str | None
    average_improvement: float | str | None


@dataclass(frozen=True, slots=True)
class MeasurementStatistics:
    measurement: str
    anchor_pivot: str
    acceptable_variation: float
    case_count: int
    pivot_statistics: tuple[PivotMainStatistics, ...]
    comparisons: tuple[ComparisonStatistics, ...]
    top_failure_cases: tuple[FailureCaseStatistics, ...]
    top_pass_cases: tuple[FailureCaseStatistics, ...]


@dataclass(frozen=True, slots=True)
class GroupedAnalysis:
    group_key: tuple[tuple[str, Any], ...]
    statistics: MeasurementStatistics
    include_failures: bool = False
    include_marginal_passes: bool = False


@dataclass(frozen=True, slots=True)
class MeasurementAnalysis:
    measurement: str
    parsed: ParsedMeasurement
    statistics: MeasurementStatistics
    grouped_analyses: tuple[GroupedAnalysis, ...] = field(default_factory=tuple)
    group_warnings: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    settings: Settings
    measurement_analyses: tuple[MeasurementAnalysis, ...]
    generated_at: str
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def parsed(self) -> ParsedMeasurement:
        return self.measurement_analyses[0].parsed

    @property
    def statistics(self) -> MeasurementStatistics:
        return self.measurement_analyses[0].statistics

    @property
    def grouped_analyses(self) -> tuple[GroupedAnalysis, ...]:
        return self.measurement_analyses[0].grouped_analyses

    @property
    def group_warnings(self) -> tuple[str, ...]:
        return self.measurement_analyses[0].group_warnings
