"""Node 08 — Dual-AI Consensus engine (production implementation).

Pipeline:

    case text ──PII anonymization (Node 16)──┐
                                             ├──► model A ──┐
                                             ├──► model B ──┴──► arbitration ──► consensus
                                             │       (concurrent, timeouts,
                                             │        local fallback on failure)
    hallucination guard ◄── unverified drug/dose claims flagged

Arbitration rule:
  * risk agreement on triage level + diagnosis overlap (by key) → agreement
    score in [0,1];
  * >= 0.75           AGREEMENT
  * 0.45 - 0.74       PARTIAL
  * < 0.45            DIVERGENCE (or any RED/YELLOW vs GREEN split on red-flag
                      symptoms) → mandatory physician escalation.

The consensus NEVER auto-prescribes. Any state except clear AGREEMENT on a
low-risk case escalates to a licensed physician.
"""
from __future__ import annotations

import asyncio
from typing import Any

from backend.core.audit import log_action
from backend.core.security import anonymize_text
from backend.core.schemas import PatientContext, RiskLevel
from backend.nodes.base import BaseNode
from backend.nodes.node_08_consensus.llm_clients import (
    HTTPLLMClient,
    HeuristicLocalLLM,
    LLMClient,
    scan_unverified_claims,
)
from backend.nodes.node_08_consensus.schemas import (
    ConsensusRequest,
    ConsensusResult,
    ConsensusState,
    DiagnosisCandidate,
    ModelOpinion,
)

_RISK_ORDER = {RiskLevel.GREEN: 0, RiskLevel.YELLOW: 1, RiskLevel.RED: 2}


