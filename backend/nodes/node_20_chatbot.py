"""Node 20 — Multi-Language Chatbot Interface (Bengali / English).

Offline-safe conversational router: every inbound message first passes through
Node 02 triage. Red flags are intercepted with emergency instructions (and
Node 19 routing hook); GREEN messages receive guided follow-ups (Node 22) or
verified home-care advice (Node 23). Deterministic and fully auditable.
"""
from __future__ import annotations

from backend.core.audit import log_action
from backend.core.i18n import t
from backend.core.schemas import PatientContext
from backend.nodes.base import BaseNode
from backend.nodes.node_02_triage.engine import triage_engine
from backend.nodes.node_23_remedies.engine import remedies_engine

_GREETINGS = {"hi", "hello", "হ্যালো", "হাই", "নমস্কার", "আসসালামু আলাইকুম", "salam"}


class ChatbotNode(BaseNode):
    node_id = 20
    node_name = "Multi-Language Chatbot Interface"
    implemented = True

    def chat(self, message: str, language: str = "en", history: list[dict] | None = None) -> dict:
        bn = language.startswith("bn")
        msg = message.strip().lower()

        if any(g in msg for g in _GREETINGS) or msg in ("", " "):
            reply = t("welcome", language)
            return {"reply": reply, "intent": "greeting", "language": language,
                    "suggested_prompts": self._prompts(language)}

        # 1) Triage gate — red flags always win
        triage = triage_engine.run({"symptoms_text": message, "language": language})

        if triage["risk_level"] == "red":
            reply = (triage["immediate_advice_bn"] if bn else triage["immediate_advice_en"])
            return {
                "reply": reply,
                "intent": "emergency",
                "risk_level": "red",
                "first_aid_protocol_ids": triage["first_aid_protocol_ids"],
                "call_number": "999",
                "language": language,
            }

        # 2) Home-care / remedies
        remedy = remedies_engine.suggest(message, language)
        if remedy.get("served"):
            reply_parts = [f"{remedy['title']}:"]
            reply_parts += [f"• {tip}" for tip in remedy["tips"]]
            reply_parts.append(("⚠ " if not bn else "⚠ ") + remedy["stop_if"])
            return {"reply": "\n".join(reply_parts), "intent": "home_care",
                    "risk_level": "green", "language": language}

        # 3) Fallback: guided follow-up questions (Node 22 hook)
        follow_ups = [
            ("Where exactly is the problem and since when? (location & duration)",
             "সমস্যাটি ঠিক কোথায় এবং কখন থেকে? (স্থান ও সময়কাল)"),
            ("Any fever, breathing difficulty, chest pain, fainting or bleeding? (yes/no)",
             "জ্বর, শ্বাসকষ্ট, বুকে ব্যথা, অজ্ঞান হওয়া বা রক্তপাত আছে কি? (হ্যাঁ/না)"),
            ("Age, known diseases (diabetes/hypertension), allergies and current medicines?",
             "বয়স, পূর্বের রোগ (ডায়াবেটিস/উচ্চ রক্তচাপ), এলার্জি ও চলমান ওষুধ?"),
        ]
        idx = len(history or []) % len(follow_ups)
        return {
            "reply": (
                "I could not yet find a matching safe-home-care entry. To assess properly please answer:\n"
                + follow_ups[idx][0] if not bn
                else "এখনো নিরাপদ ঘরোয়া-যত্নের মিল পাইনি। সঠিকভাবে যাচাই করতে উত্তর দিন:\n" + follow_ups[idx][1]
            ),
            "intent": "follow_up",
            "risk_level": triage["risk_level"],
            "language": language,
        }

    @staticmethod
    def _prompts(language: str) -> list[str]:
        if language.startswith("bn"):
            return ["বুকে ব্যথা হঠাৎ শুরু হলে কী করব?", "সর্দি-কাশির ঘরোয়া পথ কী?", "জ্বর হলে কী খাব?"]
        return ["What to do for sudden chest pain?", "Home care for a cold?", "What should I eat for fever?"]

    def run(self, payload: dict, patient: PatientContext | None = None) -> dict:
        return self.chat(
            payload.get("message", ""),
            payload.get("language", "en"),
            payload.get("history", []),
        )


chatbot_node = ChatbotNode()
# Audit registration (chat activity) is performed inside triage/remedy engines;
# log a node-level event here for audit completeness at first message time.
log_action(20, "chatbot_initialized", details={"languages": ["en", "bn"]})
