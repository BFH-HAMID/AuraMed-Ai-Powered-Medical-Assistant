"""Tests for Node 05 — Drug Safety & Allergy Check (production engine)."""
from __future__ import annotations

import pytest

from backend.core.schemas import PatientContext, Severity
from backend.nodes.node_05_drug_safety.engine import DrugSafetyEngine
from backend.nodes.node_05_drug_safety.knowledge import resolve_drug
from backend.nodes.node_05_drug_safety.schemas import DrugSafetyRequest, MedicationInput

engine = DrugSafetyEngine()


def req(meds, **patient_kwargs) -> DrugSafetyRequest:
    return DrugSafetyRequest(
        medications=[MedicationInput(name=m) for m in meds],
        patient=PatientContext(**patient_kwargs),
        language=patient_kwargs.pop("language", "en"),
    )


# ---------------------------------------------------------------- knowledge
def test_alias_resolution_brand_and_bengali():
    assert resolve_drug("Napa")[0] == "paracetamol"          # brand
    assert resolve_drug("প্যারাসিটামল")[0] == "paracetamol"  # bengali
    assert resolve_drug("Aspirin 75mg tablet")[0] == "aspirin"  # token match
    key, rec = resolve_drug("totally-unknown-drug-xyz")
    assert key is None and rec is None


# ------------------------------------------------------------- interactions
def test_warfarin_ibuprofen_is_critical_hard_stop():
    report = engine.check(req(["warfarin", "ibuprofen"]))
    assert report.overall_severity == Severity.CRITICAL
    assert report.safe_to_proceed is False
    assert report.escalate_to_physician is True
    cats = {f.category for f in report.findings}
    assert "drug_drug_interaction" in cats
    top = report.findings[0]
    assert top.severity == Severity.CRITICAL
    assert top.action == "stop_and_review"


def test_sildenafil_nitroglycerin_absolute_contraindication():
    report = engine.check(req(["sildenafil", "nitroglycerin"]))
    assert report.safe_to_proceed is False
    assert any("nitroglycerin" in f.drugs or "Nitroglycerin" in f.title_en
               for f in report.findings)


def test_paracetamol_with_unknown_is_not_critical():
    report = engine.check(req(["paracetamol", "some-new-unlisted-syrup"]))
    # Unknown drug raises an INFO/LOW finding but must not crash or hard-stop.
    assert report.unknown_medications == ["some-new-unlisted-syrup"]
    assert report.safe_to_proceed is True


# ------------------------------------------------------------------ allergy
def test_penicillin_allergy_blocks_amoxicillin():
    report = engine.check(req(["amoxicillin"], allergies=["penicillin"]))
    assert report.overall_severity == Severity.CRITICAL
    assert any(f.category == "allergy" for f in report.findings)


def test_nsaid_class_allergy_blocks_ibuprofen():
    report = engine.check(req(["ibuprofen"], allergies=["nsaid"]))
    assert any(f.category == "allergy" and f.severity == Severity.CRITICAL
               for f in report.findings)


def test_no_allergy_no_finding():
    report = engine.check(req(["paracetamol"]))
    assert all(f.category != "allergy" for f in report.findings)


# -------------------------------------------------------------------- renal
def test_metformin_contraindicated_at_low_egfr():
    report = engine.check(req(["metformin"], renal_egfr=22.0))
    renal = [f for f in report.findings if f.category == "renal"]
    assert renal and renal[0].severity == Severity.HIGH
    assert report.safe_to_proceed is False


def test_metformin_ok_at_normal_egfr():
    report = engine.check(req(["metformin"], renal_egfr=88.0))
    assert all(f.category != "renal" for f in report.findings)


# ------------------------------------------------------------------ cardiac
def test_qt_stacking_flagged():
    report = engine.check(req(["ciprofloxacin", "ondansetron"],
                              conditions=["long QT syndrome"]))
    cardiac = [f for f in report.findings if f.category == "cardiac"]
    assert cardiac
    assert any(f.severity == Severity.HIGH for f in cardiac)


# --------------------------------------------------------------- pregnancy
def test_ace_inhibitor_pregnancy():
    report = engine.check(req(["enalapril"], pregnant=True))
    assert any(f.category == "pregnancy" for f in report.findings)
    assert report.safe_to_proceed is False


# -------------------------------------------------------------- duplicates
def test_duplicate_nsaid_therapy():
    report = engine.check(req(["ibuprofen", "diclofenac"]))
    assert any(f.category == "duplicate" for f in report.findings)


# ------------------------------------------------------------- confidence
def test_confidence_reduced_by_unknowns():
    full = engine.check(req(["warfarin", "aspirin"]))
    partial = engine.check(req(["warfarin", "mystery-drug-zzz"]))
    assert full.confidence > partial.confidence


# ---------------------------------------------------------------- bengali
def test_bengali_output_populated():
    report = engine.check(req(["warfarin", "fluconazole"], language="bn"))
    assert report.summary_bn
    critical = report.findings[0]
    assert critical.title_bn or critical.detail_bn
