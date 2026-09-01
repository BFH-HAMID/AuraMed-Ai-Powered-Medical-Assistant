# Deployment Guide

## 1. Local development (fastest)

```bash
cd AuraMed-Ai-Powered-Medical-Assistant
python3 -m venv .venv && source .venv/bin/activate     # optional
pip install -r requirements.txt
cp .env.example .env                                   # edit secrets in production
uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Open:

* App: http://localhost:8000/
* Swagger UI: http://localhost:8000/docs
* Health: http://localhost:8000/health

Run tests: `python3 -m pytest tests/`

## 2. Docker Compose (API + PostgreSQL + Redis)

```bash
cp .env.example .env       # set AURAMED_ENCRYPTION_KEY / AURAMED_AUDIT_TOKEN
docker compose up --build
```

Generate the production encryption key:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## 3. Offline edge node (clinic tablet / rural server)

The safety-critical nodes run **with no internet**: set `AURAMED_OFFLINE=1`
(or simply leave the LLM endpoints unconfigured). The engines use local JSON
knowledge bases and deterministic local LLM personas:

* Nodes 02, 05, 14, 19, 23, 22, 20, 08(local), 16(anonymize) → fully offline.
* Leave `AURAMED_LLM_A_ENDPOINT` / `AURAMED_LLM_B_ENDPOINT` empty for the
  built-in offline personas; when endpoints ARE configured, the engine uses
  the cloud clinical LLMs and automatically falls back on network failure.

### Optional on-device models (uncomment in requirements.txt)

| Capability | Cloud node | Offline edge alternative |
|---|---|---|
| STT (01) | `openai-whisper large-v3` (bn) | `vosk` bn streaming |
| OCR (04) | `microsoft/trocr-large-handwritten` | Tesseract (`ben+eng`) + Pillow |
| TTS (06) | `edge-tts` neural voices | Piper / Festival (local voices) |
| RDBMS (09) | PostgreSQL | local JSON snapshot |

System packages for full-fat nodes (Debian/Ubuntu):

```bash
apt-get install -y tesseract-ocr tesseract-ocr-ben ffmpeg
```

## 4. TLS 1.3 in transit (Node 16)

Terminate TLS at a reverse proxy (nginx example skeleton) or with uvicorn
SSL directly:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8443 \
  --ssl-keyfile=/etc/ssl/auramed.key --ssl-certfile=/etc/ssl/auramed.crt
```

nginx:

```nginx
server {
    listen 443 ssl;
    server_name auramed.clinic.local;
    ssl_protocols TLSv1.3;
    add_header Strict-Transport-Security "max-age=63072000" always;
    location / { proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; }
}
```

## 5. Compliance checklist (Node 16/26)

- [ ] Set `AURAMED_ENCRYPTION_KEY` (32-byte hex) — startup logs a warning in
      production otherwise (dev fallback is clearly labelled insecure).
- [ ] Set a strong `AURAMED_AUDIT_TOKEN`; audit endpoints return 401 without.
- [ ] TLS 1.3 at the proxy; HSTS enabled.
- [ ] `data/audit/*.jsonl` and `data/feedback/*.jsonl` shipped to immutable
      storage / SIEM; verify with `GET /api/v1/26/audit/verify`.
- [ ] PHI never logged: audit details contain counts/summaries only; free text
      passes through PII anonymization (Node 16) before LLM/audit.
- [ ] Configure data retention per local health-data regulation.

## 6. Regulatory disclaimer

Every surface (API body, response header, spoken TTS preamble, printed
leaflets) must show:

> **AuraMed AI output is for decision-support only; requires licensed
> physician review before clinical action.**
