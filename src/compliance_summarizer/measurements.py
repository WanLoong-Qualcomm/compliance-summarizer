"""Measurement-specific calculation definitions and registry."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Literal


ComparisonClass = Literal["degradation", "unchanged", "improvement"]


@dataclass(frozen=True, slots=True)
class MeasurementDefinition:
    name: str
    margin_statistic: str
    comparison_statistics: tuple[str, ...]
    higher_is_better: bool
    comparison_transform: Literal["raw", "midpoint_deviation"] = "raw"

    def delta(self, main_value: float, comparison_value: float) -> float:
        """Return the documented main-pivot-relative-to-comparison delta."""

        return main_value - comparison_value

    def classify(self, delta: float, tolerance: float) -> ComparisonClass:
        oriented_delta = self.oriented_delta(delta)
        if oriented_delta < -tolerance:
            return "degradation"
        if oriented_delta > tolerance:
            return "improvement"
        return "unchanged"

    def oriented_delta(self, delta: float) -> float:
        """Return a signed delta where degradation is negative."""

        return delta if self.higher_is_better else -delta

    @property
    def requires_limits(self) -> bool:
        return self.comparison_transform == "midpoint_deviation"

    def transform_comparison_value(
        self,
        value: float | None,
        metadata_values: dict[str, object],
    ) -> float | None:
        if value is None:
            return None
        if self.comparison_transform == "raw":
            return value
        midpoint = metadata_midpoint(metadata_values)
        if midpoint is None:
            return None
        return abs(value - midpoint)

MEASUREMENTS = {
    "GAIN": MeasurementDefinition(
        name="GAIN",
        margin_statistic="wcMargin",
        comparison_statistics=("MEAN", "NN_25C AVG"),
        higher_is_better=True,
    ),
    "GAIN-DNL": MeasurementDefinition(
        name="GAIN-DNL",
        margin_statistic="wcMargin",
        comparison_statistics=("MEAN", "NN_25C AVG"),
        higher_is_better=False,
        comparison_transform="midpoint_deviation",
    ),
    "GCIB": MeasurementDefinition(
        name="GCIB",
        margin_statistic="wcMargin",
        comparison_statistics=("MEAN", "NN_25C AVG"),
        higher_is_better=False,
    ),
    "IP2ACS": MeasurementDefinition(
        name="IP2ACS",
        margin_statistic="wcMargin",
        comparison_statistics=("MEAN", "NN_25C AVG"),
        higher_is_better=True,
    ),
    "IP2IB": MeasurementDefinition(
        name="IP2IB",
        margin_statistic="wcMargin",
        comparison_statistics=("MEAN", "NN_25C AVG"),
        higher_is_better=True,
    ),
    "IP3ACS": MeasurementDefinition(
        name="IP3ACS",
        margin_statistic="wcMargin",
        comparison_statistics=("MEAN", "NN_25C AVG"),
        higher_is_better=True,
    ),
    "IP3IB": MeasurementDefinition(
        name="IP3IB",
        margin_statistic="wcMargin",
        comparison_statistics=("MEAN", "NN_25C AVG"),
        higher_is_better=True,
    ),
    "S11-LOW": MeasurementDefinition(
        name="S11-LOW",
        margin_statistic="wcMargin",
        comparison_statistics=("MEAN", "NN_25C AVG"),
        higher_is_better=False,
    ),
    "S11-MID": MeasurementDefinition(
        name="S11-MID",
        margin_statistic="wcMargin",
        comparison_statistics=("MEAN", "NN_25C AVG"),
        higher_is_better=False,
    ),
    "S11-HIGH": MeasurementDefinition(
        name="S11-HIGH",
        margin_statistic="wcMargin",
        comparison_statistics=("MEAN", "NN_25C AVG"),
        higher_is_better=False,
    ),
    "SSNFWSPURREMOVAL": MeasurementDefinition(
        name="SSNFWSPURREMOVAL",
        margin_statistic="wcMargin",
        comparison_statistics=("MEAN", "NN_25C AVG"),
        higher_is_better=False,
    ),
}


def metadata_midpoint(metadata_values: dict[str, object]) -> float | None:
    """Return the finite midpoint of row-level LL and UL limits."""

    lower = _finite_number(metadata_values.get("LL"))
    upper = _finite_number(metadata_values.get("UL"))
    if lower is None or upper is None:
        return None
    return (lower + upper) / 2.0


def _finite_number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def get_measurement_definition(name: str) -> MeasurementDefinition:
    return MEASUREMENTS[name.upper()]
