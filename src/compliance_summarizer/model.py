"""Deterministic v0.1 model-stage bypass."""

from __future__ import annotations

from dataclasses import dataclass

from .contracts import ModelBypassStatus


MODEL_BYPASS_STATEMENT = "AI generation is bypassed in v0.1."


@dataclass(frozen=True, slots=True)
class ModelBypassResult:
    """Fixed output of the v0.1 model stage."""

    status: ModelBypassStatus = ModelBypassStatus.BYPASSED
    statement: str = MODEL_BYPASS_STATEMENT

    def __post_init__(self) -> None:
        if self.status is not ModelBypassStatus.BYPASSED:
            raise ValueError("v0.1 model stage must be bypassed")
        if self.statement != MODEL_BYPASS_STATEMENT:
            raise ValueError("v0.1 model stage statement is fixed")


def run_model_stage() -> ModelBypassResult:
    """Return the fixed local model-stage result without external calls."""

    return ModelBypassResult()
