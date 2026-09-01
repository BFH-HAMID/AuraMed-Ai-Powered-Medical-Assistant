"""Drug knowledge-base loader for Node 05.

Loads ``backend/data/drug_kb.json`` once and caches it. Resolution of drug
names is alias/brand-aware and case-insensitive, with basic Bengali-alias
support so prescriptions written in বাংলা match the same entries.
"""
from __future__ import annotations

import json
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.config import REPO_ROOT

KB_PATH = Path(REPO_ROOT) / "backend" / "data" / "drug_kb.json"
_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def load_drug_kb() -> dict[str, Any]:
    with KB_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def _normalize(name: str) -> str:
    return " ".join(name.lower().strip().replace(".", "").split())


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, str]:
    """Map every alias / brand / Bengali name → canonical drug key."""
    kb = load_drug_kb()
    index: dict[str, str] = {}
    for key, drug in kb["drugs"].items():
        index[_normalize(key)] = key
        index[_normalize(drug["name"])] = key
        for alias in drug.get("aliases", []):
            index[_normalize(alias)] = key
    return index


def resolve_drug(name: str) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve a free-text drug name to ``(canonical_key, drug_record)``.

    Returns ``(None, None)`` when the drug is not in the local KB — callers
    treat unknown drugs as an INFO finding ("manual verification needed"),
    never silently ignoring them.
    """
    key = _alias_index().get(_normalize(name))
    if key:
        return key, load_drug_kb()["drugs"][key]
    # Partial token match (e.g. "aspirin 75mg tablet" -> aspirin)
    norm = _normalize(name)
    for alias, canon in _alias_index().items():
        if len(alias) >= 4 and alias in norm:
            return canon, load_drug_kb()["drugs"][canon]
    return None, None
