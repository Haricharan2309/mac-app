"""xAI Grok Voice Agent provider over WebSocket.

The Grok Voice Agent API is compatible with the OpenAI Realtime API spec, so the
event names below (``session.update``, ``input_audio_buffer.*``, ``response.*``)
match that schema. We connect to ``wss://api.x.ai/v1/realtime`` and translate the
raw events into the normalized :class:`VoiceEvent`s the orchestrator consumes.

Docs: https://docs.x.ai/developers/model-capabilities/audio/voice-agent
"""

from __future__ import annotations

import asyncio
import base64
import json
from typing import Any, AsyncIterator, Optional

import websockets

from ..config import Settings
from .base import EventType, VoiceConnectionError, VoiceEvent, VoiceProvider


def _status_code(exc: Exception):
    code = getattr(exc, "status_code", None)
    resp = getattr(exc, "response", None)
    if code is None and resp is not None:
        code = getattr(resp, "status_code", None)
    return code


def _explain(exc: Exception) -> str:
    """Turn a websocket/transport failure into an actionable, user-facing hint."""
    code = _status_code(exc)
    if code in (401, 403):
        return (
            f"Authentication failed (HTTP {code}). Your XAI_API_KEY looks invalid "
            "or lacks Voice Agent access — check it at https://console.x.ai."
        )
    if code == 429:
        return "Rate limited (HTTP 429) by xAI. Wait a moment and try again."
    if code is not None:
        return f"The xAI realtime endpoint returned HTTP {code}."
    return (
        "Couldn't reach the xAI realtime endpoint (wss://api.x.ai). Check your "
        "network connection and that the service is reachable."
    )


def _is_retryable(exc: Exception) -> bool:
    """Auth/access failures won't fix themselves; network and rate limits might."""
    return _status_code(exc) not in (401, 403)


class GrokRealtimeProvider(VoiceProvider):
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._ws: Optional[Any] = None  # websockets client connection
        self._events: asyncio.Queue[VoiceEvent] = asyncio.Queue()
        self._reader: Optional[asyncio.Task] = None
        # Track function-call items so we can pair a call_id/name (from
        # output_item.added) with its arguments (from the .done event).
        self._fn_items: dict[str, dict] = {}
        self._session_ready = False

    # --- lifecycle ----------------------------------------------------------
    async def connect(self, *, instructions: str, tools: list[dict], voice: str) -> None:
        try:
            self._ws = await websockets.connect(
                self._settings.realtime_url,
                additional_headers={"Authorization": f"Bearer {self._settings.xai_api_key}"},
                max_size=1 << 24,
            )
        except Exception as exc:  # noqa: BLE001 - normalize into an actionable error
            raise VoiceConnectionError(_explain(exc), retryable=_is_retryable(exc)) from exc
        await self._send(
            {
                "type": "session.update",
                "session": {
                    "modalities": ["audio", "text"],
                    "instructions": instructions,
                    "voice": voice,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    # Server-side VAD gives us turn-taking *and* barge-in for free:
                    # it emits input_audio_buffer.speech_started the instant the
                    # user talks over Aria.
                    "turn_detection": {"type": "server_vad"},
                    "tools": tools,
                    "tool_choice": "auto",
                },
            }
        )
        self._reader = asyncio.create_task(self._read_loop(), name="grok-reader")

    async def close(self) -> None:
        if self._reader:
            self._reader.cancel()
        if self._ws:
            await self._ws.close()

    # --- sending ------------------------------------------------------------
    async def _send(self, payload: dict) -> None:
        if self._ws is None:
            raise RuntimeError("provider not connected")
        await self._ws.send(json.dumps(payload))

    async def send_audio(self, pcm16: bytes) -> None:
        await self._send(
            {"type": "input_audio_buffer.append", "audio": base64.b64encode(pcm16).decode("ascii")}
        )

    async def send_user_text(self, text: str) -> None:
        await self._send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "message",
                    "role": "user",
                    "content": [{"type": "input_text", "text": text}],
                },
            }
        )

    async def create_response(self, instructions: Optional[str] = None) -> None:
        payload: dict = {"type": "response.create"}
        if instructions is not None:
            payload["response"] = {"instructions": instructions}
        await self._send(payload)

    async def send_function_result(self, call_id: str, output: dict) -> None:
        await self._send(
            {
                "type": "conversation.item.create",
                "item": {
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": json.dumps(output),
                },
            }
        )

    async def cancel_response(self) -> None:
        # Best-effort: with server VAD the server often auto-cancels, but we send
        # this too so barge-in stops generation immediately. Any "no active
        # response" error is surfaced as an ERROR event and ignored upstream.
        try:
            await self._send({"type": "response.cancel"})
        except Exception:  # pragma: no cover - socket may already be tearing down
            pass

    # --- receiving ----------------------------------------------------------
    def events(self) -> AsyncIterator[VoiceEvent]:
        async def _gen() -> AsyncIterator[VoiceEvent]:
            while True:
                yield await self._events.get()

        return _gen()

    async def _read_loop(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                self._handle(json.loads(raw))
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize transport errors
            await self._events.put(VoiceEvent(EventType.ERROR, {"message": str(exc)}))
        finally:
            await self._events.put(VoiceEvent(EventType.CLOSED))

    def _emit(self, etype: str, data: Optional[dict] = None) -> None:
        self._events.put_nowait(VoiceEvent(etype, data or {}))

    def _handle(self, ev: dict) -> None:
        t = ev.get("type", "")

        if t in ("session.created", "session.updated"):
            if not self._session_ready:
                self._session_ready = True
                self._emit(EventType.SESSION_READY)

        elif t == "input_audio_buffer.speech_started":
            self._emit(EventType.SPEECH_STARTED)
        elif t == "input_audio_buffer.speech_stopped":
            self._emit(EventType.SPEECH_STOPPED)

        elif t == "response.created":
            self._emit(EventType.RESPONSE_STARTED)
        elif t == "response.done":
            self._emit(EventType.RESPONSE_DONE)

        elif t in ("response.audio.delta", "response.output_audio.delta"):
            delta = ev.get("delta")
            if delta:
                self._emit(EventType.AUDIO_DELTA, {"audio": base64.b64decode(delta)})
        elif t in ("response.audio_transcript.delta", "response.output_audio_transcript.delta"):
            self._emit(EventType.TRANSCRIPT_DELTA, {"text": ev.get("delta", "")})

        elif t == "response.output_item.added":
            item = ev.get("item", {})
            if item.get("type") == "function_call":
                self._fn_items[item.get("id", "")] = {
                    "name": item.get("name", ""),
                    "call_id": item.get("call_id", ""),
                }
        elif t == "response.function_call_arguments.done":
            meta = self._fn_items.get(ev.get("item_id", ""), {})
            self._emit(
                EventType.FUNCTION_CALL,
                {
                    "name": ev.get("name") or meta.get("name", ""),
                    "call_id": ev.get("call_id") or meta.get("call_id", ""),
                    "arguments": ev.get("arguments", "{}"),
                },
            )

        elif t == "error":
            err = ev.get("error", {})
            self._emit(EventType.ERROR, {"message": err.get("message", str(err))})
