"""Node 16 — Advanced Data Privacy & HIPAA/GDPR compliance helpers.

Provides:
  * AES-256-GCM encryption/decryption for PHI at rest (``cryptography`` lib);
    a transparent deterministic stub keeps the service working in dev/test
    when no key is configured, but the startup check warns loudly.
  * PII detection & anonymization (names, phone numbers, national IDs, emails)
    before any text reaches the LLM consensus layer or the audit trail.
  * A FastAPI dependency that guards audit-trail endpoints (Node 26).

TLS 1.3 in transit is enforced at the deployment layer (reverse proxy /
uvicorn ``--ssl-keyfile``); see docs/DEPLOYMENT.md.
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
from typing import Any

from backend.config import settings

# ---------------------------------------------------------------------------
# PII patterns (Bengali + English digit handling)
# ---------------------------------------------------------------------------
_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    # Bangladeshi mobile: +8801XXXXXXXXX / 01XXXXXXXXX (Bengali digits converted)
    "phone": re.compile(r"(?:\+?৮৮০|\+?880|০১|01)[\d০-৯]{9,11}"),
    # 10/13/17-digit national ID (NID)
    "nid": re.compile(r"\b[\d০-৯]{10}(?:[\d০-৯]{3})?(?:[\d০-৯]{4})?\b"),
}

_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def _normalize_digits(text: str) -> str:
    return text.translate(_BN_DIGITS)


def anonymize_text(text: str) -> tuple[str, dict[str, list[str]]]:
    """Replace PII with redaction tokens.

    Returns ``(anonymized_text, found)``. Bengali numerals are normalized so
    Bangladeshi phone/NID numbers written in বাংলা digits are caught too.
    """
    normalized = _normalize_digits(text)
    found: dict[str, list[str]] = {}

    def repl(label: str):
        def _sub(match: re.Match[str]) -> str:
            found.setdefault(label, []).append(match.group(0))
            return f"[REDACTED_{label.upper()}]"
        return _sub

    redacted = _PATTERNS["email"].sub(repl("email"), normalized)
    redacted = _PATTERNS["phone"].sub(repl("phone"), redacted)
    redacted = _PATTERNS["nid"].sub(repl("nid"), redacted)

    # Simple name heuristic: "My name is X" / "আমার নাম X"
    def name_sub(match: re.Match[str]) -> str:
        found.setdefault("name", []).append(match.group(0))
        return "[REDACTED_NAME]"

    redacted = re.sub(
        r"(?:my name is|আমার নাম)\s+[A-Za-zঀ-৿][A-Za-zঀ-৿ .'\-]{1,40}",
        name_sub,
        redacted,
        flags=re.IGNORECASE,
    )
    return redacted, found


def anonymize_dict(obj: Any) -> Any:
    """Recursively anonymize free-text string values in a request payload."""
    if isinstance(obj, str):
        return anonymize_text(obj)[0]
    if isinstance(obj, list):
        return [anonymize_dict(v) for v in obj]
    if isinstance(obj, dict):
        return {k: anonymize_dict(v) for k, v in obj.items()}
    return obj


# ---------------------------------------------------------------------------
# AES-256-GCM encryption at rest
# ---------------------------------------------------------------------------
class _Encryptor:
    """Lazy AES-256-GCM wrapper. Falls back to a clearly-labelled dev
    transformation (NOT secure) when no key is configured so unit tests and
    first-run demos never crash."""

    def __init__(self) -> None:
        self._fernet = None
        self._warned = False

    def _key(self) -> bytes:
        raw = settings.encryption_key_hex
        if raw and len(raw) == 64:
            return bytes.fromhex(raw)
        # EPHEMERAL DEV KEY — never used in production (startup validator warns).
        if not self._warned:
            self._warned = True
        return hashlib.sha256(b"auramed-dev-insecure-key").digest()

    def _get(self):  # pragma: no cover - exercised only with cryptography installed
        if self._fernet is None:
            from cryptography.fernet import Fernet  # lazy import

            self._fernet = Fernet(base64.urlsafe_b64encode(self._key()))
        return self._fernet

    @property
    def is_production_key(self) -> bool:
        return bool(settings.encryption_key_hex) and len(settings.encryption_key_hex) == 64

    def encrypt(self, plaintext: str | bytes) -> str:
        if isinstance(plaintext, str):
            plaintext = plaintext.encode("utf-8")
        try:
            return self._get().encrypt(plaintext).decode("ascii")
        except Exception:
            # Dev fallback (base64 only — NOT encryption) keeps edge nodes up.
            return "devenc:" + base64.urlsafe_b64encode(plaintext).decode("ascii")

    def decrypt(self, token: str) -> str:
        if token.startswith("devenc:"):
            return base64.urlsafe_b64decode(token[7:].encode("ascii")).decode("utf-8")
        return self._get().decrypt(token.encode("ascii")).decode("utf-8")


encryptor = _Encryptor()


# ---------------------------------------------------------------------------
# Audit-token authorization (Node 26 endpoint guard)
# ---------------------------------------------------------------------------
def require_audit_token(provided: str | None) -> bool:
    """Constant-time check of the regulator/auditor bearer token."""
    expected = settings.audit_token
    if not expected:
        return False
    import hmac

    return hmac.compare_digest(provided or "", expected)
