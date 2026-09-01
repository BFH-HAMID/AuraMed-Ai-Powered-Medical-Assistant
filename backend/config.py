"""Central configuration for AuraMed.

Values are read from environment variables (optionally a local ``.env`` file)
so the same image can be deployed on a cloud VM or an offline edge node in a
rural clinic. No third-party dependency — works with the standard library.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Minimal .env loader (no python-dotenv dependency required at runtime)
# ---------------------------------------------------------------------------
def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(Path(__file__).resolve().parent.parent / ".env")

REPO_ROOT = Path(__file__).resolve().parent.parent


def _env(key: str, default: Any = "") -> Any:
    return os.environ.get(key, default)


@dataclass(frozen=True)
class Settings:
    """Immutable runtime settings."""

    env: str = field(default_factory=lambda: str(_env("AURAMED_ENV", "development")))
    host: str = field(default_factory=lambda: str(_env("AURAMED_HOST", "0.0.0.0")))
    port: int = field(default_factory=lambda: int(_env("AURAMED_PORT", "8000")))
    default_language: str = field(default_factory=lambda: str(_env("AURAMED_LANGUAGE", "en")))

    # Security (Node 16)
    encryption_key_hex: str = field(default_factory=lambda: str(_env("AURAMED_ENCRYPTION_KEY", "")))
    audit_token: str = field(default_factory=lambda: str(_env("AURAMED_AUDIT_TOKEN", "")))

    # Storage
    data_dir: Path = field(
        default_factory=lambda: Path(str(_env("AURAMED_DATA_DIR", str(REPO_ROOT / "data"))))
    )
    redis_url: str = field(default_factory=lambda: str(_env("REDIS_URL", "")))
    database_url: str = field(default_factory=lambda: str(_env("DATABASE_URL", "")))

    # Dual-AI Consensus (Node 08)
    llm_a_endpoint: str = field(default_factory=lambda: str(_env("AURAMED_LLM_A_ENDPOINT", "")))
    llm_b_endpoint: str = field(default_factory=lambda: str(_env("AURAMED_LLM_B_ENDPOINT", "")))
    llm_a_key: str = field(default_factory=lambda: str(_env("AURAMED_LLM_A_KEY", "")))
    llm_b_key: str = field(default_factory=lambda: str(_env("AURAMED_LLM_B_KEY", "")))
    consensus_timeout: float = field(default_factory=lambda: float(_env("AURAMED_CONSENSUS_TIMEOUT", "8.0")))
    min_confidence: float = field(default_factory=lambda: float(_env("AURAMED_MIN_CONFIDENCE", "0.65")))

    # Edge
    offline_mode: bool = field(default_factory=lambda: str(_env("AURAMED_OFFLINE", "0")) == "1")

    @property
    def audit_dir(self) -> Path:
        return self.data_dir / "audit"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def feedback_dir(self) -> Path:
        return self.data_dir / "feedback"

    @property
    def models_dir(self) -> Path:
        return REPO_ROOT / "models"

    def validate(self) -> list[str]:
        """Return a list of configuration warnings (non-fatal)."""
        warnings: list[str] = []
        if self.env == "production":
            if not self.encryption_key_hex:
                warnings.append(
                    "AURAMED_ENCRYPTION_KEY is not set — PHI encryption at rest (Node 16) "
                    "is using an EPHEMERAL dev key. Set a 64-hex-char key in production."
                )
            if self.audit_token in ("", "change-me-audit-token"):
                warnings.append(
                    "AURAMED_AUDIT_TOKEN is default/empty — the regulatory audit trail "
                    "(Node 26) must be token-protected in production."
                )
        if self.offline_mode and (self.llm_a_endpoint or self.llm_b_endpoint):
            warnings.append(
                "Offline mode is ON but cloud LLM endpoints are configured; the edge "
                "node will still fall back to local models if cloud calls fail."
            )
        return warnings


settings = Settings()

# Ensure runtime directories exist (created, git-ignored).
for _d in (settings.audit_dir, settings.cache_dir, settings.feedback_dir):
    _d.mkdir(parents=True, exist_ok=True)
