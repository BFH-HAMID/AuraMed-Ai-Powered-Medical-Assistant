"""Node 01 — Audio Processing & Regional Language STT.

Multilingual speech-to-text (Bengali + regional dialects), noise filtering and
medical entity recognition. Full inference uses Whisper (cloud server nodes)
or VOSK (offline edge streaming). This module defines the contract and a
lightweight deployment that clearly reports when no audio backend is present.
"""
from __future__ import annotations

from backend.core.schemas import PatientContext
from backend.nodes.base import StubNode


class AudioSTTNode(StubNode):
    node_id = 1
    node_name = "Audio Processing & Regional Language STT"
    integration = (
        "Cloud node: openai-whisper (model='large-v3') with language='bn' and "
        "a Bengali medical-term vocabulary bias. Edge node: vosk-model-bn "
        "(streaming, offline). Noise front-end: noisereduce spectral gating; "
        "entity recognition feeds Node 22 symptom tracker. Endpoint accepts "
        "multipart audio (wav/webm/m4a)."
    )

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        result = super().run(payload, patient)
        result["supported_formats"] = ["wav", "webm", "m4a", "mp3", "ogg"]
        result["supported_languages"] = ["bn", "en"]
        result["offline_backend"] = "vosk-model-small-bn-0.45"
        result["cloud_backend"] = "whisper-large-v3"
        result["next_step"] = (
            "Transcribed text is forwarded to Node 02 triage and Node 22 symptom tracker."
        )
        self.audit("audio_stt_request", details={"stub": True})
        return result


audio_stt_node = AudioSTTNode()
