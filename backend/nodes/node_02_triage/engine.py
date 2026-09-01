"""Node 02 — Emergency Triage engine (production).

Runs 100% offline on the edge device. Two evidence channels:

1. **Symptom text** matched against bilingual red/yellow-flag rule catalog.
2. **Objective vitals** hard thresholds (SpO2, systolic BP, heart rate,
   respiratory rate, temperature, GCS) — these are deliberately conservative:
   abnormal vitals alone can promote a patient to RED even if the text is
   vague or understated.

RED    → activate emergency services now (Node 19 routing + Node 14 first aid)
YELLOW → urgent same-day care
GREEN  → routine / conservative path (Nodes 23/25), monitor.
"""
from __future__ import annotations

from typing import Any

from backend.core.audit import log_action
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode
from backend.nodes.node_02_triage.rules import match_red_flags, match_yellow_flags
from backend.nodes.node_02_triage.schemas import TriageRequest, TriageResult

# Hard vitals thresholds (adult-oriented; conservative for decision support)
VITAL_RED_RULES = [
    ("spo2", lambda v: v < 92, "Oxygen saturation below 92%"),
    ("sbp", lambda v: v < 90, "Systolic BP below 90 mmHg (shock range)"),
    ("gcs", lambda v: v < 13, "Reduced consciousness (GCS < 13)"),
    ("hr", lambda v: v < 40 or v > 130, "Heart rate outside 40-130 bpm"),
    ("rr", lambda v: v < 8 or v > 30, "Respiratory rate outside 8-30/min"),
]
VITAL_YELLOW_RULES = [
    ("spo2", lambda v: 92 <= v < 95, "Oxygen saturation 92-94%"),
    ("sbp", lambda v: 90 <= v < 100, "Systolic BP 90-99 mmHg"),
    ("hr", lambda v: 110 < v <= 130 or 40 <= v < 50, "Borderline heart rate"),
    ("temp_c", lambda v: v >= 39.5 or v <= 35.0, "Extreme temperature (≥39.5°C or ≤35°C)"),
    ("rr", lambda v: 24 < v <= 30, "Tachypnoea 25-30/min"),
]


class TriageEngine(BaseNode):
    node_id = 2
    node_name = "Emergency Triage & Red Flag Detection"
    implemented = True

    def triage(self, request: TriageRequest) -> TriageResult:
        red_hits = match_red_flags(request.symptoms_text)
        yellow_hits = match_yellow_flags(request.symptoms_text)
        vital_reds, vital_yellows = self._evaluate_vitals(request.vitals)

        level = "green"
        if red_hits or vital_reds:
            level = "red"
        elif yellow_hits or vital_yellows:
            level = "yellow"

        possible = sorted({c for hit in red_hits for c in hit.get("possible", [])})
        protocols = sorted({hit["first_aid"] for hit in red_hits if hit.get("first_aid")})

        advice_en, advice_bn = self._advice(level, red_hits, vital_reds, vital_yellows, request.language)

        confidence = self._confidence(red_hits, yellow_hits, vital_reds, vital_yellows, request.vitals)

        result = TriageResult(
            risk_level=level,
            matched_red_flags=[
                {"id": h["id"], "message_en": h["message_en"], "message_bn": h["message_bn"]}
                for h in red_hits
            ],
            yellow_flag_hits=yellow_hits,
            possible_conditions=possible,
            first_aid_protocol_ids=protocols,
            immediate_advice_en=advice_en,
            immediate_advice_bn=advice_bn,
            confidence=confidence,
        )

        log_action(
            self.node_id,
            "triage",
            details={
                "risk_level": level,
                "red_flag_ids": [h["id"] for h in red_hits],
                "vital_reds": [r[2] for r in vital_reds],
                "vital_yellows": [r[2] for r in vital_yellows],
                "yellow_hits": len(yellow_hits),
                "language": request.language,
            },
            risk_level=level,
        )
        return result

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        return self.triage(TriageRequest.model_validate(payload)).model_dump()

    # ------------------------------------------------------------------
    def _evaluate_vitals(self, vitals: dict[str, float]):
        reds, yellows = [], []
        for key, rule, label in VITAL_RED_RULES:
            if key in vitals and rule(vitals[key]):
                reds.append((key, vitals[key], label))
        for key, rule, label in VITAL_YELLOW_RULES:
            if key in vitals and rule(vitals[key]):
                yellows.append((key, vitals[key], label))
        return reds, yellows

    def _advice(self, level, red_hits, vital_reds, vital_yellows, language) -> tuple[str, str]:
        if level == "red":
            msgs_en = [h["message_en"] for h in red_hits]
            msgs_bn = [h["message_bn"] for h in red_hits]
            vit_en = "Abnormal vital signs detected: " + "; ".join(r[2] for r in vital_reds)
            vit_bn = "অস্বাভাবিক ভাইটাল সাইন: " + "; ".join(r[2] for r in vital_reds)
            en = "EMERGENCY (RED). Call emergency number 999 now. " + " | ".join(msgs_en + ([vit_en] if vital_reds else []))
            bn = "জরুরি (লাল)। এখনই ৯৯৯ নম্বরে কল করুন। " + " | ".join(msgs_bn + ([vit_bn] if vital_reds else []))
            return en, bn
        if level == "yellow":
            y_en = "Warning signs: " + ", ".join(h for h in vital_yellows and [r[2] for r in vital_yellows] or [])
            en = (
                "URGENT (YELLOW): warning symptom(s) detected. Seek medical care today at the "
                "nearest clinic. " + ("Vitals: " + "; ".join(r[2] for r in vital_yellows) if vital_yellows else "")
            )
            bn = (
                "জরুরি (হলুদ): সতর্কতা লক্ষণ পাওয়া গেছে। আজই নিকটস্থ ক্লিনিকে চিকিৎসা সেবা নিন। "
                + ("ভাইটাল: " + "; ".join(r[2] for r in vital_yellows) if vital_yellows else "")
            )
            return en.strip(), bn.strip()
        en = (
            "LOW RISK (GREEN) based on the information provided. Safe home care with monitoring; "
            "use Node 23 verified home remedies. Return for care immediately if chest pain, "
            "breathing difficulty, fainting, bleeding or worsening occurs."
        )
        bn = (
            "কম ঝুঁকি (সবুজ)। পর্যবেক্ষণসহ নিরাপদ ঘরোয়া যত্ন; Node 23-এর যাচাইকৃত পরামর্শ ব্যবহার করুন। "
            "বুকে ব্যথা, শ্বাসকষ্ট, অজ্ঞান, রক্তপাত বা অবস্থার অবনতি হলে দ্রুত সেবা নিন।"
        )
        return en, bn

    @staticmethod
    def _confidence(red_hits, yellow_hits, vital_reds, vital_yellows, vitals) -> float:
        # More independent evidence channels -> higher confidence.
        channels = 0
        if red_hits:
            channels += 1
        if vital_reds:
            channels += 1
        if vitals:
            channels += 0.3
        if not red_hits and not yellow_hits and not vitals:
            return 0.4  # vague free text only
        return round(min(0.97, 0.55 + 0.2 * channels + (0.1 if red_hits else 0.0)), 2)


triage_engine = TriageEngine()
