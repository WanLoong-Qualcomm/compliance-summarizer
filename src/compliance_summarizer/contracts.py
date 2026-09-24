"""Shared, validated data contracts for the compliance workflow.

The contracts in this module intentionally contain source values alongside
derived values.  Parsers and analyzers can therefore preserve worksheet
traceability without asking report renderers to recalculate business rules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import Mapping


REQUIRED_FIXED_HEADERS: tuple[str, ...] = (
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
OPTIONAL_CONTEXT_HEADERS: tuple[str, ...] = ("BW", "F0_MHZ")
REQUIRED_PIVOT_STATISTICS: tuple[str, ...] = (
    "MIN",
    "MAX",
    "NN_25C AVG",
    "wcMargin",
)
OPTIONAL_PIVOT_STATISTICS: tuple[str, ...] = ("wcValue",)


class SourceResult(str, Enum):
    """Canonical values from the source ``Result?`` column."""

    PASS = "PASS"
    FAIL = "FAIL"


class PivotMarginStatus(str, Enum):
    """Status derived from one pivot's numeric ``wcMargin``."""

    PASS = "PASS"
    FAIL = "FAIL"
    UNAVAILABLE = "UNAVAILABLE"


class DeltaClassification(str, Enum):
    """Classification of a selected-pivot GAIN delta."""

    DEGRADATION = "degradation"
    IMPROVEMENT = "improvement"
    NEUTRAL = "neutral"
    UNAVAILABLE = "unavailable"


class FindingSeverity(str, Enum):
    """Severity of a validation finding."""

    WARNING = "warning"
    ERROR = "error"


class NegativeGainDecision(str, Enum):
    """Decision recorded after the negative-GAIN safety check."""

    NOT_REQUIRED = "not_required"
    PENDING = "pending"
    PROCEED = "proceed"
    ABORT = "abort"


class ModelBypassStatus(str, Enum):
    """The only supported model-stage status in v0.1."""

    BYPASSED = "bypassed"


def _copy_mapping(values: Mapping[str, object], name: str) -> dict[str, object]:
    if not isinstance(values, Mapping):
        raise TypeError(f"{name} must be a mapping")
    copied = dict(values)
    if any(not isinstance(key, str) for key in copied):
        raise TypeError(f"{name} keys must be strings")
    return copied


