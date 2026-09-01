"""Node 11 — Health Risk Predictor Score.

Transparent, point-based risk scores for 10-year cardiovascular disease
(adapted from Framingham-style risk factors), type-2 diabetes risk
(Finnish-style simplified) and CKD progression watch. Pure stdlib, fully
auditable — no opaque model. ML models (XGBoost/LightGBM trained on cohort
data) can replace ``compute_*`` at deploy time behind the same interface.
"""
from __future__ import annotations

from pydantic import BaseModel

from backend.core.audit import log_action
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode


class RiskFactors(BaseModel):
    age_years: float = 40
    sex: str = "other"                 # male | female | other
    sbp: float = 120.0                 # systolic BP mmHg
    on_bp_medication: bool = False
    smoker: bool = False
    diabetic: bool = False
    total_cholesterol_mg_dl: float = 190.0
    hdl_mg_dl: float = 45.0
    bmi: float | None = None
    family_history_diabetes: bool = False
    egfr: float | None = None


class RiskPredictorNode(BaseNode):
    node_id = 11
    node_name = "Health Risk Predictor Score"
    implemented = True

    def predict(self, f: RiskFactors) -> dict:
        cvd_pct, cvd_band = self._cvd_risk(f)
        dm_score, dm_band = self._diabetes_risk(f)
        ckd_note = self._ckd_note(f)
        log_action(
            self.node_id, "risk_prediction",
            details={"cvd_band": cvd_band, "diabetes_band": dm_band,
                     "ckd_flag": ckd_note["ckd_watch"]},
        )
        return {
            "status": "ok",
            "scores": {
                "cvd_10yr_pct_estimate": cvd_pct,
                "cvd_band": cvd_band,
                "diabetes_risk_score": dm_score,
                "diabetes_band": dm_band,
            },
            "ckd_watch": ckd_note,
            "recommendations_en": [
                "Scores are population estimates for screening — not a diagnosis.",
                "High/very-high bands: physician review, BP/lipid/glucose follow-up.",
                "Smoking cessation, 150 min/week activity, DASH-style regional diet (see Node 18).",
            ],
            "recommendations_bn": [
                "স্কোর জনসংখ্যা-ভিত্তিক অনুমান — রোগ নির্ণয় নয়।",
                "উচ্চ/খুব উচ্চ ঝুঁকি: চিকিৎসকের পরামর্শ, BP/লিপিড/সুগার ফলোআপ।",
                "ধূমপান বর্জন, সপ্তাহে ১৫০ মিনিট ব্যায়াম, আঞ্চলিক স্বাস্থ্যকর খাদ্য (Node 18)।",
            ],
        }

    # --------------------------------------------------------------- CVD
    @staticmethod
    def _cvd_risk(f: RiskFactors) -> tuple[float, str]:
        score = 0
        if f.age_years >= 50: score += 3
        elif f.age_years >= 40: score += 2
        elif f.age_years >= 30: score += 1
        if f.sex == "male": score += 1
        if f.sbp >= 160: score += 4
        elif f.sbp >= 140: score += 3
        elif f.sbp >= 130: score += 1
        if f.on_bp_medication: score += 1
        if f.smoker: score += 3
        if f.diabetic: score += 3
        if f.total_cholesterol_mg_dl >= 240: score += 2
        elif f.total_cholesterol_mg_dl >= 200: score += 1
        if f.hdl_mg_dl < 35: score += 2
        elif f.hdl_mg_dl < 45: score += 1
        # Map point score to approximate 10-year %
        pct = round(min(30.0, 0.6 * score + max(0.0, (score - 8) * 1.1)), 1)
        band = "very_high" if pct >= 20 else "high" if pct >= 10 else "moderate" if pct >= 5 else "low"
        return pct, band

    # ----------------------------------------------------------- diabetes
    @staticmethod
    def _diabetes_risk(f: RiskFactors) -> tuple[int, str]:
        score = 0
        if f.bmi:
            if f.bmi >= 30: score += 3
            elif f.bmi >= 25: score += 2
            elif f.bmi >= 23: score += 1
        if f.age_years >= 55: score += 3
        elif f.age_years >= 45: score += 2
        if f.family_history_diabetes: score += 3
        if f.sbp >= 140 or f.on_bp_medication: score += 2
        if f.smoker: score += 1
        band = "very_high" if score >= 11 else "high" if score >= 8 else "moderate" if score >= 5 else "low"
        return score, band

    @staticmethod
    def _ckd_note(f: RiskFactors) -> dict:
        watch = f.egfr is not None and f.egfr < 60
        return {
            "ckd_watch": watch,
            "egfr": f.egfr,
            "message_en": "eGFR <60 — CKD follow-up and renal-safe prescribing (Node 05)." if watch else "No CKD signal from available data.",
            "message_bn": "eGFR <60 — CKD ফলোআপ ও কিডনি-নিরাপদ ওষুধ (Node 05)।" if watch else "প্রাপ্ত তথ্যে CKD সংকেত নেই।",
        }

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        data = dict(payload)
        if patient is not None:
            data.setdefault("age_years", patient.age_years or 40)
            data.setdefault("sex", patient.sex)
            data.setdefault("egfr", patient.renal_egfr)
        return self.predict(RiskFactors.model_validate(data))


risk_predictor_node = RiskPredictorNode()
