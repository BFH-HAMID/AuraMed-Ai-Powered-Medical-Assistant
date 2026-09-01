"""Patient Report Pack — the report the patient downloads from AuraMed.

Covers the composition (every field the product promises: patient identity,
diagnosis, medicines + dosing rules, advice, diet) and the printable HTML
rendering, including escaping of user-supplied free text.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.config import settings
from backend.core.report_html import render_patient_report
from backend.core.report_pack import (
    PatientReportRequest,
    build_patient_report,
    report_filename,
)
from backend.main import app

client = TestClient(app)

BASE = {
    "patient": {
        "name": "রহিমা বেগম",
        "age_years": 54,
        "sex": "female",
        "weight_kg": 68,
        "height_cm": 155,
        "phone": "01712345678",
        "address": "গাজীপুর সদর, গাজীপুর",
        "allergies": ["penicillin"],
        "conditions": ["hypertension", "diabetes"],
        "renal_egfr": 58,
        "diabetic": True,
    },
    "symptoms_text": "তিন সপ্তাহ ধরে মাথা ঘোরা, ঘাড়ে ব্যথা, পিপাসা বেশি",
    "vitals": {"sbp": 158, "dbp": 96, "hr": 92, "spo2": 97},
    "diagnosis": "hypertension",
    "diagnosis_key": "hypertension",
    "medications": [
        {"name": "metformin", "dose": "500 mg", "frequency": "1+0+1", "duration": "30 days"},
        {"name": "atorvastatin", "dose": "20 mg", "frequency": "0+0+1", "duration": "চলমান"},
    ],
    "language": "bn",
}


def _report(**overrides) -> dict:
    payload = dict(BASE)
    payload.update(overrides)
    return build_patient_report(PatientReportRequest.model_validate(payload))


# --------------------------------------------------------------------- pack
def test_report_contains_every_promised_section():
    report = _report()
    for key in ("report_id", "generated_at", "risk_level", "patient", "assessment",
                "diagnosis", "medications", "diet", "suggestions", "disclaimer",
                "lab_tests", "risk_scores", "sources"):
        assert key in report, f"missing {key}"
    assert report["requires_physician_review"] is True
    assert report["report_id"].startswith("AMR-")


def test_patient_identity_and_bmi_are_present():
    patient = _report()["patient"]
    assert patient["name"] == "রহিমা বেগম"
    assert patient["age_years"] == 54
    assert patient["weight_kg"] == 68
    assert patient["height_cm"] == 155
    # 68 kg / 1.55 m² = 28.3 → obese on WHO Asia-Pacific cut-offs
    assert patient["bmi"] == pytest.approx(28.3, abs=0.05)
    assert patient["bmi_category"] == "স্থূলকায়"
    assert patient["allergies"] == ["penicillin"]


@pytest.mark.parametrize("weight,height,expected_band", [
    (45, 160, "underweight"),
    (60, 165, "normal"),
    (70, 165, "overweight"),
    (95, 165, "obese"),
])
def test_bmi_bands_use_asia_pacific_cutoffs(weight, height, expected_band):
    payload = dict(BASE)
    payload["patient"] = dict(BASE["patient"], weight_kg=weight, height_cm=height)
    assert build_patient_report(PatientReportRequest.model_validate(payload))["patient"]["bmi_category_key"] == expected_band


def test_dosing_shorthand_is_expanded_in_bengali():
    meds = _report()["medications"]
    metformin = next(m for m in meds if m["name"] == "metformin")
    assert metformin["frequency"] == "সকালে 1টি · রাতে 1টি"
    statin = next(m for m in meds if m["name"] == "atorvastatin")
    assert statin["frequency"] == "রাতে 1টি"


def test_timing_rules_follow_the_drug_class():
    meds = {m["name"]: m for m in _report()["medications"]}
    assert "খাবার" in meds["metformin"]["timing"]      # biguanide → with/after food
    assert "রাতে" in meds["atorvastatin"]["timing"]    # statin → at night


def test_free_text_frequency_and_timing_are_preserved():
    payload = dict(BASE)
    payload["medications"] = [{
        "name": "paracetamol", "dose": "500 mg",
        "frequency": "প্রয়োজনে", "duration": "3 দিন", "timing": "জ্বর এলে",
    }]
    med = build_patient_report(PatientReportRequest.model_validate(payload))["medications"][0]
    assert med["frequency"] == "প্রয়োজনে"
    assert med["timing"] == "জ্বর এলে"


def test_drug_safety_hard_stop_forces_a_red_report():
    payload = dict(BASE)
    payload["medications"] = [
        {"name": "warfarin", "dose": "5 mg", "frequency": "0+0+1"},
        {"name": "ibuprofen", "dose": "400 mg", "frequency": "1+0+1"},
    ]
    payload["symptoms_text"] = "হালকা মাথাব্যথা"
    report = build_patient_report(PatientReportRequest.model_validate(payload))
    assert report["drug_safety"]["safe_to_proceed"] is False
    assert report["risk_level"] == "red"
    assert any(m["warnings"] for m in report["medications"])


def test_red_flag_symptoms_produce_red_risk_and_first_aid():
    payload = dict(BASE)
    payload["symptoms_text"] = "crushing chest pain radiating to the left arm, heavy sweating"
    report = build_patient_report(PatientReportRequest.model_validate(payload))
    assert report["risk_level"] == "red"
    assert report["assessment"]["triage"]["matched_red_flags"]
    # the emergency number is localized: ৯৯৯ in Bengali, 999 in English
    assert report["assessment"]["emergency_number"] == "৯৯৯"
    en = dict(BASE, language="en", symptoms_text="crushing chest pain radiating to the left arm")
    en_report = build_patient_report(PatientReportRequest.model_validate(en))
    assert en_report["assessment"]["emergency_number"] == "999"


def test_suggestions_and_diet_are_filled():
    report = _report()
    assert report["suggestions"], "report must carry advice for the patient"
    assert report["diet"]["diet"] and report["diet"]["activity"]
    assert report["diet"]["plan_key"] == "hypertension"


def test_report_is_written_to_the_audit_trail():
    report = _report()
    logs = sorted(settings.audit_dir.glob("auramed-audit-*.jsonl"))
    assert logs, "audit log missing"
    assert report["report_id"] in logs[-1].read_text(encoding="utf-8")


# ------------------------------------------------------------------ HTML doc
def test_html_report_is_self_contained_and_printable():
    html = render_patient_report(_report())
    assert html.startswith("<!DOCTYPE html>")
    assert "<style>" in html and "http" not in html.split("<style>")[1].split("</style>")[0]
    assert "@page" in html and "@media print" in html
    assert "window.print()" in html


def test_html_report_contains_all_sections():
    html = render_patient_report(_report())
    for fragment in ("রহিমা বেগম", "54", "68 kg", "155 cm", "hypertension",
                     "metformin", "500 mg", "সকালে 1টি · রাতে 1টি",
                     "খাদ্য ও জীবনযাপন পরিকল্পনা", "রোগীর জন্য পরামর্শ"):
        assert fragment in html, f"missing {fragment!r} in the HTML report"
    assert "AuraMed AI" in html or "AuraMed" in html
    assert "পর্যালোচনাকারী চিকিৎসকের স্বাক্ষর" in html


def test_html_report_escapes_user_supplied_text():
    payload = dict(BASE)
    payload["symptoms_text"] = "<script>alert('xss')</script> জ্বর"
    payload["diagnosis"] = '"><img src=x onerror=alert(1)>'
    html = render_patient_report(build_patient_report(PatientReportRequest.model_validate(payload)))
    assert "<script>alert" not in html
    assert "<img src=x" not in html
    assert "&lt;script&gt;" in html


def test_report_filename_is_ascii_and_has_no_phi():
    name = report_filename(_report())
    assert name.endswith(".html")
    assert name.isascii()
    assert "রহিমা" not in name


# ------------------------------------------------------------------ endpoints
def test_report_endpoint_returns_the_envelope():
    response = client.post("/api/v1/report/patient", json=BASE)
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["node"] == 7
    assert body["data"]["patient"]["name"] == "রহিমা বেগম"
    assert {"requires_physician_review": True} in body["alerts"]
    assert body["disclaimer"]


def test_download_endpoint_attaches_a_file():
    response = client.post("/api/v1/report/patient/download", json=BASE)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["X-AuraMed-Report-Id"].startswith("AMR-")
    assert response.headers["X-AuraMed-Risk-Level"] in {"red", "yellow", "green"}
    assert "X-AuraMed-Disclaimer" in response.headers
    assert "<!DOCTYPE html>" in response.text


def test_download_validates_required_patient_name():
    payload = dict(BASE)
    payload["patient"] = {"age_years": 40}
    assert client.post("/api/v1/report/patient/download", json=payload).status_code == 422
