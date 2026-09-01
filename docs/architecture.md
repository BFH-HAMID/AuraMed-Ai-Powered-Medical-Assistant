# AuraMed System Architecture

> **Mandatory safety notice:** *AuraMed AI output is for decision-support only;
> requires licensed physician review before clinical action.* Every API
> response enforces this in the body (`disclaimer`), HTTP header
> (`X-AuraMed-Disclaimer`) and spoken TTS preamble.

AuraMed is a 26-node integrated medical AI platform designed for localized,
edge-friendly deployment in Bengali (বাংলা) + English settings (community
clinics, upazila health complexes, ambulances, offline tablets).

---

## 1. High-Level System Architecture

```mermaid
flowchart TB
    subgraph CLIENTS["🎙️ Clients (Bengali / English)"]
        direction LR
        WEB["Web / Mobile UI<br/>(PWA, works offline)"]
        VOICE["Voice Kiosk<br/>(illiterate / visually impaired)"]
        DOC["Doctor Workstation"]
        EDGE["Edge Tablet<br/>(offline clinic node)"]
    end

    subgraph GATEWAY["API GATEWAY — FastAPI"]
        GW["REST /api/v1/NN/*<br/>CORS · rate-limit · audit-token guard"]
        MID["Safety Middleware<br/>disclaimer header · PII guard · error fallback"]
    end

    subgraph L1["1 · INPUT & INITIAL PROCESSING"]
        N01["01 STT (Whisper/VOSK)<br/>Bengali dialects + noise filter"]
        N02["02 Emergency Triage<br/>RED / YELLOW / GREEN"]
        N03["03 Document Reader"]
        N04["04 Handwriting OCR<br/>(TrOCR + confidence)"]
        N05["05 Drug Safety & Allergy"]
        N06["06 TTS Output"]
        N07["07 Report Comparison"]
    end

    subgraph L2["2 · CORE AI & DATA PIPELINE"]
        N08["08 Dual-AI Consensus<br/>LLM-A + LLM-B → arbitration"]
        N09["09 EHR / Vitals / Family Hx"]
        N10["10 Data Synthesis<br/>(normalize · anonymize)"]
    end

    subgraph L3["3 · RISK & DIAGNOSTICS"]
        N11["11 Risk Predictor<br/>(CVD / DM / CKD)"]
        N12["12 Drug Leaflets"]
        N13["13 Guidelines Engine"]
        N14["14 First-Aid Guidebook"]
        N15["15 Lab Test Recommender"]
    end

    subgraph L4["4 · SECURITY, INFRA & COMPLIANCE"]
        N16["16 Privacy: AES-256-GCM<br/>TLS 1.3 · HIPAA/GDPR"]
        N17["17 Plain-Language NLG"]
        N18["18 Diet & Lifestyle"]
        N19["19 Emergency Proximity<br/>Routing (geo)"]
        N20["20 Bengali/English Chatbot"]
    end

    subgraph L5["5 · OFFLINE & FEEDBACK LOOP"]
        N21["21 Offline Node +<br/>Local Edge Cache"]
        N22["22 Symptom Tracker<br/>(decision tree)"]
        N23["23 Verified Home Remedies"]
        N24["24 Doctor Feedback<br/>(fine-tune loop)"]
        N25["25 Conservative Care Plans"]
        N26["26 Immutable Audit Log<br/>(hash-chained JSONL)"]
    end

    subgraph DATA["STORAGE / KNOWLEDGE"]
        PG[("PostgreSQL<br/>EHR · patients · telemetry")]
        REDIS[("Redis + File Cache<br/>offline knowledge base")]
        KB["Clinical Knowledge JSON<br/>drugs · red flags · first aid<br/>facilities · remedies"]
    end

    WEB & VOICE & DOC & EDGE --> GW
    GW --> MID --> N01 & N02 & N03 & N04
    N01 --> N02
    N02 -->|RED 🚨| N14 & N19
    N04 --> N05
    N02 --> N10 --> N08
    N03 & N07 & N09 --> N10
    N08 --> N11 & N13 & N15
    N05 --> N13
    N08 --> N17 --> N06
    N13 --> N12
    N11 --> N18 & N25
    N02 -->|GREEN| N22 & N23 & N20
    N20 --> N02
    N14 & N23 & N19 --> N06
    DOC -->|corrections| N24
    N24 --> N08
    L1 & L2 & L3 & L4 & L5 --> N26
    N16 -.->|encryption / anonymization| L1 & L2
    N21 -.->|powers offline| N02 & N05 & N08 & N14 & N19 & N23
    N08 & N09 --> PG
    N21 --> REDIS
    L1 & L2 & L3 --> KB
```

---

## 2. Node Map (5 layers, 26 nodes)

| Layer | Nodes |
|---|---|
| **1. Input & Initial Processing** | 01 STT · 02 Triage · 03 Reader · 04 OCR · 05 Drug Safety · 06 TTS · 07 Report Comparison |
| **2. Core AI & Data Pipeline** | 08 Dual-AI Consensus · 09 EHR/Vitals · 10 Synthesis |
| **3. Risk & Diagnostics** | 11 Risk Scores · 12 Leaflets · 13 Guidelines · 14 First Aid · 15 Lab Tests |
| **4. Security, Infra & Compliance** | 16 Privacy/HIPAA · 17 Plain-Language NLG · 18 Diet · 19 Emergency Routing · 20 Chatbot |
| **5. Offline & Feedback Loop** | 21 Offline Cache · 22 Symptom Tracker · 23 Home Remedies · 24 Doctor Feedback · 25 Alt Care · 26 Audit Log |

