"""The orchestrator is the make-or-break of Phase 0, so these tests pin the loop:

- the spoken acknowledgment comes first, before any work or content;
- progress milestones are narrated in order, then the page content;
- a barge-in mid-task cancels the in-flight task cleanly and **never leaks the
  page content** (no half-finished read);
- a barge-in mid-speech cancels the active response and flushes audio;
- an unknown tool call is ignored (no task, nothing spoken).

Only Layer 1 is faked (a RecordingProvider stands in for the realtime socket and
a FakeAudio for the speaker); the real Orchestrator, state machine, and task
dispatch run unchanged.
"""

import asyncio

import pytest

from aria import orchestrator as orch_mod
from aria.config import Settings
from aria.orchestrator import Orchestrator
from aria.voice.base import EventType, VoiceEvent, VoiceProvider


def _settings() -> Settings:
    return Settings(
        xai_api_key="test",
        dashboard_url="demo://dashboard",
        voice="eve",
        model="grok-voice-latest",
        read_method="fetch",
        read_max_chars=200,
    )


class RecordingProvider(VoiceProvider):
    """Captures everything the orchestrator says/does and lets the test inject events."""

    def __init__(self) -> None:
        self.q: asyncio.Queue = asyncio.Queue()
        self.spoken: list[str] = []        # instructions passed to create_response
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
        # Emit a realistic response lifecycle so the idle-gating advances.
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


async def _wait_until(pred, timeout=2.0) -> bool:
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if pred():
            return True
        await asyncio.sleep(0.01)
    return pred()


def test_ack_first_then_narration_then_content(monkeypatch):
    async def impl():
        prov = RecordingProvider()
        orch = Orchestrator(_settings(), prov)

        async def fake_read(*, url, method, max_chars, token, narrate):
            await narrate("opening")
            await narrate("reading")
            return "DASHBOARD_CONTENT_HERE"

        monkeypatch.setattr(orch_mod, "run_read_dashboard", fake_read)

        run_task = asyncio.create_task(orch.run())
        prov.inject(VoiceEvent(EventType.FUNCTION_CALL, {"name": "read_dashboard", "call_id": "c1"}))

        ok = await _wait_until(lambda: prov.said("DASHBOARD_CONTENT_HERE"))
        assert ok, prov.spoken

        # Acknowledgment is spoken first, before any work product.
        assert "Opening your dashboard now." in prov.spoken[0]
        # Ordering: ack -> opening -> reading -> content.
        assert (
            prov.index_of("Opening it now")
            < prov.index_of("Reading you the top")
            < prov.index_of("DASHBOARD_CONTENT_HERE")
        )
        # The tool result was returned to the model.
        assert prov.fn_results and prov.fn_results[0][0] == "c1"

        prov.end()
        await run_task

    asyncio.run(impl())


def test_barge_in_mid_task_cancels_cleanly_without_leaking_content(monkeypatch):
    async def impl():
        prov = RecordingProvider()
        audio = FakeAudio()
        orch = Orchestrator(_settings(), prov, audio)

        gate = asyncio.Event()  # never set -> simulates a long, in-flight read

        async def fake_read(*, url, method, max_chars, token, narrate):
            await narrate("opening")
            await narrate("reading")
            await gate.wait()
            token.raise_if_cancelled()
            return "CONTENT_THAT_MUST_NOT_BE_READ"

        monkeypatch.setattr(orch_mod, "run_read_dashboard", fake_read)

        run_task = asyncio.create_task(orch.run())
        prov.inject(VoiceEvent(EventType.FUNCTION_CALL, {"name": "read_dashboard", "call_id": "c1"}))

        # Wait until the task is genuinely in flight (past "reading", awaiting the gate).
        assert await _wait_until(
            lambda: prov.said("Reading you the top") and orch._running is not None
        )
        running = orch._running.task

        # User barges in.
        prov.inject(VoiceEvent(EventType.SPEECH_STARTED))

        assert await _wait_until(lambda: orch._running is None)
        assert running.cancelled() or running.done()      # task torn down
        assert audio.stop_calls >= 1                       # playback flushed
        assert orch.state.name == "LISTENING"
        # The crucial guarantee: nothing half-finished was read aloud.
        assert not prov.said("CONTENT_THAT_MUST_NOT_BE_READ")

        prov.end()
        await run_task

    asyncio.run(impl())


def test_barge_in_during_speech_cancels_active_response(monkeypatch):
    async def impl():
        prov = RecordingProvider()
        audio = FakeAudio()
        orch = Orchestrator(_settings(), prov, audio)

        run_task = asyncio.create_task(orch.run())

        # Simulate Aria mid-sentence: a response is active and not yet done.
        prov.inject(VoiceEvent(EventType.RESPONSE_STARTED))
        assert await _wait_until(lambda: orch._response_active)

        prov.inject(VoiceEvent(EventType.SPEECH_STARTED))
        assert await _wait_until(lambda: prov.cancel_calls >= 1)
        assert audio.stop_calls >= 1
        assert not orch._response_active

        prov.end()
        await run_task

    asyncio.run(impl())


def test_unknown_tool_is_ignored(monkeypatch):
    async def impl():
        prov = RecordingProvider()
        orch = Orchestrator(_settings(), prov)

        run_task = asyncio.create_task(orch.run())
        prov.inject(VoiceEvent(EventType.FUNCTION_CALL, {"name": "launch_missiles", "call_id": "x"}))

        await asyncio.sleep(0.1)
        assert orch._running is None
        assert prov.fn_results == []   # no result sent for an unknown tool
        assert prov.spoken == []       # nothing spoken
        assert orch.state.name == "IDLE"

        prov.end()
        await run_task

    asyncio.run(impl())
