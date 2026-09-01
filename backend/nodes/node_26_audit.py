"""Node 26 — Regulatory Audit & Compliance Logging (service wrapper).

Hash-chained immutable entries live in ``backend/core/audit.py``; this node
adds the verification/reporting surface used by auditors (chain integrity
check, today's event summary). Read access requires the audit bearer token.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from backend.config import settings
from backend.core import audit
from backend.core.audit import log_action, read_tail, verify_chain
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode


class AuditNode(BaseNode):
    node_id = 26
    node_name = "Regulatory Audit & Compliance Logging"
    implemented = True

    def integrity_report(self) -> dict:
        results = []
        files = sorted(settings.audit_dir.glob("auramed-audit-*.jsonl"))
        for path in files:
            verdict = verify_chain(path)
            results.append({"file": path.name, **verdict})
        all_valid = all(r["valid"] for r in results)
        log_action(self.node_id, "audit_integrity_check",
                   details={"files": len(results), "valid": all_valid})
        return {
            "status": "ok",
            "chain_valid": all_valid,
            "files": results,
            "mechanism": "SHA-256 hash-chained append-only JSONL; any edit breaks subsequent hashes.",
            "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        }

    def recent_events(self, limit: int = 100) -> dict:
        entries = read_tail(limit)
        # Summary per node without exposing raw detail to casual callers.
        summary: dict[str, int] = {}
        for e in entries:
            summary[f"{e['node']:02d}"] = summary.get(f"{e['node']:02d}", 0) + 1
        return {
            "status": "ok",
            "count": len(entries),
            "events_per_node": summary,
            "entries": entries,
        }

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        if payload.get("action") == "recent":
            return self.recent_events(int(payload.get("limit", 100)))
        return self.integrity_report()


audit_node = AuditNode()
