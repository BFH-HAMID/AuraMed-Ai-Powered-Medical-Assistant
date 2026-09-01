"""Node 04 — Handwritten Prescription OCR Engine.

TrOCR (handwriting transformer) for handwritten prescriptions with Tesseract
fallback for printed labels, producing per-token confidence scores, then
structured extraction of medicine names / dosage / frequency via the Node 05
drug KB alias resolver. The model layer is optional; the contract and the
post-processing (name normalization + confidence policy) are defined here.
"""
from __future__ import annotations

from backend.core.schemas import PatientContext
from backend.nodes.base import StubNode
from backend.nodes.node_05_drug_safety.knowledge import resolve_drug


class HandwritingOCRNode(StubNode):
    node_id = 4
    node_name = "Handwritten Prescription OCR Engine"
    integration = (
        "Inference: microsoft/trocr-large-handwritten (or trocr-base-handwritten) "
        "via transformers on GPU nodes; Tesseract (ben+eng) for printed text on "
        "edge nodes. Image pre-processing: deskew, binarization (Otsu), line "
        "segmentation with OpenCV. OCR tokens with confidence <0.6 are routed "
        "for human pharmacist verification; recognized medicine names are "
        "normalized through the Node 05 drug KB."
    )

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        result = super().run(payload, patient)
        # Even in stub mode, demonstrate the structured extraction contract:
        # callers may pass raw OCR text lines and get normalized medicine hits.
        raw_lines = payload.get("raw_text_lines") or []
        extracted = []
        for line in raw_lines:
            key, record = resolve_drug(line)
            extracted.append(
                {
                    "raw": line,
                    "recognized_drug": record["name"] if record else None,
                    "in_formulary": record is not None,
                    "confidence": 0.0,  # filled by the OCR model in production
                    "requires_verification": record is None,
                }
            )
        result["extracted_medications"] = extracted
        result["confidence_threshold"] = 0.6
        result["verification_policy"] = (
            "Any medication below confidence 0.6 or outside the formulary must be "
            "verified by a licensed pharmacist before dispensing."
        )
        self.audit("handwriting_ocr_request", details={"lines": len(raw_lines), "stub": True})
        return result


handwriting_ocr_node = HandwritingOCRNode()