def _is_finite_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def normalize_source_result(value: object) -> SourceResult | None:
    """Normalize a source result without converting unknown values to a pass."""

    if not isinstance(value, str):
        return None
    try:
        return SourceResult(value.strip().upper())
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated shape of the v0.1 settings file.

    Empty path and pivot values are permitted for the generated template;
    workbook- and schema-dependent checks belong to the settings workflow.
    """

    excel_file_path: str = ""
    compliance_sheet_name: str = "Combined"
    tests_to_report: tuple[str, ...] = ("GAIN",)
    acceptable_variation: Mapping[str, float] = field(
        default_factory=lambda: {"GAIN": 0.2}
    )
    background_information: str = ""
    pivot_field_of_interest: str = ""
    bypass_model: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.excel_file_path, str):
            raise TypeError("excel_file_path must be a string")
        if not isinstance(self.compliance_sheet_name, str):
            raise TypeError("compliance_sheet_name must be a string")
        if not isinstance(self.background_information, str):
            raise TypeError("background_information must be a string")
        if not isinstance(self.pivot_field_of_interest, str):
            raise TypeError("pivot_field_of_interest must be a string")
        if type(self.bypass_model) is not bool:
            raise TypeError("bypass_model must be a boolean")
        if not self.bypass_model:
            raise ValueError("bypass_model must be true in v0.1")

        tests = tuple(self.tests_to_report)
        if not tests:
            raise ValueError("tests_to_report must not be empty")
        if tests != ("GAIN",):
            raise ValueError("tests_to_report supports only GAIN in v0.1")
        object.__setattr__(self, "tests_to_report", tests)

        variations = _copy_mapping(self.acceptable_variation, "acceptable_variation")
        if set(variations) != {"GAIN"}:
            raise ValueError("acceptable_variation must contain only GAIN")
        variation = variations["GAIN"]
        if not _is_finite_number(variation) or variation < 0:
            raise ValueError("acceptable_variation.GAIN must be finite and nonnegative")
        variations["GAIN"] = float(variation)
        object.__setattr__(self, "acceptable_variation", variations)


@dataclass(frozen=True, slots=True)
class PivotSchema:
    """One discovered pivot field and its physical statistic columns."""

    name: str
    statistics: Mapping[str, int]
    unknown_statistics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("pivot name must be a nonempty string")
        if self.name != self.name.strip():
            raise ValueError("pivot name must already be trimmed")

        statistics = _copy_mapping(self.statistics, "pivot statistics")
        invalid = set(statistics) - set(REQUIRED_PIVOT_STATISTICS) - set(
            OPTIONAL_PIVOT_STATISTICS
        )
        if invalid:
            raise ValueError(f"unrecognized pivot statistics: {sorted(invalid)}")
        missing = set(REQUIRED_PIVOT_STATISTICS) - set(statistics)
        if missing:
            raise ValueError(f"pivot is missing required statistics: {sorted(missing)}")
        columns = tuple(statistics.values())
        if any(type(column) is not int or column < 1 for column in columns):
            raise ValueError("pivot statistic columns must be positive 1-based integers")
        if len(set(columns)) != len(columns):
            raise ValueError("pivot statistic columns must be unique")
        unknown = tuple(self.unknown_statistics)
        if any(not isinstance(statistic, str) for statistic in unknown):
            raise TypeError("unknown_statistics entries must be strings")
        object.__setattr__(self, "statistics", statistics)
        object.__setattr__(self, "unknown_statistics", unknown)


@dataclass(frozen=True, slots=True)
class SheetSchema:
    """Validated worksheet headers, fixed fields, and ordered pivots."""

    sheet_name: str
    fixed_columns: Mapping[str, int]
    optional_columns: Mapping[str, int]
    pivots: tuple[PivotSchema, ...]
    header_rows: tuple[int, int, int] = (2, 3, 4)
    data_start_row: int = 5
    unknown_columns: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.sheet_name, str) or not self.sheet_name:
            raise ValueError("sheet_name must be a nonempty string")
        fixed = _copy_mapping(self.fixed_columns, "fixed_columns")
        optional = _copy_mapping(self.optional_columns, "optional_columns")
        for name, columns in (("fixed_columns", fixed), ("optional_columns", optional)):
            if any(type(column) is not int or column < 1 for column in columns.values()):
                raise ValueError(f"{name} values must be positive 1-based integers")
        missing = set(REQUIRED_FIXED_HEADERS) - set(fixed)
        if missing:
            raise ValueError(f"fixed columns are missing required headers: {sorted(missing)}")
        if set(fixed).intersection(optional):
            raise ValueError("fixed and optional columns must not overlap")
        if set(fixed.values()).intersection(optional.values()):
            raise ValueError("fixed and optional column positions must not overlap")

        pivots = tuple(self.pivots)
        if not pivots:
            raise ValueError("at least one pivot is required")
        if any(not isinstance(pivot, PivotSchema) for pivot in pivots):
            raise TypeError("pivots must contain PivotSchema instances")
        if len({pivot.name for pivot in pivots}) != len(pivots):
            raise ValueError("pivot names must be unique")

        if len(self.header_rows) != 3 or any(
            type(row) is not int or row < 1 for row in self.header_rows
        ):
            raise ValueError("header_rows must contain three positive row numbers")
        if type(self.data_start_row) is not int or self.data_start_row <= max(self.header_rows):
            raise ValueError("data_start_row must follow the header rows")
        unknown = tuple(self.unknown_columns)
        if any(not isinstance(column, str) for column in unknown):
            raise TypeError("unknown_columns entries must be strings")

        object.__setattr__(self, "fixed_columns", fixed)
        object.__setattr__(self, "optional_columns", optional)
        object.__setattr__(self, "pivots", pivots)
        object.__setattr__(self, "unknown_columns", unknown)

    @property
    def pivot_names(self) -> tuple[str, ...]:
        """Return pivots in worksheet discovery order."""

        return tuple(pivot.name for pivot in self.pivots)


@dataclass(frozen=True, slots=True)
class ParsedCase:
    """One parsed worksheet row with raw values and normalized source result."""

    worksheet_row_number: int
    source_values: Mapping[str, object]
    fixed_values: Mapping[str, object]
    pivot_values: Mapping[str, Mapping[str, object]]
    source_result: SourceResult | None = None

    def __post_init__(self) -> None:
        if type(self.worksheet_row_number) is not int or self.worksheet_row_number < 5:
            raise ValueError("worksheet_row_number must be a data row number (>= 5)")
        source_values = _copy_mapping(self.source_values, "source_values")
        fixed_values = _copy_mapping(self.fixed_values, "fixed_values")
        pivot_values = _copy_mapping(self.pivot_values, "pivot_values")
        normalized_pivots: dict[str, dict[str, object]] = {}
        for pivot_name, statistics in pivot_values.items():
            if not pivot_name.strip():
                raise ValueError("pivot names in pivot_values must be nonempty")
            normalized_pivots[pivot_name] = _copy_mapping(
                statistics, f"pivot_values[{pivot_name!r}]"
            )
        if self.source_result is not None and not isinstance(self.source_result, SourceResult):
            raise TypeError("source_result must be SourceResult or None")
        object.__setattr__(self, "source_values", source_values)
        object.__setattr__(self, "fixed_values", fixed_values)
        object.__setattr__(self, "pivot_values", normalized_pivots)

    def pivot_margin_status(self, pivot_name: str) -> PivotMarginStatus:
        """Derive pivot status without changing the source ``Result?`` value."""

        statistics = self.pivot_values.get(pivot_name)
        if statistics is None:
            return PivotMarginStatus.UNAVAILABLE
        margin = statistics.get("wcMargin")
        if not _is_finite_number(margin):
            return PivotMarginStatus.UNAVAILABLE
        return PivotMarginStatus.FAIL if margin < 0 else PivotMarginStatus.PASS


@dataclass(frozen=True, slots=True)
class ValidationFinding:
    """A structured warning or error with optional worksheet traceability."""

    code: str
    message: str
    severity: FindingSeverity = FindingSeverity.WARNING
    blocking: bool = False
    worksheet_row_number: int | None = None
    field_name: str | None = None
    pivot_name: str | None = None
    count: int = 1
    sample_rows: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.code.strip() or not self.message.strip():
            raise ValueError("finding code and message must be nonempty")
        if not isinstance(self.severity, FindingSeverity):
            raise TypeError("severity must be FindingSeverity")
        if type(self.blocking) is not bool:
            raise TypeError("blocking must be a boolean")
        if self.worksheet_row_number is not None and self.worksheet_row_number < 5:
            raise ValueError("worksheet_row_number must be a data row number")
        if type(self.count) is not int or self.count < 1:
            raise ValueError("finding count must be a positive integer")
        sample_rows = tuple(self.sample_rows)
        if any(type(row) is not int or row < 5 for row in sample_rows):
            raise ValueError("sample_rows must contain data row numbers")
        object.__setattr__(self, "sample_rows", sample_rows)


@dataclass(frozen=True, slots=True)
class Rate:
    """A count-based rate whose value is unavailable when denominator is zero."""

    numerator: int
    denominator: int
    value: float | None = field(init=False)

    def __post_init__(self) -> None:
        if type(self.numerator) is not int or self.numerator < 0:
            raise ValueError("rate numerator must be a nonnegative integer")
        if type(self.denominator) is not int or self.denominator < 0:
            raise ValueError("rate denominator must be a nonnegative integer")
        if self.numerator > self.denominator:
            raise ValueError("rate numerator cannot exceed denominator")
        value = None if self.denominator == 0 else self.numerator / self.denominator
        object.__setattr__(self, "value", value)

    @property
    def percentage(self) -> float | None:
        """Return the report percentage, or ``None`` when unavailable."""

        return None if self.value is None else self.value * 100

    @property
    def is_available(self) -> bool:
        return self.value is not None


@dataclass(frozen=True, slots=True)
class PivotFailureSummary:
    """Failure counts and coverage for one pivot's ``wcMargin`` values."""

    pivot_name: str
    failure_count: int
    numeric_margin_count: int
    unavailable_margin_count: int
    failure_rate: Rate = field(init=False)

    def __post_init__(self) -> None:
        if not self.pivot_name.strip():
            raise ValueError("pivot_name must be nonempty")
        counts = (
            self.failure_count,
            self.numeric_margin_count,
            self.unavailable_margin_count,
        )
        if any(type(count) is not int or count < 0 for count in counts):
            raise ValueError("pivot failure counts must be nonnegative integers")
        if self.failure_count > self.numeric_margin_count:
            raise ValueError("failure_count cannot exceed numeric_margin_count")
        object.__setattr__(self, "failure_rate", Rate(self.failure_count, self.numeric_margin_count))


