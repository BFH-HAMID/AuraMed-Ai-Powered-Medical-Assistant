"""Whole-gateway contract suite: every documented route is exercised.

Why this file exists
--------------------
A node emitting an out-of-contract ``risk_level`` (Node 23's no-match path
returned ``"unknown"``) used to raise a ``ValidationError`` inside the shared
``AuraMedResponse`` envelope. The gateway middleware converted that into
**HTTP 500** for ``POST /api/v1/23/home-remedies`` — the patient got an internal
error instead of the "no verified entry, see a clinician" answer the node had
already produced.

These tests walk every path in the generated OpenAPI schema and assert the two
invariants that must hold for all 26 nodes:

1. no route may return a 5xx for a well-formed request;
2. every response carries the mandatory disclaimer (header **and** body) and a
   ``risk_level`` that is either ``null`` or one of RED/YELLOW/GREEN.

``test_every_documented_route_is_covered`` fails when a new endpoint is added
without a case here, so coverage cannot silently rot.
"""
from __future__ import annotations

from dataclasses import replace
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from backend.config import settings as real_settings
from backend.core import security as security_module
from backend.core.schemas import AuraMedResponse, RiskLevel, coerce_risk_level, ok
from backend.main import app

client = TestClient(app)

_AUDIT_TOKEN = "contract-suite-audit-token"

# (method, url, json-body) — one well-formed call per documented route.
ROUTE_CASES: list[tuple[str, str, dict | None]] = [
    ("GET", "/", None),
    ("GET", "/health", None),
    # --- layer 1: input & initial processing -------------------------------
    ("POST", "/api/v1/01/stt", {"audio_base64": "", "language": "bn"}),
    ("POST", "/api/v1/02/triage", {"symptoms_text": "বুকে চাপ ব্যথা আর ঘাম", "language": "bn"}),
    ("POST", "/api/v1/03/reader", {"text": "Fever and cough for 3 days", "language": "en"}),
    ("POST", "/api/v1/04/ocr/prescription", {"image_base64": "", "language": "bn"}),
    ("POST", "/api/v1/05/drug-safety", {
        "medications": [{"name": "warfarin"}, {"name": "ibuprofen"}],
        "patient": {"renal_egfr": 25, "allergies": ["penicillin"]},
    }),
    ("POST", "/api/v1/06/tts", {"text": "খাবারের পরে একটি ট্যাবলেট খান", "language": "bn"}),
    ("POST", "/api/v1/07/report-comparison", {"reports": [
        {"source": "lab_a", "date": "2025-01-01", "tests": {"hba1c": 8.2}},
        {"source": "lab_b", "date": "2025-06-01", "tests": {"hba1c": 7.1}},
    ]}),
    # --- layer 2: core AI & data pipeline ----------------------------------
    ("POST", "/api/v1/08/consensus", {
        "case_text": "60yo male, crushing chest pain radiating to left arm, sweating",
    }),
    ("POST", "/api/v1/09/ehr", {
        "patient": {"age": 55, "sex": "male", "height_cm": 170, "weight_kg": 82},
        "vitals": [{"date": "2025-01-01", "sbp": 150, "dbp": 95}],
    }),
    ("POST", "/api/v1/10/synthesis", {"raw_text": "BP 150/95, sugar 11 mmol/L", "language": "en"}),
    # --- layer 3: risk assessment & diagnostics -----------------------------
    ("POST", "/api/v1/11/risk-score", {"age": 55, "sex": "male", "sbp": 150, "smoker": True, "bmi": 28}),
    ("POST", "/api/v1/12/leaflet", {"drug": "metformin", "language": "bn"}),
    ("POST", "/api/v1/13/guidelines/draft", {"diagnosis": "hypertension", "patient": {"age": 55}}),
    ("GET", "/api/v1/14/first-aid?language=bn", None),
    ("POST", "/api/v1/14/first-aid/lookup", {"query": "burn", "language": "en"}),
    ("POST", "/api/v1/15/lab-tests", {"symptoms": ["fever", "cough"]}),
    # --- layer 4: security, infrastructure & compliance ---------------------
    ("POST", "/api/v1/16/privacy/anonymize", {"text": "ফোন 01712345678", "language": "bn"}),
    ("GET", "/api/v1/16/privacy/posture", None),
    ("POST", "/api/v1/17/explain", {"term": "hypertension", "language": "bn"}),
    ("POST", "/api/v1/18/diet", {"condition": "diabetes", "language": "bn"}),
    ("POST", "/api/v1/19/routing", {"lat": 23.7178, "lon": 90.3979, "condition": "chest_pain"}),
    ("POST", "/api/v1/20/chat", {"message": "মাথা ঘোরছে", "language": "bn"}),
    # --- layer 5: offline accessibility & feedback loop ---------------------
    ("GET", "/api/v1/21/offline/status", None),
    ("POST", "/api/v1/22/symptom-tracker", {"step_id": "start", "answer": "breathing"}),
    ("POST", "/api/v1/23/home-remedies", {"complaint": "sore throat", "language": "bn"}),
    ("POST", "/api/v1/24/feedback", {"doctor_id": "d-1", "node": 5, "correction": "interaction overstated"}),
    ("POST", "/api/v1/25/alternative-care", {"condition": "back pain", "language": "en"}),
    ("GET", "/api/v1/26/audit/verify", None),
    ("GET", "/api/v1/26/audit/events?limit=5", None),
    # --- patient report pack ------------------------------------------------
    ("POST", "/api/v1/report/patient", {
        "patient": {
            "name": "রহিমা বেগম", "age_years": 54, "sex": "female",
            "weight_kg": 68, "height_cm": 155, "phone": "01712345678",
            "allergies": ["penicillin"], "conditions": ["hypertension", "diabetes"],
            "renal_egfr": 58, "diabetic": True,
        },
        "symptoms_text": "তিন সপ্তাহ ধরে মাথা ঘোরা, ঘাড়ে ব্যথা, পিপাসা বেশি",
        "vitals": {"sbp": 158, "dbp": 96, "hr": 92, "spo2": 97},
        "diagnosis": "hypertension",
        "diagnosis_key": "hypertension",
        "medications": [
            {"name": "metformin", "dose": "500 mg", "frequency": "1+0+1", "duration": "30 days"},
            {"name": "ibuprofen", "dose": "400 mg", "frequency": "0+1+0", "duration": "5 days"},
            {"name": "warfarin", "dose": "5 mg", "frequency": "0+0+1", "duration": "ongoing"},
        ],
        "language": "bn",
    }),
    ("POST", "/api/v1/report/patient/download", {
        "patient": {"name": "Abdul Karim", "age_years": 61, "sex": "male",
                    "weight_kg": 78, "height_cm": 170, "allergies": ["sulfa"]},
        "symptoms_text": "crushing chest pain radiating to left arm, sweating",
        "diagnosis": "acute coronary syndrome",
        "medications": [{"name": "aspirin", "dose": "75 mg", "frequency": "0+0+1"}],
        "language": "en",
    }),
]

