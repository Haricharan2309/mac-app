"""The one Phase 0 background task: open the dashboard and read the top aloud.

This deliberately runs as a sequence of awaitable steps with cancellation checks
between them, so a barge-in can stop it cleanly at any boundary. It emits coarse
progress milestones via the ``narrate`` callback (latency masking — the talking
fills the dead air of slow actuation) and returns the page text for Aria to read.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from ..actuation import macos
from ..state import CancelToken

# A milestone key -> the orchestrator decides how Aria voices it.
Narrate = Callable[[str], Awaitable[None]]


async def run_read_dashboard(
    *,
    url: str,
    method: str,
    max_chars: int,
    token: CancelToken,
    narrate: Narrate,
) -> str:
    """Open ``url`` and return the text near the top of the page.

    Raises ``asyncio.CancelledError`` if a barge-in cancels it mid-flight.
    """
    token.raise_if_cancelled()
    await narrate("opening")           # e.g. "Opening it now…"

    await macos.open_url(url, token=token)
    token.raise_if_cancelled()
    await narrate("reading")           # e.g. "Got it, it's up — reading you the top…"

    text = await macos.read_top_of_page(
        url, method=method, max_chars=max_chars, token=token
    )
    token.raise_if_cancelled()
    return text
