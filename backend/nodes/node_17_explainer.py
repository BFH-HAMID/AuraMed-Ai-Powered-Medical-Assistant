"""Node 17 — Simplified Patient Explanation (NLG).

Translates medical jargon into plain, culturally relevant language. Deterministic
jargon glossary (bilingual) + readability rules: short sentences, local analogies
(e.g., heart = "the body's pump" / "শরীরের পাম্প").
"""
from __future__ import annotations

import re

from backend.core.audit import log_action
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode

_GLOSSARY: dict[str, dict[str, str]] = {
    "hypertension": {"en": "high blood pressure — when blood pushes too hard against the vessel walls, like a pipe under too much pressure",
                     "bn": "উচ্চ রক্তচাপ — যখন রক্তনালীতে রক্তের চাপ খুব বেশি থাকে, ঠিক যেমন বেশি চাপে থাকা পাইপ"},
    "myocardial infarction": {"en": "heart attack — when the heart's own blood supply is blocked",
                              "bn": "হার্ট অ্যাটাক — যখন হৃদপিণ্ডের নিজের রক্ত সরবরাহ বন্ধ হয়ে যায়"},
    "acute coronary syndrome": {"en": "a serious heart problem where the heart muscle is not getting enough blood",
                                "bn": "হৃদরোগের গুরুতর সমস্যা যেখানে হৃদপেশী যথেষ্ট রক্ত পায় না"},
    "pneumonia": {"en": "an infection that fills the air sacs of the lungs, making breathing harder",
                  "bn": "ফুসফুসের সংক্রমণ যাতে শ্বাস-থলি পানি/কফে ভরে যায়, শ্বাস নিতে কষ্ট হয়"},
    "gastroenteritis": {"en": "stomach bug — infection causing loose stools and vomiting",
                        "bn": "পেটের সংক্রমণ — পাতলা পায়খানা ও বমি হয়"},
    "ecg": {"en": "a painless tracing of the heart's electrical activity",
            "bn": "হৃদপিণ্ডের বৈদ্যুতিক কার্যকলাপের ব্যথাহীন রেকর্ড"},
    "troponin": {"en": "a blood test that checks whether the heart muscle has been injured",
                 "bn": "হৃদপেশী ক্ষতিগ্রস্ত হয়েছে কিনা দেখতে রক্ত পরীক্ষা"},
    "egfr": {"en": "a number showing how well the kidneys are cleaning the blood",
             "bn": "কিডনি রক্ত কত ভালোভাবে পরিষ্কার করছে তার সংখ্যা"},
    "ut i": {"en": "", "bn": ""},
    "uti": {"en": "urinary infection — germs in the urine tube, causing burning when passing urine",
            "bn": "প্রস্রাবের নালিতে জীবাণু — প্রস্রাবে জ্বালাপোড়া হয়"},
    "hba1c": {"en": "a blood test showing average sugar over about 3 months",
              "bn": "প্রায় ৩ মাসের গড় রক্তে সুগার দেখায় এমন রক্তপরীক্ষা"},
}


class ExplainerNode(BaseNode):
    node_id = 17
    node_name = "Simplified Patient Explanation"
    implemented = True

    def explain(self, medical_text: str, language: str = "en") -> dict:
        bn = language.startswith("bn")
        lowered = medical_text.lower()
        replacements = []
        for term, gloss in _GLOSSARY.items():
            if term in lowered and gloss["en"]:
                replacements.append({"term": term, "explanation": gloss["bn"] if bn else gloss["en"]})

        # Readability: split into short sentences; count.
        sentences = re.split(r"(?<=[.!?।])\s+", medical_text.strip())
        avg_len = round(sum(len(s.split()) for s in sentences) / max(1, len(sentences)), 1)

        plain = medical_text
        for rep in replacements:
            plain = re.sub(re.escape(rep["term"]), rep["explanation"], plain, flags=re.IGNORECASE)

        result = {
            "status": "ok",
            "language": language,
            "plain_version": plain,
            "glossed_terms": replacements,
            "readability": {
                "sentence_count": len(sentences),
                "avg_words_per_sentence": avg_len,
                "target": "short sentences (<15 words) for verbal/TTS delivery (Node 06)",
            },
        }
        log_action(self.node_id, "plain_explanation",
                   details={"terms_glossed": len(replacements), "language": language})
        return result

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        return self.explain(payload.get("medical_text", ""), payload.get("language", "en"))


explainer_node = ExplainerNode()
