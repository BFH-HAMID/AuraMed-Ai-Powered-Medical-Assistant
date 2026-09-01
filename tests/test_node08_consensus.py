"""Tests for Node 08 — Second Opinion & Dual-AI Consensus (production engine)."""
from __future__ import annotations

import asyncio

import pytest

from backend.core.schemas import RiskLevel
from backend.nodes.node_08_consensus.engine import ConsensusEngine
from backend.nodes.node_08_consensus.llm_clients import (
    HeuristicLocalLLM,
    ModelOpinion,
    scan_unverified_claims,
)
from backend.nodes.node_08_consensus.schemas import (
    ConsensusRequest,
    ConsensusState,
    DiagnosisCandidate,
)


def run_consensus(case_text: str, language: str = "en"):
    engine = ConsensusEngine(
        client_a=HeuristicLocalLLM(persona="A"),
        client_b=HeuristicLocalLLM(persona="B"),
    )
    return asyncio.run(
        engine.consult(ConsensusRequest(case_text=case_text, language=language))
    )


# ------------------------------------------------------------- red flags
def test_chest_pain_reaches_red_consensus_and_escalation():
    res = run_consensus(
        "Severe crushing chest pain, pressure, sweating, pain to left arm", "en"
    )
    assert res.risk_level == RiskLevel.RED
    assert res.opinions[0].primary_diagnosis == "acs"
    assert res.escalate_to_physician is True
    assert any("chest" in a.lower() or "ecg" in a.lower()
               for a in res.consensus_actions)


def test_stroke_bengali_red():
    res = run_consensus("মুখ বেঁকে গেছে, কথা জড়ানো, এক পাশ অবশ", "bn")
    assert res.risk_level == RiskLevel.RED
    assert any(o.primary_diagnosis == "stroke" for o in res.opinions)
    assert "স্ট্রোক" in res.rationale or "লাল" in res.rationale or "red" in res.rationale.lower()


# --------------------------------------------------------- agreement on URI
def test_common_cold_agreement_low_risk():
    # Multi-cue URI picture: both personas agree on the diagnosis key.
    res = run_consensus(
        "runny nose, sore throat, sneezing with mild cold and nasal congestion", "en"
    )
    assert res.state == ConsensusState.AGREEMENT
    assert res.opinions[0].primary_diagnosis == "uri"
    assert res.agreement_score >= 0.75
    assert isinstance(res.escalate_to_physician, bool)


def test_personas_independently_differ_on_yellow_threshold():
    # Single mild cue: sensitive persona A calls YELLOW, specific persona B stays GREEN.
    res = run_consensus("slight sore throat", "en")
    risks = {o.risk_level for o in res.opinions}
    assert RiskLevel.YELLOW in risks or res.state in (
        ConsensusState.PARTIAL, ConsensusState.DIVERGENCE
    )


# ------------------------------------------------------- single-model mode
def test_one_model_failure_degrades_to_single_model():
    class FailingModel(HeuristicLocalLLM):
        async def consult(self, *a, **k):
            raise RuntimeError("cloud unreachable")

    engine = ConsensusEngine(
        client_a=FailingModel(persona="A"),
        client_b=HeuristicLocalLLM(persona="B"),
    )
    res = asyncio.run(engine.consult(ConsensusRequest(case_text="fever and cough", language="en")))
    # The failed cloud model is transparently replaced by its local persona twin;
    # that degradation is flagged and forces physician escalation.
    assert res.local_fallback_used is True
    assert "fallback after error" in res.opinions[0].model_name
    assert res.escalate_to_physician is True


def test_both_models_fail_is_fail_state_and_safe(monkeypatch):
    class FailingModel(HeuristicLocalLLM):
        async def consult(self, *a, **k):
            raise RuntimeError("down")

    # Simulate a fully degraded edge node: cloud models AND local personas down.
    import backend.nodes.node_08_consensus.engine as engine_mod

    async def _boom(self, safe_text, ctype, lang):
        raise RuntimeError("local fallback also down")

    monkeypatch.setattr(engine_mod.HeuristicLocalLLM, "consult", _boom)

    engine = ConsensusEngine(client_a=FailingModel(persona="A"),
                             client_b=FailingModel(persona="B"))
    res = asyncio.run(engine.consult(ConsensusRequest(case_text="anything", language="en")))
    assert res.state == ConsensusState.FAILED
    # Fail-safe: never under-call risk when no model is available.
    assert res.risk_level in (RiskLevel.YELLOW, RiskLevel.RED)
    assert res.escalate_to_physician is True


# ---------------------------------------------------- hallucination guard
def test_specific_dose_claim_is_flagged():
    op = ModelOpinion(
        model_id="test", model_name="test",
        recommended_actions=["Give metoprolol 50 mg now and send home"],
    )
    warnings = scan_unverified_claims(op)
    assert warnings  # dosage claim caught


def test_named_drug_in_advice_is_flagged():
    op = ModelOpinion(
        model_id="test", model_name="test",
        recommended_actions=["Start warfarin without any monitoring"],
    )
    warnings = scan_unverified_claims(op)
    assert any("warfarin" in w for w in warnings)


def test_safe_advice_not_flagged():
    op = ModelOpinion(
        model_id="test", model_name="test",
        recommended_actions=["Rest, hydrate, monitor temperature twice daily."],
    )
    assert scan_unverified_claims(op) == []


# ------------------------------------------------------------- pii guard
def test_pii_is_anonymized_before_models():
    engine = ConsensusEngine(
        client_a=HeuristicLocalLLM(persona="A"),
        client_b=HeuristicLocalLLM(persona="B"),
    )

    captured = {}

    async def spy(case_text, ctype, lang):
        captured["text"] = case_text
        return await HeuristicLocalLLM(persona="A").consult(case_text, ctype, lang)

    engine.client_a.consult = spy  # type: ignore[method-assign]
    asyncio.run(engine.consult(ConsensusRequest(
        case_text="My name is Karim Mia, phone 01711223344, fever and cough", language="en")))
    assert "Karim" not in captured["text"]
    assert "01711223344" not in captured["text"]
    assert "REDACTED" in captured["text"]


# ------------------------------------------------------- disagreement test
def test_arbitration_scores_agree_and_differ():
    # Two identical opinions -> high agreement
    opt = ModelOpinion(
        model_id="a", model_name="a", primary_diagnosis="uri",
        differential=[DiagnosisCandidate(key="uri", label_en="URI", probability=0.8)],
        risk_level=RiskLevel.GREEN, confidence=0.9, red_flags=[],
        recommended_actions=["rest", "fluids"], rationale="",
    )
    opt2 = opt.model_copy(update={"model_id": "b", "model_name": "b"})

    class StubA(HeuristicLocalLLM):
        async def consult(self, *a, **k):
            return opt

    class StubB(HeuristicLocalLLM):
        async def consult(self, *a, **k):
            return opt2

    engine = ConsensusEngine(client_a=StubA(persona="A"), client_b=StubB(persona="B"))
    res = asyncio.run(engine.consult(ConsensusRequest(case_text="cold symptoms", language="en")))
    assert res.agreement_score == 1.0
    assert res.state == ConsensusState.AGREEMENT
