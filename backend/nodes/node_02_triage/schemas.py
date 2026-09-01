"""Node 02 request/response schemas."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class TriageRequest(BaseModel):
    symptoms_text: str = Field(..., min_length=2, description="Free-text symptoms (English or Bengali)")
    vitals: dict[str, float] = Field(
        default_factory=dict,
        description="Optional vitals, e.g. {'spo2': 91, 'sbp': 85, 'hr': 120, 'temp_c': 39.2, 'rr': 28}",
    )
    language: Literal["en", "bn"] = "en"


class TriageResult(BaseModel):
    risk_level: Literal["red", "yellow", "green"]
    matched_red_flags: list[dict] = Field(default_factory=list)
    yellow_flag_hits: list[str] = Field(default_factory=list)
    possible_conditions: list[str] = Field(default_factory=list)
    first_aid_protocol_ids: list[str] = Field(default_factory=list)
    immediate_advice_en: str
    immediate_advice_bn: str
    emergency_number: str = "999"
    confidence: float
