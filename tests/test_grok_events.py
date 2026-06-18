"""The Grok provider's job is to normalize the raw OpenAI-Realtime-compatible
event stream into our internal VoiceEvents. This pins down the trickiest bits:
pairing a function call's name/call_id (from output_item.added) with its
arguments (from the .done event), audio base64 decode, and barge-in/error mapping.
"""

import base64

from aria.config import Settings
from aria.voice.base import EventType
from aria.voice.grok_realtime import GrokRealtimeProvider


def _provider() -> GrokRealtimeProvider:
    settings = Settings(
        xai_api_key="test",
        dashboard_url="demo://d",
        voice="eve",
        model="grok-voice-latest",
        read_method="fetch",
        read_max_chars=100,
    )
    return GrokRealtimeProvider(settings)


def _drain(p):
    out = []
    while not p._events.empty():
        out.append(p._events.get_nowait())
    return out


def test_event_stream_is_normalized_in_order():
    p = _provider()
    raw_stream = [
        {"type": "session.updated"},
        {"type": "input_audio_buffer.speech_started"},
        {"type": "response.created"},
        {"type": "response.audio.delta", "delta": base64.b64encode(b"\x01\x02\x03\x04").decode()},
        {"type": "response.audio_transcript.delta", "delta": "Opening"},
        {
            "type": "response.output_item.added",
            "item": {"id": "item_1", "type": "function_call", "name": "read_dashboard", "call_id": "call_42"},
        },
        {"type": "response.function_call_arguments.done", "item_id": "item_1", "arguments": "{}"},
        {"type": "response.done"},
        {"type": "error", "error": {"message": "boom"}},
    ]
    for ev in raw_stream:
        p._handle(ev)

    got = _drain(p)
    assert [e.type for e in got] == [
        EventType.SESSION_READY,
        EventType.SPEECH_STARTED,
        EventType.RESPONSE_STARTED,
        EventType.AUDIO_DELTA,
        EventType.TRANSCRIPT_DELTA,
        EventType.FUNCTION_CALL,
        EventType.RESPONSE_DONE,
        EventType.ERROR,
    ]


def test_audio_delta_is_decoded_to_raw_pcm():
    p = _provider()
    p._handle({"type": "response.audio.delta", "delta": base64.b64encode(b"\x10\x20").decode()})
    (ev,) = _drain(p)
    assert ev.type == EventType.AUDIO_DELTA
    assert ev.data["audio"] == b"\x10\x20"


def test_function_call_pairs_name_callid_and_arguments():
    p = _provider()
    p._handle(
        {
            "type": "response.output_item.added",
            "item": {"id": "i9", "type": "function_call", "name": "read_dashboard", "call_id": "c9"},
        }
    )
    p._handle({"type": "response.function_call_arguments.done", "item_id": "i9", "arguments": '{"x":1}'})
    events = _drain(p)
    fn = [e for e in events if e.type == EventType.FUNCTION_CALL]
    assert fn and fn[0].data == {"name": "read_dashboard", "call_id": "c9", "arguments": '{"x":1}'}


def test_session_ready_emitted_once():
    p = _provider()
    p._handle({"type": "session.created"})
    p._handle({"type": "session.updated"})
    ready = [e for e in _drain(p) if e.type == EventType.SESSION_READY]
    assert len(ready) == 1
