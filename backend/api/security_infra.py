"""API routes — layer 4: Security, Infrastructure & Compliance (Nodes 16-20)."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.api.deps import verify_audit_access
from backend.core.schemas import ok
from backend.nodes.node_16_privacy import privacy_node
from backend.nodes.node_17_explainer import explainer_node
from backend.nodes.node_18_diet import diet_node
from backend.nodes.node_19_routing.engine import routing_engine
from backend.nodes.node_20_chatbot import chatbot_node

router = APIRouter(prefix="/api/v1", tags=["4. Security, Infrastructure & Compliance"])


@router.get("/16/privacy/posture")
async def privacy_posture():
    return ok(16, "Advanced Data Privacy & HIPAA Compliance", privacy_node.compliance_posture())


@router.post("/16/privacy/anonymize")
async def anonymize(payload: dict):
    return ok(16, "Advanced Data Privacy & HIPAA Compliance",
              privacy_node.anonymize(payload.get("text", "")))


@router.post("/17/explain")
async def plain_explanation(payload: dict):
    return ok(17, "Simplified Patient Explanation", explainer_node.run(payload),
              language=payload.get("language", "en"))


@router.post("/18/diet")
async def diet_plan(payload: dict):
    return ok(18, "Diet & Lifestyle Guide Generator", diet_node.run(payload),
              language=payload.get("language", "en"))


@router.post("/19/routing")
async def emergency_routing(payload: dict):
    """Nearest ER / ambulance routing (haversine over local facility dir)."""
    try:
        data = routing_engine.route(
            float(payload["lat"]), float(payload["lon"]),
            payload.get("condition", "general"), payload.get("language", "en"),
        )
    except (KeyError, TypeError, ValueError):
        return ok(19, "Emergency Proximity Routing",
                  {"error": "Provide numeric 'lat' and 'lon'."})
    return ok(19, "Emergency Proximity Routing", data, risk_level="red",
              language=payload.get("language", "en"))


@router.post("/20/chat")
async def chat(payload: dict):
    data = chatbot_node.run(payload)
    return ok(20, "Multi-Language Chatbot Interface", data,
              risk_level=data.get("risk_level"),
              language=payload.get("language", "en"))
