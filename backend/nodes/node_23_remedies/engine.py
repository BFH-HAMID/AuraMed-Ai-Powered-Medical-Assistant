"""Node 23 — Verified Home Remedies & Traditional Tips.

Only serves GREEN-triage, non-emergency complaints. Every entry includes an
explicit ``stop_if`` escalation rule so patients know exactly when home care
stops being safe. If the caller's text contains red flags, the engine refuses
home-care advice and returns a RED warning instead.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.config import REPO_ROOT
from backend.core.audit import log_action
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode
from backend.nodes.node_02_triage.rules import match_red_flags

_PATH = Path(REPO_ROOT) / "backend" / "data" / "home_remedies.json"

# Complaint keyword -> remedy key (bilingual)
_INDEX = {
    "common_cold": ["cold", "cough", "sardi", "সর্দি", "কাশি", "নাক বন্ধ"],
    "mild_fever": ["fever", "jwor", "জ্বর", "তাপ"],
    "mild_diarrhea": ["diarrhea", "loose stool", "paikhana", "ডায়রিয়া", "পাতলা পায়খানা"],
    "constipation": ["constipation", "kosthokathinno", "কোষ্ঠকাঠিন্য", "পায়খানা কষ্ট"],
    "mild_headache": ["headache", "matha betha", "মাথাব্যথা", "মাথা ব্যথা"],
    "acidity_mild": ["acidity", "heartburn", "gas", "অ্যাসিডিটি", "বুক জ্বালা", "পেট জ্বালা"],
}


class RemediesEngine(BaseNode):
    node_id = 23
    node_name = "Verified Home Remedies & Traditional Tips"
    implemented = True

    def __init__(self) -> None:
        self._data = json.loads(_PATH.read_text(encoding="utf-8"))["remedies"]

    def suggest(self, complaint: str, language: str = "en") -> dict:
        # Hard guard: red flags never receive home-remedy advice.
        red_hits = match_red_flags(complaint)
        if red_hits:
            return {
                "served": False,
                "risk_level": "red",
                "message_en": "These symptoms may be an emergency — do NOT rely on home care. Call 999 or go to the nearest emergency department.",
                "message_bn": "এই লক্ষণ জরুরি হতে পারে — ঘরোয়া চিকিৎসায় নির্ভর করবেন না। ৯৯৯-এ কল করুন বা নিকটস্থ জরুরি বিভাগে যান।",
                "matched_red_flags": [h["id"] for h in red_hits],
            }

        text = complaint.lower()
        best: str | None = None
        for key, kws in _INDEX.items():
            if any(kw in text for kw in kws):
                best = key
                break
        if not best or best not in self._data:
            return {
                "served": False,
                "risk_level": "unknown",
                "message_en": "No verified home-care entry matched. Please consult a clinician.",
                "message_bn": "কোনো যাচাইকৃত ঘরোয়া পরামর্শ মেলেনি। অনুগ্রহ করে চিকিৎসকের সাথে পরামর্শ করুন।",
            }

        entry = self._data[best]
        bn = language.startswith("bn")
        result = {
            "served": True,
            "risk_level": "green",
            "condition_key": best,
            "title": entry["title_bn"] if bn else entry["title_en"],
            "tips": entry["tips_bn"] if bn else entry["tips_en"],
            "stop_if": entry["stop_if_bn"] if bn else entry["stop_if_en"],
        }
        log_action(self.node_id, "remedy_suggestion", details={"condition": best})
        return result

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        return self.suggest(
            payload.get("complaint", ""), payload.get("language", "en")
        )


remedies_engine = RemediesEngine()
