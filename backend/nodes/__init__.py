"""AuraMed's 26 architecture nodes.

Each node is a self-contained subsystem. Safety-critical nodes are fully
implemented (02 triage, 05 drug safety, 08 dual-AI consensus, 14 first aid,
19 emergency routing, 23 home remedies). The remaining nodes expose complete
request/response contracts plus documented integration stubs for the heavy ML
models (Whisper/VOSK, TrOCR/Tesseract, clinical LLMs) so they can run on
resource-constrained edge hardware in rule-based mode.
"""
from __future__ import annotations

NODE_REGISTRY: dict[int, dict[str, str | bool]] = {}


def register(node_id: int, name: str, *, implemented: bool = False) -> None:
    NODE_REGISTRY[node_id] = {"name": name, "implemented": implemented}


def registry_snapshot() -> list[dict[str, Any]]:  # noqa: F821 (Any imported below)
    from typing import Any

    return [
        {"node": nid, "name": meta["name"], "implemented": meta["implemented"]}
        for nid, meta in sorted(NODE_REGISTRY.items())
    ]