@dataclass(frozen=True, slots=True)
class DeltaResult:
    """A signed pairwise delta and its threshold classification."""

    delta: float | None
    classification: DeltaClassification

    def __post_init__(self) -> None:
        if self.delta is None:
            if self.classification is not DeltaClassification.UNAVAILABLE:
                raise ValueError("missing delta must be classified as unavailable")
        elif not _is_finite_number(self.delta):
            raise ValueError("delta must be finite when present")
        elif self.classification is DeltaClassification.UNAVAILABLE:
            raise ValueError("numeric delta cannot be classified as unavailable")


@dataclass(frozen=True, slots=True)
class CaseAnalysis:
    """A parsed case plus derived statuses and pairwise delta results."""

    case: ParsedCase
    selected_pivot: str
    selected_margin: float | None
    pivot_statuses: Mapping[str, PivotMarginStatus]
    comparisons: Mapping[str, DeltaResult]
    degradation_led_comparison_pivots: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.selected_pivot.strip():
            raise ValueError("selected_pivot must be nonempty")
        if self.selected_margin is not None and not _is_finite_number(self.selected_margin):
            raise ValueError("selected_margin must be finite or None")
        statuses = _copy_mapping(self.pivot_statuses, "pivot_statuses")
        if any(not isinstance(status, PivotMarginStatus) for status in statuses.values()):
            raise TypeError("pivot_statuses values must be PivotMarginStatus")
        comparisons = _copy_mapping(self.comparisons, "comparisons")
        if any(not isinstance(result, DeltaResult) for result in comparisons.values()):
            raise TypeError("comparisons values must be DeltaResult")
        candidate_pivots = tuple(self.degradation_led_comparison_pivots)
        if any(not isinstance(pivot, str) or not pivot.strip() for pivot in candidate_pivots):
            raise ValueError("degradation candidate pivot names must be nonempty strings")
        object.__setattr__(self, "pivot_statuses", statuses)
        object.__setattr__(self, "comparisons", comparisons)
        object.__setattr__(self, "degradation_led_comparison_pivots", candidate_pivots)


