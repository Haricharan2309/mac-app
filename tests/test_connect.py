"""Connection failures should become clear, actionable messages — not raw
tracebacks — so a first-time setup mistake (bad key, no network) is obvious.
"""

import asyncio

import pytest

import aria.voice.grok_realtime as gr
from aria.config import Settings
from aria.voice.base import VoiceConnectionError


def _settings() -> Settings:
    return Settings(
        xai_api_key="test",
        dashboard_url="demo://d",
        voice="eve",
        model="grok-voice-latest",
        read_method="fetch",
        read_max_chars=100,
    )


def test_explain_auth_from_status_code():
    class AuthErr(Exception):
        status_code = 401

    msg = gr._explain(AuthErr())
    assert "Authentication failed" in msg and "401" in msg


def test_explain_auth_from_response_attr():
    class Resp:
        status_code = 403

    class Err(Exception):
        response = Resp()

    assert "403" in gr._explain(Err())


def test_explain_rate_limit():
    class RL(Exception):
        status_code = 429

    assert "Rate limited" in gr._explain(RL())


def test_explain_network_default():
    msg = gr._explain(OSError("connection refused"))
    assert "Couldn't reach" in msg


def test_connect_wraps_transport_error(monkeypatch):
    async def impl():
        async def boom(*args, **kwargs):
            raise OSError("refused")

        monkeypatch.setattr(gr.websockets, "connect", boom)
        provider = gr.GrokRealtimeProvider(_settings())
        with pytest.raises(VoiceConnectionError) as ei:
            await provider.connect(instructions="x", tools=[], voice="eve")
        assert "Couldn't reach" in str(ei.value)

    asyncio.run(impl())


def test_connect_wraps_auth_error(monkeypatch):
    async def impl():
        class AuthErr(Exception):
            status_code = 401

        async def boom(*args, **kwargs):
            raise AuthErr()

        monkeypatch.setattr(gr.websockets, "connect", boom)
        provider = gr.GrokRealtimeProvider(_settings())
        with pytest.raises(VoiceConnectionError) as ei:
            await provider.connect(instructions="x", tools=[], voice="eve")
        assert "401" in str(ei.value)

    asyncio.run(impl())