---

## 3. Emergency Triage Flow (Node 02 → 14 → 19)

```mermaid
flowchart TD
    A["Patient input<br/>(voice / text / OCR / chat)"] --> B{"Node 02<br/>Red-flag + vitals engine"}
    B -->|"RED 🚨<br/>chest pain · stroke · breathing<br/>bleeding · seizure · poisoning"| C["🚨 Node 19: route to nearest ER<br/>+ ambulance dispatch (999)"]
    B -->|"YELLOW ⚠<br/>persistent fever · black stool<br/>jaundice · abnormal vitals"| D["⚠ Same-day clinic visit<br/>Node 15 tests · Node 13 guideline draft"]
    B -->|"GREEN ✅"| E["Node 22 Symptom Tracker<br/>(follow-up decision tree)"]

    C --> F["Node 14: bilingual first-aid<br/>protocol steps"]
    F --> G["Node 06: spoken instructions<br/>(Bengali TTS with disclaimer preamble)"]
    D --> H["Node 08 Dual-AI consensus<br/>→ physician sign-off"]
    E --> I["Node 23 verified home remedies<br/>(with stop-if escalation rules)"]
    I --> J{"Worsening or<br/>new red flag?"}
    J -->|yes| B
    J -->|no| K["Node 25 conservative care<br/>+ Node 18 diet/lifestyle"]
    H --> L["Node 26 immutable audit log"]
    F --> L
    I --> L
```

---

## 4. Dual-AI Consensus Engine (Node 08)

See [`docs/consensus-engine.md`](./consensus-engine.md) for the detailed
sequence, agreement scoring and fail-safe behavior.

```mermaid
sequenceDiagram
    participant API as API Gateway
    participant P16 as Node 16 (Privacy)
    participant A as LLM "A"<br/>(sensitivity)
    participant B as LLM "B"<br/>(specificity)
    participant ARB as Arbitrator
    participant P05 as Node 05 (Drug Safety)
    participant AUD as Node 26 (Audit)
    participant DR as Licensed Physician

    API->>P16: case text (PHI)
    P16-->>API: anonymized text
    par Concurrent inference (timeout guarded)
        API->>A: consult(case)
        API->>B: consult(case)
    end
    Note over A,B: HTTP clinical LLMs if configured,<br/>else deterministic local personas (offline edge)
    A-->>ARB: opinion A (dx, risk, confidence, actions)
    B-->>ARB: opinion B (dx, risk, confidence, actions)
    ARB->>ARB: agreement = 0.40·risk + 0.35·primaryDx + 0.25·differential Jaccard
    ARB->>P05: verify any drug/dose claims (hallucination guard)
    ARB->>AUD: append hash-chained audit entry
    alt score ≥ 0.75 AND low risk AND no claim warnings
        ARB-->>API: AGREEMENT (still decision-support only)
    else divergence / RED / single-model / fallback used
        ARB-->>DR: ⚠ ESCALATE with both opinions side-by-side
    end
```

---

## 5. Data Security & Compliance (Nodes 16 + 26)

```mermaid
flowchart LR
    subgraph IN["In transit"]
        T1["TLS 1.3 (reverse proxy / uvicorn SSL)"]
        T2["Bearer audit token for Node 26"]
    end
    subgraph CORE["Processing"]
        C1["PII redaction<br/>email · phone (BD) · NID · name<br/>Bengali digit normalization"]
        C2["PHI never reaches LLMs raw"]
    end
    subgraph REST["At rest"]
        R1["AES-256-GCM encryption<br/>(cryptography / Fernet envelope)"]
        R2["PostgreSQL + local file store"]
    end
    subgraph AUDIT["Accountability"]
        A1["Append-only JSONL audit trail"]
        A2["SHA-256 hash chain<br/>(tamper-evident)"]
        A3["Node 24 doctor corrections logged"]
    end
    T1 --> C1 --> C2
    C2 --> R1 --> R2
    C2 --> A1 --> A2
    A3 --> A1
    A2 -.->|chain verify endpoint| A2
```

---

## 6. Edge / Offline Deployment (Node 21)

Safety-critical nodes run **without internet** from local JSON knowledge bases
and deterministic engines:

**Offline-capable:** 02 triage · 05 drug safety · 08 consensus (local
personas) · 10 synthesis · 11 risk scores · 12 leaflets · 13 guideline drafts ·
14 first aid · 16 anonymization · 17 explainer · 18 diet · 19 routing ·
20 chatbot · 21 cache · 22 tracker · 23 remedies · 26 audit.

**Cloud/accelerated when available:** 01 Whisper STT (VOSK is offline
alternative) · 04 TrOCR (Tesseract edge fallback) · 06 neural TTS · 09 EHR
PostgreSQL sync · 24 telemetry sync.

```mermaid
flowchart LR
    subgraph CLOUD["Cloud / upazila server (optional)"]
        W["Whisper STT"] --- T["TrOCR"] --- L["Clinical LLM-A/B"]
        PG[("PostgreSQL")]
    end
    subgraph EDGE["Edge clinic node (offline-first)"]
        V["VOSK STT"] --- LS["Local LLM personas"]
        FC[("File/Redis edge cache")]
        KB["Local clinical JSON KB"]
        AUD[("Hash-chained audit log")]
    end
    EDGE -->|"sync when online"| CLOUD
    CLOUD -.->|"fallback when offline"| EDGE
```