@dataclass(frozen=True, slots=True)
class ComparisonExtremum:
    """A qualifying maximum degradation or improvement with full case context."""

    case_analysis: CaseAnalysis
    comparison_pivot: str
    delta: float

    def __post_init__(self) -> None:
        if not self.comparison_pivot.strip():
            raise ValueError("comparison_pivot must be nonempty")
        if not _is_finite_number(self.delta):
            raise ValueError("extremum delta must be finite")
        if self.comparison_pivot not in self.case_analysis.comparisons:
            raise ValueError("extremum pivot must have a comparison result")


@dataclass(frozen=True, slots=True)
class DegradationLedFailureEvidence:
    """Aggregate and case-level evidence for one pivot comparison."""

    selected_pivot: str
    comparison_pivot: str
    aggregate_signal: bool
    candidates: tuple[CaseAnalysis, ...] = ()

    def __post_init__(self) -> None:
        if not self.selected_pivot.strip() or not self.comparison_pivot.strip():
            raise ValueError("evidence pivot names must be nonempty")
        if self.selected_pivot == self.comparison_pivot:
            raise ValueError("evidence requires two different pivots")
        if type(self.aggregate_signal) is not bool:
            raise TypeError("aggregate_signal must be a boolean")
        candidates = tuple(self.candidates)
        if any(not isinstance(candidate, CaseAnalysis) for candidate in candidates):
            raise TypeError("candidates must contain CaseAnalysis instances")
        object.__setattr__(self, "candidates", candidates)


