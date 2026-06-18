"""Provider-agnostic voice interface.

The brief (Section 9, "Dependency risk") says to abstract providers behind our
own interface so we can swap them. The orchestrator talks only to this surface;
``GrokRealtimeProvider`` and the offline ``FakeProvider`` both implement it.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional


class EventType:
    """Normalized events flowing from a provider up to the orchestrator."""

    SESSION_READY = "session_ready"
    SPEECH_STARTED = "speech_started"      # user began speaking -> barge-in
    SPEECH_STOPPED = "speech_stopped"
    RESPONSE_STARTED = "response_started"  # Aria began a spoken response
    RESPONSE_DONE = "response_done"        # Aria finished a spoken response
    AUDIO_DELTA = "audio_delta"            # data["audio"]: PCM16 bytes to play
    TRANSCRIPT_DELTA = "transcript_delta"  # data["text"]: text of Aria's speech
    FUNCTION_CALL = "function_call"        # data: name, arguments(str), call_id
    ERROR = "error"                        # data["message"]
    CLOSED = "closed"


@dataclass
class VoiceEvent:
    type: str
    data: dict = field(default_factory=dict)


class VoiceProvider(abc.ABC):
    """A realtime, full-duplex speech provider with native tool-calling."""

    @abc.abstractmethod
    async def connect(self, *, instructions: str, tools: list[dict], voice: str) -> None:
        """Open the session and configure instructions, tools, and turn detection."""

    @abc.abstractmethod
    async def send_audio(self, pcm16: bytes) -> None:
        """Append a frame of microphone PCM16 audio to the input buffer."""

    @abc.abstractmethod
    async def send_user_text(self, text: str) -> None:
        """Inject a typed user turn (used by --text mode)."""

    @abc.abstractmethod
    async def create_response(self, instructions: Optional[str] = None) -> None:
        """Ask the model to produce a spoken response.

        ``instructions`` overrides what to say for this one response — this is how
        the orchestrator drives progress narration in Aria's own voice.
        """

    @abc.abstractmethod
    async def send_function_result(self, call_id: str, output: dict) -> None:
        """Return the result of a tool call to the model's context."""

    @abc.abstractmethod
    async def cancel_response(self) -> None:
        """Stop the in-progress spoken response (barge-in)."""

    @abc.abstractmethod
    def events(self) -> AsyncIterator[VoiceEvent]:
        """Async iterator of normalized :class:`VoiceEvent`s."""

    @abc.abstractmethod
    async def close(self) -> None:
        ...