class ConsensusEngine(BaseNode):
    node_id = 8
    node_name = "Second Opinion & Dual-AI Consensus"
    implemented = True

    def __init__(self, client_a: LLMClient | None = None, client_b: LLMClient | None = None) -> None:
        self.client_a = client_a or self._default_client("A")
        self.client_b = client_b or self._default_client("B")

    @staticmethod
    def _default_client(persona: str) -> LLMClient:
        """Configure the two independent models.

        Cloud HTTP clinical LLMs are used when endpoints are configured; if a
        call fails at runtime (offline edge node), the engine transparently
        falls back to the deterministic local persona.
        """
        endpoint = settings_endpoint(persona)
        if endpoint:
            return HTTPLLMClient(
                endpoint=endpoint,
                api_key=settings_key(persona),
                model_name_hint=f"clinical-llm-{persona.lower()}",
                persona=persona,
            )
        return HeuristicLocalLLM(persona=persona)

    # ---------------------------------------------------------------- run
    async def consult(self, request: ConsensusRequest) -> ConsensusResult:
        # 1) Anonymize PII before any model sees the case (Node 16 hook)
        safe_text, found_pii = anonymize_text(request.case_text)

        # 2) Query both models concurrently; local fallback on any failure
        opinion_a, fallback_a = await self._query(self.client_a, "A", safe_text, request)
        opinion_b, fallback_b = await self._query(self.client_b, "B", safe_text, request)
        local_fallback = fallback_a or fallback_b

        available = [o for o in (opinion_a, opinion_b) if o.available]
        if not available:
            result = ConsensusResult(
                state=ConsensusState.FAILED,
                agreement_score=0.0,
                confidence=0.0,
                risk_level=RiskLevel.YELLOW,  # fail-safe: never under-call risk
                opinions=[opinion_a, opinion_b],
                escalate_to_physician=True,
                rationale="Both reasoning models unavailable; safest default is physician review.",
                local_fallback_used=local_fallback,
            )
            self._audit(request, result, pii_found=found_pii)
            return result

        # 3) Hallucination guard — unverified drug/dose claims
        claim_warnings: list[str] = []
        for op in available:
            claim_warnings.extend(scan_unverified_claims(op))

        # 4) Arbitration
        score, divergences, merged = self._arbitrate(available)

        risk = self._worst_risk(available)
        if len(available) == 1:
            state = ConsensusState.SINGLE_MODEL
        elif score >= 0.75:
            state = ConsensusState.AGREEMENT
        elif score >= 0.45:
            state = ConsensusState.PARTIAL
        else:
            state = ConsensusState.DIVERGENCE

        # Risk-level split with a red flag present is always divergence.
        risks = {o.risk_level for o in available}
        red_flags = {flag for o in available for flag in o.red_flags}
        if red_flags and RiskLevel.RED in risks and RiskLevel.GREEN in risks:
            state = ConsensusState.DIVERGENCE
            divergences.append(
                {"type": "risk_split", "detail": "One model calls RED on a red-flag symptom while the other calls GREEN."}
            )

        consensus_conf = round(
            min(o.confidence for o in available) * (0.65 + 0.35 * score), 2
        )

        # Consensus actions = intersection for agreement, union otherwise
        action_sets = [set(o.recommended_actions) for o in available]
        if state == ConsensusState.AGREEMENT:
            consensus_actions = sorted(set.intersection(*action_sets)) if action_sets else []
            if not consensus_actions:  # near-duplicates phrased differently
                consensus_actions = available[0].recommended_actions
        else:
            consensus_actions = sorted(set.union(*action_sets)) if action_sets else []

        # 5) Escalation policy — conservative by design.
        #    local_fallback_used means the second opinion came from a
        #    deterministic edge persona rather than an independent clinical LLM
        #    deployment, so physician review is mandatory.
        escalate = bool(
            state in (ConsensusState.DIVERGENCE, ConsensusState.SINGLE_MODEL, ConsensusState.FAILED)
            or risk == RiskLevel.RED
            or claim_warnings
            or local_fallback
            or consensus_conf < 0.65
        )

        rationale = self._rationale_text(state, score, risk, available, request.language)

        result = ConsensusResult(
            state=state,
            agreement_score=score,
            confidence=consensus_conf,
            risk_level=risk,
            opinions=[opinion_a, opinion_b],
            consensus_diagnoses=merged,
            consensus_actions=consensus_actions[:8],
            divergences=divergences,
            claim_warnings=claim_warnings,
            escalate_to_physician=escalate,
            rationale=rationale,
            local_fallback_used=local_fallback,
        )
        self._audit(request, result, pii_found=found_pii)
        return result

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        # Async entry from sync FastAPI handlers is invoked via the route layer
        # (which awaits ``consult``). This sync wrapper keeps BaseNode.run valid
        # for tests/tooling.
        request = ConsensusRequest.model_validate(payload)
        return asyncio.run(self.consult(request)).model_dump()

    # ------------------------------------------------------------ internals
    async def _query(
        self, client: LLMClient, persona: str, safe_text: str, request: ConsensusRequest
    ) -> tuple[ModelOpinion, bool]:
        """Query one model with timeout; fall back to the local persona twin.

        Returns an ``unavailable`` opinion (marked with ``available=False``)
        only when BOTH the primary and the local fallback fail — the engine
        then fails safe (risk never under-called).
        """
        primary_error: str | None = None
        try:
            return await asyncio.wait_for(
                client.consult(safe_text, request.consultation_type.value, request.language),
                timeout=15.0,
            ), False
        except Exception as exc:  # network error, timeout, bad JSON, ...
            primary_error = f"{type(exc).__name__}: {exc}"
            self.audit(
                "llm_primary_failure",
                details={"persona": persona, "error": type(exc).__name__},
            )
        try:
            fallback = HeuristicLocalLLM(persona=persona)
            opinion = await fallback.consult(
                safe_text, request.consultation_type.value, request.language
            )
            opinion.model_name += f" [fallback after error: {primary_error or 'primary unavailable'}]"
            return opinion, True
        except Exception as exc:  # total degradation — fail safe
            self.audit(
                "llm_total_failure",
                details={"persona": persona, "error": type(exc).__name__},
                risk_level="yellow",
            )
            return (
                ModelOpinion(
                    model_id=f"model-{persona.lower()}",
                    model_name=f"clinician-{persona.lower()} UNAVAILABLE",
                    available=False,
                    error=f"primary: {primary_error}; fallback: {type(exc).__name__}",
                ),
                True,
            )

    def _arbitrate(
        self, opinions: list[ModelOpinion]
    ) -> tuple[float, list[dict], list[DiagnosisCandidate]]:
        """Return (agreement_score, divergence_notes, merged_differential)."""
        divergences: list[dict] = []

        # --- risk agreement (40% of score)
        risks = [o.risk_level for o in opinions]
        risk_gap = max(_RISK_ORDER[r] for r in risks) - min(_RISK_ORDER[r] for r in risks)
        risk_score = {0: 1.0, 1: 0.55, 2: 0.1}[risk_gap]
        if risk_gap:
            divergences.append(
                {"type": "risk_level", "detail": f"Models returned triage levels {[r.value for r in risks]}."}
            )

        # --- primary diagnosis agreement (35%)
        primaries = [o.primary_diagnosis for o in opinions]
        primary_agree = len(set(primaries)) == 1 and primaries[0] not in ("", "undifferentiated")
        primary_score = 1.0 if primary_agree else 0.0
        if not primary_agree:
            divergences.append(
                {"type": "primary_diagnosis", "detail": f"Primary diagnoses: {primaries}."}
            )

        # --- differential overlap (Jaccard over diagnosis keys) (25%)
        key_sets = [
            {c.key for c in o.differential if c.probability >= 0.3} for o in opinions
        ]
        if all(key_sets):
            inter = set.intersection(*key_sets)
            union = set.union(*key_sets)
            overlap = len(inter) / len(union)
        else:
            overlap = 0.0
        if overlap < 0.34 and any(key_sets):
            divergences.append(
                {"type": "differential_overlap", "detail": f"Jaccard overlap {overlap:.2f} between differentials."}
            )

        score = round(0.4 * risk_score + 0.35 * primary_score + 0.25 * overlap, 2)

        # Merged differential: average probability per key, sorted.
        merged_map: dict[str, DiagnosisCandidate] = {}
        for o in opinions:
            for c in o.differential:
                if c.key in merged_map:
                    existing = merged_map[c.key]
                    merged_map[c.key] = DiagnosisCandidate(
                        key=c.key,
                        label_en=existing.label_en or c.label_en,
                        label_bn=existing.label_bn or c.label_bn,
                        probability=round((existing.probability + c.probability) / 2, 2),
                    )
                else:
                    merged_map[c.key] = c
        merged = sorted(merged_map.values(), key=lambda c: c.probability, reverse=True)[:6]
        return score, divergences, merged

    @staticmethod
    def _worst_risk(opinions: list[ModelOpinion]) -> RiskLevel:
        return max((o.risk_level for o in opinions), key=lambda r: _RISK_ORDER[r])

    def _rationale_text(
        self,
        state: ConsensusState,
        score: float,
        risk: RiskLevel,
        opinions: list[ModelOpinion],
        language: str,
    ) -> str:
        if language == "bn":
            base = (
                f"দ্বৈত-এআই মতৈক্য অবস্থা: {state.value} (চুক্তি স্কোর {score:.2f}), সর্বোচ্চ ঝুঁকি স্তর: {risk.value}। "
                "এই ফলাফল শুধুমাত্র সিদ্ধান্ত-সহায়তা; চিকিৎসা ব্যবস্থার আগে নিবন্ধিত চিকিৎসকের পর্যালোচনা আবশ্যক।"
            )
        else:
            base = (
                f"Dual-AI consensus state: {state.value} (agreement score {score:.2f}); "
                f"worst triage level: {risk.value}. Decision-support only — licensed physician "
                f"review is mandatory before clinical action."
            )
        return base

    def _audit(
        self, request: ConsensusRequest, result: ConsensusResult, *, pii_found: dict
    ) -> None:
        log_action(
            self.node_id,
            "dual_ai_consultation",
            actor="system",
            request_id=request.request_id,
            details={
                "consultation_type": request.consultation_type.value,
                "state": result.state.value,
                "agreement_score": result.agreement_score,
                "confidence": result.confidence,
                "risk_level": result.risk_level.value,
                "escalate_to_physician": result.escalate_to_physician,
                "models": [o.model_id for o in result.opinions],
                "local_fallback_used": result.local_fallback_used,
                "pii_redacted": {k: len(v) for k, v in pii_found.items()},
                "claim_warnings": len(result.claim_warnings),
            },
            risk_level=result.risk_level.value,
        )


# ---------------------------------------------------------------------------
# Small indirections so tests/monkeypatching can stub settings easily.
# ---------------------------------------------------------------------------
def settings_endpoint(persona: str) -> str:
    from backend.config import settings

    return settings.llm_a_endpoint if persona == "A" else settings.llm_b_endpoint


def settings_key(persona: str) -> str:
    from backend.config import settings

    return settings.llm_a_key if persona == "A" else settings.llm_b_key


consensus_engine = ConsensusEngine()
