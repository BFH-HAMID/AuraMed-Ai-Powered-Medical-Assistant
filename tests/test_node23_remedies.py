"""Node 23 — Verified Home Remedies: refusal paths and the HTTP regression.

Covers the three ways the node can answer, including the no-match path that
used to return ``risk_level="unknown"`` and take the whole endpoint down with a
500.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.nodes.node_23_remedies.engine import remedies_engine

client = TestClient(app)


# ------------------------------------------------------------------ engine level
def test_matched_complaint_serves_remedies_with_stop_if_rule():
    result = remedies_engine.suggest("cold and cough", language="en")
    assert result["served"] is True
    assert result["risk_level"] == "green"
    assert result["tips"] and result["stop_if"]


def test_bengali_complaint_serves_bengali_remedy():
    result = remedies_engine.suggest("জ্বর হয়েছে", language="bn")
    assert result["served"] is True
    assert result["condition_key"] == "mild_fever"


def test_red_flag_complaint_refuses_home_care():
    result = remedies_engine.suggest("crushing chest pain and sweating", language="en")
    assert result["served"] is False
    assert result["risk_level"] == "red"
    assert result["seek_emergency_care"] is True
    assert "chest_pain" in result["matched_red_flags"]


@pytest.mark.parametrize("complaint", ["sore throat", "ringing in my ears", ""])
def test_unmatched_complaint_makes_no_risk_assertion(complaint):
    result = remedies_engine.suggest(complaint, language="en")
    assert result["served"] is False
    assert result["risk_level"] is None            # not "unknown", not "green"
    assert result["escalate_to_clinician"] is True


# ------------------------------------------------------------------ HTTP level
@pytest.mark.parametrize("payload", [
    {"complaint": "sore throat", "language": "en"},
    {"complaint": "", "language": "bn"},
    {"symptom": "sore throat"},                   # documented alias
])
def test_unmatched_complaint_returns_200_not_500(payload):
    """Regression: this used to be HTTP 500 (envelope ValidationError)."""
    response = client.post("/api/v1/23/home-remedies", json=payload)
    assert response.status_code == 200, response.text[:300]
    body = response.json()
    assert body["success"] is True
    assert body["node"] == 23
    assert body["risk_level"] is None
    assert body["data"]["served"] is False
    assert {"home_care_withheld": True, "reason": "no_verified_entry"} in body["alerts"]
    assert body["disclaimer"]


def test_red_flag_complaint_still_returns_red_over_http():
    response = client.post("/api/v1/23/home-remedies", json={"complaint": "chest pain", "language": "en"})
    body = response.json()
    assert response.status_code == 200
    assert body["risk_level"] == "red"
    assert {"home_care_withheld": True, "reason": "red_flag"} in body["alerts"]


def test_matched_complaint_over_http_is_green_with_no_withholding_alert():
    response = client.post("/api/v1/23/home-remedies", json={"complaint": "mild headache", "language": "en"})
    body = response.json()
    assert response.status_code == 200
    assert body["risk_level"] == "green"
    assert body["data"]["served"] is True
    assert body["alerts"] == []
