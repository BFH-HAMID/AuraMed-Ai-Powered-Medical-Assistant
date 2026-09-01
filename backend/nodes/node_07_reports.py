"""Node 07 — Multi-Source Report Comparison (lab trend / delta analysis).

Compares historic vs current lab results: absolute delta, percent change, and
flagging against reference ranges and clinically significant change
thresholds. Pure stdlib; works offline.
"""
from __future__ import annotations

from backend.core.audit import log_action
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode

# test -> (low, high, unit, pct_change_threshold_for_alert)
REFERENCE: dict[str, tuple[float, float, str, float]] = {
    "hemoglobin": (12.0, 17.0, "g/dL", 15.0),
    "wbc": (4.0, 11.0, "x10^9/L", 30.0),
    "platelets": (150.0, 450.0, "x10^9/L", 30.0),
    "creatinine": (0.6, 1.3, "mg/dL", 25.0),
    "egfr": (90.0, 140.0, "mL/min/1.73m2", 15.0),
    "alt": (7.0, 56.0, "U/L", 40.0),
    "ast": (10.0, 40.0, "U/L", 40.0),
    "fasting_glucose": (70.0, 100.0, "mg/dL", 25.0),
    "hba1c": (4.0, 5.7, "%", 10.0),
    "ldl": (0.0, 100.0, "mg/dL", 20.0),
    "potassium": (3.5, 5.1, "mmol/L", 15.0),
    "sodium": (135.0, 146.0, "mmol/L", 5.0),
    "ts_hs_troponin": (0.0, 0.04, "ng/mL", 50.0),
}


class ReportComparisonNode(BaseNode):
    node_id = 7
    node_name = "Multi-Source Report Comparison"
    implemented = True

    def compare(self, current: dict[str, float], history: list[dict[str, float]] | None = None) -> dict:
        findings = []
        for test, value in current.items():
            ref = REFERENCE.get(test.lower())
            entry: dict = {"test": test, "current": value}
            if ref:
                low, high, unit, pct_thresh = ref
                entry["unit"] = unit
                entry["reference_range"] = [low, high]
                if value < low:
                    entry["range_flag"] = "low"
                elif value > high:
                    entry["range_flag"] = "high"
                else:
                    entry["range_flag"] = "normal"
            # trend vs most recent historic value
            if history:
                prev_values = [h[test] for h in history if test in h]
                if prev_values:
                    prev = prev_values[-1]
                    delta = value - prev
                    pct = (delta / prev * 100.0) if prev else 0.0
                    entry["previous"] = prev
                    entry["delta"] = round(delta, 3)
                    entry["pct_change"] = round(pct, 1)
                    thresh = ref[3] if ref else 25.0
                    entry["trend_flag"] = "significant_change" if abs(pct) >= thresh else "stable"
            findings.append(entry)

        anomalies = [
            f for f in findings
            if f.get("range_flag") in ("low", "high") or f.get("trend_flag") == "significant_change"
        ]
        log_action(
            self.node_id, "report_comparison",
            details={"tests": len(current), "anomalies": len(anomalies)},
        )
        return {
            "status": "ok",
            "findings": findings,
            "anomaly_count": len(anomalies),
            "anomalies": anomalies,
            "note": "Trend flags are decision-support; physician review required before action.",
        }

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        return self.compare(payload.get("current", {}), payload.get("history", []))


report_comparison_node = ReportComparisonNode()
