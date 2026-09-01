"""Node 09 — Patient History & Vitals Integration.

Structured ingestion of historical EHR data, baseline vitals and family
history. In production this connects to PostgreSQL (SQLAlchemy) / FHIR R4
endpoints; the local mode validates and normalizes a structured JSON payload
and builds the unified patient timeline used by downstream nodes.
"""
from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field

from backend.core.audit import log_action
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode


class VitalsRecord(BaseModel):
    date: str = Field(default_factory=lambda: date.today().isoformat())
    sbp: float | None = None
    dbp: float | None = None
    hr: float | None = None
    temp_c: float | None = None
    spo2: float | None = None
    weight_kg: float | None = None
    height_cm: float | None = None
    glucose_mg_dl: float | None = None
    notes: str = ""


class HistoryEvent(BaseModel):
    date: str
    event: str
    details: str = ""


class EHRPayload(BaseModel):
    patient: PatientContext
    vitals: list[VitalsRecord] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    medications: list[str] = Field(default_factory=list)
    family_history: list[str] = Field(default_factory=list)
    events: list[HistoryEvent] = Field(default_factory=list)


class EHRIntegrationNode(BaseNode):
    node_id = 9
    node_name = "Patient History & Vitals Integration"
    implemented = True

    def ingest(self, payload: EHRPayload) -> dict:
        vitals = sorted(payload.vitals, key=lambda v: v.date)
        latest = vitals[-1] if vitals else None
        bmi = None
        if latest and latest.weight_kg and latest.height_cm:
            h_m = latest.height_cm / 100.0
            bmi = round(latest.weight_kg / (h_m * h_m), 1)

        # Merge conditions/meds into the patient context for downstream nodes.
        merged_conditions = sorted(set(payload.patient.conditions + payload.conditions))
        merged_meds = sorted(set(payload.patient.current_medications + payload.medications))

        timeline = [
            {"date": e.date, "event": e.event, "details": e.details} for e in payload.events
        ] + [{"date": v.date, "event": "vitals_recorded",
              "details": f"BP {v.sbp}/{v.dbp}, SpO2 {v.spo2}, HR {v.hr}"} for v in vitals]
        timeline.sort(key=lambda x: x["date"])

        log_action(
            self.node_id, "ehr_ingest",
            details={"vitals": len(payload.vitals), "events": len(payload.events),
                     "conditions": len(merged_conditions), "bmi": bmi},
        )
        return {
            "status": "ok",
            "patient_id": payload.patient.patient_id,
            "bmi": bmi,
            "latest_vitals": latest.model_dump() if latest else None,
            "merged_conditions": merged_conditions,
            "merged_medications": merged_meds,
            "family_history": payload.family_history,
            "timeline": timeline,
            "storage_note": "Structured records persist to PostgreSQL via SQLAlchemy/FHIR in full deployment.",
        }

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        return self.ingest(EHRPayload.model_validate(payload))


ehr_node = EHRIntegrationNode()
