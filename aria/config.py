"""Configuration for Aria, loaded from environment / .env.

Kept deliberately small: Phase 0 needs one API key, one target URL, and a few
voice/audio knobs. Everything has a sane default except the API key.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional

try:
    # Optional: load a local .env if python-dotenv is installed.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - dotenv is a convenience, not a requirement
    pass


# Audio format for the realtime session. PCM16 mono at 24 kHz matches the
# OpenAI-Realtime-compatible default that the Grok Voice Agent API speaks.
SAMPLE_RATE = 24_000
CHANNELS = 1
SAMPLE_WIDTH = 2  # bytes per sample (16-bit)


@dataclass(frozen=True)
class Settings:
    """Resolved runtime settings."""

    xai_api_key: str
    dashboard_url: str
    voice: str
    model: str
    read_method: str  # "browser" | "fetch"
    read_max_chars: int
    greeting: str = ""           # spoken once on connect; "" disables it
    log_file: Optional[str] = None  # JSONL audit trail path; None disables it

    # Endpoint is derived from the model so the whole thing stays swappable.
    @property
    def realtime_url(self) -> str:
        return f"wss://api.x.ai/v1/realtime?model={self.model}"


DEFAULT_GREETING = (
    "Hi, I'm Aria. Try saying: open my dashboard and read me the top of the page."
)


def load_settings(*, require_key: bool = True) -> Settings:
    """Build Settings from the environment.

    Args:
        require_key: when False (e.g. ``--simulate``), a missing API key is
            tolerated so the orchestrator glue can be exercised offline.
    """

    key = os.environ.get("XAI_API_KEY", "").strip()
    if require_key and not key:
        raise SystemExit(
            "XAI_API_KEY is not set.\n"
            "  1. Copy the template:  cp .env.example .env\n"
            "  2. Add your key from https://console.x.ai\n"
            "Or run the offline demo with:  python -m aria --simulate"
        )

    # An empty ARIA_LOG_FILE disables the audit trail; unset uses the default path.
    log_file = os.environ.get("ARIA_LOG_FILE", "aria-actions.jsonl").strip() or None

    return Settings(
        xai_api_key=key,
        dashboard_url=os.environ.get("ARIA_DASHBOARD_URL", "http://localhost:8000").strip(),
        voice=os.environ.get("ARIA_VOICE", "eve").strip(),
        model=os.environ.get("ARIA_MODEL", "grok-voice-latest").strip(),
        read_method=os.environ.get("ARIA_READ_METHOD", "browser").strip().lower(),
        read_max_chars=int(os.environ.get("ARIA_READ_MAX_CHARS", "1200")),
        greeting=os.environ.get("ARIA_GREETING", DEFAULT_GREETING).strip(),
        log_file=log_file,
    )
