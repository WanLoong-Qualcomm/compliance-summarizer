from __future__ import annotations

from compliance_summarizer.measurements import (
    MEASUREMENTS,
    get_measurement_definition,
)


def test_measurement_registry_matches_json_definitions():
    expected = {
        "GAIN",
        "GAIN-DNL",
        "GCIB",
        "GCTX",
        "IP2ACS",
        "IP2IB",
        "IP3ACS",
        "IP3IB",
        "IP3TB",
        "S11-LOW",
        "S11-MID",
        "S11-HIGH",
        "SSNFWSPURREMOVAL",
        "SSNF-FIRSTRBWSPURREMOVAL",
        "SSNF-LASTRBWSPURREMOVAL",
    }

    assert set(MEASUREMENTS) == expected
    assert get_measurement_definition("GAIN").delta_fn == "main - other"
    assert get_measurement_definition("GCIB").delta_fn == "other - main"
    definition = get_measurement_definition("GAIN-DNL")
    assert definition.delta_fn == "midpoint deviation"
    assert definition.acceptable_variation == 0.2