_ROUTE_IDS = [f"{m} {u}" for m, u, _ in ROUTE_CASES]


@pytest.fixture()
def audit_token(monkeypatch):
    """Configure Node 26's bearer token (settings is a frozen dataclass).

    A full ``dataclasses.replace`` copy is required — Node 16 and ``/health``
    read other fields off the same object, so a partial stand-in breaks them.
    """
    monkeypatch.setattr(security_module, "settings", replace(real_settings, audit_token=_AUDIT_TOKEN))
    return _AUDIT_TOKEN


def _headers(url: str, token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"} if url.startswith("/api/v1/26/audit") else {}


# ---------------------------------------------------------------------------
# Coverage guard
# ---------------------------------------------------------------------------
def test_every_documented_route_is_covered():
    """Every OpenAPI path must have a case above (and vice versa)."""
    documented = set(app.openapi()["paths"])
    covered = {urlsplit(url).path for _, url, _ in ROUTE_CASES}
    assert covered == documented, (
        f"routes without a contract case: {sorted(documented - covered)}; "
        f"stale cases: {sorted(covered - documented)}"
    )


# ---------------------------------------------------------------------------
# The two gateway invariants
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("method,url,body", ROUTE_CASES, ids=_ROUTE_IDS)
def test_route_never_5xx_and_carries_the_safety_envelope(method, url, body, audit_token):
    response = client.request(method, url, json=body, headers=_headers(url, audit_token))

    assert response.status_code < 500, f"{method} {url} -> {response.status_code}: {response.text[:400]}"
    assert "AuraMed AI output is for decision-support only" in response.headers["X-AuraMed-Disclaimer"]

    if not response.headers.get("content-type", "").startswith("application/json"):
        return
    envelope = response.json()
    assert envelope.get("disclaimer"), f"{method} {url} returned no disclaimer in the body"
    risk = envelope.get("risk_level", None)
    assert risk is None or risk in {level.value for level in RiskLevel}, (
        f"{method} {url} returned risk_level={risk!r}, off the RED/YELLOW/GREEN contract"
    )


@pytest.mark.parametrize("method,url,body", ROUTE_CASES, ids=_ROUTE_IDS)
def test_route_success_flag_matches_status(method, url, body, audit_token):
    """A 200 must not carry ``success: false`` (the old 500 fallback did)."""
    response = client.request(method, url, json=body, headers=_headers(url, audit_token))
    if response.status_code != 200:
        pytest.skip("non-200 handled by the envelope test")
    if not response.headers.get("content-type", "").startswith("application/json"):
        return
    assert response.json().get("success") is not False


# ---------------------------------------------------------------------------
# Envelope hardening (unit level)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("raw,expected", [
    ("red", RiskLevel.RED),
    ("YELLOW", RiskLevel.YELLOW),
    (" green ", RiskLevel.GREEN),
    (RiskLevel.RED, RiskLevel.RED),
    (None, None),
    ("unknown", None),
    ("", None),
    ("n/a", None),
    ("not_assessed", None),
    ("purple", None),
    (17, None),
])
def test_coerce_risk_level(raw, expected):
    assert coerce_risk_level(raw) is expected


