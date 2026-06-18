"""The audit log is a safety requirement (and the live path's best debugging
aid). These cover the in-memory and on-disk behavior, plus that the orchestrator
records the key lifecycle events for a completed read and for a barge-in.
"""

import asyncio
import json

from aria.audit import ActionLog
from tests.helpers import RecordingProvider, make_orchestrator, run_read_dashboard_fake, wait_until
from aria.voice.base import EventType, VoiceEvent


def test_in_memory_when_no_path():
    log = ActionLog()
    log.record("intent", tool="read_dashboard")
    log.record("task_completed", chars=42)
    assert [e["kind"] for e in log.entries] == ["intent", "task_completed"]
    assert log.entries[1]["chars"] == 42
    assert "ts" in log.entries[0]


def test_writes_jsonl_to_disk(tmp_path):
    path = tmp_path / "nested" / "actions.jsonl"
    log = ActionLog(str(path))
    log.record("session_ready")
    log.record("barge_in", task_running=True)

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["kind"] == "session_ready"
    assert json.loads(lines[1])["task_running"] is True


def test_orchestrator_records_completed_read(monkeypatch):
    async def impl():
        prov = RecordingProvider()
        audit = ActionLog()
        orch = make_orchestrator(prov, audit=audit)
        run_read_dashboard_fake(monkeypatch, returns="HELLO_WORLD")

        run_task = asyncio.create_task(orch.run())
        prov.inject(VoiceEvent(EventType.FUNCTION_CALL, {"name": "read_dashboard", "call_id": "c1"}))
        assert await wait_until(lambda: prov.said("HELLO_WORLD"))

        kinds = [e["kind"] for e in audit.entries]
        assert "intent" in kinds
        assert "task_started" in kinds
        assert kinds.count("narrate") == 2          # opening + reading
        completed = [e for e in audit.entries if e["kind"] == "task_completed"]
        assert completed and completed[0]["chars"] == len("HELLO_WORLD")

        prov.end()
        await run_task

    asyncio.run(impl())


def test_orchestrator_records_barge_in_cancel(monkeypatch):
    async def impl():
        prov = RecordingProvider()
        audit = ActionLog()
        orch = make_orchestrator(prov, audit=audit)
        gate = asyncio.Event()
        run_read_dashboard_fake(monkeypatch, gate=gate, returns="NEVER_READ")

        run_task = asyncio.create_task(orch.run())
        prov.inject(VoiceEvent(EventType.FUNCTION_CALL, {"name": "read_dashboard", "call_id": "c1"}))
        assert await wait_until(lambda: orch._running is not None and prov.said("Reading you the top"))

        prov.inject(VoiceEvent(EventType.SPEECH_STARTED))
        assert await wait_until(lambda: orch._running is None)

        kinds = [e["kind"] for e in audit.entries]
        assert "barge_in" in kinds
        cancelled = [e for e in audit.entries if e["kind"] == "task_cancelled"]
        assert cancelled and cancelled[0]["reason"] == "barge_in"
        assert "task_completed" not in kinds  # nothing finished

        prov.end()
        await run_task

    asyncio.run(impl())
