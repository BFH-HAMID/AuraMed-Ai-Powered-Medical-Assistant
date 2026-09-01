"""Node 14 — First Aid & Emergency Guidebook.

Instant bilingual retrieval of first-aid protocols. Runs offline (local JSON),
audited. Protocols are standard community first-aid guidance; severe
presentations always route through Node 02 red-flag triage first.
"""
from __future__ import annotations

import json
from pathlib import Path

from backend.config import REPO_ROOT
from backend.core.audit import log_action
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode

_PROTOCOLS_PATH = Path(REPO_ROOT) / "backend" / "data" / "first_aid.json"


class FirstAidEngine(BaseNode):
    node_id = 14
    node_name = "First Aid & Emergency Guidebook"
    implemented = True

    def __init__(self) -> None:
        self._data = json.loads(_PROTOCOLS_PATH.read_text(encoding="utf-8"))["protocols"]

    def list_protocols(self, language: str = "en") -> list[dict]:
        return [
            {"id": pid, "title": p["title_bn" if language.startswith("bn") else "title_en"]}
            for pid, p in self._data.items()
        ]

    def get_protocol(self, protocol_id: str, language: str = "en") -> dict:
        p = self._data.get(protocol_id)
        if not p:
            return {
                "found": False,
                "message_en": f"No first-aid protocol with id '{protocol_id}'.",
                "message_bn": f"'{protocol_id}' আইডিতে কোনো প্রোটোকল নেই।",
                "available": self.list_protocols(language),
            }
        bn = language.startswith("bn")
        result = {
            "found": True,
            "id": protocol_id,
            "title": p["title_bn"] if bn else p["title_en"],
            "steps": p["steps_bn"] if bn else p["steps_en"],
            "call_emergency": True,  # guidebook protocols all assume emergency activation
            "emergency_number": "999",
        }
        log_action(self.node_id, "first_aid_retrieval", details={"protocol": protocol_id})
        return result

    def search(self, query: str, language: str = "en") -> dict:
        """Find the closest protocol by keyword (English/Bengali)."""
        q = query.lower()
        matches = []
        for pid, p in self._data.items():
            haystack = " ".join(
                [p["title_en"], p["title_bn"]] + p["steps_en"] + p["steps_bn"]
            ).lower()
            score = sum(1 for token in q.split() if token in haystack)
            if score:
                matches.append((score, pid))
        matches.sort(reverse=True)
        if not matches:
            return {
                "found": False,
                "message_en": "No matching protocol. If symptoms are severe, call 999 immediately.",
                "message_bn": "কোনো মিল প্রোটোকল নেই। লক্ষণ গুরুতর হলে অবিলম্বে ৯৯৯-এ কল করুন।",
                "available": self.list_protocols(language),
            }
        return self.get_protocol(matches[0][1], language)

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        language = payload.get("language", "en")
        if payload.get("protocol_id"):
            return self.get_protocol(payload["protocol_id"], language)
        return self.search(payload.get("query", ""), language)


first_aid_engine = FirstAidEngine()
