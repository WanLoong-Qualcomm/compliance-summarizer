"""Measurement definitions loaded from the repository test-definition JSON."""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path
from typing import Literal


ComparisonClass = Literal["degradation", "unchanged", "improvement"]
DeltaFunction = Literal["this - other", "other - this", "midpoint deviation"]

THIS_MINUS_OTHER: DeltaFunction = "this - other"
OTHER_MINUS_THIS: DeltaFunction = "other - this"
MIDPOINT_DEVIATION: DeltaFunction = "midpoint deviation"
_DELTA_FUNCTIONS = frozenset(
    {THIS_MINUS_OTHER, OTHER_MINUS_THIS, MIDPOINT_DEVIATION}
)

_DEFINITION_PATH = (
    Path(__file__).resolve().parents[2] / "configs" / "test_definition.json"
)
_DEFAULT_MARGIN_STATISTIC = "wcMargin"
_DEFAULT_COMPARISON_STATISTICS = ("MEAN", "NN_25C AVG")


@dataclass(frozen=True, slots=True)
class MeasurementDefinition:
    name: str
    margin_statistic: str
    comparison_statistics: tuple[str, ...]
    acceptable_variation: float
    delta_fn: DeltaFunction

    def delta(self, main_value: float, comparison_value: float) -> float:
        """Return the configured signed main/comparison delta."""

        if self.delta_fn == THIS_MINUS_OTHER:
            return main_value - comparison_value
        if self.delta_fn in {OTHER_MINUS_THIS, MIDPOINT_DEVIATION}:
            return comparison_value - main_value
        raise ValueError(f"Unsupported measurement delta function '{self.delta_fn}'.")

    def classify(self, delta: float, tolerance: float) -> ComparisonClass:
        if delta < -tolerance:
            return "degradation"
        if delta > tolerance:
            return "improvement"
        return "unchanged"

    @property
    def requires_limits(self) -> bool:
        return self.delta_fn == MIDPOINT_DEVIATION

    @property
    def formula_text(self) -> str:
        return self.delta_fn

    def transform_comparison_value(
        self,
        value: float | None,
        metadata_values: dict[str, object],
    ) -> float | None:
        if value is None:
            return None
        if not self.requires_limits:
            return value
        midpoint = metadata_midpoint(metadata_values)
        if midpoint is None:
            return None
        return abs(value - midpoint)


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


def _load_measurements() -> dict[str, MeasurementDefinition]:
    try:
        payload = json.loads(_DEFINITION_PATH.read_text(encoding="utf-8"))
    except OSError as error:
        raise RuntimeError(
            f"Could not read measurement definitions from '{_DEFINITION_PATH}': "
            f"{error}."
        ) from error
    except json.JSONDecodeError as error:
        raise RuntimeError(
            f"Invalid measurement definitions JSON in '{_DEFINITION_PATH}' at "
            f"line {error.lineno}, column {error.colno}: {error.msg}."
        ) from error

    if not isinstance(payload, dict) or not payload:
        raise RuntimeError(
            f"Measurement definitions in '{_DEFINITION_PATH}' must be a "
            "non-empty JSON object."
        )

    definitions: dict[str, MeasurementDefinition] = {}
    for raw_name, raw_definition in payload.items():
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise RuntimeError("Measurement definition names must be non-empty strings.")
        name = raw_name.strip().upper()
        if name in definitions:
            raise RuntimeError(
                f"Measurement definition '{raw_name}' duplicates '{name}'."
            )
        if not isinstance(raw_definition, dict):
            raise RuntimeError(f"Measurement definition '{name}' must be a JSON object.")

        delta_fn = raw_definition.get("delta_fn")
        if not isinstance(delta_fn, str) or delta_fn not in _DELTA_FUNCTIONS:
            raise RuntimeError(
                f"Measurement definition '{name}' must define delta_fn as "
                f"one of: {', '.join(sorted(_DELTA_FUNCTIONS))}."
            )

        acceptable_variation = raw_definition.get("acceptable_variation")
        if (
            isinstance(acceptable_variation, bool)
            or not isinstance(acceptable_variation, (int, float))
            or not isfinite(acceptable_variation)
            or acceptable_variation < 0
        ):
            raise RuntimeError(
                f"Measurement definition '{name}' must define "
                "acceptable_variation as a finite non-negative number."
            )

        margin_statistic = raw_definition.get(
            "margin_statistic",
            _DEFAULT_MARGIN_STATISTIC,
        )
        comparison_statistics = raw_definition.get(
            "comparison_statistics",
            list(_DEFAULT_COMPARISON_STATISTICS),
        )
        if (
            not isinstance(margin_statistic, str)
            or not margin_statistic.strip()
            or type(comparison_statistics) is not list
            or not comparison_statistics
            or any(
                not isinstance(statistic, str) or not statistic.strip()
                for statistic in comparison_statistics
            )
        ):
            raise RuntimeError(
                f"Measurement definition '{name}' has invalid statistic fields."
            )

        definitions[name] = MeasurementDefinition(
            name=name,
            margin_statistic=margin_statistic.strip(),
            comparison_statistics=tuple(
                statistic.strip() for statistic in comparison_statistics
            ),
            acceptable_variation=float(acceptable_variation),
            delta_fn=delta_fn,
        )
    return definitions


MEASUREMENTS = _load_measurements()


def get_measurement_definition(name: str) -> MeasurementDefinition:
    return MEASUREMENTS[name.upper()]
