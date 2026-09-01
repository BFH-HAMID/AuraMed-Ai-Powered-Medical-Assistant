"""Node 22 — Interactive Symptom Tracker (decision tree / flowchart).

A compact, auditable decision tree. Each step returns the next question plus
acceptable answer options; dangerous branches terminate in RED triage and
first-aid routing. Bengali/English. The tree is intentionally small and
explainable — clinicians can review every branch.
"""
from __future__ import annotations

from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode

# Flow: start -> chief -> red-flag screen -> duration -> severity -> advice tier
STEPS: dict[str, dict] = {
    "start": {
        "question_en": "What is the main problem today?",
        "question_bn": "আজকের প্রধান সমস্যা কী?",
        "options": ["chest_pain", "breathing", "fever", "stomach", "injury", "other"],
        "next": {
            "chest_pain": "redflag_chest",
            "breathing": "redflag_breath",
            "fever": "duration",
            "stomach": "stomach_detail",
            "injury": "injury_detail",
            "other": "redflag_screen",
        },
    },
    "redflag_chest": {
        "terminal": True, "risk_level": "red",
        "message_en": "Chest symptoms can be a heart attack. Call 999 now; see first-aid protocol 'chest_pain'.",
        "message_bn": "বুকের উপসর্গ হার্ট অ্যাটাক হতে পারে। এখনই ৯৯৯-এ কল করুন; 'chest_pain' প্রোটোকল দেখুন।",
        "first_aid": "chest_pain",
    },
    "redflag_breath": {
        "terminal": True, "risk_level": "red",
        "message_en": "Breathing difficulty is an emergency. Call 999 now; see protocol 'choking_breathing'.",
        "message_bn": "শ্বাসকষ্ট জরুরি অবস্থা। এখনই ৯৯৯-এ কল করুন; 'choking_breathing' প্রোটোকল দেখুন।",
        "first_aid": "choking_breathing",
    },
    "redflag_screen": {
        "question_en": "Do you have ANY of: fainting, one-sided weakness, severe bleeding, severe allergy swelling? (yes/no)",
        "question_bn": "এগুলোর কোনোটি কি আছে: অজ্ঞান, এক পাশ অবশ, প্রচণ্ড রক্তপাত, মারাত্মক ফোলা এলার্জি? (হ্যাঁ/না)",
        "options": ["yes", "no"],
        "next": {"yes": "terminal_red", "no": "duration"},
    },
    "terminal_red": {
        "terminal": True, "risk_level": "red",
        "message_en": "These are emergency warning signs. Call 999 or go to the nearest emergency department now.",
        "message_bn": "এগুলো জরুরি সতর্কতা সংকেত। এখনই ৯৯৯-এ কল করুন বা নিকটস্থ জরুরি বিভাগে যান।",
    },
    "duration": {
        "question_en": "How long has it lasted?",
        "question_bn": "কতক্ষণ/কতদিন ধরে আছে?",
        "options": ["hours", "1-2_days", "3+_days", "weeks"],
        "next": {"hours": "severity", "1-2_days": "severity", "3+_days": "yellow_visit", "weeks": "yellow_visit"},
    },
    "stomach_detail": {
        "question_en": "Is there black stool, blood in vomit, or severe abdominal pain? (yes/no)",
        "question_bn": "কালো পায়খানা, বমিতে রক্ত বা প্রচণ্ড পেট ব্যথা আছে? (হ্যাঁ/না)",
        "options": ["yes", "no"],
        "next": {"yes": "terminal_red", "no": "duration"},
    },
    "injury_detail": {
        "question_en": "Is there heavy bleeding, deformity, head injury with unconsciousness, or burns? (yes/no)",
        "question_bn": "প্রচণ্ড রক্তপাত, হাড় বাঁকা, মাথায় আঘাতে অজ্ঞান হওয়া বা পোড়া আছে? (হ্যাঁ/না)",
        "options": ["yes", "no"],
        "next": {"yes": "terminal_red", "no": "duration"},
    },
    "severity": {
        "question_en": "Is it mild (can do daily work), moderate (needs rest) or severe (cannot walk/talk normally)?",
        "question_bn": "সমস্যাটি হালকা (দৈনন্দিন কাজ করা যায়), মাঝারি (বিশ্রাম দরকার) না গুরুতর (স্বাভাবিক হাঁটা/কথা বলা যায় না)?",
        "options": ["mild", "moderate", "severe"],
        "next": {"mild": "green_home", "moderate": "yellow_visit", "severe": "yellow_visit"},
    },
    "yellow_visit": {
        "terminal": True, "risk_level": "yellow",
        "message_en": "Please seek medical care today at the nearest clinic. Use Node 15 test guidance and Node 19 routing.",
        "message_bn": "অনুগ্রহ করে আজই নিকটস্থ ক্লিনিকে চিকিৎসা সেবা নিন। Node 15 ও Node 19 ব্যবহার করুন।",
    },
    "green_home": {
        "terminal": True, "risk_level": "green",
        "message_en": "Low-risk presentation. Use verified home remedies (Node 23), monitor for warning signs, and seek care if worsening.",
        "message_bn": "কম ঝুঁকির উপস্থাপনা। যাচাইকৃত ঘরোয়া পরামর্শ (Node 23) নিন, সতর্কতা লক্ষণ খেয়াল রাখুন, অবনতি হলে সেবা নিন।",
    },
}


class SymptomTrackerNode(BaseNode):
    node_id = 22
    node_name = "Interactive Symptom Tracker"
    implemented = True

    def step(self, step_id: str = "start", answer: str | None = None, language: str = "en") -> dict:
        bn = language.startswith("bn")
        # Advance from the current step using the answer.
        current = STEPS.get(step_id)
        if current is None:
            return {"error": f"Unknown step '{step_id}'", "next_step": "start"}
        if answer and "next" in current:
            step_id = current["next"].get(answer, step_id)
            current = STEPS[step_id]

        if current.get("terminal"):
            return {
                "terminal": True,
                "risk_level": current["risk_level"],
                "message": current["message_bn"] if bn else current["message_en"],
                "first_aid": current.get("first_aid"),
            }
        return {
            "terminal": False,
            "step_id": step_id,
            "question": current["question_bn"] if bn else current["question_en"],
            "options": current["options"],
        }

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        return self.step(
            payload.get("step_id", "start"),
            payload.get("answer"),
            payload.get("language", "en"),
        )


symptom_tracker_node = SymptomTrackerNode()
