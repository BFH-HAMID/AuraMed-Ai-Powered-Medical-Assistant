"""Node 21 — Offline Node & Local Caching (edge capability service).

Reports the edge node's capability matrix and warms the local knowledge
caches. Safety-critical nodes (02 triage, 05 drug safety, 08 local consensus,
14 first aid, 19 routing, 23 remedies, 20 chatbot) run WITHOUT internet; this
endpoint lets the client UI show which features are available offline.
"""
from __future__ import annotations

from backend.core.cache import cache
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode

# Nodes that operate entirely from local files/rule engines.
OFFLINE_CAPABLE = {
    2: "Emergency triage & red flags",
    5: "Drug safety & allergy check",
    8: "Dual-AI consensus (local model fallback)",
    10: "Data synthesis & anonymization",
    11: "Risk predictor scores",
    12: "Medicine leaflets",
    13: "Guideline drafts",
    14: "First-aid guidebook",
    16: "Encryption / PII anonymization",
    17: "Plain-language explainer",
    18: "Diet & lifestyle plans",
    19: "Emergency proximity routing",
    20: "Bengali/English chatbot",
    21: "Offline cache status",
    22: "Symptom tracker",
    23: "Verified home remedies",
    26: "Regulatory audit logging",
}

CLOUD_DEPENDENT = {
    1: "Whisper STT (VOSK alternative is offline-capable)",
    3: "Bulk PDF/DOCX parsing (native text is offline)",
    4: "TrOCR handwriting OCR (Tesseract edge fallback)",
    6: "Neural TTS audio rendering (script generation is offline)",
    7: "Report comparison (fully offline actually)",
    9: "EHR PostgreSQL sync (local snapshot offline)",
    15: "Lab test recommendations (fully offline actually)",
    24: "Doctor feedback telemetry (local queue offline)",
    25: "Alternative care plans (fully offline actually)",
}


class OfflineNode(BaseNode):
    node_id = 21
    node_name = "Offline Node & Local Caching"
    implemented = True

    def status(self) -> dict:
        warmed = cache.warm_knowledge_bases()
        return {
            "status": "ok",
            "offline_mode": True,
            "cached_knowledge": warmed,
            "offline_capable_nodes": [
                {"node": nid, "feature": feat} for nid, feat in sorted(OFFLINE_CAPABLE.items())
            ],
            "cloud_dependent_nodes": [
                {"node": nid, "feature": feat} for nid, feat in sorted(CLOUD_DEPENDENT.items())
            ],
            "message_en": "Safety-critical triage, first-aid and drug checks work fully offline.",
            "message_bn": "জরুরি ট্রায়েজ, প্রাথমিক চিকিৎসা ও ওষুধ যাচাই সম্পূর্ণ অফলাইনে চলে।",
        }

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        return self.status()


offline_node = OfflineNode()
