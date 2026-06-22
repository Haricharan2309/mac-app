"""Entry point:  python -m aria  [--check | --simulate | --text]

Modes:
  (default)    Live voice loop — mic in, Aria's voice out. Needs macOS, a
               microphone, headphones, and XAI_API_KEY.
  --check      Setup pre-flight: validates your key, audio devices, and a live
               Grok connection, with a clear pass/fail. Run this first.
  --text       Type commands instead of speaking (still drives the real Grok
               session, tool call, and actuation). Handy for testing on a Mac
               without dealing with the mic. Needs XAI_API_KEY.
  --simulate   Offline scripted demo of the full loop (ack, async task,
               narration, barge-in, clean cancel). No key, mic, or Mac needed.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from .audit import ActionLog
from .config import load_settings
from .orchestrator import Orchestrator
from .tasks.registry import TOOLS
from .voice.base import EventType, VoiceConnectionError


async def _run_live() -> None:
    from .audio.io import AudioIO
    from .backoff import Backoff
    from .voice.grok_realtime import GrokRealtimeProvider

    settings = load_settings(require_key=True)
    audit = ActionLog(settings.log_file)
    backoff = Backoff()
    print("Aria — live voice. Speak into your mic; press Ctrl-C to quit.")

    # Reconnect-on-drop: an ambient agent shouldn't die on a transient network
    # blip. Each attempt gets a fresh provider/audio/orchestrator (clean state,
    # no stranded task). A bad-key failure is not retryable and exits immediately.
    while True:
        provider = GrokRealtimeProvider(settings)
        audio = AudioIO(sample_rate=24_000)
        orch = Orchestrator(settings, provider, audio, audit=audit)
        try:
            await orch.run()  # returns when the socket closes
            if orch.session_established:
                backoff.reset()  # a working session dropped; start backoff fresh
        except VoiceConnectionError as exc:
            audit.record("connect_failed", message=str(exc), retryable=exc.retryable)
            if not exc.retryable:
                raise  # bad key / no access -> surfaced by main(), exit
        finally:
            await audio.stop()
            await provider.close()

        delay = backoff.next()
        if delay is None:
            print("  [reconnect] giving up after repeated failures.")
            break
        audit.record("reconnecting", in_seconds=delay)
        print(f"  [reconnect] connection lost — retrying in {delay:.0f}s…")
        await asyncio.sleep(delay)


async def _run_text() -> None:
    from .voice.grok_realtime import GrokRealtimeProvider

    settings = load_settings(require_key=True)
    provider = GrokRealtimeProvider(settings)
    orch = Orchestrator(settings, provider, audit=ActionLog(settings.log_file))

    # Feed typed lines in as user turns alongside the normal event loop.
    async def reader() -> None:
        loop = asyncio.get_running_loop()
        while True:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            line = line.strip()
            if line:
                await provider.send_user_text(line)
                await provider.create_response()

    print('Aria — text mode. Type e.g. "open my dashboard and read me the top". Ctrl-D to quit.')
    runner = asyncio.create_task(orch.run())
    typer = asyncio.create_task(reader())
    try:
        # Stop as soon as either side finishes, and surface a crashed session
        # instead of leaving the user typing into the void.
        done, pending = await asyncio.wait(
            {runner, typer}, return_when=asyncio.FIRST_COMPLETED
        )
        for task in pending:
            task.cancel()
        for task in done:
            if task.exception() is not None:
                raise task.exception()  # type: ignore[misc]
    finally:
        await provider.close()


async def _run_simulate() -> None:
    from .voice.fake import FakeProvider

    # No key required for the offline demo; use a deterministic demo URL.
    settings = load_settings(require_key=False)
    object.__setattr__(settings, "dashboard_url", "demo://dashboard")
    provider = FakeProvider()
    audit = ActionLog()  # in-memory only for the demo
    orch = Orchestrator(settings, provider, audit=audit)
    print("Aria — offline simulation of the Phase 0 loop "
          "(ack → async task → narration → barge-in → clean cancel)\n")
    await orch.run()

    print("\n  [audit trail] what Aria recorded:")
    for e in audit.entries:
        extra = " ".join(f"{k}={v}" for k, v in e.items() if k not in ("ts", "kind"))
        print(f"    - {e['kind']:<15} {extra}")


def _check_audio() -> None:
    try:
        import sounddevice as sd  # lazy: requires PortAudio
    except Exception as exc:  # noqa: BLE001
        print(f"  • audio:   sounddevice unavailable ({exc}). "
              "Run `pip install -r requirements.txt` (PortAudio ships with the wheel on macOS).")
        return
    try:
        mic = sd.query_devices(kind="input")
        spk = sd.query_devices(kind="output")
        print(f"  ✓ mic:     {mic['name']}")
        print(f"  ✓ speaker: {spk['name']}")
    except Exception as exc:  # noqa: BLE001
        print(f"  • audio:   no usable devices found ({exc}). Check macOS Microphone permission.")


async def _run_check() -> None:
    from .voice.grok_realtime import GrokRealtimeProvider

    settings = load_settings(require_key=True)
    print("Aria — setup check\n")
    print(f"  ✓ key:     XAI_API_KEY is set ({len(settings.xai_api_key)} chars)")
    print(f"  ✓ target:  dashboard URL = {settings.dashboard_url}")
    _check_audio()

    provider = GrokRealtimeProvider(settings)
    print(f"  • connecting to {settings.realtime_url} …")
    await provider.connect(instructions="(preflight)", tools=TOOLS, voice=settings.voice)

    ready = False
    try:
        async def _watch() -> None:
            nonlocal ready
            async for ev in provider.events():
                if ev.type == EventType.SESSION_READY:
                    ready = True
                    return
                if ev.type == EventType.ERROR:
                    print(f"  ✗ server:  {ev.data.get('message', '')}")
                    return
                if ev.type == EventType.CLOSED:
                    return

        await asyncio.wait_for(_watch(), timeout=10)
    except asyncio.TimeoutError:
        print("  ✗ grok:    connected but no session-ready within 10s.")
    finally:
        await provider.close()

    if ready:
        print("  ✓ grok:    connected and session ready — your key works.\n")
        print("All set. Run:  python -m aria")
    else:
        print("\nSomething's not right above — fix it and re-run `python -m aria --check`.")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(prog="aria", description="Aria — Phase 0 voice agent")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="setup pre-flight (key, audio, connection)")
    group.add_argument("--text", action="store_true", help="type commands instead of speaking")
    group.add_argument("--simulate", action="store_true", help="offline scripted demo, no key needed")
    args = parser.parse_args()

    try:
        if args.check:
            asyncio.run(_run_check())
        elif args.simulate:
            asyncio.run(_run_simulate())
        elif args.text:
            asyncio.run(_run_text())
        else:
            asyncio.run(_run_live())
    except VoiceConnectionError as exc:
        print(f"\n✗ Couldn't connect to the voice service:\n  {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nbye 👋")


if __name__ == "__main__":
    main()