@dataclass(frozen=True, slots=True)
class PairwiseComparison:
    """Complete deterministic comparison of the selected pivot to one other pivot."""

    selected_pivot: str
    comparison_pivot: str
    comparable_case_count: int
    degradation_count: int
    improvement_count: int
    neutral_count: int
    selected_failure_summary: PivotFailureSummary
    comparison_failure_summary: PivotFailureSummary
    maximum_degradation: ComparisonExtremum | None = None
    maximum_improvement: ComparisonExtremum | None = None
    degradation_led_failure_candidates: tuple[CaseAnalysis, ...] = ()
    degradation_rate: Rate = field(init=False)
    improvement_rate: Rate = field(init=False)
    neutral_rate: Rate = field(init=False)
    degradation_led_failure: DegradationLedFailureEvidence = field(init=False)

    def __post_init__(self) -> None:
        if not self.selected_pivot.strip() or not self.comparison_pivot.strip():
            raise ValueError("comparison pivot names must be nonempty")
        if self.selected_pivot == self.comparison_pivot:
            raise ValueError("a pairwise comparison requires different pivots")
        counts = (
            self.comparable_case_count,
            self.degradation_count,
            self.improvement_count,
            self.neutral_count,
        )
        if any(type(count) is not int or count < 0 for count in counts):
            raise ValueError("comparison counts must be nonnegative integers")
        if (
            self.degradation_count + self.improvement_count + self.neutral_count
            != self.comparable_case_count
        ):
            raise ValueError("comparison classifications must sum to comparable_case_count")
        if self.selected_failure_summary.pivot_name != self.selected_pivot:
            raise ValueError("selected failure summary does not match selected pivot")
        if self.comparison_failure_summary.pivot_name != self.comparison_pivot:
            raise ValueError("comparison failure summary does not match comparison pivot")
        for extremum in (self.maximum_degradation, self.maximum_improvement):
            if extremum is not None and extremum.comparison_pivot != self.comparison_pivot:
                raise ValueError("extremum does not match comparison pivot")
        candidates = tuple(self.degradation_led_failure_candidates)
        if any(not isinstance(candidate, CaseAnalysis) for candidate in candidates):
            raise TypeError("degradation candidates must contain CaseAnalysis instances")
        if any(
            candidate.selected_pivot != self.selected_pivot
            or self.comparison_pivot not in candidate.comparisons
            for candidate in candidates
        ):
            raise ValueError("degradation candidates must match the pairwise pivots")

        object.__setattr__(self, "degradation_rate", Rate(self.degradation_count, self.comparable_case_count))
        object.__setattr__(self, "improvement_rate", Rate(self.improvement_count, self.comparable_case_count))
        object.__setattr__(self, "neutral_rate", Rate(self.neutral_count, self.comparable_case_count))
        object.__setattr__(
            self,
            "degradation_led_failure",
            DegradationLedFailureEvidence(
                selected_pivot=self.selected_pivot,
                comparison_pivot=self.comparison_pivot,
                aggregate_signal=(
                    self.selected_failure_summary.failure_count
                    > self.comparison_failure_summary.failure_count
                    or (
                        self.selected_failure_summary.failure_rate.value is not None
                        and self.comparison_failure_summary.failure_rate.value is not None
                        and self.selected_failure_summary.failure_rate.value
                        > self.comparison_failure_summary.failure_rate.value
                    )
                ),
                candidates=candidates,
            ),
        )
        object.__setattr__(self, "degradation_led_failure_candidates", candidates)


