"""Red-flag rule loader for the triage engine (Node 02)."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.config import REPO_ROOT

RULES_PATH = Path(REPO_ROOT) / "backend" / "data" / "red_flags.json"

_BN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


def _normalize(text: str) -> str:
    return text.translate(_BN_DIGITS).lower()


@lru_cache(maxsize=1)
def load_red_flags() -> list[dict[str, Any]]:
    with RULES_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    flags = data["red_flags"]
    for flag in flags:
        flag["_kw"] = [_normalize(k) for k in flag.get("keywords_en", []) + flag.get("keywords_bn", [])]
    return flags


@lru_cache(maxsize=1)
def load_yellow_flags() -> dict[str, Any]:
    with RULES_PATH.open(encoding="utf-8") as fh:
        data = json.load(fh)
    yf = data["yellow_flags"]
    yf["_kw"] = [_normalize(k) for k in yf.get("keywords_en", []) + yf.get("keywords_bn", [])]
    return yf


def match_red_flags(text: str) -> list[dict[str, Any]]:
    """Return all red-flag rules whose keywords appear in ``text``."""
    norm = _normalize(text)
    hits: list[dict[str, Any]] = []
    for flag in load_red_flags():
        if any(kw in norm for kw in flag["_kw"]):
            hits.append(flag)
    return hits


def match_yellow_flags(text: str) -> list[str]:
    norm = _normalize(text)
    yf = load_yellow_flags()
    return [kw for kw in yf["_kw"] if kw in norm]
