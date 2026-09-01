"""HTML renderer for the AuraMed patient report pack.

The report is delivered as a **self-contained HTML document** (no external CSS,
fonts or scripts). Two reasons that matter for this project:

* Bangla text renders correctly with the reader's own system fonts — embedding
  a Bangla font + complex-script shaping into a PDF would need a heavyweight
  toolchain and would break the offline/edge deployment target;
* the browser's own "Save as PDF / Print" produces a clean A4 PDF from the
  bundled ``@page`` print stylesheet, so the patient gets a real PDF without
  the server needing one.

Every interpolated value is HTML-escaped: the patient's free-text symptoms and
diagnosis are user input.
"""
from __future__ import annotations

from html import escape

RISK_COLORS = {
    "red": ("#b91c1c", "#fef2f2", "🔴"),
    "yellow": ("#b45309", "#fffbeb", "🟡"),
    "green": ("#047857", "#ecfdf5", "🟢"),
}

_CSS = """
:root{--ink:#0f172a;--muted:#475569;--line:#e2e8f0;--brand:#0f766e;--brand-2:#0891b2}
*{box-sizing:border-box}
body{margin:0;padding:32px;background:#eef2f6;color:var(--ink);
  font-family:'Hind Siliguri','Noto Sans Bengali','SolaimanLipi','Nikosh','Inter',system-ui,sans-serif;
  font-size:14px;line-height:1.65}
.sheet{max-width:820px;margin:0 auto;background:#fff;border:1px solid var(--line);
  border-radius:14px;overflow:hidden;box-shadow:0 12px 40px rgba(15,23,42,.10)}
header.masthead{padding:22px 28px;color:#fff;
  background:linear-gradient(120deg,#0f766e 0%,#0891b2 55%,#4338ca 100%)}
.masthead .brand{display:flex;align-items:center;gap:12px;font-size:20px;font-weight:700;letter-spacing:.2px}
.masthead .brand svg{width:28px;height:28px}
.masthead .sub{opacity:.92;font-size:12.5px;margin-top:4px}
.meta{display:flex;flex-wrap:wrap;gap:18px;margin-top:14px;font-size:12.5px}
.meta div span{opacity:.8}
.disclaimer{padding:12px 28px;background:#fff7ed;border-bottom:1px solid #fed7aa;
  color:#9a3412;font-size:12.5px;font-weight:600}
.banner{padding:14px 28px;font-weight:700;font-size:15px;border-bottom:1px solid var(--line)}
section{padding:20px 28px;border-bottom:1px solid var(--line)}
section:last-of-type{border-bottom:0}
h2{margin:0 0 12px;font-size:15px;letter-spacing:.2px;color:var(--brand);
  display:flex;align-items:center;gap:8px}
h2 .n{display:inline-grid;place-items:center;width:22px;height:22px;border-radius:6px;
  background:#ccfbf1;color:#0f766e;font-size:11.5px;font-weight:800}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:10px}
.field{background:#f8fafc;border:1px solid var(--line);border-radius:9px;padding:9px 11px}
.field .k{font-size:11px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
.field .v{font-size:14.5px;font-weight:600;margin-top:2px;word-break:break-word}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{border:1px solid var(--line);padding:8px 9px;text-align:left;vertical-align:top}
th{background:#f1f5f9;font-size:11.5px;text-transform:uppercase;letter-spacing:.3px;color:#334155}
ul{margin:6px 0 0;padding-left:20px}
li{margin:4px 0}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.chip{background:#f1f5f9;border:1px solid var(--line);border-radius:999px;
  padding:2px 10px;font-size:12px}
.warn{background:#fef2f2;border:1px solid #fecaca;color:#991b1b;border-radius:9px;
  padding:10px 12px;margin-top:8px;font-size:13px}
.note{color:var(--muted);font-size:12.5px;margin-top:8px}
.sign{display:flex;justify-content:space-between;gap:24px;padding:22px 28px;flex-wrap:wrap}
.sign .box{flex:1;min-width:220px;border-top:1px solid #94a3b8;padding-top:6px;
  font-size:12px;color:var(--muted)}
footer{padding:16px 28px;background:#f8fafc;font-size:11.5px;color:var(--muted);
  border-top:1px solid var(--line)}
.toolbar{max-width:820px;margin:0 auto 16px;display:flex;gap:10px;flex-wrap:wrap}
.toolbar button{border:0;border-radius:10px;padding:10px 16px;font-size:13.5px;font-weight:700;
  cursor:pointer;background:#0f766e;color:#fff;font-family:inherit}
.toolbar button.ghost{background:#fff;color:#0f766e;border:1px solid #99f6e4}
@media print{
  @page{size:A4;margin:14mm}
  body{background:#fff;padding:0;font-size:12px}
  .sheet{border:0;border-radius:0;box-shadow:none;max-width:none}
  .toolbar{display:none !important}
  section{break-inside:avoid;page-break-inside:avoid}
  header.masthead{-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
"""

