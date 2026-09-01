"""Node 08 — Second Opinion & Dual-AI Consensus (production).

Runs TWO independent clinical reasoning models over the same (anonymized)
case, then arbitrates:

  * agreement scoring on diagnoses & triage level,
  * divergence escalation to a human physician,
  * hallucination/claim verification hooks (unverifiable medication advice is
    never silently trusted),
  * graceful degradation: if a cloud LLM endpoint is unreachable (offline edge
    node), deterministic local models take over so consensus still runs.

Every result carries the mandatory physician-review disclaimer.
"""
from backend.nodes.node_08_consensus.engine import ConsensusEngine

__all__ = ["ConsensusEngine"]
