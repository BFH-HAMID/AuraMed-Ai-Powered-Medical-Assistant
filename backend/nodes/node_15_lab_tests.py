"""Node 15 — Lab Test Recommendations.

Rule-based suggestion of diagnostic tests from presenting symptoms +
preliminary findings. Conservative: suggests first-line investigations only,
bilingual output.
"""
from __future__ import annotations

from backend.core.audit import log_action
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode

_TEST_RULES: list[tuple[tuple[str, ...], list[dict]]] = [
    (("fever", "জ্বর"), [
        {"test": "CBC with differential", "rationale_en": "Infection/inflammation screen", "rationale_bn": "সংক্রমণ/প্রদাহ যাচাই"},
        {"test": "Malaria + dengue rapid test (endemic season)", "rationale_en": "Regional fever pathogens", "rationale_bn": "আঞ্চলিক জ্বরের কারণ"},
        {"test": "Urine routine", "rationale_en": "Occult UTI", "rationale_bn": "মূত্রতন্ত্র সংক্রমণ"},
    ]),
    (("cough", "কাশি", "breath", "শ্বাস"), [
        {"test": "Chest X-ray", "rationale_en": "Pneumonia/TB screen if persistent", "rationale_bn": "নিউমোনিয়া/টিবি যাচাই"},
        {"test": "SpO2 + respiratory rate", "rationale_en": "Oxygenation assessment", "rationale_bn": "অক্সিজেন অবস্থা"},
    ]),
    (("chest pain", "বুকে ব্যথা", "বুকে চাপ"), [
        {"test": "ECG (12-lead) within 10 minutes", "rationale_en": "Acute coronary syndrome", "rationale_bn": "হৃদরোগ-সংকট যাচাই"},
        {"test": "High-sensitivity troponin serial", "rationale_en": "Myocardial injury", "rationale_bn": "হৃদপেশী ক্ষতি"},
    ]),
    (("diarrhea", "পাতলা পায়খানা", "ডায়রিয়া"), [
        {"test": "Dehydration assessment + ORS", "rationale_en": "Severity guide", "rationale_bn": "তীব্রতা নির্ধারণ"},
        {"test": "Stool microscopy/culture if bloody or >3 days", "rationale_en": "Bacterial/dysentery", "rationale_bn": "ব্যাকটেরিয়া/রক্ত আম"},
    ]),
    (("urine", "প্রস্রাব", "burning"), [
        {"test": "Urinalysis + culture", "rationale_en": "UTI confirmation & antibiotic choice", "rationale_bn": "ইউটিআই নিশ্চিতকরণ"},
    ]),
    (("glucose", "সুগার", "thirst", "পিপাসা"), [
        {"test": "Fasting/2h glucose + HbA1c", "rationale_en": "Diabetes diagnosis/control", "rationale_bn": "ডায়াবেটিস নির্ণয়/নিয়ন্ত্রণ"},
    ]),
    (("dizziness", "মাথা ঘোরা", "bp"), [
        {"test": "Blood pressure both arms (lying/standing)", "rationale_en": "Hypertension/orthostasis", "rationale_bn": "রক্তচাপ যাচাই"},
        {"test": "ECG", "rationale_en": "Arrhythmia screen", "rationale_bn": "হৃদছন্দ সমস্যা"},
    ]),
]


class LabTestNode(BaseNode):
    node_id = 15
    node_name = "Lab Test Recommendations"
    implemented = True

    def recommend(self, symptoms_text: str, language: str = "en") -> dict:
        text = symptoms_text.lower()
        tests: list[dict] = []
        matched = []
        for keywords, test_list in _TEST_RULES:
            if any(k in text for k in keywords):
                matched.append(keywords[0])
                for t in test_list:
                    if t["test"] not in {x["test"] for x in tests}:
                        tests.append(t)
        bn = language.startswith("bn")
        result = {
            "status": "ok",
            "matched_symptom_groups": matched,
            "recommended_tests": [
                {"test": t["test"], "rationale": t["rationale_bn"] if bn else t["rationale_en"]}
                for t in tests
            ],
            "note_en": "Investigations are suggestions for the treating clinician; history/exam findings guide final selection.",
            "note_bn": "পরীক্ষাগুলো চিকিৎসকের জন্য পরামর্শ; চূড়ান্ত নির্বাচন রোগের ইতিহাস ও পরীক্ষার ওপর নির্ভরশীল।",
        }
        log_action(self.node_id, "lab_test_recommendation",
                   details={"groups": matched, "tests": len(tests)})
        return result

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        return self.recommend(payload.get("symptoms_text", ""), payload.get("language", "en"))


lab_tests_node = LabTestNode()
