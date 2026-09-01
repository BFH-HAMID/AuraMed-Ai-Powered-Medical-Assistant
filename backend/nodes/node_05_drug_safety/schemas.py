"""Node 05 request/response schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from backend.core.schemas import PatientContext, Severity


class MedicationInput(BaseModel):
    """A single medication on the prescription to be checked."""

    name: str = Field(..., description="Generic or brand name, English or Bengali")
    dose: str | None = Field(default=None, description="Free-text dose, e.g. '500 mg twice daily'")


class DrugSafetyRequest(BaseModel):
    medications: list[MedicationInput] = Field(
        ..., min_length=1, description="Proposed + current medications to cross-reference"
    )
    patient: PatientContext = Field(default_factory=PatientContext)
    language: Literal["en", "bn"] = "en"


class SafetyFinding(BaseModel):
    severity: Severity
    category: Literal[
        "drug_drug_interaction",
        "allergy",
        "renal",
        "cardiac",
        "pregnancy",
        "duplicate",
        "unknown_drug",
    ]
    drugs: list[str] = Field(default_factory=list)
    title_en: str
    title_bn: str = ""
    detail_en: str
    detail_bn: str = ""
    recommendation_en: str
    recommendation_bn: str = ""
    action: Literal["stop_and_review", "avoid", "monitor", "info"] = "info"


class DrugSafetyReport(BaseModel):
    overall_severity: Severity = Severity.INFO
    safe_to_proceed: bool = True
    escalate_to_physician: bool = False
    findings: list[SafetyFinding] = Field(default_factory=list)
    checked_medications: list[str] = Field(default_factory=list)
    unknown_medications: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    summary_en: str = ""
    summary_bn: str = ""
