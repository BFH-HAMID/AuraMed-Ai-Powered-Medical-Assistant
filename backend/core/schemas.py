"""Common Pydantic v2 API schemas shared by all 26 AuraMed nodes."""
from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, Field

from backend.core.disclaimer import get_disclaimer

# ---------------------------------------------------------------------------
# Multilingual support (Node 20): 'en' English, 'bn' Bengali (বাংলা)
# ---------------------------------------------------------------------------
Language = Literal["en", "bn"]


class RiskLevel(str, Enum):
    """Triage / risk stratification levels (Nodes 02, 11)."""

    RED = "red"        # life-threatening — immediate emergency care
    YELLOW = "yellow"  # urgent — care within hours
    GREEN = "green"    # low-risk — routine / conservative management


class Severity(str, Enum):
    """Severity of a safety finding (Node 05) or consensus issue (Node 08)."""

    CRITICAL = "critical"
    HIGH = "high"
    MODERATE = "moderate"
    LOW = "low"
    INFO = "info"


T = TypeVar("T")


class PatientContext(BaseModel):
    """Minimal patient profile used by safety-sensitive nodes (05, 08, 11…).

    All fields optional so triage can run on anonymous walk-in patients.
    """

    patient_id: str | None = Field(default=None, description="Anonymized patient identifier")
    age_years: float | None = None
    sex: Literal["male", "female", "other", "unknown"] = "unknown"
    weight_kg: float | None = None
    allergies: list[str] = Field(default_factory=list, description="Drug / class allergy names")
    conditions: list[str] = Field(default_factory=list, description="Known diagnoses, e.g. 'cKD', 'long QT'")
    current_medications: list[str] = Field(default_factory=list, description="Active prescriptions")
    renal_egfr: float | None = Field(default=None, description="eGFR mL/min/1.73m² (Node 05 renal check)")
    hepatic_impairment: bool = False
    pregnant: bool = False
    language: Language = "en"


class AuraMedResponse(BaseModel, Generic[T]):
    """**Envelope for every API response** — the disclaimer is mandatory and
    cannot be omitted (Implementation Directive #2)."""

    success: bool = True
    node: int = Field(..., description="Architecture node number (1-26)")
    node_name: str
    risk_level: RiskLevel | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    data: T | dict[str, Any] = Field(default_factory=dict)
    alerts: list[dict[str, Any]] = Field(
        default_factory=list, description="Hard safety alerts / red flags (always English-keyed)"
    )
    disclaimer: str = ""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    offline: bool = False
    language: Language = "en"

    def model_post_init(self, __context: Any) -> None:
        # Never allow an empty disclaimer to leave the service.
        if not self.disclaimer:
            self.disclaimer = get_disclaimer(self.language)


def ok(
    node: int,
    node_name: str,
    data: Any = None,
    *,
    risk_level: RiskLevel | None = None,
    confidence: float = 0.0,
    alerts: list[dict[str, Any]] | None = None,
    language: Language = "en",
    offline: bool = False,
) -> dict[str, Any]:
    """Convenience builder for a success envelope (plain dict for FastAPI)."""
    payload = AuraMedResponse(
        node=node,
        node_name=node_name,
        data=data if data is not None else {},
        risk_level=risk_level,
        confidence=confidence,
        alerts=alerts or [],
        language=language,
        offline=offline,
    )
    return payload.model_dump()


def fail(
    node: int,
    node_name: str,
    error: str,
    *,
    language: Language = "en",
    offline: bool = False,
) -> dict[str, Any]:
    """Error envelope — still carries the mandatory disclaimer."""
    payload = AuraMedResponse(
        success=False,
        node=node,
        node_name=node_name,
        data={"error": error},
        confidence=0.0,
        language=language,
        offline=offline,
    )
    return payload.model_dump()
