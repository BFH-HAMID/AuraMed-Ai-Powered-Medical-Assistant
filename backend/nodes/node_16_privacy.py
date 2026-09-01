"""Node 16 — Advanced Data Privacy & HIPAA Compliance (service wrapper).

The cryptographic engine lives in ``backend/core/security.py`` (AES-256-GCM
at rest, PII anonymization). This node exposes the service surface used by the
API: text anonymization, field encryption/decryption, and a compliance
self-check describing TLS 1.3 in-transit posture.
"""
from __future__ import annotations

from backend.core.audit import log_action
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode
from backend.core import security


class PrivacyNode(BaseNode):
    node_id = 16
    node_name = "Advanced Data Privacy & HIPAA Compliance"
    implemented = True

    def anonymize(self, text: str) -> dict:
        redacted, found = security.anonymize_text(text)
        log_action(self.node_id, "pii_anonymization",
                   details={"fields_redacted": {k: len(v) for k, v in found.items()}})
        return {
            "status": "ok",
            "original_length": len(text),
            "redacted_text": redacted,
            "pii_detected": found,
        }

    def encrypt_field(self, value: str) -> dict:
        token = security.encryptor.encrypt(value)
        log_action(self.node_id, "phi_encrypted", details={"length": len(value)})
        return {
            "status": "ok",
            "ciphertext": token,
            "algorithm": "AES-256-GCM (Fernet/AES-GCM envelope)",
            "production_key_configured": security.encryptor.is_production_key,
        }

    def compliance_posture(self) -> dict:
        return {
            "status": "ok",
            "at_rest": {
                "algorithm": "AES-256-GCM",
                "key_management": "Operator-provided 32-byte key via AURAMED_ENCRYPTION_KEY; never stored in the repo",
                "production_key_configured": security.encryptor.is_production_key,
            },
            "in_transit": {
                "tls": "1.3 (terminate at reverse proxy / uvicorn ssl; see docs/DEPLOYMENT.md)",
                "hsts": "recommended at proxy",
            },
            "privacy": {
                "pii_anonymization": "email/phone/NID/name redaction before LLM calls (bilingual)",
                "audit_trail": "immutable hash-chained logs (Node 26), PHI summaries de-identified",
                "data_residency": "local edge storage keeps PHI within the clinic network",
            },
            "alignment": ["HIPAA Security Rule (safeguards approach)", "GDPR principles (minimization, auditability)",
                          "Local health-data regulation — configure retention per jurisdiction"],
        }

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        action = payload.get("action", "posture")
        if action == "anonymize":
            return self.anonymize(payload.get("text", ""))
        if action == "encrypt":
            return self.encrypt_field(payload.get("value", ""))
        return self.compliance_posture()


privacy_node = PrivacyNode()
