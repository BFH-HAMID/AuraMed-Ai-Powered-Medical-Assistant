"""Node 08 request/response schemas."""
from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from backend.core.schemas import PatientContext, RiskLevel, Severity


class ConsultationType(str, Enum):
    TRIAGE = "triage"
    DIAGNOSIS_SUPPORT = "diagnosis_support"
    REPORT_SUMMARY = "report_summary"
    PRESCRIPTION_REVIEW = "prescription_review"


class ConsensusRequest(BaseModel):
    case_text: str = Field(
        ..., min_length=2, description="Free-text case: symptoms, history, findings (PII auto-anonymized)"
    )
    consultation_type: ConsultationType = ConsultationType.DIAGNOSIS_SUPPORT
    patient: PatientContext = Field(default_factory=PatientContext)
    language: Literal["en", "bn"] = "en"
    request_id: str | None = None


class DiagnosisCandidate(BaseModel):
    key: str
    label_en: str
    label_bn: str = ""
    probability: float = Field(ge=0.0, le=1.0)


class ModelOpinion(BaseModel):
    """Structured opinion returned by one clinical LLM."""

    model_id: str
    model_name: str
    available: bool = True
    error: str | None = None
    primary_diagnosis: str = ""
    differential: list[DiagnosisCandidate] = Field(default_factory=list)
    risk_level: RiskLevel = RiskLevel.GREEN
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    red_flags: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    rationale: str = ""
    requests_more_info: list[str] = Field(default_factory=list)


class ConsensusState(str, Enum):
    AGREEMENT = "agreement"      # models substantially agree
    PARTIAL = "partial"          # overlapping differentials / adjacent risk
    DIVERGENCE = "divergence"    # materially disagree → physician escalation
    SINGLE_MODEL = "single_model"  # one model unavailable
    FAILED = "failed"            # both models unavailable


class ConsensusResult(BaseModel):
    state: ConsensusState
    agreement_score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    risk_level: RiskLevel
    opinions: list[ModelOpinion]
    consensus_diagnoses: list[DiagnosisCandidate] = Field(default_factory=list)
    consensus_actions: list[str] = Field(default_factory=list)
    divergences: list[dict] = Field(default_factory=list)
    claim_warnings: list[str] = Field(default_factory=list)
    escalate_to_physician: bool = True
    rationale: str = ""
    local_fallback_used: bool = False
