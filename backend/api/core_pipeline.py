"""API routes — layer 2: Core AI & Data Pipeline (Nodes 08-10)."""
from __future__ import annotations

from fastapi import APIRouter

from backend.core.schemas import ok
from backend.nodes.node_08_consensus.engine import consensus_engine
from backend.nodes.node_08_consensus.schemas import ConsensusRequest
from backend.nodes.node_09_ehr import ehr_node
from backend.nodes.node_10_synthesis import synthesis_node

router = APIRouter(prefix="/api/v1", tags=["2. Core AI & Data Pipeline"])


@router.post("/08/consensus")
async def dual_ai_consensus(request: ConsensusRequest):
    """PRODUCTION — Node 08: dual clinical LLM consensus with arbitration.

    Runs both models concurrently (HTTP clinical LLMs when configured,
    deterministic local personas otherwise), anonymizes the case first,
    verifies claims, and escalates to a physician on divergence / red flags.
    """
    result = await consensus_engine.consult(request)
    data = result.model_dump()
    return ok(
        8, "Second Opinion & Dual-AI Consensus", data,
        risk_level=result.risk_level,
        confidence=result.confidence,
        alerts=[
            {"escalate_to_physician": result.escalate_to_physician},
            {"state": result.state.value},
        ] + [{"claim_warning": w} for w in result.claim_warnings],
        language=request.language,
    )


@router.post("/09/ehr")
async def ehr_ingest(payload: dict):
    return ok(9, "Patient History & Vitals Integration", ehr_node.run(payload))


@router.post("/10/synthesis")
async def synthesize(payload: dict):
    return ok(10, "Data Synthesis & Preparation", synthesis_node.run(payload),
              language=payload.get("language", "en"))
