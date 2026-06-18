"""An offline, scripted voice provider for `python -m aria --simulate`.

It implements the same :class:`VoiceProvider` surface as the real Grok provider,
but instead of a microphone it plays out a fixed scenario: the user asks Aria to
read the dashboard, Aria acknowledges and starts narrating, the user barges in
mid-read (the task is cancelled cleanly), then asks again and lets it finish.

This exercises the real orchestrator, state machine, task, and actuation code —
only Layer 1 (the network/audio) is faked — so the Phase 0 *feel* is verifiable
with no API key, no audio hardware, and no macOS.
"""

from __future__ import annotations

import asyncio
import re
from typing import AsyncIterator, Callable, Optional

from .base import EventType, VoiceEvent, VoiceProvider


def _spoken(instructions: str) -> str:
    """Pull the literal line Aria was told to say out of the instructions."""
    m = re.search(r'"([^"]+)"', instructions)
    if m:
        return m.group(1)
    if instructions.lower().startswith("read the top"):
        return "(reads the page) " + instructions.split("page text:", 1)[-1].strip()[:200]
    return instructions


class FakeProvider(VoiceProvider):
    def __init__(self, *, log: Callable[[str], None] = print) -> None:
        self._events: asyncio.Queue[VoiceEvent] = asyncio.Queue()
        self._log = log
        self._script: Optional[asyncio.Task] = None
        self._done_timer: Optional[asyncio.Task] = None

    async def connect(self, *, instructions: str, tools: list[dict], voice: str) -> None:
        self._emit(EventType.SESSION_READY)
        self._script = asyncio.create_task(self._run_scenario())

    async def close(self) -> None:
        for t in (self._script, self._done_timer):
            if t is not None:
                t.cancel()

    # --- provider surface ---------------------------------------------------
    async def send_audio(self, pcm16: bytes) -> None:  # no mic in simulate mode
        pass

    async def send_user_text(self, text: str) -> None:
        self._log(f"  [you · typed]  {text}")

    async def create_response(self, instructions: Optional[str] = None) -> None:
        # Simulate Aria speaking: start now, finish after a short, length-based delay.
        self._emit(EventType.RESPONSE_STARTED)
        line = _spoken(instructions or "")
        self._log(f"  [aria · 🔊]   {line}")
        if self._done_timer is not None:
            self._done_timer.cancel()
        self._done_timer = asyncio.create_task(self._finish_response(line))

    async def _finish_response(self, line: str) -> None:
        try:
            await asyncio.sleep(max(0.4, min(2.0, len(line) * 0.025)))
            self._emit(EventType.RESPONSE_DONE)
        except asyncio.CancelledError:
            pass

    async def send_function_result(self, call_id: str, output: dict) -> None:
        pass

    async def cancel_response(self) -> None:
        if self._done_timer is not None:
            self._done_timer.cancel()
        # Mirror the real provider: barge-in ends the current response.
        self._emit(EventType.RESPONSE_DONE)

    def events(self) -> AsyncIterator[VoiceEvent]:
        async def _gen() -> AsyncIterator[VoiceEvent]:
            while True:
                yield await self._events.get()

        return _gen()

    # --- helpers ------------------------------------------------------------
    def _emit(self, etype: str, data: Optional[dict] = None) -> None:
        self._events.put_nowait(VoiceEvent(etype, data or {}))

    def _call_read_dashboard(self, call_id: str) -> None:
        self._emit(
            EventType.FUNCTION_CALL,
            {"name": "read_dashboard", "call_id": call_id, "arguments": "{}"},
        )

    async def _run_scenario(self) -> None:
        await asyncio.sleep(0.5)

        # Act 1: ask, then barge in mid-read.
        self._log("\n  [you · 🎙]    open my dashboard and read me the top of the page")
        self._call_read_dashboard("call_1")
        await asyncio.sleep(1.6)  # ack + "opening" play; task is mid-read
        self._log("\n  [you · 🎙]    (cutting in) wait — stop")
        self._emit(EventType.SPEECH_STARTED)  # barge-in
        await asyncio.sleep(0.4)
        self._emit(EventType.SPEECH_STOPPED)

        # Act 2: ask again and let it complete cleanly.
        await asyncio.sleep(0.8)
        self._log("\n  [you · 🎙]    okay, go ahead and read it now")
        self._call_read_dashboard("call_2")
        await asyncio.sleep(5.0)  # let ack + milestones + full read play out

        self._log("\n  [simulate] scenario complete")
        self._emit(EventType.CLOSED)
