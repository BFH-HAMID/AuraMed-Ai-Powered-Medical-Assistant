"""Patient Report Pack — the report a patient downloads from AuraMed.

Composes ONE structured, printable document out of the existing nodes:

    patient identity + vitals + BMI →  Node 09
    symptom triage & red flags      →  Node 02
    drug-safety cross-check         →  Node 05
    medicine leaflets + dosing      →  Node 12 (+ local dosing-rule table)
    guideline / care-plan draft     →  Node 13
    lab test suggestions            →  Node 15
    plain-language explanation      →  Node 17
    diet & lifestyle plan           →  Node 18
    10-year risk scores             →  Node 11

Nothing here invents clinical content — the pack only assembles what those
nodes already produce, in the patient's language. It is always marked
``requires_physician_review`` and always carries the mandatory disclaimer
(Implementation Directive #2).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from backend.core.audit import log_action
from backend.core.disclaimer import get_disclaimer
from backend.core.i18n import t
from backend.nodes.node_02_triage.engine import triage_engine
from backend.nodes.node_02_triage.schemas import TriageRequest
from backend.nodes.node_05_drug_safety.engine import drug_safety_engine
from backend.nodes.node_05_drug_safety.knowledge import resolve_drug
from backend.nodes.node_05_drug_safety.schemas import DrugSafetyRequest, MedicationInput
from backend.nodes.node_09_ehr import EHRPayload, PatientContext, VitalsRecord
from backend.nodes.node_09_ehr import ehr_node
from backend.nodes.node_11_risk_score import RiskFactors, risk_predictor_node
from backend.nodes.node_12_leaflets import leaflet_node
from backend.nodes.node_13_guidelines import guidelines_node
from backend.nodes.node_14_first_aid.engine import first_aid_engine
from backend.nodes.node_15_lab_tests import lab_tests_node
from backend.nodes.node_17_explainer import explainer_node
from backend.nodes.node_18_diet import diet_node

REPORT_NODE_ID = 7  # audited under Node 07 ("Reports") as a composed document

Language = Literal["en", "bn"]


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class ReportPatient(BaseModel):
    """রোগীর পরিচয় ও শারীরিক তথ্য (identity + anthropometry)."""

    name: str = Field(..., min_length=1, description="Patient name")
    age_years: float | None = Field(default=None, ge=0, le=130)
    sex: Literal["male", "female", "other", "unknown"] = "unknown"
    weight_kg: float | None = Field(default=None, gt=0, le=500)
    height_cm: float | None = Field(default=None, gt=0, le=280)
    phone: str = ""
    address: str = ""
    patient_id: str = ""
    allergies: list[str] = Field(default_factory=list)
    conditions: list[str] = Field(default_factory=list)
    current_medications: list[str] = Field(default_factory=list)
    renal_egfr: float | None = None
    pregnant: bool = False
    smoker: bool = False
    diabetic: bool = False
    systolic_bp: float | None = None


class ReportMedication(BaseModel):
    """একটি ওষুধ + সেবনবিধি (one prescribed medicine and how to take it)."""

    name: str = Field(..., min_length=1)
    dose: str | None = Field(default=None, description="e.g. '500 mg'")
    frequency: str | None = Field(
        default=None, description="e.g. '1+0+1' (morning+midday+night) or 'twice daily'"
    )
    duration: str | None = Field(default=None, description="e.g. '30 days'")
    timing: str | None = Field(default=None, description="Overrides the class default, e.g. 'after meal'")


class PatientReportRequest(BaseModel):
    patient: ReportPatient
    symptoms_text: str = Field(default="", description="Free-text symptoms (bn/en)")
    vitals: dict[str, float] = Field(default_factory=dict)
    diagnosis: str = Field(default="", description="রোগের নাম (free text)")
    diagnosis_key: str = Field(default="", description="Protocol key for Node 13, e.g. 'hypertension'")
    medications: list[ReportMedication] = Field(default_factory=list)
    language: Language = "bn"


# ---------------------------------------------------------------------------
# Local helpers: BMI, dosing shorthand, class-based timing
# ---------------------------------------------------------------------------
# WHO Asia-Pacific cut-offs (appropriate for Bangladeshi adults).
_BMI_BANDS = (
    (18.5, "underweight", "কম ওজন", "Underweight"),
    (23.0, "normal", "স্বাভাবিক", "Normal"),
    (27.5, "overweight", "বেশি ওজন", "Overweight"),
    (float("inf"), "obese", "স্থূলকায়", "Obese"),
)

_TIMING_BY_CLASS: dict[str, tuple[str, str]] = {
    # drug_class: (english, bengali)
    "statin": ("At night (statins work best overnight)", "রাতে ঘুমানোর আগে (স্ট্যাটিন রাতে ভালো কাজ করে)"),
    "biguanide_antidiabetic": ("With or just after a meal", "খাবারের সাথে বা ঠিক খাবারের পরে"),
    "sulfonylurea": ("30 minutes before breakfast", "সকালের নাস্তার ৩০ মিনিট আগে"),
    "nsaid": ("After food, with a full glass of water", "খাবারের পরে, এক গ্লাস পানির সাথে"),
    "nsaid_antiplatelet": ("After food", "খাবারের পরে"),
    "ace_inhibitor": ("On an empty stomach, 1 hour before food", "খালি পেটে, খাবারের ১ ঘণ্টা আগে"),
    "arb": ("Any time of day, keep the same time daily", "দিনের যেকোনো সময়, প্রতিদিন একই সময়ে"),
    "beta_blocker": ("With or after food; do not stop suddenly", "খাবারের সাথে/পরে; হঠাৎ বন্ধ করবেন না"),
    "calcium_channel_blocker": ("Same time daily, with or without food", "প্রতিদিন একই সময়ে, খাবারসহ বা ছাড়া"),
    "penicillin": ("1 hour before or 2 hours after food", "খাবারের ১ ঘণ্টা আগে বা ২ ঘণ্টা পরে"),
    "macrolide": ("With food if it upsets the stomach", "পেটে অস্বস্তি হলে খাবারের সাথে"),
    "fluoroquinolone": ("2 hours apart from milk/antacids/iron", "দুধ/অ্যান্টাসিড/আয়রন থেকে ২ ঘণ্টা ব্যবধানে"),
    "sulfonamide": ("With plenty of water", "প্রচুর পানির সাথে"),
    "nitroimidazole": ("After food; NO alcohol during and 3 days after", "খাবারের পরে; সেবনকালীন ও পরের ৩ দিন অ্যালকোহল নয়"),
    "ppi": ("30 minutes before breakfast", "সকালের নাস্তার ৩০ মিনিট আগে"),
    "loop_diuretic": ("In the morning (avoids night urination)", "সকালে (রাতে প্রস্রাবের অসুবিধা এড়াতে)"),
    "potassium_sparing_diuretic": ("In the morning, as advised", "সকালে, পরামর্শ অনুযায়ী"),
    "anticoagulant": ("Same time daily; do not miss doses", "প্রতিদিন একই সময়ে; ডোজ বাদ দেবেন না"),
    "antiplatelet": ("After food", "খাবারের পরে"),
    "analgesic_antipyretic": ("After food; maximum 4 g paracetamol/day", "খাবারের পরে; প্যারাসিটামল সর্বোচ্চ ৪ গ্রাম/দিন"),
    "antihistamine_sedating": ("At night (causes drowsiness)", "রাতে (তন্দ্রাভাব হয়)"),
    "antiemetic_5ht3": ("30 minutes before food", "খাবারের ৩০ মিনিট আগে"),
    "nitrate": ("As prescribed; never with erectile-dysfunction drugs", "নির্দেশ অনুযায়ী; ইডি-র ওষুধের সাথে কখনো নয়"),
    "pde5_inhibitor": ("As prescribed; never with nitrates", "নির্দেশ অনুযায়ী; নাইট্রেটের সাথে কখনো নয়"),
    "azole_antifungal": ("With food (absorption improves)", "খাবারের সাথে (শোষণ বাড়ে)"),
    "antidiabetic_injectable": ("As trained by your clinician", "চিকিৎসকের প্রশিক্ষণ অনুযায়ী"),
}

_DEFAULT_TIMING = ("As directed by your physician", "চিকিৎসকের নির্দেশ অনুযায়ী")


def _bmi(weight_kg: float | None, height_cm: float | None) -> tuple[float | None, dict]:
    if not weight_kg or not height_cm:
        return None, {"key": "unknown", "en": "Not calculated", "bn": "নির্ণয় করা হয়নি"}
    value = round(weight_kg / ((height_cm / 100.0) ** 2), 1)
    for limit, key, bn, en in _BMI_BANDS:
        if value < limit:
            return value, {"key": key, "en": en, "bn": bn}
    return value, {"key": "obese", "en": "Obese", "bn": "স্থূলকায়"}


def _frequency_text(frequency: str | None, language: str) -> str:
    """Expand the local ``1+0+1`` prescription shorthand into plain words."""
    if not frequency:
        return ""
    bn = language.startswith("bn")
    cleaned = frequency.strip().replace("-", "+").replace("–", "+")
    parts = [p.strip() for p in cleaned.split("+")] if "+" in cleaned else []
    slots = (("সকালে", "morning"), ("দুপুরে", "midday"), ("রাতে", "night"))
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        chunks = []
        for count, (bn_slot, en_slot) in zip(parts, slots):
            if int(count) == 0:
                continue
            chunks.append(f"{bn_slot} {count}টি" if bn else f"{count} × {en_slot}")
        return " · ".join(chunks) if chunks else ("সেবন নয়" if bn else "not taken")
    return frequency


def _timing_for(drug_name: str, language: str) -> tuple[str, str]:
    """Class-based administration rule; falls back to 'as directed'."""
    bn = language.startswith("bn")
    _key, record = resolve_drug(drug_name)
    pair = _TIMING_BY_CLASS.get(record.get("drug_class", "") if record else "", _DEFAULT_TIMING)
    return (pair[1], pair[0]) if bn else pair  # (display, english)


def _pick(pair_en_bn: tuple[str, str] | dict | str, language: str) -> str:
    """Render a bilingual field for the report language."""
    if isinstance(pair_en_bn, dict):
        return pair_en_bn.get("bn" if language.startswith("bn") else "en", "")
    if isinstance(pair_en_bn, tuple):
        return pair_en_bn[1] if language.startswith("bn") else pair_en_bn[0]
    return str(pair_en_bn or "")


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------
def build_patient_report(request: PatientReportRequest) -> dict:
    """Assemble the full patient report pack (plain dict, JSON-safe)."""
    lang = request.language
    bn = lang.startswith("bn")
    p = request.patient

    # --- Node 02: triage ----------------------------------------------------
    triage = None
    first_aid = []
    if request.symptoms_text.strip():
        triage_result = triage_engine.triage(
            TriageRequest(symptoms_text=request.symptoms_text, vitals=request.vitals, language=lang)
        )
        triage = triage_result.model_dump()
        first_aid = [
            first_aid_engine.get_protocol(pid, lang)
            for pid in triage_result.first_aid_protocol_ids
        ]

    risk_level = (triage or {}).get("risk_level", "green")

    # --- Node 05: drug safety ----------------------------------------------
    drug_safety = None
    if request.medications:
        report = drug_safety_engine.check(
            DrugSafetyRequest(
                medications=[MedicationInput(name=m.name, dose=m.dose) for m in request.medications],
                patient=PatientContext(
                    patient_id=p.patient_id or None,
                    age_years=p.age_years,
                    sex=p.sex,
                    weight_kg=p.weight_kg,
                    allergies=p.allergies,
                    conditions=p.conditions,
                    current_medications=p.current_medications,
                    renal_egfr=p.renal_egfr,
                    pregnant=p.pregnant,
                    language=lang,
                ),
                language=lang,
            )
        )
        drug_safety = report.model_dump()
        if not report.safe_to_proceed:
            risk_level = "red"   # a hard-stop prescription outranks a GREEN triage

    # --- Node 09: vitals + BMI ---------------------------------------------
    vitals_record = VitalsRecord(
        weight_kg=p.weight_kg,
        height_cm=p.height_cm,
        sbp=request.vitals.get("sbp") or p.systolic_bp,
        dbp=request.vitals.get("dbp"),
        hr=request.vitals.get("hr"),
        temp_c=request.vitals.get("temp_c"),
        spo2=request.vitals.get("spo2"),
    )
    ehr = ehr_node.ingest(
        EHRPayload(
            patient=PatientContext(
                patient_id=p.patient_id or None, age_years=p.age_years, sex=p.sex,
                weight_kg=p.weight_kg, allergies=p.allergies, conditions=p.conditions,
                current_medications=p.current_medications, language=lang,
            ),
            vitals=[vitals_record],
            conditions=p.conditions,
            medications=[m.name for m in request.medications],
        )
    )
    bmi_value, bmi_band = _bmi(p.weight_kg, p.height_cm)
    bmi_value = ehr.get("bmi") or bmi_value

    # --- Node 13 / 17 / 15 / 18 / 11 ---------------------------------------
    diagnosis_key = request.diagnosis_key or request.diagnosis.strip().lower()
    protocol = guidelines_node.draft(diagnosis_key, lang) if diagnosis_key else None
    plain = explainer_node.explain(request.diagnosis, lang) if request.diagnosis else None
    labs = lab_tests_node.recommend(request.symptoms_text, lang) if request.symptoms_text else None
    diet = diet_node.generate(request.diagnosis or "general", p.age_years, lang)
    risk_scores = risk_predictor_node.predict(
        RiskFactors(
            age_years=p.age_years or 40, sex=p.sex,
            sbp=request.vitals.get("sbp") or p.systolic_bp or 120.0,
            smoker=p.smoker, diabetic=p.diabetic, bmi=bmi_value, egfr=p.renal_egfr,
        )
    )

    # --- Node 12 + local dosing rules: the medication schedule --------------
    medications: list[dict] = []
    for med in request.medications:
        timing_display, timing_en = (
            (med.timing, med.timing) if med.timing else _timing_for(med.name, lang)
        )
        leaflet = leaflet_node.generate(med.name, lang)
        warnings = [
            f.get("title_bn" if bn else "title_en")
            for f in (drug_safety or {}).get("findings", [])
            if med.name.lower() in [d.lower() for d in f.get("drugs", [])]
            and f.get("severity") in ("critical", "high", "moderate")
        ]
        medications.append({
            "name": med.name,
            "dose": med.dose or "",
            "frequency_raw": med.frequency or "",
            "frequency": _frequency_text(med.frequency, lang),
            "duration": med.duration or "",
            "timing": timing_display or _pick(_DEFAULT_TIMING, lang),
            "timing_en": timing_en,
            "in_formulary": leaflet.get("status") == "ok",
            "leaflet": leaflet,
            "warnings": [w for w in warnings if w],
        })

    # --- Suggestions (রোগীর জন্য পরামর্শ) ----------------------------------
    suggestions: list[str] = []
    if triage:
        advice = triage.get("immediate_advice_bn" if bn else "immediate_advice_en")
        if advice:
            suggestions.append(advice)
    if drug_safety and not drug_safety.get("safe_to_proceed"):
        summary = drug_safety.get("summary_bn" if bn else "summary_en")
        if summary:
            suggestions.append(summary)
    if protocol and protocol.get("non_drug_measures"):
        label = "ঔষধ ছাড়া করণীয়" if bn else "Non-drug measures"
        suggestions.append(f"{label}: {', '.join(protocol['non_drug_measures'])}")
    for item in diet.get("activity", [])[:2]:
        suggestions.append(item)
    if labs and labs.get("recommended_tests"):
        label = "প্রয়োজনীয় পরীক্ষা" if bn else "Investigations"
        tests = ", ".join(t_["test"] for t_ in labs["recommended_tests"][:4])
        suggestions.append(f"{label}: {tests}")
    if protocol and protocol.get("review_in_days"):
        suggestions.append(
            f"{protocol['review_in_days']} দিন পর আবার চিকিৎসককে দেখান।" if bn
            else f"Review with your physician in {protocol['review_in_days']} days."
        )
    suggestions.append(t("see_doctor", lang))

    report = {
        "report_id": f"AMR-{datetime.now(timezone.utc):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "language": lang,
        "requires_physician_review": True,
        "risk_level": risk_level,
        "risk_banner": t(f"risk_{risk_level}", lang),
        "disclaimer": get_disclaimer(lang),
        "patient": {
            "name": p.name,
            "patient_id": p.patient_id,
            "age_years": p.age_years,
            "sex": p.sex,
            "sex_bn": {"male": "পুরুষ", "female": "মহিলা", "other": "অন্যান্য", "unknown": "অজানা"}[p.sex],
            "weight_kg": p.weight_kg,
            "height_cm": p.height_cm,
            "bmi": bmi_value,
            "bmi_category": bmi_band["bn"] if bn else bmi_band["en"],
            "bmi_category_key": bmi_band["key"],
            "phone": p.phone,
            "address": p.address,
            "allergies": p.allergies,
            "conditions": p.conditions,
            "current_medications": p.current_medications,
            "renal_egfr": p.renal_egfr,
            "pregnant": p.pregnant,
            "smoker": p.smoker,
            "diabetic": p.diabetic,
        },
        "assessment": {
            "symptoms_text": request.symptoms_text,
            "vitals": request.vitals,
            "triage": triage,
            "first_aid": [f for f in first_aid if f.get("found")],
            "emergency_number": t("emergency_number", lang),
        },
        "diagnosis": {
            "text": request.diagnosis,
            "diagnosis_key": diagnosis_key,
            "plain_explanation": (plain or {}).get("plain_version", ""),
            "glossed_terms": (plain or {}).get("glossed_terms", []),
            "protocol": protocol,
        },
        "medications": medications,
        "drug_safety": drug_safety,
        "diet": diet,
        "lab_tests": labs,
        "risk_scores": risk_scores,
        "suggestions": suggestions,
        "sources": [
            {"node": 2, "name": "Emergency Triage & Red Flag Detection", "used": triage is not None},
            {"node": 5, "name": "Drug Safety & Allergy Check", "used": drug_safety is not None},
            {"node": 9, "name": "Patient History & Vitals Integration", "used": True},
            {"node": 11, "name": "Health Risk Predictor Score", "used": True},
            {"node": 12, "name": "Medicine-Related Documentation", "used": bool(medications)},
            {"node": 13, "name": "Prescription & Guidelines Engine", "used": protocol is not None},
            {"node": 14, "name": "First Aid & Emergency Guidebook", "used": bool(first_aid)},
            {"node": 15, "name": "Lab Test Recommendations", "used": labs is not None},
            {"node": 17, "name": "Simplified Patient Explanation", "used": plain is not None},
            {"node": 18, "name": "Diet & Lifestyle Guide Generator", "used": True},
        ],
    }

    log_action(
        REPORT_NODE_ID,
        "patient_report_generated",
        details={
            "report_id": report["report_id"],
            "risk_level": risk_level,
            "medications": len(medications),
            "language": lang,
        },
    )
    return report


def report_filename(report: dict) -> str:
    """ASCII-safe download filename (PHI stays out of the filename)."""
    date = report["generated_at"][:10]
    return f"AuraMed-Report-{report['risk_level']}-{date}-{report['report_id'].split('-')[-1]}.html"
