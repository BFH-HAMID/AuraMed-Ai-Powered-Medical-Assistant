"""Node 06 — Text-to-Speech Output.

Reads diagnostic summaries and instructions aloud for illiterate or visually
impaired patients. Production synthesis uses edge-tts (neural Bengali/English
voices) or gTTS fallback; on fully offline edge nodes VOSK-compatible Piper /
Festival voices can be attached. The safety contract enforced here: the spoken
disclaimer (Node core disclaimer) is ALWAYS prepended to the audio script.
"""
from __future__ import annotations

from backend.core.disclaimer import get_spoken_disclaimer
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode


class TTSNode(BaseNode):
    node_id = 6
    node_name = "Text-to-Speech Output"
    implemented = True

    def build_script(self, text: str, language: str = "en") -> dict:
        """Return the speakable script (disclaimer first). Audio rendering is
        performed by the attached TTS backend; without one, the script itself
        is returned so any external player/screen-reader can speak it."""
        script = f"{get_spoken_disclaimer(language)}\n\n{text}"
        return {
            "status": "ok",
            "language": language,
            "audio_format": "mp3",
            "script": script,
            "spoken_disclaimer_prepended": True,
            "backend_note": (
                "Attach edge-tts/gTTS (online) or Piper (offline) to render audio; "
                "the script is ready for synthesis."
            ),
        }

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        language = payload.get("language", "en")
        return self.build_script(payload.get("text", ""), language)


tts_node = TTSNode()
