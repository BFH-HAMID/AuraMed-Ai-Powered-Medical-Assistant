"""Node 05 — Drug Safety & Allergy Check (production).

Automated cross-referencing for:
  * drug–drug interactions (severity-graded, mechanism + action + Bengali),
  * patient drug / class allergies (with cross-reactivity classes),
  * renal (eGFR) dosing/contraindication limits,
  * cardiac contraindications (QT prolongation, bleeding, hyperkalemia…),
  * pregnancy flags and duplicate-drug detection.

Pure Python (stdlib + Pydantic). Deterministic, auditable, works fully
offline — designed for edge clinics.
"""
from backend.nodes.node_05_drug_safety.engine import DrugSafetyEngine

__all__ = ["DrugSafetyEngine"]
