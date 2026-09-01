"""Node 21 — Offline Node & Local Caching.

Two-tier cache:

1. **Redis** when reachable (shared, multi-process, TTL-aware) — used in
   clinic-server deployments.
2. **File-backed local cache** always available (``data/cache/``) — this is
   what makes core triage / first-aid / drug-safety work fully offline on an
   edge tablet. All knowledge bases are also read from local JSON files, so no
   internet connection is ever needed for the safety-critical nodes.

The module never raises: if Redis is down it transparently falls back to the
file cache, and if persistence fails it simply behaves as an uncached no-op.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from backend.config import settings

try:  # Redis is optional
    import redis as _redis_lib  # type: ignore
except Exception:  # pragma: no cover
    _redis_lib = None


class EdgeCache:
    def __init__(self) -> None:
        self._redis = None
        self._redis_failed = False
        self._dir = settings.cache_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    # -- Redis (best effort) -------------------------------------------------
    def _redis_client(self):  # pragma: no cover - depends on live Redis
        if self._redis is not None:
            return self._redis
        if self._redis_failed or not settings.redis_url or _redis_lib is None:
            return None
        try:
            self._redis = _redis_lib.from_url(
                settings.redis_url, socket_connect_timeout=0.4, socket_timeout=0.4
            )
            self._redis.ping()
        except Exception:
            self._redis_failed = True
            self._redis = None
        return self._redis

    # -- File cache ----------------------------------------------------------
    def _path(self, key: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_." else "_" for c in key)
        return self._dir / f"{safe}.json"

    def get(self, key: str) -> Any | None:
        r = self._redis_client()
        if r is not None:  # pragma: no cover
            try:
                val = r.get(f"auramed:{key}")
                if val:
                    return json.loads(val)
            except Exception:
                self._redis_failed = True
        path = self._path(key)
        if path.exists():
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if record.get("expires_at", 0) > time.time():
                    return record["value"]
                path.unlink(missing_ok=True)
            except Exception:
                return None
        return None

    def set(self, key: str, value: Any, ttl_seconds: int = 86400) -> None:
        payload = json.dumps({"expires_at": time.time() + ttl_seconds, "value": value}, ensure_ascii=False)
        r = self._redis_client()
        if r is not None:  # pragma: no cover
            try:
                r.setex(f"auramed:{key}", ttl_seconds, payload)
            except Exception:
                self._redis_failed = True
        try:
            self._path(key).write_text(payload, encoding="utf-8")
        except Exception:
            pass

    def warm_knowledge_bases(self) -> dict[str, int]:
        """Preload local clinical knowledge JSON into cache (called at startup)
        so the very first request is instant even on a cold edge device."""
        from backend.nodes.node_05_drug_safety.knowledge import load_drug_kb
        from backend.nodes.node_02_triage.rules import load_red_flags

        counts: dict[str, int] = {}
        try:
            kb = load_drug_kb()
            self.set("kb:drugs", {"drugs": len(kb.get("drugs", {}))}, ttl_seconds=3600)
            counts["drugs"] = len(kb.get("drugs", {}))
        except Exception:
            counts["drugs"] = 0
        try:
            rf = load_red_flags()
            counts["red_flags"] = len(rf)
        except Exception:
            counts["red_flags"] = 0
        return counts


cache = EdgeCache()
