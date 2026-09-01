"""Lightweight i18n: English ↔ Bengali (বাংলা) strings for patient-facing
output (Nodes 06, 17, 20, 23). Medical terminology keeps the English/brand
name alongside the Bengali so clinicians are never confused.
"""
from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "welcome": "Hello, I am AuraMed, your medical assistant. How can I help you today?",
        "emergency_advice": "This may be an emergency. Please go to the nearest emergency department or call the emergency number immediately.",
        "emergency_number": "999",
        "first_aid_title": "First Aid Instructions",
        "remedies_title": "Safe home care tips",
        "see_doctor": "Please consult a licensed physician if symptoms worsen or persist.",
        "no_diagnosis": "AuraMed cannot replace a doctor's diagnosis.",
        "risk_red": "HIGH RISK — emergency care required now",
        "risk_yellow": "MODERATE RISK — seek medical care today",
        "risk_green": "LOW RISK — home care with monitoring",
    },
    "bn": {
        "welcome": "হ্যালো, আমি AuraMed, আপনার চিকিৎসা সহকারী। আজ আমি কীভাবে সাহায্য করতে পারি?",
        "emergency_advice": "এটি জরুরি অবস্থা হতে পারে। অনুগ্রহ করে অবিলম্বে নিকটস্থ জরুরি বিভাগে যান বা জরুরি নম্বরে কল করুন।",
        "emergency_number": "৯৯৯",
        "first_aid_title": "প্রাথমিক চিকিৎসা নির্দেশিকা",
        "remedies_title": "নিরাপদ ঘরোয়া যত্নের পরামর্শ",
        "see_doctor": "উপসর্গ বাড়লে বা অব্যাহত থাকলে অনুগ্রহ করে একজন নিবন্ধিত চিকিৎসকের সাথে পরামর্শ করুন।",
        "no_diagnosis": "AuraMed ডাক্তারের রোগ নির্ণয়ের বিকল্প হতে পারে না।",
        "risk_red": "উচ্চ ঝুঁকি — এখনই জরুরি চিকিৎসা প্রয়োজন",
        "risk_yellow": "মাঝারি ঝুঁকি — আজই চিকিৎসা সেবা নিন",
        "risk_green": "কম ঝুঁকি — পর্যবেক্ষণসহ ঘরোয়া যত্ন",
    },
}


def t(key: str, language: str = "en") -> str:
    """Translate a key; falls back to English then to the key itself."""
    lang = "bn" if language.lower().startswith("bn") else "en"
    return STRINGS.get(lang, {}).get(key) or STRINGS["en"].get(key, key)
