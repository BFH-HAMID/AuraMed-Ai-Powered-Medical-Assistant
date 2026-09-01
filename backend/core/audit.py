"""Node 26 — Regulatory Audit & Compliance Logging.

Immutable, append-only, tamper-evident audit trail (hash-chained JSONL).

Each entry stores:
  * a monotonic sequence number,
  * UTC ISO timestamp,
  * node id + action (which subsystem did what),
  * actor (system / doctor id / patient session),
  * a SHA-256 chain hash over (previous_hash + entry body)

Changing or deleting any historical entry breaks every subsequent hash, so
tampering is detectable on verification. Logs are written under
``$AURAMED_DATA_DIR/audit/`` (git-ignored, may be AES-encrypted at rest via
Node 16 by the operator's storage layer).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.config import settings

_LOCK = threading.Lock()


def _today_log() -> Path:
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return settings.audit_dir / f"auramed-audit-{day}.jsonl"


def _hash_entry(previous_hash: str, body: dict[str, Any]) -> str:
    canonical = json.dumps(body, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256((previous_hash + canonical).encode("utf-8")).hexdigest()


def _last_hash(path: Path) -> str:
    if not path.exists() or path.stat().st_size == 0:
        return "GENESIS"
    with path.open("rb") as fh:
        fh.seek(-min(4096, path.stat().st_size), os.SEEK_END)
        tail = fh.read().decode("utf-8", errors="ignore").strip().splitlines()
    for line in reversed(tail):
        try:
            return json.loads(line)["hash"]
        except (json.JSONDecodeError, KeyError):
            continue
    return "GENESIS"


def log_action(
    node: int,
    action: str,
    *,
    actor: str = "system",
    request_id: str | None = None,
    details: dict[str, Any] | None = None,
    risk_level: str | None = None,
) -> dict[str, Any]:
    """Append one immutable audit entry. Returns the stored entry."""
    path = _today_log()
    with _LOCK:
        previous_hash = _last_hash(path)
        seq = _count_lines(path) + 1
        body = {
            "seq": seq,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "node": node,
            "action": action,
            "actor": actor,
            "request_id": request_id,
            "risk_level": risk_level,
            # Details are expected to be de-identified by the caller (Node 16).
            "details": details or {},
        }
        entry = dict(body)
        entry["hash"] = _hash_entry(previous_hash, body)
        entry["prev_hash"] = previous_hash
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("rb") as fh:
        return sum(1 for _ in fh)


def verify_chain(path: Path) -> dict[str, Any]:
    """Verify a log file's hash chain. Returns ``{valid, entries, broken_at}``."""
    if not path.exists():
        return {"valid": True, "entries": 0, "broken_at": None}
    previous_hash = "GENESIS"
    count = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            count += 1
            entry = json.loads(line)
            stored = entry.pop("hash")
            prev = entry.pop("prev_hash", None)
            expected = _hash_entry(previous_hash, entry)
            if stored != expected or prev != previous_hash:
                return {"valid": False, "entries": count, "broken_at": count}
            previous_hash = stored
    return {"valid": True, "entries": count, "broken_at": None}


def read_tail(limit: int = 100) -> list[dict[str, Any]]:
    """Read the most recent audit entries (newest last). Caller must be
    authenticated with the audit token (enforced at the API layer, Node 26)."""
    path = _today_log()
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        lines = fh.readlines()[-limit:]
    return [json.loads(line) for line in lines if line.strip()]
