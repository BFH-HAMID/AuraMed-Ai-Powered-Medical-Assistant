"""API routes — layer 5: Offline Accessibility & Feedback Loop (Nodes 21-26)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.deps import verify_audit_access
from backend.core.schemas import ok
from backend.nodes.node_21_offline import offline_node
from backend.nodes.node_22_symptom_tracker import symptom_tracker_node
from backend.nodes.node_23_remedies.engine import remedies_engine
from backend.nodes.node_24_feedback import feedback_node
from backend.nodes.node_25_alt_treatment import alt_treatment_node
from backend.nodes.node_26_audit import audit_node

router = APIRouter(prefix="/api/v1", tags=["5. Offline Accessibility & Feedback Loop"])


@router.get("/21/offline/status")
async def offline_status():
    return ok(21, "Offline Node & Local Caching", offline_node.status(), offline=True)


@router.post("/22/symptom-tracker")
async def symptom_tracker(payload: dict):
    data = symptom_tracker_node.run(payload)
    return ok(22, "Interactive Symptom Tracker", data,
              risk_level=data.get("risk_level"), language=payload.get("language", "en"))


@router.post("/23/home-remedies")
async def home_remedies(payload: dict):
    data = remedies_engine.run(payload)
    return ok(23, "Verified Home Remedies & Traditional Tips", data,
              risk_level=data.get("risk_level"), language=payload.get("language", "en"))


@router.post("/24/feedback")
async def doctor_feedback(payload: dict):
    return ok(24, "Doctor Feedback Loop & Logging", feedback_node.run(payload))


@router.post("/25/alternative-care")
async def alternative_care(payload: dict):
    data = alt_treatment_node.run(payload)
    return ok(25, "Alternative Treatment & Lifestyle Options", data,
              language=payload.get("language", "en"))


@router.get("/26/audit/verify", dependencies=[Depends(verify_audit_access)])
async def audit_verify():
    return ok(26, "Regulatory Audit & Compliance Logging", audit_node.integrity_report())


@router.get("/26/audit/events", dependencies=[Depends(verify_audit_access)])
async def audit_events(limit: int = 100):
    return ok(26, "Regulatory Audit & Compliance Logging", audit_node.recent_events(limit))
