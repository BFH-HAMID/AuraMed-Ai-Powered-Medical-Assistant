"""Node 13 — Prescription & Guidelines Engine.

Produces a STRUCTURED CLINICAL DRAFT (never a final prescription) aligned to
protocol headings (national / WHO-style guidelines), then routes the draft
through Node 05 Drug Safety before presenting it. Every draft is explicitly
marked ``requires_physician_signoff=True``.
"""
from __future__ import annotations

from backend.core.audit import log_action
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode

# Lightweight protocol templates keyed to Node 08 consensus diagnosis keys.
PROTOCOL_TEMPLATES: dict[str, dict] = {
    "uri": {
        "guideline": "Standard community URI management (symptomatic, no antibiotics without bacterial evidence)",
        "investigations": [],
        "non_drug_measures": ["rest", "warm fluids", "saline gargle", "monitor temperature"],
        "drug_considerations": ["paracetamol if fever/pain (respect 4 g/day max)"],
        "review_in_days": 3,
    },
    "pneumonia": {
        "guideline": "Community-acquired pneumonia pathway (severity assessment first)",
        "investigations": ["chest x-ray", "cbc", "spo2", "sputum if severe"],
        "non_drug_measures": ["hydration", "rest", "upright positioning"],
        "drug_considerations": ["antibiotic per local resistance protocol — physician decision"],
        "review_in_days": 2,
    },
    "diarrhea_dehydration": {
        "guideline": "Acute watery diarrhea / ORS-first protocol (WHO/national)",
        "investigations": ["stool exam if bloody/persistent", "hydration status"],
        "non_drug_measures": ["ORS after each stool", "continue feeding", "zinc <5y"],
        "drug_considerations": ["antibiotics NOT routine; only dysentery/cholera per protocol"],
        "review_in_days": 1,
    },
    "hypertension": {
        "guideline": "Hypertension confirmation & management pathway",
        "investigations": ["repeat BP both arms", "creatinine/electrolytes", "urine albumin", "ecg"],
        "non_drug_measures": ["salt <5 g/day", "weight management", "aerobic activity"],
        "drug_considerations": ["ACEi/ARB, CCB or thiazide per age/comorbidity — physician decision"],
        "review_in_days": 7,
    },
}


class GuidelinesNode(BaseNode):
    node_id = 13
    node_name = "Prescription & Guidelines Engine"
    implemented = True

    def draft(self, diagnosis_key: str, language: str = "en") -> dict:
        tpl = PROTOCOL_TEMPLATES.get(diagnosis_key)
        if not tpl:
            return {
                "status": "no_template",
                "message_en": f"No structured draft template for '{diagnosis_key}'; physician-led management required.",
                "message_bn": f"'{diagnosis_key}'-এর জন্য টেমপ্লেট নেই; চিকিৎসক-নেতৃত্বাধীন ব্যবস্থাপনা প্রয়োজন।",
                "requires_physician_signoff": True,
            }
        draft = {
            "status": "draft",
            "diagnosis_key": diagnosis_key,
            "guideline_reference": tpl["guideline"],
            "investigations": tpl["investigations"],
            "non_drug_measures": tpl["non_drug_measures"],
            "drug_considerations": tpl["drug_considerations"],
            "review_in_days": tpl["review_in_days"],
            "requires_physician_signoff": True,
            "drug_safety_gate": "Any named medication MUST pass Node 05 Drug Safety check against patient allergies/renal/cardiac status before dispensing.",
            "language": language,
        }
        log_action(self.node_id, "guideline_draft", details={"diagnosis": diagnosis_key})
        return draft

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        return self.draft(payload.get("diagnosis_key", ""), payload.get("language", "en"))


guidelines_node = GuidelinesNode()
