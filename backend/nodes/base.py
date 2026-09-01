"""Base class for every AuraMed architecture node."""
from __future__ import annotations

from backend.core import audit
from backend.core.schemas import PatientContext


class BaseNode:
    """All 26 nodes inherit from this.

    Subclasses set ``node_id`` / ``node_name`` and implement :meth:`run`.
    Every run is written to the immutable audit trail (Node 26) and returns a
    payload that the API layer wraps in :class:`AuraMedResponse` (which always
    carries the mandatory physician-review disclaimer).
    """

    node_id: int = 0
    node_name: str = "base"
    implemented: bool = False

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:  # pragma: no cover
        raise NotImplementedError

    # -- audit helper --------------------------------------------------------
    def audit(
        self,
        action: str,
        *,
        actor: str = "system",
        request_id: str | None = None,
        details: dict | None = None,
        risk_level: str | None = None,
    ) -> dict:
        return audit.log_action(
            self.node_id,
            action,
            actor=actor,
            request_id=request_id,
            details=details,
            risk_level=risk_level,
        )


class StubNode(BaseNode):
    """Base for nodes whose heavy ML models run on GPU/edge nodes.

    Returns a complete, well-typed response that clearly states the model is
    in stub mode on this deployment, plus integration guidance — never a fake
    clinical result.
    """

    implemented = False
    integration: str = ""

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        language = (patient.language if patient else None) or payload.get("language", "en")
        return {
            "status": "stub",
            "message": (
                f"Node {self.node_id:02d} ({self.node_name}) is deployed in lightweight "
                f"mode. Attach the configured model/runtime to enable full functionality."
            ),
            "integration": self.integration,
            "received_fields": sorted(payload.keys()),
            "language": language,
        }