def test_ok_survives_off_contract_risk_level_and_reports_it():
    payload = ok(23, "Verified Home Remedies & Traditional Tips", {"served": False}, risk_level="unknown")
    assert payload["risk_level"] is None
    assert {"risk_level_unmapped": "unknown"} in payload["alerts"]


def test_ok_keeps_valid_risk_levels_untouched():
    assert ok(2, "Emergency Triage", {}, risk_level="red")["risk_level"] == "red"
    assert ok(2, "Emergency Triage", {}, risk_level=None)["risk_level"] is None


def test_response_model_rejects_nothing_on_risk_level():
    """Direct construction (not just ``ok``) must tolerate node labels."""
    model = AuraMedResponse(node=22, node_name="Interactive Symptom Tracker", risk_level="unknown")
    assert model.risk_level is None


# ---------------------------------------------------------------------------
# Node 26 token guard still enforced
# ---------------------------------------------------------------------------
def test_audit_endpoints_reject_missing_and_wrong_tokens(audit_token):
    assert client.get("/api/v1/26/audit/verify").status_code == 401
    wrong = client.get("/api/v1/26/audit/verify", headers={"Authorization": "Bearer nope"})
    assert wrong.status_code == 401


def test_audit_endpoints_accept_the_configured_token(audit_token):
    response = client.get("/api/v1/26/audit/verify", headers={"Authorization": f"Bearer {audit_token}"})
    assert response.status_code == 200
    assert response.json()["success"] is True


# ---------------------------------------------------------------------------
# Interactive docs must keep rendering (OpenAPI schema stays buildable)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", ["/openapi.json", "/docs", "/redoc"])
def test_interactive_docs_render(path):
    assert client.get(path).status_code == 200


# ---------------------------------------------------------------------------
# Web UI: content negotiation on "/" and static assets
# ---------------------------------------------------------------------------
def test_root_serves_the_web_app_to_browsers_but_json_to_machines():
    browser = client.get("/", headers={"Accept": "text/html,application/xhtml+xml"})
    assert browser.status_code == 200
    assert browser.headers["content-type"].startswith("text/html")
    assert "AuraMed" in browser.text

    machine = client.get("/", headers={"Accept": "application/json"})
    assert machine.status_code == 200
    assert machine.json()["service"].startswith("AuraMed")
    assert machine.json()["web_ui"]


@pytest.mark.parametrize("asset", [
    "/static/css/styles.css",
    "/static/js/app.js",
    "/static/js/brain.js",
])
def test_frontend_assets_are_served(asset):
    response = client.get(asset)
    assert response.status_code == 200
    assert len(response.content) > 100

