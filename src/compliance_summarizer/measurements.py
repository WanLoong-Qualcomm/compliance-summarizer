"""Measurement-specific calculation definitions and registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ComparisonClass = Literal["degradation", "unchanged", "improvement"]


@dataclass(frozen=True, slots=True)
class MeasurementDefinition:
    name: str
    margin_statistic: str
    comparison_statistic: str
    higher_is_better: bool

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

MEASUREMENTS = {
    "GAIN": MeasurementDefinition(
        name="GAIN",
        margin_statistic="wcMargin",
        comparison_statistic="NN_25C AVG",
        higher_is_better=True,
    )
}


def get_measurement_definition(name: str) -> MeasurementDefinition:
    return MEASUREMENTS[name.upper()]
