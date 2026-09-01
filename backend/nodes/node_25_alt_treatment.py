"""Node 25 — Alternative Treatment & Lifestyle Options.

Conservative, non-emergency care plans for GREEN/YELLOW-LOW conditions:
physiotherapy-style guidance, watchful waiting criteria, follow-up triggers.
Refuses to generate plans for RED triage (those go straight to emergency).
"""
from __future__ import annotations

from backend.core.audit import log_action
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode

_PLANS: dict[str, dict] = {
    "back_pain": {
        "en": {"measures": ["Stay active — short walks; avoid bed rest >1-2 days",
                             "Local heat 15-20 min; gentle forward-bend stretches",
                             "Lift with bent knees, not the back"],
               "watchful_wait_days": 14,
               "escalate_if": ["leg weakness/numbness", "loss of bladder/bowel control",
                               "pain after major injury", "fever with back pain"]},
        "bn": {"measures": ["সক্রিয় থাকুন — ছোট হাঁটা; ১-২ দিনের বেশি বিছানায় বিশ্রাম নয়",
                            "১৫-২০ মিনিট সেঁক; হালকা স্ট্রেচ",
                            "কোমরে নয়, হাঁটু ভাঁজ করে জিনিস তোলা"],
               "watchful_wait_days": 14,
               "escalate_if": ["পায়ে দুর্বলতা/অবশভাব", "প্রস্রাব-পায়খানা নিয়ন্ত্রণে সমস্যা",
                               "বড় আঘাতের পর ব্যথা", "কোমর ব্যথার সাথে জ্বর"]},
    },
    "common_cold": {
        "en": {"measures": ["Rest, warm fluids, saline gargle (Node 23)",
                             "No antibiotics without bacterial evidence"],
               "watchful_wait_days": 10,
               "escalate_if": ["breathing difficulty", "high fever >3 days", "chest pain"]},
        "bn": {"measures": ["বিশ্রাম, উষ্ণ পানীয়, লবণ-পানি গার্গল (Node 23)",
                            "ব্যাকটেরিয়ার প্রমাণ ছাড়া অ্যান্টিবায়োটিক নয়"],
               "watchful_wait_days": 10,
               "escalate_if": ["শ্বাসকষ্ট", "৩ দিনের বেশি জ্বর", "বুকে ব্যথা"]},
    },
    "general": {
        "en": {"measures": ["Conservative monitoring with symptom diary",
                             "Non-drug measures first (Node 23 remedies + Node 18 lifestyle)"],
               "watchful_wait_days": 7,
               "escalate_if": ["worsening symptoms", "new red-flag symptoms (Node 02)"]},
        "bn": {"measures": ["উপসর্গের ডায়েরিসহ পর্যবেক্ষণ",
                            "প্রথমে অ-ওষুধ ব্যবস্থা (Node 23 + Node 18)"],
               "watchful_wait_days": 7,
               "escalate_if": ["লক্ষণ বাড়লে", "নতুন সতর্কতা সংকেত (Node 02)"]},
    },
}


class AltTreatmentNode(BaseNode):
    node_id = 25
    node_name = "Alternative Treatment & Lifestyle Options"
    implemented = True

    def plan(self, condition: str, risk_level: str = "green", language: str = "en") -> dict:
        if risk_level == "red":
            return {
                "status": "refused",
                "message_en": "RED triage — conservative plans are not appropriate; emergency care now (Node 02/19).",
                "message_bn": "লাল ট্রায়েজ — রক্ষণশীল পরিকল্পনা উপযুক্ত নয়; এখনই জরুরি সেবা (Node 02/19)।",
            }
        key = condition.lower().replace(" ", "_")
        plan = _PLANS.get(key) or _PLANS["general"]
        loc = plan["bn" if language.startswith("bn") else "en"]
        result = {
            "status": "ok",
            "condition": condition,
            "care_type": "conservative_non_emergency",
            "measures": loc["measures"],
            "watchful_wait_days": loc["watchful_wait_days"],
            "escalate_if": loc["escalate_if"],
        }
        log_action(self.node_id, "alt_care_plan", details={"condition": key, "risk": risk_level})
        return result

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        return self.plan(
            payload.get("condition", "general"),
            payload.get("risk_level", "green"),
            payload.get("language", "en"),
        )


alt_treatment_node = AltTreatmentNode()
