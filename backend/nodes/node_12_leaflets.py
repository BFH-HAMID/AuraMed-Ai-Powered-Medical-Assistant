"""Node 12 — Medicine-Related Documentation (patient-friendly leaflets).

Generates bilingual drug information leaflets (usage, mechanism, cautions,
side-effects) from the local formulary (Node 05 KB), with plain-language and
Bengali sections suitable for printing or TTS read-aloud (Node 06).
"""
from __future__ import annotations

from backend.core.audit import log_action
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode
from backend.nodes.node_05_drug_safety.knowledge import load_drug_kb, resolve_drug

_SIDE_EFFECT_HINTS = {
    "nsaid": ["Stomach irritation — take with food; watch for black stools.", "Kidney caution in dehydration/CKD."],
    "anticoagulant": ["Bleeding/bruising — report immediately.", "Requires INR blood monitoring."],
    "biguanide_antidiabetic": ["Mild stomach upset initially; take with meals.", "Hold during severe illness/contrast scans."],
    "ace_inhibitor": ["Dry cough; dizziness on standing.", "Blood tests for potassium and kidney function."],
    "statin": ["Muscle ache — report severe pain/weakness.", "Usually taken at night."],
    "fluoroquinolone": ["Tendon pain — stop and seek care.", "May affect heart rhythm."],
    "macrolide": ["Nausea; take with food if needed.", "Heart rhythm caution with other medicines."],
    "penicillin": ["Rash/diarrhea; severe allergy requires emergency care."],
    "sulfonamide": ["Rash; severe skin reactions — stop and seek care.", "Sun sensitivity."],
}


class LeafletNode(BaseNode):
    node_id = 12
    node_name = "Medicine-Related Documentation"
    implemented = True

    def generate(self, drug_name: str, language: str = "en") -> dict:
        key, record = resolve_drug(drug_name)
        if not record:
            return {
                "status": "not_found",
                "message_en": f"'{drug_name}' not in local formulary; pharmacist must draft the leaflet.",
                "message_bn": f"'{drug_name}' স্থানীয় ফর্মুলারিতে নেই; ফার্মাসিস্ট লিফলেট তৈরি করবেন।",
            }
        cls = record.get("drug_class", "")
        side_effects = _SIDE_EFFECT_HINTS.get(cls, ["Take exactly as prescribed; do not share medicines."])
        leaflet = {
            "status": "ok",
            "drug": record["name"],
            "drug_class": cls,
            "language": language,
            "sections": {
                "what_it_is_en": f"{record['name']} is a {cls.replace('_', ' ')} medicine.",
                "what_it_is_bn": f"{record['name']} একটি {cls.replace('_', ' ')} শ্রেণির ওষুধ।",
                "how_to_take_en": "Take exactly the dose and timing written on the prescription; complete the full course for antibiotics even if you feel better.",
                "how_to_take_bn": "প্রেসক্রিপশনে লেখা মাত্রা ও সময় অনুযায়ী খান; অ্যান্টিবায়োটিক হলে ভালো লাগলেও পুরো কোর্স শেষ করুন।",
                "cautions_en": record.get("notes", ""),
                "side_effects_en": side_effects,
                "when_to_seek_help_en": [
                    "Swelling of face/lips/tongue, breathing trouble, or severe rash — emergency care.",
                    "Black stools, vomiting blood, unusual bruising — contact your doctor immediately.",
                ],
                "when_to_seek_help_bn": [
                    "মুখ/ঠোঁট/জিহ্বা ফোলা, শ্বাসকষ্ট বা প্রচণ্ড র‍্যাশ — জরুরি সেবা।",
                    "কালো পায়খানা, রক্ত বমি বা অস্বাভাবিক ক্ষত — দ্রুত চিকিৎসককে জানান।",
                ],
            },
        }
        log_action(self.node_id, "leaflet_generated", details={"drug": key})
        return leaflet

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        return self.generate(payload.get("drug_name", ""), payload.get("language", "en"))


leaflet_node = LeafletNode()
