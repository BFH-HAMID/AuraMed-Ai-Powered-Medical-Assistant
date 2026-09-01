"""Node 10 — Data Synthesis & Preparation.

Normalizes, sanitizes and feature-engineers raw inputs into the unified case
representation consumed by the LLM reasoning core (Node 08): unit
normalization (mg/dL ↔ mmol/L), symptom canonicalization, PII stripping
(Node 16), and missing-field reporting.
"""
from __future__ import annotations

from backend.core.audit import log_action
from backend.core.schemas import PatientContext
from backend.core.security import anonymize_text
from backend.nodes.base import BaseNode

MGDL_TO_MMOL = 0.0555


class DataSynthesisNode(BaseNode):
    node_id = 10
    node_name = "Data Synthesis & Preparation"
    implemented = True

    def prepare(self, case_text: str, vitals: dict | None = None, language: str = "en") -> dict:
        safe_text, pii = anonymize_text(case_text)
        normalized_vitals = self._normalize_vitals(vitals or {})
        missing = self._missing(normalized_vitals)

        feature_block = self._feature_block(safe_text, normalized_vitals)
        log_action(
            self.node_id, "case_synthesis",
            details={"pii_fields": list(pii.keys()), "missing_vitals": missing},
        )
        return {
            "status": "ok",
            "language": language,
            "sanitized_case_text": safe_text,
            "normalized_vitals": normalized_vitals,
            "missing_recommended_fields": missing,
            "feature_block": feature_block,
            "ready_for_node": 8,
        }

    @staticmethod
    def _normalize_vitals(v: dict) -> dict:
        out = dict(v)
        # Glucose unit harmonization to mg/dL
        if "glucose_mmol" in out and "glucose_mg_dl" not in out:
            out["glucose_mg_dl"] = round(float(out.pop("glucose_mmol")) / MGDL_TO_MMOL, 1)
        if "bp" in out and isinstance(out["bp"], str) and "/" in out["bp"]:
            sbp, dbp = out.pop("bp").split("/", 1)
            out.setdefault("sbp", float(sbp.strip()))
            out.setdefault("dbp", float(dbp.strip()))
        return {k: (round(float(val), 2) if isinstance(val, (int, float)) else val)
                for k, val in out.items()}

    @staticmethod
    def _missing(v: dict) -> list[str]:
        recommended = ["sbp", "dbp", "hr", "temp_c", "spo2"]
        return [k for k in recommended if k not in v]

    @staticmethod
    def _feature_block(text: str, vitals: dict) -> str:
        v = ", ".join(f"{k}={val}" for k, val in sorted(vitals.items())) or "none provided"
        return f"SYMPTOMS: {text[:400]}\nVITALS: {v}"

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        return self.prepare(
            payload.get("case_text", ""),
            payload.get("vitals", {}),
            payload.get("language", "en"),
        )


synthesis_node = DataSynthesisNode()
