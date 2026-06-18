"""The orchestrator is the make-or-break of Phase 0, so these tests pin the loop:

- the spoken acknowledgment comes first, before any work or content;
- progress milestones are narrated in order, then the page content;
- a barge-in mid-task cancels the in-flight task cleanly and **never leaks the
  page content** (no half-finished read);
- a barge-in mid-speech cancels the active response and flushes audio;
- an unknown tool call is ignored (no task, nothing spoken);
- a greeting is spoken on connect to tell the user what to ask.
"""

import asyncio

from tests.helpers import (
    FakeAudio,
    RecordingProvider,
    make_orchestrator,
    run_read_dashboard_fake,
    wait_until,
)
from aria.voice.base import EventType, VoiceEvent


def test_ack_first_then_narration_then_content(monkeypatch):
    async def impl():
        prov = RecordingProvider()
        orch = make_orchestrator(prov)
        run_read_dashboard_fake(monkeypatch, returns="DASHBOARD_CONTENT_HERE")

        run_task = asyncio.create_task(orch.run())
        prov.inject(VoiceEvent(EventType.FUNCTION_CALL, {"name": "read_dashboard", "call_id": "c1"}))

        assert await wait_until(lambda: prov.said("DASHBOARD_CONTENT_HERE")), prov.spoken

        # Acknowledgment is spoken first, before any work product.
        assert "Opening your dashboard now." in prov.spoken[0]
        # Ordering: ack -> opening -> reading -> content.
        assert (
            prov.index_of("Opening it now")
            < prov.index_of("Reading you the top")
            < prov.index_of("DASHBOARD_CONTENT_HERE")
        )
        assert prov.fn_results and prov.fn_results[0][0] == "c1"

        prov.end()
        await run_task

    asyncio.run(impl())


def test_barge_in_mid_task_cancels_cleanly_without_leaking_content(monkeypatch):
    async def impl():
        prov = RecordingProvider()
        audio = FakeAudio()
        orch = make_orchestrator(prov, audio=audio)
        gate = asyncio.Event()  # never set -> simulates a long, in-flight read
        run_read_dashboard_fake(monkeypatch, gate=gate, returns="CONTENT_THAT_MUST_NOT_BE_READ")

        run_task = asyncio.create_task(orch.run())
        prov.inject(VoiceEvent(EventType.FUNCTION_CALL, {"name": "read_dashboard", "call_id": "c1"}))

        # Wait until the task is genuinely in flight (past "reading", awaiting the gate).
        assert await wait_until(
            lambda: prov.said("Reading you the top") and orch._running is not None
        )
        running = orch._running.task

        prov.inject(VoiceEvent(EventType.SPEECH_STARTED))  # barge-in

        assert await wait_until(lambda: orch._running is None)
        assert running.cancelled() or running.done()      # task torn down
        assert audio.stop_calls >= 1                       # playback flushed
        assert orch.state.name == "LISTENING"
        assert not prov.said("CONTENT_THAT_MUST_NOT_BE_READ")  # nothing half-read

        prov.end()
        await run_task

    asyncio.run(impl())


def test_barge_in_during_speech_cancels_active_response():
    async def impl():
        prov = RecordingProvider()
        audio = FakeAudio()
        orch = make_orchestrator(prov, audio=audio)

        run_task = asyncio.create_task(orch.run())

        # Simulate Aria mid-sentence: a response is active and not yet done.
        prov.inject(VoiceEvent(EventType.RESPONSE_STARTED))
        assert await wait_until(lambda: orch._response_active)

        prov.inject(VoiceEvent(EventType.SPEECH_STARTED))
        assert await wait_until(lambda: prov.cancel_calls >= 1)
        assert audio.stop_calls >= 1
        assert not orch._response_active

        prov.end()
        await run_task

    asyncio.run(impl())


def test_unknown_tool_is_ignored():
    async def impl():
        prov = RecordingProvider()
        orch = make_orchestrator(prov)

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


def test_greeting_spoken_on_connect():
    async def impl():
        prov = RecordingProvider()
        orch = make_orchestrator(prov, greeting="Hi, I'm Aria.")

        run_task = asyncio.create_task(orch.run())
        assert await wait_until(lambda: prov.said("Hi, I'm Aria."))

        prov.end()
        await run_task

    asyncio.run(impl())
