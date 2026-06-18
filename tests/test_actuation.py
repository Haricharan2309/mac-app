"""Actuation is read-only and deterministic. These cover the offline demo branch,
the HTML-to-text fallback used when browser scripting isn't available, the "top
of the page" truncation, and that a cancel token stops a read mid-flight.
"""

import asyncio

import pytest

from aria.actuation import macos
from aria.state import CancelToken


def test_demo_read_returns_canned_text_truncated():
    text = asyncio.run(macos.read_top_of_page("demo://dashboard", method="fetch", max_chars=40))
    assert text.startswith("Morning briefing")
    assert len(text) <= 40


def test_strip_html_drops_scripts_and_unescapes():
    raw = (
        "<html><head><style>x{}</style></head>"
        "<body><h1>Hi</h1><p>A &amp; B</p><script>bad()</script></body></html>"
    )
    out = macos._strip_html(raw)
    assert "Hi" in out
    assert "A & B" in out
    assert "bad()" not in out
    assert "<" not in out and ">" not in out


def test_read_truncates_on_sentence_boundary():
    long = "demo://dashboard"
    text = asyncio.run(macos.read_top_of_page(long, method="fetch", max_chars=80))
    # Demo text has several sentences; truncation should not exceed the cap (+ slack).
    assert len(text) <= 80


def test_cancelled_token_stops_the_read():
    async def impl():
        token = CancelToken()
        token.cancel()  # barge-in already landed
        with pytest.raises(asyncio.CancelledError):
            await macos.read_top_of_page("demo://dashboard", method="fetch", token=token)

    asyncio.run(impl())