@dataclass(frozen=True, slots=True)
class SourceMetadata:
    """Source identity and processing timestamp included in reports."""

    source_filename: str
    sheet_name: str
    processed_at: datetime

    def __post_init__(self) -> None:
        if not self.source_filename.strip() or not self.sheet_name.strip():
            raise ValueError("source filename and sheet name must be nonempty")
        if self.processed_at.tzinfo is None:
            raise ValueError("processed_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class CompleteAnalysisResult:
    """All deterministic inputs, findings, metrics, and derived case outputs."""

    source_metadata: SourceMetadata
    settings: Settings
    global_background_information: str
    pivot_background_information: Mapping[str, str]
    sheet_schema: SheetSchema
    total_worksheet_data_rows: int
    total_gain_rows: int
    pass_row_count: int
    fail_row_count: int
    negative_gain_findings: tuple[ValidationFinding, ...]
    negative_gain_decision: NegativeGainDecision
    warnings: tuple[ValidationFinding, ...]
    exclusion_counts: Mapping[str, int]
    pivot_failure_summaries: tuple[PivotFailureSummary, ...]
    top_failure_cases: tuple[CaseAnalysis, ...]
    worst_failure_cases: tuple[CaseAnalysis, ...]
    closest_pass_cases: tuple[CaseAnalysis, ...]
    zero_margin_pass_boundary_count: int
    pairwise_comparisons: tuple[PairwiseComparison, ...]
    model_bypass_status: ModelBypassStatus

    def __post_init__(self) -> None:
        if not isinstance(self.source_metadata, SourceMetadata):
            raise TypeError("source_metadata must be SourceMetadata")
        if not isinstance(self.settings, Settings):
            raise TypeError("settings must be Settings")
        if not isinstance(self.sheet_schema, SheetSchema):
            raise TypeError("sheet_schema must be SheetSchema")
        if not isinstance(self.global_background_information, str):
            raise TypeError("global_background_information must be a string")
        pivot_background = _copy_mapping(
            self.pivot_background_information, "pivot_background_information"
        )
        if any(not isinstance(value, str) for value in pivot_background.values()):
            raise TypeError("pivot background values must be strings")
        if set(pivot_background) != set(self.sheet_schema.pivot_names):
            raise ValueError("pivot background information must cover every discovered pivot")

        counts = (
            self.total_worksheet_data_rows,
            self.total_gain_rows,
            self.pass_row_count,
            self.fail_row_count,
            self.zero_margin_pass_boundary_count,
        )
        if any(type(count) is not int or count < 0 for count in counts):
            raise ValueError("analysis counts must be nonnegative integers")
        if self.total_gain_rows > self.total_worksheet_data_rows:
            raise ValueError("total_gain_rows cannot exceed total worksheet data rows")
        if self.pass_row_count + self.fail_row_count > self.total_gain_rows:
            raise ValueError("PASS and FAIL counts cannot exceed total GAIN rows")
        if self.zero_margin_pass_boundary_count > self.pass_row_count:
            raise ValueError("zero-margin pass count cannot exceed PASS count")

        negative_findings = tuple(self.negative_gain_findings)
        warnings = tuple(self.warnings)
        if any(not isinstance(finding, ValidationFinding) for finding in negative_findings + warnings):
            raise TypeError("findings must contain ValidationFinding instances")
        if any(finding.severity is not FindingSeverity.WARNING for finding in warnings):
            raise ValueError("warnings must have warning severity")
        if type(self.negative_gain_decision) is not NegativeGainDecision:
            raise TypeError("negative_gain_decision must be NegativeGainDecision")

        exclusions = _copy_mapping(self.exclusion_counts, "exclusion_counts")
        if any(type(count) is not int or count < 0 for count in exclusions.values()):
            raise ValueError("exclusion counts must be nonnegative integers")

        summaries = tuple(self.pivot_failure_summaries)
        if any(not isinstance(summary, PivotFailureSummary) for summary in summaries):
            raise TypeError("pivot_failure_summaries must contain PivotFailureSummary instances")
        if len({summary.pivot_name for summary in summaries}) != len(summaries):
            raise ValueError("pivot failure summaries must have unique pivot names")

        case_groups = (
            tuple(self.top_failure_cases),
            tuple(self.worst_failure_cases),
            tuple(self.closest_pass_cases),
        )
        if any(not isinstance(case, CaseAnalysis) for group in case_groups for case in group):
            raise TypeError("case outputs must contain CaseAnalysis instances")
        if len(case_groups[0]) > 50 or len(case_groups[1]) > 5 or len(case_groups[2]) > 5:
            raise ValueError("case output limits are 50, 5, and 5 respectively")

        comparisons = tuple(self.pairwise_comparisons)
        if any(not isinstance(comparison, PairwiseComparison) for comparison in comparisons):
            raise TypeError("pairwise_comparisons must contain PairwiseComparison instances")
        if any(comparison.selected_pivot != self.settings.pivot_field_of_interest for comparison in comparisons):
            raise ValueError("pairwise comparisons must use the configured selected pivot")
        if len({comparison.comparison_pivot for comparison in comparisons}) != len(comparisons):
            raise ValueError("pairwise comparisons must have unique comparison pivots")
        if self.model_bypass_status is not ModelBypassStatus.BYPASSED:
            raise ValueError("v0.1 analysis results must record the model as bypassed")

        object.__setattr__(self, "pivot_background_information", pivot_background)
        object.__setattr__(self, "negative_gain_findings", negative_findings)
        object.__setattr__(self, "warnings", warnings)
        object.__setattr__(self, "exclusion_counts", exclusions)
        object.__setattr__(self, "pivot_failure_summaries", summaries)
        object.__setattr__(self, "top_failure_cases", case_groups[0])
        object.__setattr__(self, "worst_failure_cases", case_groups[1])
        object.__setattr__(self, "closest_pass_cases", case_groups[2])
        object.__setattr__(self, "pairwise_comparisons", comparisons)
