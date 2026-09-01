"""Tests for Node 02 triage, safety middleware and key edge services."""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.core.audit import verify_chain
from backend.config import settings
from backend.main import app
from backend.nodes.node_02_triage.engine import triage_engine
from backend.nodes.node_02_triage.schemas import TriageRequest

client = TestClient(app)


# ------------------------------------------------------------- triage 02
def test_bengali_chest_pain_is_red():
    r = triage_engine.triage(TriageRequest(symptoms_text="বুকে চাপ ব্যথা আর প্রচণ্ড ঘাম", language="bn"))
    assert r.risk_level == "red"
    assert "chest_pain" in [f["id"] for f in r.matched_red_flags]
    assert "chest_pain" in r.first_aid_protocol_ids
    assert r.immediate_advice_bn


def test_stroke_english_red():
    r = triage_engine.triage(TriageRequest(symptoms_text="sudden facial droop and slurred speech"))
    assert r.risk_level == "red"


def test_vitals_only_red_when_spo2_critical():
    r = triage_engine.triage(TriageRequest(symptoms_text="feeling unwell", vitals={"spo2": 88}))
    assert r.risk_level == "red"


def test_yellow_vitals():
    r = triage_engine.triage(TriageRequest(symptoms_text="fever", vitals={"temp_c": 39.8}))
    assert r.risk_level == "yellow"


def test_green_path():
    r = triage_engine.triage(TriageRequest(symptoms_text="mild runny nose today"))
    assert r.risk_level == "green"


# ------------------------------------------------- disclaimer enforcement
def test_every_response_carries_disclaimer_header():
    r = client.get("/health")
    assert "AuraMed AI output is for decision-support only" in r.headers["X-AuraMed-Disclaimer"]


def test_response_body_has_disclaimer():
    r = client.post("/api/v1/02/triage", json={"symptoms_text": "headache"})
    body = r.json()
    assert body["disclaimer"].startswith("AuraMed AI output is for decision-support only")


def test_bengali_disclaimer_in_body():
    r = client.post("/api/v1/02/triage", json={"symptoms_text": "মাথাব্যথা", "language": "bn"})
    assert "চিকিৎসক" in r.json()["disclaimer"]


# ----------------------------------------------------------- audit chain
def test_audit_trail_hash_chain_valid():
    client.post("/api/v1/02/triage", json={"symptoms_text": "chest pain"})
    log_files = list(settings.audit_dir.glob("auramed-audit-*.jsonl"))
    assert log_files
    verdict = verify_chain(log_files[-1])
    assert verdict["valid"] is True


# ------------------------------------------------------ offline / routing
def test_offline_status_lists_safety_nodes():
    r = client.get("/api/v1/21/offline/status")
    nodes = {n["node"] for n in r.json()["data"]["offline_capable_nodes"]}
    assert {2, 5, 8, 14, 19, 23} <= nodes


def test_emergency_routing_returns_nearest_facility():
    r = client.post("/api/v1/19/routing", json={"lat": 23.7178, "lon": 90.3979, "condition": "chest_pain"})
    data = r.json()["data"]
    assert data["nearest_emergency_departments"]
    assert data["national_emergency_number"] == "999"


# ---------------------------------------------------- chatbot red-flag gate
def test_chatbot_intercepts_stroke():
    r = client.post("/api/v1/20/chat", json={"message": "face droop, one side weakness", "language": "en"})
    assert r.json()["data"]["intent"] == "emergency"
    assert r.json()["risk_level"] == "red"


# ---------------------------------------------------- symptom tracker tree
def test_symptom_tracker_red_branch():
    r = client.post("/api/v1/22/symptom-tracker", json={"step_id": "start", "answer": "breathing"})
    data = r.json()["data"]
    assert data["terminal"] is True and data["risk_level"] == "red"
