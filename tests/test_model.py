import socket

import pytest

from compliance_summarizer.contracts import ModelBypassStatus
from compliance_summarizer.model import (
    MODEL_BYPASS_STATEMENT,
    ModelBypassResult,
    run_model_stage,
)


def test_model_stage_is_fixed_and_does_not_open_network_connections(monkeypatch):
    def unexpected_connection(*args, **kwargs):
        raise AssertionError("model bypass must not open a network connection")

    monkeypatch.setattr(socket, "create_connection", unexpected_connection)

    first = run_model_stage()
    second = run_model_stage()

    assert isinstance(first, ModelBypassResult)
    assert first == second
    assert first.status is ModelBypassStatus.BYPASSED
    assert first.statement == MODEL_BYPASS_STATEMENT


def test_model_bypass_result_rejects_non_fixed_content():
    with pytest.raises(ValueError, match="must be bypassed"):
        ModelBypassResult(status="active")
    with pytest.raises(ValueError, match="statement is fixed"):
        ModelBypassResult(statement="provider output")