_PRINT_BUTTONS_EN = ("Print / Save as PDF", "Download this file")
_PRINT_BUTTONS_BN = ("প্রিন্ট / PDF হিসেবে সংরক্ষণ", "ফাইলটি ডাউনলোড করুন")


def _esc(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return escape(str(value))


def _num(value) -> str:
    """Render a measurement without a trailing ``.0`` (Pydantic widens to float)."""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return _esc(value)


def _field(key: str, value) -> str:
    return f'<div class="field"><div class="k">{_esc(key)}</div><div class="v">{_esc(value)}</div></div>'


def _chips(items: list[str], empty_label: str) -> str:
    if not items:
        return f'<span class="note">{_esc(empty_label)}</span>'
    return '<div class="chips">' + "".join(f'<span class="chip">{_esc(i)}</span>' for i in items) + "</div>"


def _section(number: str, title: str, body: str) -> str:
    return f'<section><h2><span class="n">{_esc(number)}</span>{_esc(title)}</h2>{body}</section>'


def render_patient_report(report: dict) -> str:
    """Render the full report pack as a standalone printable HTML document."""
    lang = report.get("language", "en")
    bn = lang.startswith("bn")
    patient = report.get("patient", {})
    assessment = report.get("assessment", {})
    diagnosis = report.get("diagnosis", {})
    triage = assessment.get("triage") or {}
    drug_safety = report.get("drug_safety") or {}
    diet = report.get("diet") or {}
    labs = report.get("lab_tests") or {}
    risk_scores = report.get("risk_scores") or {}
    protocol = diagnosis.get("protocol") or {}

    risk = report.get("risk_level", "green")
    color, tint, dot = RISK_COLORS.get(risk, RISK_COLORS["green"])

    L = (lambda en, bng: bng if bn else en)

    # ---- 1. patient identity ------------------------------------------------
    fields = "".join([
        _field(L("Patient name", "রোগীর নাম"), patient.get("name")),
        _field(L("Age", "বয়স"), f"{_num(patient.get('age_years'))} {L('years', 'বছর')}" if patient.get("age_years") is not None else "—"),
        _field(L("Sex", "লিঙ্গ"), patient.get("sex_bn") if bn else patient.get("sex")),
        _field(L("Weight", "ওজন"), f"{_num(patient.get('weight_kg'))} kg" if patient.get("weight_kg") else "—"),
        _field(L("Height", "উচ্চতা"), f"{_num(patient.get('height_cm'))} cm" if patient.get("height_cm") else "—"),
        _field("BMI", f"{_num(patient.get('bmi'))} — {patient.get('bmi_category')}" if patient.get("bmi") else "—"),
        _field(L("Phone", "মোবাইল"), patient.get("phone") or "—"),
        _field(L("ID", "আইডি"), patient.get("patient_id") or "—"),
    ])
    extra = "".join([
        _field(L("Address", "ঠিকানা"), patient.get("address") or "—"),
        _field(L("Kidney function (eGFR)", "কিডনি কার্যকারিতা (eGFR)"),
               _num(patient.get("renal_egfr")) if patient.get("renal_egfr") else "—"),
    ])
    allergy_block = (
        f'<div class="field" style="grid-column:1/-1"><div class="k">{_esc(L("Drug allergies", "ঔষধে অ্যালার্জি"))}</div>'
        f'{_chips(patient.get("allergies", []), L("No known allergy recorded", "কোনো অ্যালার্জির তথ্য নেই"))}</div>'
        f'<div class="field" style="grid-column:1/-1"><div class="k">{_esc(L("Known conditions", "পূর্ব থেকে থাকা রোগ"))}</div>'
        f'{_chips(patient.get("conditions", []), L("None recorded", "কিছু উল্লেখ নেই"))}</div>'
    )
    sec_patient = _section("১" if bn else "1", L("Patient information", "রোগীর তথ্য"),
                           f'<div class="grid">{fields}{extra}{allergy_block}</div>')

    # ---- 2. symptoms & triage ----------------------------------------------
    rows = ""
    if assessment.get("symptoms_text"):
        rows += f'<div class="field" style="grid-column:1/-1"><div class="k">{_esc(L("Symptoms", "উপসর্গ"))}</div>' \
                f'<div class="v">{_esc(assessment["symptoms_text"])}</div></div>'
    vitals = assessment.get("vitals") or {}
    if vitals:
        rows += '<div class="field" style="grid-column:1/-1"><div class="k">' \
                + _esc(L("Vitals", "ভাইটালস")) + '</div><div class="chips">' + "".join(
                    f'<span class="chip">{_esc(k)}: {_num(v)}</span>' for k, v in vitals.items()
                ) + "</div></div>"
    red_flags = [f.get("title_bn" if bn else "title_en", f.get("id")) for f in triage.get("matched_red_flags", [])]
    if red_flags:
        rows += f'<div class="warn"><strong>{_esc(L("RED FLAGS DETECTED", "রেড ফ্ল্যাগ শনাক্ত হয়েছে"))}:</strong> ' \
                f'{_esc(", ".join(str(r) for r in red_flags))}<br/>' \
                f'{_esc(L("Call", "কল করুন"))} {_esc(assessment.get("emergency_number", "999"))} ' \
                f'{_esc(L("or go to the nearest emergency department now.", "অথবা এখনই নিকটস্থ জরুরি বিভাগে যান।"))}</div>'
    advice = triage.get("immediate_advice_bn" if bn else "immediate_advice_en")
    if advice:
        rows += f'<div class="field" style="grid-column:1/-1;margin-top:8px"><div class="k">' \
                f'{_esc(L("Immediate advice", "তাৎক্ষণিক পরামর্শ"))}</div><div class="v">{_esc(advice)}</div></div>'
    first_aid = ""
    for fa in assessment.get("first_aid", []):
        first_aid += f'<div class="field" style="grid-column:1/-1;margin-top:8px"><div class="k">' \
                     f'{_esc(L("First aid", "প্রাথমিক চিকিৎসা"))}: {_esc(fa.get("title"))}</div><ul>' + "".join(
                         f"<li>{_esc(s)}</li>" for s in fa.get("steps", [])) + "</ul></div>"
    sec_triage = _section(
        "২" if bn else "2",
        L("Symptoms & triage assessment", "উপসর্গ ও ট্রয়েজ মূল্যায়ন"),
        (f'<div class="grid">{rows}</div>{first_aid}' if rows or first_aid
         else f'<p class="note">{_esc(L("No symptoms recorded for this report.", "এই রিপোর্টে কোনো উপসর্গ উল্লেখ নেই।"))}</p>'),
    )

    # ---- 3. diagnosis -------------------------------------------------------
    d_rows = _field(L("Diagnosis", "রোগ নির্ণয়"), diagnosis.get("text") or "—")
    d_rows += _field(L("Care pathway", "চিকিৎসা পথ"), protocol.get("guideline_reference") or "—")
    plain = diagnosis.get("plain_explanation")
    plain_block = ""
    if plain and plain.strip():
        plain_block = f'<div class="field" style="grid-column:1/-1;margin-top:8px"><div class="k">' \
                      f'{_esc(L("In simple words", "সহজ কথায়"))}</div><div class="v">{_esc(plain)}</div></div>'
    sec_diagnosis = _section("৩" if bn else "3", L("Diagnosis", "রোগ নির্ণয়"),
                             f'<div class="grid">{d_rows}{plain_block}</div>')

    # ---- 4. medication schedule --------------------------------------------
    meds = report.get("medications", [])
    if meds:
        head = (
            f"<tr><th>{_esc(L('Medicine', 'ঔষধ'))}</th><th>{_esc(L('Dose', 'মাত্রা'))}</th>"
            f"<th>{_esc(L('Frequency', 'কতবার'))}</th><th>{_esc(L('When to take', 'কখন খাবেন'))}</th>"
            f"<th>{_esc(L('Duration', 'কতদিন'))}</th></tr>"
        )
        body = ""
        for m in meds:
            freq = m.get("frequency") or m.get("frequency_raw") or "—"
            body += (
                f"<tr><td><strong>{_esc(m.get('name'))}</strong>"
                + (f'<br/><span class="note">{_esc(L("not in local formulary", "স্থানীয় ফর্মুলারিতে নেই"))}</span>'
                   if not m.get("in_formulary") else "")
                + f"</td><td>{_esc(m.get('dose') or '—')}</td><td>{_esc(freq)}</td>"
                f"<td>{_esc(m.get('timing') or '—')}</td><td>{_esc(m.get('duration') or '—')}</td></tr>"
            )
            for w in m.get("warnings", []):
                body += f'<tr><td colspan="5"><div class="warn">⚠ {_esc(w)}</div></td></tr>'
        med_table = f"<table>{head}{body}</table>"
        how_to = (
            L("Complete the full course even if you feel better. Do not share or reuse prescription medicines.",
              "ভালো লাগলেও পুরো কোর্স শেষ করুন। প্রেসক্রিপশনের ওষুধ অন্যকে দেবেন না বা পুনর্ব্যবহার করবেন না।")
        )
        sec_meds = _section("৪" if bn else "4", L("Medicines & how to take them", "ঔষধ ও সেবনবিধি"),
                            f"{med_table}<p class='note'>{_esc(how_to)}</p>")
    else:
        sec_meds = _section("৪" if bn else "4", L("Medicines & how to take them", "ঔষধ ও সেবনবিধি"),
                            f"<p class='note'>{_esc(L('No medicine recorded in this report.', 'এই রিপোর্টে কোনো ওষুধ উল্লেখ নেই।'))}</p>")

    # ---- 5. drug-safety findings -------------------------------------------
    findings = drug_safety.get("findings", [])
    if findings:
        rows_f = "".join(
            f"<tr><td>{_esc(f.get('severity'))}</td>"
            f"<td>{_esc(f.get('title_bn' if bn else 'title_en'))}</td>"
            f"<td>{_esc(f.get('detail_bn' if bn else 'detail_en'))}</td>"
            f"<td>{_esc(f.get('recommendation_bn' if bn else 'recommendation_en'))}</td></tr>"
            for f in findings
        )
        sec_safety = _section(
            "৫" if bn else "5", L("Drug safety check", "ঔষধ নিরাপত্তা যাচাই"),
            f"<table><tr><th>{_esc(L('Severity', 'তীব্রতা'))}</th><th>{_esc(L('Finding', 'ফলাফল'))}</th>"
            f"<th>{_esc(L('Detail', 'বিস্তারিত'))}</th><th>{_esc(L('Action', 'করণীয়'))}</th></tr>{rows_f}</table>",
        )
    else:
        sec_safety = ""

    # ---- 6. suggestions -----------------------------------------------------
    sec_suggestions = _section(
        "৬" if bn else "6", L("Advice for the patient", "রোগীর জন্য পরামর্শ"),
        "<ul>" + "".join(f"<li>{_esc(s)}</li>" for s in report.get("suggestions", [])) + "</ul>",
    )

    # ---- 7. diet ------------------------------------------------------------
    diet_items = "".join(f"<li>{_esc(d)}</li>" for d in diet.get("diet", []))
    activity_items = "".join(f"<li>{_esc(a)}</li>" for a in diet.get("activity", []))
    age_note = diet.get("age_adjustment")
    sec_diet = _section(
        "৭" if bn else "7",
        L("Diet & lifestyle plan", "খাদ্য ও জীবনযাপন পরিকল্পনা"),
        f"<p><strong>{_esc(diet.get('title', ''))}</strong></p>"
        f"<p class='note'>{_esc(L('What to eat / avoid', 'কী খাবেন / এড়াবেন'))}</p><ul>{diet_items}</ul>"
        f"<p class='note'>{_esc(L('Activity', 'শারীরিক কার্যকলাপ'))}</p><ul>{activity_items}</ul>"
        + (f"<p class='note'>{_esc(age_note)}</p>" if age_note else ""),
    )

    # ---- 8. lab tests -------------------------------------------------------
    tests = labs.get("recommended_tests", [])
    if tests:
        sec_labs = _section(
            "৮" if bn else "8", L("Recommended tests", "প্রয়োজনীয় পরীক্ষা"),
            "<ul>" + "".join(
                f"<li><strong>{_esc(t_['test'])}</strong> — {_esc(t_.get('rationale', ''))}</li>"
                for t_ in tests
            ) + f"</ul><p class='note'>{_esc(labs.get('note_bn' if bn else 'note_en', ''))}</p>",
        )
    else:
        sec_labs = ""

    # ---- 9. risk score ------------------------------------------------------
    if risk_scores:
        score_fields = "".join(
            _field(str(k).replace("_", " ").title(), _num(v) if isinstance(v, (int, float)) else v)
            for k, v in risk_scores.items()
            if isinstance(v, (int, float, str)) and k not in {"status"}
        )
        sec_risk = _section("৯" if bn else "9", L("Risk score (10-year estimate)", "ঝুঁকি স্কোর (১০ বছরের সম্ভাবনা)"),
                            f"<div class='grid'>{score_fields}</div>")
    else:
        sec_risk = ""

    # ---- assemble -----------------------------------------------------------
    print_en, print_bn = _PRINT_BUTTONS_EN, _PRINT_BUTTONS_BN
    buttons = (
        '<div class="toolbar">'
        f'<button onclick="window.print()">{_esc(print_bn if bn else print_en)}</button>'
        f'<button class="ghost" onclick="window.location.reload()">{_esc("রিলোড" if bn else "Reload")}</button>'
        "</div>"
    )

    signature = (
        '<div class="sign">'
        f'<div class="box">{_esc(L("Signature of the reviewing physician", "পর্যালোচনাকারী চিকিৎসকের স্বাক্ষর"))}</div>'
        f'<div class="box">{_esc(L("Name & BMDC registration no.", "নাম ও বিএমডিসি নিবন্ধন নম্বর"))}</div>'
        f'<div class="box">{_esc(L("Date", "তারিখ"))}</div>'
        "</div>"
    )

    sources = ", ".join(f"N{str(s['node']).zfill(2)}" for s in report.get("sources", []) if s.get("used"))
    footer = (
        "<footer>"
        f"{_esc(report.get('disclaimer', ''))}<br/>"
        f"{_esc(L('Report ID', 'রিপোর্ট আইডি'))}: <strong>{_esc(report.get('report_id'))}</strong> · "
        f"{_esc(L('Generated (UTC)', 'তৈরি (UTC)'))}: {_esc(report.get('generated_at'))} · "
        f"{_esc(L('Composed from nodes', 'সমন্বিত নোড'))}: {_esc(sources)}<br/>"
        f"{_esc(L('This document is NOT a prescription and does not replace a licensed physician.', 'এই ডকুমেন্ট কোনো প্রেসক্রিপশন নয় এবং নিবন্ধিত চিকিৎসকের বিকল্প নয়।'))}"
        "</footer>"
    )

    return f"""<!DOCTYPE html>
<html lang="{_esc(lang)}">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>AuraMed {_esc(L('Patient Report', 'রোগীর রিপোর্ট'))} — {_esc(patient.get('name', ''))}</title>
<style>{_CSS}</style>
</head>
<body>
{buttons}
<div class="sheet">
  <header class="masthead">
    <div class="brand">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <path d="M3 12h4l2-5 3 10 2-5h7"/><circle cx="12" cy="12" r="9.2" opacity=".45"/>
      </svg>
      AuraMed
    </div>
    <div class="sub">{_esc(L('AI-Powered Medical Assistant — Patient Report', 'এআই-চালিত মেডিকেল অ্যাসিস্ট্যান্ট — রোগীর রিপোর্ট'))}</div>
    <div class="meta">
      <div><span>{_esc(L('Report ID', 'রিপোর্ট আইডি'))}:</span> <strong>{_esc(report.get('report_id'))}</strong></div>
      <div><span>{_esc(L('Date', 'তারিখ'))}:</span> <strong>{_esc(str(report.get('generated_at', ''))[:10])}</strong></div>
      <div><span>{_esc(L('Language', 'ভাষা'))}:</span> <strong>{_esc('বাংলা' if bn else 'English')}</strong></div>
    </div>
  </header>
  <div class="disclaimer">⚠ {_esc(report.get('disclaimer', ''))}</div>
  <div class="banner" style="background:{tint};color:{color}">{dot} {_esc(report.get('risk_banner', ''))}</div>
  {sec_patient}
  {sec_triage}
  {sec_diagnosis}
  {sec_meds}
  {sec_safety}
  {sec_suggestions}
  {sec_diet}
  {sec_labs}
  {sec_risk}
  {signature}
  {footer}
</div>
</body>
</html>"""
