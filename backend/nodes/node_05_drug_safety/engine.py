"""Node 05 — Drug Safety Check engine (production implementation).

Deterministic rule engine over the local drug knowledge base. Runs entirely
offline, writes every check to the regulatory audit trail (Node 26), and
returns structured, severity-graded findings that the prescriber MUST review
(the mandatory disclaimer rides on every response envelope).

Severity policy:
  * critical/high → ``safe_to_proceed = False`` (hard stop for AI-assisted
    prescribing; physician must resolve before the draft prescription is used)
  * moderate      → proceed with monitoring
  * low/info      → advisory
"""
from __future__ import annotations

from itertools import combinations
from typing import Any

from backend.core.audit import log_action
from backend.core.schemas import PatientContext, Severity
from backend.nodes.base import BaseNode
from backend.nodes.node_05_drug_safety.knowledge import load_drug_kb, resolve_drug
from backend.nodes.node_05_drug_safety.schemas import (
    DrugSafetyReport,
    DrugSafetyRequest,
    SafetyFinding,
)

_SEVERITY_ORDER = [
    Severity.INFO,
    Severity.LOW,
    Severity.MODERATE,
    Severity.HIGH,
    Severity.CRITICAL,
]


class DrugSafetyEngine(BaseNode):
    node_id = 5
    node_name = "Drug Safety & Allergy Check"
    implemented = True

    # ------------------------------------------------------------------ run
    def check(self, request: DrugSafetyRequest) -> DrugSafetyReport:
        findings: list[SafetyFinding] = []
        patient = request.patient
        lang = request.language

        # 1) Resolve every medication to a canonical KB entry ----------------
        resolved: list[tuple[str, dict[str, Any], str]] = []  # (key, record, raw_name)
        unknown: list[str] = []
        for med in request.medications:
            key, record = resolve_drug(med.name)
            if record is None:
                unknown.append(med.name)
                findings.append(
                    SafetyFinding(
                        severity=Severity.LOW,
                        category="unknown_drug",
                        drugs=[med.name],
                        title_en=f"Unknown medication: {med.name}",
                        title_bn=f"অপরিচিত ওষুধ: {med.name}",
                        detail_en=(
                            f"'{med.name}' is not in the local formulary. A human pharmacist "
                            "must verify its interactions manually."
                        ),
                        detail_bn=(
                            f"'{med.name}' স্থানীয় ফর্মুলারিতে নেই। একজন ফার্মাসিস্টকে ম্যানুয়ালি "
                            "যাচাই করতে হবে।"
                        ),
                        recommendation_en="Manual pharmacist verification required.",
                        recommendation_bn="ফার্মাসিস্টের ম্যানুয়াল যাচাই প্রয়োজন।",
                        action="info",
                    )
                )
            else:
                resolved.append((key, record, med.name))

        # 2) Drug–drug interactions (pairwise) -------------------------------
        findings.extend(self._interaction_findings(resolved))

        # 3) Allergy / cross-reactivity --------------------------------------
        findings.extend(self._allergy_findings(resolved, patient))

        # 4) Renal limits -----------------------------------------------------
        findings.extend(self._renal_findings(resolved, patient))

        # 5) Cardiac contraindications ---------------------------------------
        findings.extend(self._cardiac_findings(resolved, patient))

        # 6) Pregnancy --------------------------------------------------------
        if patient.pregnant:
            findings.extend(self._pregnancy_findings(resolved))

        # 7) Duplicate therapy ------------------------------------------------
        findings.extend(self._duplicate_findings(resolved))

        # Sort by severity (worst first)
        findings.sort(
            key=lambda f: _SEVERITY_ORDER.index(f.severity), reverse=True
        )

        overall = findings[0].severity if findings else Severity.INFO
        hard_stop = any(f.severity in (Severity.CRITICAL, Severity.HIGH) for f in findings)
        escalate = hard_stop or any(f.action == "stop_and_review" for f in findings)

        known_names = [raw for _, _, raw in resolved]
        confidence = self._confidence(len(request.medications), len(unknown), findings)

        summary_en = (
            f"Checked {len(request.medications)} medication(s): "
            f"{self._finding_counts(findings)}. "
            + (
                "DO NOT proceed without physician/pharmacist review — critical or high-severity issues found."
                if hard_stop
                else "No critical interaction detected; review moderate/monitor items."
            )
        )
        summary_bn = (
            f"{len(request.medications)}টি ওষুধ যাচাই করা হয়েছে: {self._finding_counts_bn(findings)}। "
            + (
                "চিকিৎসক/ফার্মাসিস্টের পর্যালোচনা ছাড়া এগিয়ে যাবেন না — গুরুতর সমস্যা পাওয়া গেছে।"
                if hard_stop
                else "কোনো মারাত্মক আন্তঃক্রিয়া পাওয়া যায়নি; মাঝারি/পর্যবেক্ষণ বিষয়গুলো দেখুন।"
            )
        )

        report = DrugSafetyReport(
            overall_severity=overall,
            safe_to_proceed=not hard_stop,
            escalate_to_physician=escalate,
            findings=findings,
            checked_medications=known_names,
            unknown_medications=unknown,
            confidence=confidence,
            summary_en=summary_en,
            summary_bn=summary_bn,
        )

        # Audit (Node 26) — de-identified summary only, no PHI names.
        log_action(
            self.node_id,
            "drug_safety_check",
            details={
                "medication_count": len(request.medications),
                "unknown_count": len(unknown),
                "overall_severity": overall.value,
                "hard_stop": hard_stop,
                "finding_categories": sorted({f.category for f in findings}),
                "language": lang,
            },
            risk_level=overall.value,
        )
        return report

    # ------------------------------------------------------------------ API
    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        request = DrugSafetyRequest.model_validate(payload)
        report = self.check(request)
        return report.model_dump()

    # ============================================================== checks
    def _interaction_findings(
        self, resolved: list[tuple[str, dict[str, Any], str]]
    ) -> list[SafetyFinding]:
        out: list[SafetyFinding] = []
        kb = load_drug_kb()
        pair_rules: dict[frozenset[str], dict[str, Any]] = {
            frozenset((rule["a"], rule["b"])): rule for rule in kb["interactions"]
        }
        for (key_a, rec_a, raw_a), (key_b, rec_b, raw_b) in combinations(resolved, 2):
            rule = pair_rules.get(frozenset((key_a, key_b)))
            if not rule:
                continue
            severity = Severity(rule["severity"])
            names = f"{rec_a['name']} + {rec_b['name']}"
            hard = severity in (Severity.CRITICAL, Severity.HIGH)
            out.append(
                SafetyFinding(
                    severity=severity,
                    category="drug_drug_interaction",
                    drugs=[raw_a, raw_b],
                    title_en=f"{severity.value.title()} interaction: {names}",
                    title_bn=rule.get("bn", f"আন্তঃক্রিয়া: {names}"),
                    detail_en=rule["mechanism"],
                    detail_bn=rule.get("bn", rule["mechanism"]),
                    recommendation_en=rule["action"],
                    recommendation_bn=rule.get("bn", rule["action"]),
                    action="stop_and_review" if hard else "monitor",
                )
            )
        return out

    def _allergy_findings(
        self,
        resolved: list[tuple[str, dict[str, Any], str]],
        patient: PatientContext,
    ) -> list[SafetyFinding]:
        out: list[SafetyFinding] = []
        if not patient.allergies:
            return out
        kb = load_drug_kb()
        cross = kb.get("allergy_cross_reactivity", {})
        allergy_tokens = [a.strip().lower() for a in patient.allergies]

        # Map allergy tokens -> set of forbidden canonical keys
        forbidden: set[str] = set()
        matched_terms: set[str] = set()
        for token in allergy_tokens:
            # direct drug match
            key, _ = resolve_drug(token)
            if key:
                forbidden.add(key)
                matched_terms.add(token)
            # class cross-reactivity (e.g. 'penicillin' -> amoxicillin)
            for class_name, members in cross.items():
                if class_name in token or token in class_name:
                    forbidden.update(members)
                    matched_terms.add(token)

        for key, record, raw in resolved:
            # direct name match OR same therapeutic class as a known-allergen
            record_class = record.get("drug_class", "")
            class_hit = any(
                record_class == load_drug_kb()["drugs"][fk].get("drug_class")
                for fk in forbidden
                if fk in load_drug_kb()["drugs"]
            )
            if key in forbidden or class_hit:
                out.append(
                    SafetyFinding(
                        severity=Severity.CRITICAL,
                        category="allergy",
                        drugs=[raw],
                        title_en=f"ALLERGY CONTRAINDICATION: {record['name']}",
                        title_bn=f"এলার্জি অসঙ্গতি: {record['name']}",
                        detail_en=(
                            f"Patient reports allergy/intolerance: "
                            f"{', '.join(sorted(matched_terms) or patient.allergies)}. "
                            f"{record['name']} belongs to a cross-reactive class."
                        ),
                        detail_bn=(
                            f"রোগীর এলার্জি রয়েছে: "
                            f"{', '.join(sorted(matched_terms) or patient.allergies)}। "
                            f"{record['name']} ক্রস-রিঅ্যাকটিভ শ্রেণির অন্তর্ভুক্ত।"
                        ),
                        recommendation_en=(
                            "Do NOT dispense without physician review; choose an alternative class."
                        ),
                        recommendation_bn="চিকিৎসকের পর্যালোচনা ছাড়া দেবেন না; বিকল্প শ্রেণির ওষুধ বেছে নিন।",
                        action="stop_and_review",
                    )
                )
        return out

    def _renal_findings(
        self,
        resolved: list[tuple[str, dict[str, Any], str]],
        patient: PatientContext,
    ) -> list[SafetyFinding]:
        out: list[SafetyFinding] = []
        egfr = patient.renal_egfr
        if egfr is None:
            return out
        ckd = any("ckd" in c.lower() or "kidney" in c.lower() or "renal" in c.lower()
                  for c in patient.conditions)
        for key, record, raw in resolved:
            cutoff = record.get("renal_cutoff_egfr")
            if cutoff is None:
                continue
            if egfr < cutoff:
                severe = egfr < max(cutoff - 15, 30)
                out.append(
                    SafetyFinding(
                        severity=Severity.HIGH if severe else Severity.MODERATE,
                        category="renal",
                        drugs=[raw],
                        title_en=f"Renal caution: {record['name']} at eGFR {egfr:g}",
                        title_bn=f"কিডনি সতর্কতা: {record['name']} (eGFR {egfr:g})",
                        detail_en=(
                            f"{record['name']} requires dose adjustment or avoidance when eGFR < "
                            f"{cutoff} mL/min/1.73m². Patient eGFR is {egfr:g}. "
                            f"{record.get('notes', '')}"
                        ),
                        detail_bn=(
                            f"eGFR {cutoff}-এর নিচে {record['name']} মাত্রা সমন্বয় বা বন্ধ প্রয়োজন। "
                            f"রোগীর eGFR {egfr:g}।"
                        ),
                        recommendation_en=(
                            "Physician/pharmacist must adjust dose or select a renal-safe alternative."
                        ),
                        recommendation_bn="চিকিৎসক/ফার্মাসিস্ট মাত্রা সমন্বয় বা কিডনি-নিরাপদ বিকল্প দেবেন।",
                        action="stop_and_review" if severe else "monitor",
                    )
                )
        if ckd and not out:
            # soft advisory so CKD is never silently ignored
            out.append(
                SafetyFinding(
                    severity=Severity.INFO,
                    category="renal",
                    drugs=[],
                    title_en="CKD noted — confirm eGFR-guided dosing",
                    title_bn="CKD রয়েছে — eGFR অনুযায়ী মাত্রা নিশ্চিত করুন",
                    detail_en="Patient has chronic kidney disease; verify renal dosing for all new medicines.",
                    detail_bn="রোগীর দীর্ঘস্থায়ী কিডনি রোগ আছে; সব নতুন ওষুধের কিডনি মাত্রা যাচাই করুন।",
                    recommendation_en="Review renal dosing before dispensing.",
                    recommendation_bn="দেওয়ার আগে কিডনি মাত্রা পর্যালোচনা করুন।",
                    action="monitor",
                )
            )
        return out

    def _cardiac_findings(
        self,
        resolved: list[tuple[str, dict[str, Any], str]],
        patient: PatientContext,
    ) -> list[SafetyFinding]:
        out: list[SafetyFinding] = []
        kb = load_drug_kb()
        guidance = kb.get("cardiac_flag_guidance", {})
        cond_text = " ".join(patient.conditions).lower()
        long_qt = any(k in cond_text for k in ("long qt", "qt", "arrhythm", "heart failure", "chf"))
        for key, record, raw in resolved:
            for flag in record.get("cardiac_flags", []):
                g = guidance.get(flag, {})
                severity = Severity.MODERATE
                if flag == "qt_prolongation" and long_qt:
                    severity = Severity.HIGH
                out.append(
                    SafetyFinding(
                        severity=severity,
                        category="cardiac",
                        drugs=[raw],
                        title_en=f"Cardiac caution ({flag.replace('_', ' ')}): {record['name']}",
                        title_bn=f"হৃদ্-সতর্কতা: {record['name']}",
                        detail_en=g.get("en", flag),
                        detail_bn=g.get("bn", g.get("en", flag)),
                        recommendation_en=(
                            "Check ECG/electrolytes and review with a physician before combining."
                        ),
                        recommendation_bn="একসাথে দেওয়ার আগে ECG/ইলেক্ট্রোলাইট দেখে চিকিৎসকের পরামর্শ নিন।",
                        action="monitor" if severity == Severity.MODERATE else "stop_and_review",
                    )
                )
        return out

    def _pregnancy_findings(
        self, resolved: list[tuple[str, dict[str, Any], str]]
    ) -> list[SafetyFinding]:
        out: list[SafetyFinding] = []
        for key, record, raw in resolved:
            flag = record.get("pregnancy_flag", "")
            if flag in ("contraindicated", "avoid", "switch_to_insulin",
                        "avoid_after_20_weeks", "avoid_high_dose", "not_indicated",
                        "avoid_first_trimester"):
                out.append(
                    SafetyFinding(
                        severity=Severity.HIGH if flag == "contraindicated" else Severity.MODERATE,
                        category="pregnancy",
                        drugs=[raw],
                        title_en=f"Pregnancy review: {record['name']} ({flag.replace('_', ' ')})",
                        title_bn=f"গর্ভাবস্থা পর্যালোচনা: {record['name']}",
                        detail_en=(
                            f"{record['name']} is flagged '{flag}' in pregnancy. "
                            f"{record.get('notes', '')}"
                        ),
                        detail_bn=f"গর্ভাবস্থায় {record['name']} ('{flag}') পর্যালোচনা প্রয়োজন।",
                        recommendation_en="Obstetrician must review before use.",
                        recommendation_bn="ব্যবহারের আগে প্রসূতি বিশেষজ্ঞের পর্যালোচনা আবশ্যক।",
                        action="stop_and_review" if flag == "contraindicated" else "monitor",
                    )
                )
        return out

    def _duplicate_findings(
        self, resolved: list[tuple[str, dict[str, Any], str]]
    ) -> list[SafetyFinding]:
        out: list[SafetyFinding] = []
        seen_class: dict[str, str] = {}
        for key, record, raw in resolved:
            cls = record.get("drug_class", "")
            # Only warn for classes where duplication is genuinely hazardous.
            hazardous = cls in {
                "nsaid", "nsaid_antiplatelet", "anticoagulant", "ace_inhibitor",
                "arb", "sulfonylurea", "fluoroquinolone",
            }
            if cls and cls in seen_class and hazardous:
                out.append(
                    SafetyFinding(
                        severity=Severity.HIGH,
                        category="duplicate",
                        drugs=[seen_class[cls], raw],
                        title_en=f"Duplicate {cls.replace('_', ' ')} therapy",
                        title_bn="একই শ্রেণির দুটি ওষুধ",
                        detail_en=(
                            f"{seen_class[cls]} and {raw} belong to the same therapeutic class "
                            f"({cls}); concurrent use raises adverse-effect risk without added benefit."
                        ),
                        detail_bn=(
                            f"{seen_class[cls]} ও {raw} একই শ্রেণির ({cls}) — একসাথে ব্যবহারে "
                            "পার্শ্বপ্রতিক্রিয়ার ঝুঁকি বাড়ে।"
                        ),
                        recommendation_en="Stop one agent after physician review.",
                        recommendation_bn="চিকিৎসকের পর্যালোচনার পর একটি ওষুধ বন্ধ করুন।",
                        action="stop_and_review",
                    )
                )
            seen_class[cls] = raw
        return out

    # ============================================================== helpers
    @staticmethod
    def _confidence(total: int, unknown: int, findings: list[SafetyFinding]) -> float:
        """Rule coverage confidence: known drugs raise it; unknowns lower it.
        Unknown drugs are never silently ignored — they cap confidence."""
        if total == 0:
            return 0.0
        base = (total - unknown) / total
        # Small penalty per low/info advisory, heavier penalty for unknowns.
        penalty = min(0.15, 0.03 * len(findings))
        return round(max(0.0, min(1.0, base - penalty)), 2)

    @staticmethod
    def _finding_counts(findings: list[SafetyFinding]) -> str:
        counts: dict[str, int] = {}
        for f in findings:
            counts[f.severity.value] = counts.get(f.severity.value, 0) + 1
        if not counts:
            return "no issues found"
        return ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))

    @staticmethod
    def _finding_counts_bn(findings: list[SafetyFinding]) -> str:
        if not findings:
            return "কোনো সমস্যা পাওয়া যায়নি"
        counts: dict[str, int] = {}
        for f in findings:
            counts[f.severity.value] = counts.get(f.severity.value, 0) + 1
        labels = {"critical": "মারাত্মক", "high": "উচ্চ", "moderate": "মাঝারি",
                  "low": "নিম্ন", "info": "তথ্য"}
        return ", ".join(f"{v}টি {labels.get(k, k)}" for k, v in sorted(counts.items()))


# Module-level singleton used by the API layer.
drug_safety_engine = DrugSafetyEngine()
