"""API routes — the downloadable AuraMed patient report pack.

``POST /api/v1/report/patient``          → the report as JSON (for the web UI)
``POST /api/v1/report/patient/download`` → the same report as a self-contained,
                                           printable HTML file (Save as PDF)
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from backend.core.report_html import render_patient_report
from backend.core.report_pack import (
    REPORT_NODE_ID,
    PatientReportRequest,
    build_patient_report,
    report_filename,
)
from backend.core.schemas import ok

router = APIRouter(prefix="/api/v1", tags=["6. Patient Report Pack"])


@router.post("/report/patient")
async def patient_report_json(request: PatientReportRequest):
    """Compose the full report pack (patient data + meds + advice + diet)."""
    report = build_patient_report(request)
    return ok(
        REPORT_NODE_ID, "Patient Report Pack", report,
        risk_level=report["risk_level"],
        alerts=[{"requires_physician_review": True}],
        language=request.language,
    )


@router.post("/report/patient/download")
async def patient_report_download(request: PatientReportRequest):
    """Same report as a downloadable, print-ready HTML document.

    The disclaimer travels inside the document (top banner + footer) as well as
    in the ``X-AuraMed-Disclaimer`` header added by the gateway middleware.
    """
    report = build_patient_report(request)
    filename = report_filename(report)
    return HTMLResponse(
        content=render_patient_report(report),
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-AuraMed-Report-Id": report["report_id"],
            "X-AuraMed-Risk-Level": report["risk_level"],
        },
    )
