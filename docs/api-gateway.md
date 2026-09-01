# API Gateway Schemas — AuraMed

Interactive OpenAPI docs are served by the running service at **`/docs`**
(Swagger UI) and the machine-readable contract at **`/openapi.json`**.

* Base URL: `http://<host>:8000`
* All responses carry `X-AuraMed-Disclaimer` header and a body `disclaimer`
  field — **decision support only, licensed physician review required.**
* Multilingual: pass `"language": "bn"` for Bengali (বাংলা) on every node.

## Universal response envelope (`AuraMedResponse`)

```jsonc
{
  "success": true,
  "node": 5,                          // architecture node 1-26
  "node_name": "Drug Safety & Allergy Check",
  "risk_level": "red",                // red | yellow | green | null
  "confidence": 0.83,                 // 0..1
  "data": { /* node-specific payload */ },
  "alerts": [ /* hard safety alerts */ ],
  "disclaimer": "AuraMed AI output is for decision-support only; requires licensed physician review before clinical action.",
  "request_id": "uuid",
  "offline": false,
  "language": "en"
}
```

Shared models: `PatientContext` (age, sex, allergies, conditions,
current_medications, renal_egfr, pregnant, language…), `RiskLevel`
(`red|yellow|green`), `Severity` (`critical|high|moderate|low|info`).

---

## Endpoint catalogue

### Layer 1 — Input & Initial Processing

| # | Method & path | Body (key fields) | `data` summary |
|---|---|---|---|
| 01 | `POST /api/v1/01/stt` | audio upload / `{language}` | STT contract + backends (Whisper cloud / VOSK offline) |
| 02 | `POST /api/v1/02/triage` | `{symptoms_text, vitals{spo2,sbp,hr,rr,temp_c,gcs}, language}` | `risk_level`, `matched_red_flags`, `first_aid_protocol_ids`, bilingual advice |
| 03 | `POST /api/v1/03/reader` | `{content, filename, anonymize}` | extracted/normalized text + PII redaction report |
| 04 | `POST /api/v1/04/ocr/prescription` | image upload / `{raw_text_lines[]}` | per-line recognized drugs, formulary match, verification policy |
| 05 | `POST /api/v1/05/drug-safety` | `{medications:[{name,dose}], patient: PatientContext}` | `safe_to_proceed`, `overall_severity`, bilingual `findings[]` |
| 06 | `POST /api/v1/06/tts` | `{text, language}` | speakable `script` with spoken disclaimer preamble |
| 07 | `POST /api/v1/07/report-comparison` | `{current:{test:value}, history:[{...}]}` | per-test delta, %, range/trend flags |

### Layer 2 — Core AI & Data Pipeline

| # | Method & path | Body | `data` summary |
|---|---|---|---|
| 08 | `POST /api/v1/08/consensus` | `{case_text, consultation_type, patient}` | `state` (agreement/partial/divergence/single_model/failed), `agreement_score`, `risk_level`, both `opinions[]`, merged differential, `claim_warnings`, `escalate_to_physician` |
| 09 | `POST /api/v1/09/ehr` | `{patient, vitals[], conditions[], medications[], family_history[], events[]}` | BMI, latest vitals, merged conditions/meds, timeline |
| 10 | `POST /api/v1/10/synthesis` | `{case_text, vitals{}, language}` | sanitized text, harmonized vitals, missing-field list, feature block for Node 08 |

### Layer 3 — Risk Assessment & Diagnostics

| # | Method & path | Body | `data` summary |
|---|---|---|---|
| 11 | `POST /api/v1/11/risk-score` | `{age_years, sex, sbp, diabetic, smoker, hdl_mg_dl, bmi, egfr…}` | CVD 10-yr %/band, diabetes score/band, CKD watch |
| 12 | `POST /api/v1/12/leaflet` | `{drug_name, language}` | bilingual patient leaflet sections |
| 13 | `POST /api/v1/13/guidelines/draft` | `{diagnosis_key, language}` | protocol draft: investigations/non-drug/drug considerations (sign-off required) |
| 14 | `GET /api/v1/14/first-aid?language=bn` | — | protocol list |
| 14 | `POST /api/v1/14/first-aid/lookup` | `{protocol_id}` or `{query}` | bilingual step-by-step first aid |
| 15 | `POST /api/v1/15/lab-tests` | `{symptoms_text, language}` | recommended tests with rationales |

### Layer 4 — Security, Infrastructure & Compliance

