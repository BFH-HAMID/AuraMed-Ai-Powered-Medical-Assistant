"""LLM client adapters for Node 08.

Two kinds of client:

1. :class:`HTTPLLMClient` — calls an OpenAI-compatible ``/chat/completions``
   endpoint (any self-hosted clinical LLM: Llama-3-Med, Mistral-Med, GPT-class,
   local vLLM/Ollama gateway). Used when ``AURAMED_LLM_A_ENDPOINT`` /
   ``AURAMED_LLM_B_ENDPOINT`` are configured.

2. :class:`HeuristicLocalLLM` — a deterministic, auditable rule-based clinical
   reasoner that runs ON the edge device with no network and no model weights.
   It is deliberately transparent: every diagnosis probability derives from
   counted keyword evidence. Two personas (A = high-sensitivity, B =
   high-specificity) give the consensus engine genuine independent opinions to
   arbitrate. When an HTTP client is configured but unreachable (offline edge
   node), its persona twin runs as fallback.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from backend.config import REPO_ROOT, settings
from backend.core.schemas import RiskLevel
from backend.nodes.node_08_consensus.schemas import DiagnosisCandidate, ModelOpinion

# ---------------------------------------------------------------------------
# Lightweight clinical evidence catalog (bilingual). Probability heuristics
# are NOT diagnostic — they drive a decision-support consensus that always
# defers to the licensed physician.
# ---------------------------------------------------------------------------
_EVIDENCE: list[dict[str, Any]] = [
    {
        "key": "acs",
        "label_en": "Acute coronary syndrome (heart attack / angina)",
        "label_bn": "হৃদরোগ-সংকট (হার্ট অ্যাটাক/অ্যানজিনা)",
        "kw_en": ["chest pain", "chest pressure", "chest tightness", "pain to left arm",
                  "sweating", "breathlessness with chest", "heavy chest"],
        "kw_bn": ["বুকে ব্যথা", "বুকে চাপ", "বুকে কষ্ট", "বুক ব্যথা", "বাম বাহুতে ব্যথা", "ঘাম"],
        "red_flag": True,
        "actions": [
            "Emergency department activation; ECG within 10 minutes of arrival.",
            "Continuous monitoring, IV access, aspirin per emergency protocol after allergy check.",
            "Cardiology consultation; troponin series.",
        ],
    },
    {
        "key": "stroke",
        "label_en": "Acute stroke (FAST positive)",
        "label_bn": "স্ট্রোক",
        "kw_en": ["face droop", "facial droop", "slurred speech", "weakness on one side",
                  "one-sided weakness", "sudden numbness", "cannot speak", "sudden severe headache"],
        "kw_bn": ["মুখ বেঁকে", "মুখ বাঁকা", "কথা জড়ানো", "এক পাশ অবশ", "হাত-পা অবশ",
                  "কথা বলতে পারছি না", "হঠাৎ প্রচণ্ড মাথাব্যথা"],
        "red_flag": True,
        "actions": [
            "Emergency stroke pathway; note last-known-well time precisely.",
            "Urgent non-contrast CT brain; blood glucose; neurology/stroke team.",
            "Keep nil by mouth until swallow screen.",
        ],
    },
    {
        "key": "uri",
        "label_en": "Viral upper respiratory infection / common cold",
        "label_bn": "ভাইরাল সর্দি-কাশি",
        "kw_en": ["runny nose", "sore throat", "sneezing", "mild cough", "cold", "nasal congestion"],
        "kw_bn": ["সর্দি", "নাক দিয়ে পানি", "গলা ব্যথা", "হাঁচি", "হালকা কাশি", "নাক বন্ধ"],
        "red_flag": False,
        "actions": [
            "Supportive care: rest, warm fluids, saline gargle (see Node 23 home remedies).",
            "Antibiotics are not indicated without bacterial evidence.",
            "Reassess if fever >3 days, breathing difficulty or chest pain develops.",
        ],
    },
    {
        "key": "pneumonia",
        "label_en": "Lower respiratory infection / pneumonia",
        "label_bn": "নিউমোনিয়া / শ্বাসতন্ত্রের সংক্রমণ",
        "kw_en": ["fever with cough", "sputum", "shortness of breath", "chest pain when breathing",
                  "fast breathing", "cough days"],
        "kw_bn": ["কাশির সাথে জ্বর", "কফ", "শ্বাসকষ্ট", "শ্বাসে বুকে ব্যথা", "দ্রুত শ্বাস"],
        "red_flag": False,
        "actions": [
            "Clinical assessment with respiratory rate, oxygen saturation, temperature.",
            "Chest X-ray and CBC if moderate/severe; physician to decide on antibiotics.",
            "Urgent care if SpO2 <94%, blue lips, or inability to speak full sentences.",
        ],
    },
    {
        "key": "gastritis",
        "label_en": "Gastritis / GERD (functional dyspepsia)",
        "label_bn": "গ্যাস্ট্রাইটিস / অ্যাসিডিটি",
        "kw_en": ["acidity", "heartburn", "burning in stomach", "indigestion", "upper abdomen burning",
                  "belching"],
        "kw_bn": ["অ্যাসিডিটি", "বুক জ্বালা", "পেট জ্বালা", "বদহজম", "পেটে জ্বালা", "ঢেকুর"],
        "red_flag": False,
        "actions": [
            "Small meals; avoid lying down 2-3 hours after eating; reduce spicy/fried food.",
            "Red-flag check: chest pressure radiating to arm/jaw must be treated as cardiac until excluded.",
            "Physician review if symptoms persist >2 weeks or with black stools/weight loss.",
        ],
    },
    {
        "key": "diarrhea_dehydration",
        "label_en": "Acute gastroenteritis with dehydration risk",
        "label_bn": "তীব্র ডায়রিয়া / পানিশূন্যতা ঝুঁকি",
        "kw_en": ["watery diarrhea", "loose stool", "vomiting and diarrhea", "ors", "dehydration"],
        "kw_bn": ["পাতলা পায়খানা", "ডায়রিয়া", "বমি ও পায়খানা", "পানিশূন্যতা", "ডিহাইড্রেশন"],
        "red_flag": False,
        "actions": [
            "ORS after every loose stool; zinc for children under 5 per national protocol.",
            "Continue feeding; watch for bloody/black stool or no urine 6-8 hours.",
            "Urgent care for profuse rice-water stools or inability to drink (Node 02 red flag).",
        ],
    },
    {
        "key": "uti",
        "label_en": "Urinary tract infection",
        "label_bn": "মূত্রতন্ত্রের সংক্রমণ",
        "kw_en": ["burning urination", "frequent urination", "pain passing urine", "lower abdominal pain urine"],
        "kw_bn": ["প্রস্রাবে জ্বালা", "ঘন ঘন প্রস্রাব", "প্রস্রাবে ব্যথা", "প্রস্রাবের সময় ব্যথা"],
        "red_flag": False,
        "actions": [
            "Urinalysis and urine culture before antibiotics when feasible.",
            "Increase fluids; pregnancy or flank pain/fever requires urgent physician review.",
        ],
    },
    {
        "key": "hypertension",
        "label_en": "Hypertension / high blood pressure",
        "label_bn": "উচ্চ রক্তচাপ",
        "kw_en": ["high blood pressure", "headache with high bp", "dizziness bp", "hypertension"],
        "kw_bn": ["উচ্চ রক্তচাপ", "ব্লাড প্রেশার বেশি", "মাথা ঘোরা প্রেশার"],
        "red_flag": False,
        "actions": [
            "Repeat BP measurement after 5 minutes seated rest; confirm both arms.",
            "Emergency thresholds (e.g. ≥180/120 with chest pain, neuro symptoms) → emergency care.",
            "Medication review — do not self-start/stop antihypertensives.",
        ],
    },
    {
        "key": "diabetes",
        "label_en": "Diabetes-related presentation (hyper/hypoglycemia)",
        "label_bn": "ডায়াবেটিস-সম্পর্কিত উপস্থাপনা",
        "kw_en": ["excessive thirst", "frequent urination", "weight loss thirst", "sweating confusion diabetic",
                  "low sugar"],
        "kw_bn": ["বেশি পিপাসা", "বারবার প্রস্রাব", "সুগার কম", "ঘাম বিভ্রান্ত ডায়াবেটিস",
                  "ওজন কমা পিপাসা"],
        "red_flag": False,
        "actions": [
            "Check capillary/venous glucose immediately.",
            "If conscious and hypoglycemic: 15 g fast sugar, recheck in 15 min; if unconscious → emergency.",
            "Physician review for medication titration.",
        ],
    },
    {
        "key": "musculoskeletal",
        "label_en": "Musculoskeletal pain (back/joint)",
        "label_bn": "হাড়-পেশি/মেরুদণ্ড ব্যথা",
        "kw_en": ["back pain", "joint pain", "muscle pain", "sprain", "neck pain"],
        "kw_bn": ["কোমর ব্যথা", "হাঁটু ব্যথা", "পিঠে ব্যথা", "মাংসপেশি ব্যথা", "গাঁট ব্যথা"],
        "red_flag": False,
        "actions": [
            "Relative rest, gentle movement, local warmth/cold as comfortable.",
            "Red flags: trauma, weakness/numbness, loss of bladder control, fever → urgent care.",
            "Paracetamol per label; avoid NSAIDs in CKD/anticoagulant use (Node 05).",
        ],
    },
    {
        "key": "anaphylaxis",
        "label_en": "Anaphylaxis (severe allergic reaction)",
        "label_bn": "অ্যানাফাইল্যাক্সিস (মারাত্মক এলার্জি)",
        "kw_en": ["throat swelling", "tongue swelling", "hives breathing trouble", "face swelling sting"],
        "kw_bn": ["গলা ফুলে", "মুখ ফুলে", "শ্বাসকষ্টসহ লাল দানা", "কামড়ে ফোলা"],
        "red_flag": True,
        "actions": [
            "Adrenaline auto-injector if available (outer thigh); call emergency services.",
            "Lie flat with legs raised; do not stand/walk.",
        ],
    },
    {
        "key": "seizure_disorder",
        "label_en": "Seizure",
        "label_bn": "খিঁচুনি / মৃগী",
        "kw_en": ["seizure", "convulsion", "fits", "shaking episode"],
        "kw_bn": ["খিঁচুনি", "মৃগী", "ঝাঁকুনি", "টান ধরা"],
        "red_flag": True,
        "actions": [
            "Protect head, clear surroundings; do not restrain or put objects in mouth.",
            "Emergency if >5 minutes, repeated, injury, pregnancy, or first seizure.",
        ],
    },
]


def _count_hits(text_lower: str, kws: list[str]) -> int:
    return sum(1 for kw in kws if kw in text_lower)


# ===========================================================================
# Abstract client
# ===========================================================================
class LLMClient:
    model_id: str
    model_name: str

    async def consult(
        self, case_text: str, consultation_type: str, language: str
    ) -> ModelOpinion:  # pragma: no cover - interface
        raise NotImplementedError


# ===========================================================================
# Deterministic local reasoners (offline edge personas)
# ===========================================================================
@dataclass
class HeuristicLocalLLM(LLMClient):
    """Transparent rule-based persona. Sensitivity/specificity bias makes the
    two models genuinely independent so consensus arbitration is meaningful."""

    persona: str = "A"  # "A" = high sensitivity, "B" = high specificity

    def __post_init__(self) -> None:
        if self.persona == "A":
            self.model_id = "local-clinician-a"
            self.model_name = "Aura-Clinician-A (local, sensitivity-weighted)"
            self._prob_gain = 0.42          # per cue
            self._prob_base = 0.28
            self._mult = 1.12
            # Persona A raises low-risk complaints on 1 distinct benign evidence group
            self._yellow_groups_needed = 1
        else:
            self.model_id = "local-clinician-b"
            self.model_name = "Aura-Clinician-B (local, specificity-weighted)"
            self._prob_gain = 0.34
            self._prob_base = 0.18
            self._mult = 0.92
            # Persona B requires stronger benign evidence before YELLOW
            self._yellow_groups_needed = 2

    async def consult(
        self, case_text: str, consultation_type: str, language: str
    ) -> ModelOpinion:
        text = case_text.lower()
        candidates: list[DiagnosisCandidate] = []
        red_flags: list[str] = []
        actions: list[str] = []
        yellow_groups: list[str] = []

        for ev in _EVIDENCE:
            hits = _count_hits(text, ev["kw_en"]) + _count_hits(text, ev["kw_bn"])
            if hits == 0:
                continue
            raw = self._prob_base + self._prob_gain * hits
            # Specificity persona (B) discounts single-cue low-strength matches
            if self.persona == "B" and hits == 1 and not ev["red_flag"]:
                raw *= 0.75
            prob = round(min(0.97, raw * self._mult), 2)
            candidates.append(
                DiagnosisCandidate(
                    key=ev["key"],
                    label_en=ev["label_en"],
                    label_bn=ev["label_bn"],
                    probability=prob,
                )
            )
            # Red-flag catalog is SAFETY-CRITICAL and evidence-curated: a single
            # keyword hit is enough for BOTH personas (never down-weight danger).
            if ev["red_flag"]:
                red_flags.append(ev["key"])
                actions.extend(ev["actions"])
            else:
                yellow_groups.append(ev["key"])
                actions.extend(ev["actions"][:2])

        candidates.sort(key=lambda c: c.probability, reverse=True)

        # Triage risk — red flags are identical across personas; YELLOW threshold
        # is where the two independent models legitimately differ.
        if red_flags:
            risk = RiskLevel.RED
        elif len(yellow_groups) >= self._yellow_groups_needed:
            risk = RiskLevel.YELLOW
        else:
            risk = RiskLevel.GREEN

        primary = candidates[0].key if candidates else "undifferentiated"
        confidence = self._confidence(candidates, red_flags)

        rationale = self._rationale(candidates, risk, language)
        more_info = [
            "Vital signs: temperature, pulse, BP, respiratory rate, SpO2.",
            "Exact onset, duration and progression of symptoms.",
            "Current medications, allergies and relevant chronic conditions.",
        ]

        return ModelOpinion(
            model_id=self.model_id,
            model_name=self.model_name,
            primary_diagnosis=primary,
            differential=candidates[:5],
            risk_level=risk,
            confidence=confidence,
            red_flags=red_flags,
            recommended_actions=list(dict.fromkeys(actions))[:6],
            rationale=rationale,
            requests_more_info=more_info,
        )

    def _confidence(
        self, candidates: list[DiagnosisCandidate], red_flags: list[str]
    ) -> float:
        if not candidates:
            return 0.25 if self.persona == "A" else 0.35
        top = candidates[0].probability
        if self.persona == "A":
            # Sensitivity model: slightly less confident, but red flags spike it
            return round(min(0.9, 0.55 + 0.3 * top + (0.1 if red_flags else 0.0)), 2)
        return round(min(0.95, 0.6 + 0.35 * top + (0.05 if red_flags else 0.0)), 2)

    def _rationale(
        self, candidates: list[DiagnosisCandidate], risk: RiskLevel, language: str
    ) -> str:
        if not candidates:
            return (
                "Insufficient keyword evidence for any structured hypothesis; "
                "history-taking (Node 22) and vitals required."
                if language == "en"
                else "পর্যাপ্ত তথ্য নেই — লক্ষণ-ট্র্যাকার (Node 22) ও ভাইটাল প্রয়োজন।"
            )
        names = ", ".join(c.label_en for c in candidates[:3])
        if language == "bn":
            return f"প্রাপ্ত ভাষা-প্রমাণ অনুযায়ী সম্ভাব্য ক্রম: {names}। ঝুঁকি স্তর: {risk.value}।"
        return f"Evidence-weighted differential: {names}. Triage level: {risk.value}."


# ===========================================================================
# HTTP client (OpenAI-compatible) for real clinical LLMs
# ===========================================================================
_SYSTEM_PROMPT = (
    "You are a cautious clinical decision-support assistant. You NEVER replace "
    "a licensed physician. Respond ONLY with minified JSON of the form: "
    '{"primary_diagnosis": str, "differential": [{"key": str, "label_en": str, '
    '"probability": number}], "risk_level": "red|yellow|green", "confidence": '
    "number, \"red_flags\": [str], \"recommended_actions\": [str], "
    '"rationale": str, "requests_more_info": [str]}. Use only evidence present '
    "in the case. When uncertain, lower confidence and request more info."
)


@dataclass
class HTTPLLMClient(LLMClient):
    """Calls an OpenAI-compatible chat-completions endpoint with httpx."""

    endpoint: str
    api_key: str = ""
    model_name_hint: str = "clinical-llm"
    persona: str = "A"
    timeout: float = field(default_factory=lambda: settings.consensus_timeout)

    def __post_init__(self) -> None:
        self.model_id = f"http-clinician-{self.persona.lower()}"
        self.model_name = f"{self.model_name_hint} ({self.endpoint})"

    async def consult(
        self, case_text: str, consultation_type: str, language: str
    ) -> ModelOpinion:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": self.model_name_hint,
            "temperature": 0.2 if self.persona == "B" else 0.4,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": f"[{consultation_type} | lang={language}]\n{case_text}"},
            ],
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(self.endpoint, json=payload, headers=headers)
            resp.raise_for_status()
            body = resp.json()
        content = body["choices"][0]["message"]["content"]
        data = json.loads(content)
        return self._parse(data)

    def _parse(self, data: dict[str, Any]) -> ModelOpinion:
        risk_map = {"red": RiskLevel.RED, "yellow": RiskLevel.YELLOW, "green": RiskLevel.GREEN}
        diff = [
            DiagnosisCandidate(
                key=str(d.get("key", d.get("label_en", "?")))[:60],
                label_en=str(d.get("label_en", "?"))[:120],
                label_bn=str(d.get("label_bn", "")),
                probability=float(d.get("probability", 0.0)),
            )
            for d in data.get("differential", [])[:5]
        ]
        return ModelOpinion(
            model_id=self.model_id,
            model_name=self.model_name,
            primary_diagnosis=str(data.get("primary_diagnosis", ""))[:80],
            differential=diff,
            risk_level=risk_map.get(str(data.get("risk_level", "green")).lower(), RiskLevel.GREEN),
            confidence=float(data.get("confidence", 0.5)),
            red_flags=[str(x) for x in data.get("red_flags", [])],
            recommended_actions=[str(x) for x in data.get("recommended_actions", [])][:6],
            rationale=str(data.get("rationale", ""))[:800],
            requests_more_info=[str(x) for x in data.get("requests_more_info", [])],
        )


# Regex used by the hallucination guard: specific doses / drug names inside a
# model action string must be routed through the Drug Safety engine + physician.
_DOSE_RE = re.compile(r"\b\d+(?:\.\d+)?\s?(?:mg|mcg|ml|g|iu|tablet|capsule)\b", re.IGNORECASE)
from backend.nodes.node_05_drug_safety.knowledge import resolve_drug  # noqa: E402


def scan_unverified_claims(opinion: ModelOpinion) -> list[str]:
    """Hallucination guard (Node 08): flag specific medication/dosage advice
    that was NOT produced via the verified Drug Safety engine (Node 05).

    Such claims are surfaced as warnings and force physician escalation — the
    consensus engine never passes free-text dosing straight to a patient.
    """
    warnings: list[str] = []
    for action in opinion.recommended_actions:
        if _DOSE_RE.search(action):
            warnings.append(
                f"{opinion.model_id} emitted a specific dosage ('{action[:80]}…') — dosing must "
                "be validated by Node 05 and a licensed physician, not free-text LLM output."
            )
            continue
        # Detect raw drug names inside advice text.
        tokens = re.findall(r"[A-Za-z][A-Za-z\-]{4,}", action)
        for tok in tokens:
            key, _rec = resolve_drug(tok)
            if key:
                warnings.append(
                    f"{opinion.model_id} named medication '{tok}' in advice — route through the "
                    "Drug Safety check (Node 05) and physician review before use."
                )
                break
    return warnings
