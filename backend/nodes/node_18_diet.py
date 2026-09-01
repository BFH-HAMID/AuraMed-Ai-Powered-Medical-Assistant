"""Node 18 — Diet & Lifestyle Guide Generator.

Personalized, region-aware (South Asian / Bengali plate) nutrition and
activity guidance tagged to diagnosis, age and risk bands. Culturally relevant
foods (rice, dal, fish, seasonal fruit) — not foreign diet plans.
"""
from __future__ import annotations

from backend.core.audit import log_action
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode

_PLANS: dict[str, dict] = {
    "hypertension": {
        "title_en": "DASH-style regional plan for high blood pressure",
        "title_bn": "উচ্চ রক্তচাপের জন্য আঞ্চলিক খাদ্যপরিকল্পনা",
        "diet_en": [
            "Salt under 1 teaspoon/day (5 g); avoid salted hilsa/achar/pappad during control phase.",
            "Half plate vegetables (lao, patrol, shak, cucumber), quarter rice, quarter dal/fish.",
            "Potassium foods: banana, kolmi shak, sweet potato — kidney patients check with doctor first.",
            "Tetul/tamarind paste, lemon, garlic paste instead of extra salt.",
        ],
        "diet_bn": [
            "লবণ দিনে ১ চা-চামচের (৫ গ্রাম) নিচে; নোনা ইলিশ/আচার/পাপড় নিয়ন্ত্রণের সময় এড়ান।",
            "অর্ধেক প্লেট সবজি (লাউ, পটোল, শাক, শসা), চতুর্থাংশ ভাত, চতুর্থাংশ ডাল/মাছ।",
            "পটাশিয়াম খাবার: কলা, কলমি শাক, মিষ্টি আলু — কিডনি রোগী আগে চিকিৎসককে জিজ্ঞেস করুন।",
            "বাড়তি লবণের বদলে তেঁতুল বাটা, লেবু, রসুন বাটা ব্যবহার করুন।",
        ],
        "activity_en": ["30 min brisk walk 5 days/week", "Waist target <90 cm (men) / <80 cm (women)"],
        "activity_bn": ["সপ্তাহে ৫ দিন ৩০ মিনিট দ্রুত হাঁটা", "কোমর <৯০ সেমি (পুরুষ) / <৮০ সেমি (মহিলা)"],
    },
    "diabetes": {
        "title_en": "Diabetes plate plan (low glycemic, regional)",
        "title_bn": "ডায়াবেটিসের প্লেট পরিকল্পনা (কম গ্লাইসেমিক, আঞ্চলিক)",
        "diet_en": [
            "Replace half the white rice with vegetables, dal and salad; red rice over polished rice.",
            "Avoid sugary tea, soft drinks, misti; one small whole fruit (jamrul, papaya, guava).",
            "Protein each meal: fish (small fish with bones), egg, chicken, dal, paneer.",
            "Never skip meals after insulin/sulfonylurea — keep fast sugar available (Node 14).",
        ],
        "diet_bn": [
            "সাদা ভাতের অর্ধেক সবজি, ডাল ও সালাদ দিয়ে বদলান; চালের ভাতের চেয়ে লাল চাল ভালো।",
            "চিনি-চা, কোমল পানীয়, মিষ্টি এড়ান; একটি ছোট পুরো ফল (জামরুল, পেঁপে, পেয়ারা)।",
            "প্রতি বেলায় প্রোটিন: ছোট মাছ, ডিম, মুরগি, ডাল, পনির।",
            "ইনসুলিন/সালফোনিলইউরিয়ার পর খাবার বাদ দেবেন না; দ্রুত চিনি হাতের কাছে রাখুন (Node 14)।",
        ],
        "activity_en": ["30 min walk after meals helps post-meal sugar", "150 min/week total activity"],
        "activity_bn": ["খাবারের পর ৩০ মিনিট হাঁটা প্রি-মিল সুগারে সাহায্য করে", "সপ্তাহে মোট ১৫০ মিনিট ব্যায়াম"],
    },
    "ckd": {
        "title_en": "Kidney-conscious eating",
        "title_bn": "কিডনি-সচেতন খাদ্য",
        "diet_en": [
            "Protein per physician advice (do not self-restrict excessively).",
            "Salt control; avoid packet soups/sauces and salt-preserved fish.",
            "Potassium restrictions (banana, coconut water, tomatoes) ONLY if blood tests show high potassium.",
        ],
        "diet_bn": [
            "প্রোটিন চিকিৎসকের পরামর্শে (নিজে থেকে অতিরিক্ত কমাবেন না)।",
            "লবণ নিয়ন্ত্রণ; প্যাকেট স্যুপ/সস ও নোনা মাছ এড়ান।",
            "পটাশিয়াম সীমাবদ্ধতা (কলা, ডাবের পানি, টমেটো) শুধুমাত্র রক্তপরীক্ষায় পটাশিয়াম বেশি হলে।",
        ],
        "activity_en": ["Light daily activity as tolerated"],
        "activity_bn": ["সহনশীল দৈনিক হালকা ব্যায়াম"],
    },
    "general": {
        "title_en": "Everyday healthy plate",
        "title_bn": "প্রতিদিনের স্বাস্থ্যকর প্লেট",
        "diet_en": [
            "Half plate seasonal vegetables and fruit, quarter staple (rice/roti), quarter protein (dal/fish/egg).",
            "Boiled/curried over fried; reuse cooking oil sparingly.",
            "Safe water; 6-8 glasses daily unless fluid-restricted by a doctor.",
        ],
        "diet_bn": [
            "অর্ধেক প্লেট মৌসুমি সবজি-ফল, চতুর্থাংশ শস্য (ভাত/রুটি), চতুর্থাংশ প্রোটিন (ডাল/মাছ/ডিম)।",
            "ভাজার চেয়ে সিদ্ধ/ঝোল; রান্নার তেল বারবার ব্যবহার এড়ান।",
            "নিরাপদ পানি; চিকিৎসকের পানি-নিষেধ না থাকলে দিনে ৬-৮ গ্লাস।",
        ],
        "activity_en": ["150-300 min/week moderate activity", "Tobacco/alcohol cessation support"],
        "activity_bn": ["সপ্তাহে ১৫০-৩০০ মিনিট মাঝারি ব্যায়াম", "ধূমপান/মদ্যপান বর্জনে সহায়তা নিন"],
    },
}


class DietLifestyleNode(BaseNode):
    node_id = 18
    node_name = "Diet & Lifestyle Guide Generator"
    implemented = True

    def generate(self, diagnosis: str = "general", age_years: float | None = None,
                 language: str = "en") -> dict:
        key = diagnosis.lower()
        plan_key = next((k for k in _PLANS if k in key), "general")
        p = _PLANS[plan_key]
        bn = language.startswith("bn")
        result = {
            "status": "ok",
            "plan_key": plan_key,
            "title": p["title_bn"] if bn else p["title_en"],
            "diet": p["diet_bn"] if bn else p["diet_en"],
            "activity": p["activity_bn"] if bn else p["activity_en"],
            "age_adjustment": (
                ("Add calcium/dairy and soft-cooked foods for older adults; dental-friendly choices."
                 if age_years and age_years >= 65 else
                 "Growth-stage patients: ensure adequate protein and three meals + snacks."
                 if age_years and age_years < 18 else "")
            ),
        }
        log_action(self.node_id, "diet_plan", details={"plan": plan_key})
        return result

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        age = payload.get("age_years") or (patient.age_years if patient else None)
        return self.generate(
            payload.get("diagnosis", "general"),
            age,
            payload.get("language", "en"),
        )


diet_node = DietLifestyleNode()
