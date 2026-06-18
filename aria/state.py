"""State machine + cancellable task handle for the orchestrator.

Per the brief (Section 6, bottleneck #1), barge-in is treated as a first-class
state transition, not an afterthought. Phase 0 actuation is read-only, so a
"clean cancel" just means: stop talking, kill the in-flight task and any child
process it spawned, and leave no half-finished work. There are no GUI mutations
to roll back yet — but the cancellation plumbing is built to extend to them.
"""

from __future__ import annotations

import asyncio
import enum
from typing import Optional


class AgentState(enum.Enum):
    """Where the orchestrator is in the conversational loop."""

    IDLE = "idle"            # connected, waiting for the user
    LISTENING = "listening"  # user is speaking
    SPEAKING = "speaking"    # Aria is producing audio
    RUNNING = "running"      # a background screen task is in flight
    INTERRUPTED = "interrupted"  # barge-in landed; cancelling
    ERROR = "error"


class CancelToken:
    """A cooperative cancellation signal shared with a running task.

    Long-running actuation checks ``raise_if_cancelled()`` between steps and
    registers child processes so they can be killed the instant a barge-in
    lands, rather than waiting for the current step to finish.
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._procs: list[asyncio.subprocess.Process] = []

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def register_proc(self, proc: asyncio.subprocess.Process) -> None:
        self._procs.append(proc)

    def cancel(self) -> None:
        self._event.set()
        for proc in self._procs:
            if proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass

    def raise_if_cancelled(self) -> None:
        if self._event.is_set():
            raise asyncio.CancelledError()


class RunningTask:
    """Handle to the single in-flight background task and its cancel token."""

    def __init__(self, task: asyncio.Task, token: CancelToken, name: str) -> None:
        self.task = task
        self.token = token
        self.name = name

    async def cancel(self) -> None:
        """Signal cooperative cancel, then hard-cancel the asyncio task."""
        self.token.cancel()
        self.task.cancel()
        try:
            await self.task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001 - we are tearing down
            pass
