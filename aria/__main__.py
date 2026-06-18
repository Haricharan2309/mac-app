"""Entry point:  python -m aria  [--simulate | --text]

Modes:
  (default)    Live voice loop — mic in, Aria's voice out. Needs macOS, a
               microphone, headphones, and XAI_API_KEY.
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

from .config import load_settings
from .orchestrator import Orchestrator


async def _run_live() -> None:
    from .audio.io import AudioIO
    from .voice.grok_realtime import GrokRealtimeProvider

    settings = load_settings(require_key=True)
    provider = GrokRealtimeProvider(settings)
    audio = AudioIO(sample_rate=24_000)
    orch = Orchestrator(settings, provider, audio)
    print("Aria — live voice. Speak into your mic; press Ctrl-C to quit.")
    try:
        await orch.run()
    finally:
        await audio.stop()
        await provider.close()


async def _run_text() -> None:
    from .voice.grok_realtime import GrokRealtimeProvider

    settings = load_settings(require_key=True)
    provider = GrokRealtimeProvider(settings)
    orch = Orchestrator(settings, provider)

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
    orch = Orchestrator(settings, provider)
    print("Aria — offline simulation of the Phase 0 loop "
          "(ack → async task → narration → barge-in → clean cancel)\n")
    await orch.run()


def main() -> None:
    parser = argparse.ArgumentParser(prog="aria", description="Aria — Phase 0 voice agent")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--text", action="store_true", help="type commands instead of speaking")
    group.add_argument("--simulate", action="store_true", help="offline scripted demo, no key needed")
    args = parser.parse_args()

    try:
        if args.simulate:
            asyncio.run(_run_simulate())
        elif args.text:
            asyncio.run(_run_text())
        else:
            asyncio.run(_run_live())
    except KeyboardInterrupt:
        print("\nbye 👋")


if __name__ == "__main__":
    main()
