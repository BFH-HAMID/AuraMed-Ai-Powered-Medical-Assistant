"""API routes — layer 3: Risk Assessment & Diagnostics (Nodes 11-15)."""
from __future__ import annotations

from fastapi import APIRouter

from backend.core.schemas import ok
from backend.nodes.node_11_risk_score import risk_predictor_node
from backend.nodes.node_12_leaflets import leaflet_node
from backend.nodes.node_13_guidelines import guidelines_node
from backend.nodes.node_14_first_aid.engine import first_aid_engine
from backend.nodes.node_15_lab_tests import lab_tests_node

router = APIRouter(prefix="/api/v1", tags=["3. Risk Assessment & Diagnostics"])


@router.post("/11/risk-score")
async def risk_scores(payload: dict):
    return ok(11, "Health Risk Predictor Score", risk_predictor_node.run(payload))


@router.post("/12/leaflet")
async def medicine_leaflet(payload: dict):
    return ok(12, "Medicine-Related Documentation", leaflet_node.run(payload),
              language=payload.get("language", "en"))


@router.post("/13/guidelines/draft")
async def guideline_draft(payload: dict):
    return ok(13, "Prescription & Guidelines Engine", guidelines_node.run(payload),
              language=payload.get("language", "en"))


@router.get("/14/first-aid")
async def list_first_aid(language: str = "en"):
    return ok(14, "First Aid & Emergency Guidebook",
              {"protocols": first_aid_engine.list_protocols(language)}, language=language)


@router.post("/14/first-aid/lookup")
async def first_aid_lookup(payload: dict):
    if payload.get("protocol_id"):
        data = first_aid_engine.get_protocol(payload["protocol_id"], payload.get("language", "en"))
    else:
        data = first_aid_engine.search(payload.get("query", ""), payload.get("language", "en"))
    return ok(14, "First Aid & Emergency Guidebook", data,
              risk_level="red", language=payload.get("language", "en"))


@router.post("/15/lab-tests")
async def lab_test_recommendations(payload: dict):
    return ok(15, "Lab Test Recommendations", lab_tests_node.run(payload),
              language=payload.get("language", "en"))
