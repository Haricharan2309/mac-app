"""Shared test doubles for exercising the real Orchestrator offline.

Only Layer 1 (the realtime socket and the speaker) is faked; the orchestrator,
state machine, audit log, and task dispatch run unchanged.
"""

from __future__ import annotations

import asyncio
from typing import Optional

from aria import orchestrator as orch_mod
from aria.audit import ActionLog
from aria.config import Settings
from aria.orchestrator import Orchestrator
from aria.voice.base import EventType, VoiceEvent, VoiceProvider


def settings(greeting: str = "") -> Settings:
    return Settings(
        xai_api_key="test",
        dashboard_url="demo://dashboard",
        voice="eve",
        model="grok-voice-latest",
        read_method="fetch",
        read_max_chars=200,
        greeting=greeting,
    )


class RecordingProvider(VoiceProvider):
    """Captures what the orchestrator says/does and lets a test inject events."""

    def __init__(self) -> None:
        self.q: asyncio.Queue = asyncio.Queue()
        self.spoken: list[str] = []   # instructions passed to create_response
        self.fn_results: list = []
        self.cancel_calls = 0

    async def connect(self, *, instructions, tools, voice):
        self.inject(VoiceEvent(EventType.SESSION_READY))

    async def send_audio(self, pcm16):
        pass

    async def send_user_text(self, text):
        pass

    async def create_response(self, instructions=None):
        self.spoken.append(instructions or "")
        # Emit a realistic response lifecycle so idle-gating advances.
        self.inject(VoiceEvent(EventType.RESPONSE_STARTED))
        self.inject(VoiceEvent(EventType.RESPONSE_DONE))

    async def send_function_result(self, call_id, output):
        self.fn_results.append((call_id, output))

    async def cancel_response(self):
        self.cancel_calls += 1

    def events(self):
        async def _gen():
            while True:
                yield await self.q.get()

        return _gen()

    async def close(self):
        pass

    # --- test helpers ---
    def inject(self, ev: VoiceEvent):
        self.q.put_nowait(ev)

    def end(self):
        self.q.put_nowait(VoiceEvent(EventType.CLOSED))

    def said(self, needle: str) -> bool:
        return any(needle in s for s in self.spoken)

    def index_of(self, needle: str) -> int:
        return next(i for i, s in enumerate(self.spoken) if needle in s)


class FakeAudio:
    def __init__(self) -> None:
        self.stop_calls = 0
        self.played = bytearray()

    async def start(self, on_input_frame):
        pass

    def play(self, pcm16):
        self.played.extend(pcm16)

    def stop_playback(self):
        self.stop_calls += 1

    async def stop(self):
        pass


def make_orchestrator(
    provider: RecordingProvider,
    *,
    audio: Optional[FakeAudio] = None,
    audit: Optional[ActionLog] = None,
    greeting: str = "",
) -> Orchestrator:
    return Orchestrator(settings(greeting=greeting), provider, audio, audit=audit)


def run_read_dashboard_fake(monkeypatch, *, returns: str = "CONTENT", gate: Optional[asyncio.Event] = None):
    """Patch the task with a controllable fake that narrates, optionally waits on
    ``gate`` (to simulate a long read for barge-in tests), then returns ``returns``.
    """

    async def fake_read(*, url, method, max_chars, token, narrate):
        await narrate("opening")
        await narrate("reading")
        if gate is not None:
            await gate.wait()
        token.raise_if_cancelled()
        return returns

    monkeypatch.setattr(orch_mod, "run_read_dashboard", fake_read)
    return fake_read


async def wait_until(pred, timeout: float = 2.0) -> bool:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if pred():
            return True
        await asyncio.sleep(0.01)
    return pred()
