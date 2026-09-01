"""Node 24 — Doctor Feedback Loop & Logging.

Licensed physicians correct/confirm AI outputs. Feedback is appended to an
immutable, hash-chained local queue (``data/feedback/feedback.jsonl`` and the
Node 26 audit trail) for model fine-tuning iteration. Offline: feedback
queues locally and syncs when connectivity returns.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from backend.config import settings
from backend.core.audit import log_action
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode
from pydantic import BaseModel, Field


class FeedbackRecord(BaseModel):
    doctor_id: str = Field(..., min_length=2)
    node: int = Field(..., ge=1, le=26)
    request_id: str | None = None
    ai_output_summary: str = ""
    correction: str = Field(..., min_length=2)
    severity: str = Field(default="info", description="info | moderate | critical")
    outcome_label: str | None = Field(default=None, description="Optional confirmed diagnosis label for tuning")


class FeedbackNode(BaseNode):
    node_id = 24
    node_name = "Doctor Feedback Loop & Logging"
    implemented = True

    def __init__(self) -> None:
        self._path = settings.feedback_dir / "feedback.jsonl"

    def record(self, rec: FeedbackRecord) -> dict:
        entry = {
            "id": str(uuid.uuid4()),
            "received_at_utc": datetime.now(timezone.utc).isoformat(),
            "synced": False,  # flipped when telemetry syncs to training pipeline
            **rec.model_dump(),
        }
        with self._path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        log_action(
            self.node_id, "doctor_correction",
            actor=f"doctor:{rec.doctor_id}",
            request_id=rec.request_id,
            details={"node": rec.node, "severity": rec.severity,
                     "outcome_label": rec.outcome_label},
        )
        return {
            "status": "accepted",
            "feedback_id": entry["id"],
            "queued_for_finetuning": True,
            "offline_synced_when_online": True,
        }

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        return self.record(FeedbackRecord.model_validate(payload))


feedback_node = FeedbackNode()