| # | Method & path | Body | `data` summary |
|---|---|---|---|
| 16 | `GET /api/v1/16/privacy/posture` | — | AES-256-GCM / TLS 1.3 / HIPAA-GDPR posture |
| 16 | `POST /api/v1/16/privacy/anonymize` | `{text}` | redacted text + detected PII |
| 17 | `POST /api/v1/17/explain` | `{medical_text, language}` | plain-language version, glossed terms |
| 18 | `POST /api/v1/18/diet` | `{diagnosis, age_years, language}` | regional (Bengali-plate) diet + activity plan |
| 19 | `POST /api/v1/19/routing` | `{lat, lon, condition, language}` | 3 nearest ER facilities (distance, phone, map link) + ambulances + 999 |
| 20 | `POST /api/v1/20/chat` | `{message, language, history[]}` | chatbot reply; intent (emergency/home_care/follow_up) |

### Layer 5 — Offline Accessibility & Feedback Loop

| # | Method & path | Body | `data` summary |
|---|---|---|---|
| 21 | `GET /api/v1/21/offline/status` | — | offline-capable node matrix + cache status |
| 22 | `POST /api/v1/22/symptom-tracker` | `{step_id, answer, language}` | next question/options or terminal risk level |
| 23 | `POST /api/v1/23/home-remedies` | `{complaint, language}` | tips + explicit stop-if escalation; refuses on red flags |
| 24 | `POST /api/v1/24/feedback` | `{doctor_id, node, correction, severity, outcome_label}` | queued for fine-tuning (audited) |
| 25 | `POST /api/v1/25/alternative-care` | `{condition, risk_level, language}` | conservative care plan; refuses on RED |
| 26 | `GET /api/v1/26/audit/verify` | **Bearer audit token** | hash-chain integrity report |
| 26 | `GET /api/v1/26/audit/events?limit=` | **Bearer audit token** | recent immutable audit entries |

### Patient report pack (composed document)

| Route | Body | Returns |
|---|---|---|
| `POST /api/v1/report/patient` | `{patient, symptoms_text, vitals, diagnosis, diagnosis_key, medications[], language}` | the report as JSON inside the standard envelope |
| `POST /api/v1/report/patient/download` | same | self-contained printable **HTML** file (`Content-Disposition: attachment`) |

The pack is assembled from Nodes 02, 05, 09, 11, 12, 13, 14, 15, 17 and 18 and
always contains: patient identity (name, age, sex, weight, height, BMI,
allergies, conditions), diagnosis + plain-language explanation, medicines with
dosing rules (frequency shorthand expanded, class-based timing, safety
warnings), advice for the patient, diet plan, recommended tests and risk
scores. Every report carries the disclaimer, a `requires_physician_review`
flag, a physician signature block and a `AMR-YYYYMMDD-XXXXXXXX` report id that
is written to the Node 26 audit trail.

`patient.name` is required; the download filename is ASCII-only so no PHI
leaks into filenames.

Meta: `GET /` (node registry JSON, or the web app for `Accept: text/html`),
`GET /health` (liveness + knowledge cache), `/static/*` (web UI assets).

---

## Example — Dual-AI consensus (Node 08)

```bash
curl -X POST http://localhost:8000/api/v1/08/consensus \
  -H 'Content-Type: application/json' \
  -d '{"case_text": "60yo male, crushing chest pain radiating to left arm, sweating",
       "language": "en",
       "patient": {"age_years": 60, "sex": "male", "allergies": ["penicillin"]}}'
```

## Example — Symptom tracker walk (Node 22)

```bash
# start → answer → follow-up answer → terminal
curl -X POST .../api/v1/22/symptom-tracker -d '{"step_id":"start","answer":"fever"}'
# => {"step_id":"duration", "question":"How long has it lasted?", "options":[...]}
curl -X POST .../api/v1/22/symptom-tracker -d '{"step_id":"duration","answer":"hours"}'
curl -X POST .../api/v1/22/symptom-tracker -d '{"step_id":"severity","answer":"severe"}'
# => {"terminal":true, "risk_level":"yellow", "message":"Seek medical care today…"}
```

## Conventions

* Unknown drugs / low OCR confidence never produce silent failure — they
  return explicit verification findings.
* `risk_level` at the envelope level is always `red` / `yellow` / `green` or
  `null` — a node that has not risk-stratified the case returns `null` (and, if
  it asserted a label outside the contract, the gateway echoes it back as a
  `{"risk_level_unmapped": ...}` alert instead of failing the request).
* Withheld advice is explicit: Node 23 returns
  `{"served": false, "risk_level": null|"red", "escalate_to_clinician": true}`
  plus a `{"home_care_withheld": true, "reason": "no_verified_entry"|"red_flag"}`
  alert.
* RED triage is surfaced at the envelope level (`risk_level:"red"`) for easy
  UI gating/coloring and SMS/voice alerts on the edge client.
* Audit endpoints require `Authorization: Bearer $AURAMED_AUDIT_TOKEN`.
