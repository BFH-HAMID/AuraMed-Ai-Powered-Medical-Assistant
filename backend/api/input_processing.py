"""API routes — layer 1: Input & Initial Processing (Nodes 01-07)."""
from __future__ import annotations

from fastapi import APIRouter

from backend.core.schemas import fail, ok
from backend.nodes.node_01_audio_stt import audio_stt_node
from backend.nodes.node_02_triage.engine import triage_engine
from backend.nodes.node_02_triage.schemas import TriageRequest
from backend.nodes.node_03_reader import custom_reader_node
from backend.nodes.node_04_ocr import handwriting_ocr_node
from backend.nodes.node_05_drug_safety.engine import drug_safety_engine
from backend.nodes.node_05_drug_safety.schemas import DrugSafetyRequest
from backend.nodes.node_06_tts import tts_node
from backend.nodes.node_07_reports import report_comparison_node

router = APIRouter(prefix="/api/v1", tags=["1. Input & Initial Processing"])


@router.post("/01/stt")
async def speech_to_text(payload: dict):
    return ok(1, "Audio Processing & Regional Language STT", audio_stt_node.run(payload))


@router.post("/02/triage")
async def triage(request: TriageRequest):
    result = triage_engine.triage(request)
    data = result.model_dump()
    return ok(
        2, "Emergency Triage & Red Flag Detection", data,
        risk_level=result.risk_level, confidence=result.confidence,
        alerts=[{"red_flags": [f["id"] for f in data["matched_red_flags"]]}],
        language=request.language,
    )


@router.post("/03/reader")
async def read_document(payload: dict):
    return ok(3, "Custom Reader & Processing", custom_reader_node.run(payload))


@router.post("/04/ocr/prescription")
async def prescription_ocr(payload: dict):
    return ok(4, "Handwritten Prescription OCR Engine", handwriting_ocr_node.run(payload))


@router.post("/05/drug-safety")
async def drug_safety(request: DrugSafetyRequest):
    """PRODUCTION — Node 05: full drug-drug / allergy / renal / cardiac check."""
    report = drug_safety_engine.check(request)
    data = report.model_dump()
    return ok(
        5, "Drug Safety & Allergy Check", data,
        risk_level=("red" if not report.safe_to_proceed else None),
        confidence=report.confidence,
        alerts=[{"hard_stop": not report.safe_to_proceed}] if not report.safe_to_proceed else [],
        language=request.language,
    )


@router.post("/06/tts")
async def text_to_speech(payload: dict):
    return ok(6, "Text-to-Speech Output", tts_node.run(payload),
              language=payload.get("language", "en"))


@router.post("/07/report-comparison")
async def compare_reports(payload: dict):
    return ok(7, "Multi-Source Report Comparison", report_comparison_node.run(payload))
