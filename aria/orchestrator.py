"""The orchestrator — Layer 4, the glue that makes Phase 0 *feel* like JARVIS.

It holds the live voice session and reconciles the core tension from the brief:
**voice is real-time, actuation is slow.** It does that with four moves, which
are the entire point of Phase 0:

1. Instant acknowledgment  — the moment the model calls ``read_dashboard`` we
   speak "Opening your dashboard now." (well under 500 ms), before any work runs.
2. Async background execution — the screen task runs as a separate asyncio task
   so it never blocks the voice loop.
3. Progress narration — coarse milestones ("opening", "reading", the content) are
   spoken as they happen, masking actuation latency.
4. Barge-in — when the user speaks, Aria stops talking *and* the in-flight task
   is cancelled cleanly (read-only, so nothing is left half-finished).

Only one model response can be active at a time, so every spoken line funnels
through :meth:`_create_response`, which waits for the session to go idle first.
"""

from __future__ import annotations

import asyncio
from typing import Callable, Optional

from .config import Settings
from .state import AgentState, CancelToken, RunningTask
from .tasks.read_dashboard import run_read_dashboard
from .tasks.registry import TOOLS
from .voice.base import EventType, VoiceEvent, VoiceProvider

SYSTEM_PROMPT = (
    "You are Aria, a warm, concise voice assistant running on the user's Mac. "
    "You speak in short, natural spoken sentences — never read out URLs, markdown, "
    "or code. You can open the user's dashboard and read the top of the page aloud "
    "by calling the read_dashboard tool. When the user asks you to do that, call the "
    "tool right away and give a quick spoken acknowledgment; progress updates and the "
    "page text will be provided to you to read out as they arrive. You only ever read "
    "things aloud — you never send, buy, change, or delete anything. If you can't do "
    "something, say so plainly."
)

# Coarse progress milestones -> the line Aria speaks. Latency masking, not status.
MILESTONES: dict[str, str] = {
    "opening": "Opening it now…",
    "reading": "Got it — it's up. Reading you the top.",
}


class Orchestrator:
    def __init__(
        self,
        settings: Settings,
        provider: VoiceProvider,
        audio=None,
        *,
        log: Callable[[str], None] = print,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.audio = audio
        self.state = AgentState.IDLE
        self._log = log

        self._running: Optional[RunningTask] = None
        self._response_active = False
        self._idle = asyncio.Event()
        self._idle.set()

    # --- main loop ----------------------------------------------------------
    async def run(self) -> None:
        await self.provider.connect(
            instructions=SYSTEM_PROMPT, tools=TOOLS, voice=self.settings.voice
        )
        if self.audio is not None:
            await self.audio.start(self.provider.send_audio)

        async for ev in self.provider.events():
            if ev.type == EventType.CLOSED:
                break
            try:
                await self._on_event(ev)
            except Exception as exc:  # noqa: BLE001 - a bad event must not kill the loop
                self._log(f"  [orchestrator error] {exc}")

    async def _on_event(self, ev: VoiceEvent) -> None:
        t = ev.type
        if t == EventType.SESSION_READY:
            self._log("  [ready] Aria is listening. Try: "
                      '"open my dashboard and read me the top of the page"')
        elif t == EventType.RESPONSE_STARTED:
            self._mark_active(True)
        elif t == EventType.RESPONSE_DONE:
            self._mark_active(False)
        elif t == EventType.AUDIO_DELTA:
            if self.audio is not None:
                self.audio.play(ev.data.get("audio", b""))
        elif t == EventType.TRANSCRIPT_DELTA:
            pass  # spoken transcript; orchestrator doesn't need to print it
        elif t == EventType.SPEECH_STARTED:
            await self._on_barge_in()
        elif t == EventType.FUNCTION_CALL:
            await self._on_function_call(ev.data)
        elif t == EventType.ERROR:
            self._log(f"  [voice error] {ev.data.get('message', '')}")

    # --- single-active-response gating --------------------------------------
    def _mark_active(self, active: bool) -> None:
        self._response_active = active
        if active:
            if self.state != AgentState.RUNNING:
                self.state = AgentState.SPEAKING
            self._idle.clear()
        else:
            self._idle.set()
            if self.state == AgentState.SPEAKING:
                self.state = AgentState.RUNNING if self._running else AgentState.IDLE

    async def _create_response(self, instructions: str) -> None:
        """Speak one response, waiting for any in-progress response to finish."""
        try:
            await asyncio.wait_for(self._idle.wait(), timeout=20)
        except asyncio.TimeoutError:
            pass  # recover from a response that never reported done
        self._idle.clear()
        self._response_active = True  # optimistic; RESPONSE_STARTED will confirm
        await self.provider.create_response(instructions=instructions)

    async def _speak(self, line: str) -> None:
        await self._create_response(f'Say to the user, naturally and briefly: "{line}"')

    # --- the one task -------------------------------------------------------
    async def _on_function_call(self, data: dict) -> None:
        if data.get("name") != "read_dashboard":
            self._log(f"  [ignored tool] {data.get('name')!r}")
            return

        call_id = data.get("call_id", "")
        # Record the result immediately so the model's context stays consistent,
        # then dispatch the real work to the background. We do NOT block the event
        # loop here — narration/ack happen inside the task so RESPONSE_DONE events
        # keep flowing.
        await self.provider.send_function_result(
            call_id, {"status": "started", "note": "opening and reading in the background"}
        )
        token = CancelToken()
        task = asyncio.create_task(self._do_read(token), name="read_dashboard")
        self._running = RunningTask(task, token, "read_dashboard")
        self.state = AgentState.RUNNING

    async def _do_read(self, token: CancelToken) -> None:
        try:
            await self._speak("Opening your dashboard now.")  # instant ack (<500ms)

            async def narrate(key: str) -> None:
                line = MILESTONES.get(key)
                if line:
                    await self._speak(line)

            text = await run_read_dashboard(
                url=self.settings.dashboard_url,
                method=self.settings.read_method,
                max_chars=self.settings.read_max_chars,
                token=token,
                narrate=narrate,
            )
            token.raise_if_cancelled()
            await self._create_response(
                "Read the top of the user's dashboard aloud, naturally and "
                "conversationally. If it's long, read just the most important lines. "
                f"Here is the page text:\n\n{text}"
            )
        except asyncio.CancelledError:
            # Clean cancel: Phase 0 actuation is read-only, so there is nothing
            # half-finished to roll back. We simply stop.
            raise
        except Exception as exc:  # noqa: BLE001
            self._log(f"  [task failed] {exc}")
            try:
                await self._speak("Sorry — I couldn't read that page.")
            except Exception:
                pass
        finally:
            if self._running is not None and self._running.token is token:
                self._running = None
                if self.state == AgentState.RUNNING:
                    self.state = AgentState.IDLE

    # --- barge-in -----------------------------------------------------------
    async def _on_barge_in(self) -> None:
        # 1) Stop talking immediately.
        if self.audio is not None:
            self.audio.stop_playback()
        await self.provider.cancel_response()
        self._response_active = False
        self._idle.set()

        # 2) Cancel any in-flight task and leave the OS clean.
        if self._running is not None:
            self._log("  [barge-in] you spoke — stopping and cancelling the task cleanly")
            self.state = AgentState.INTERRUPTED
            running, self._running = self._running, None
            await running.cancel()

        self.state = AgentState.LISTENING
