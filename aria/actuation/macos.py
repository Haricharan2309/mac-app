"""Deterministic OS control for Phase 0 — open a URL and read the visible text.

Strictly read-only and low-risk: nothing here sends, buys, or deletes anything
(per the Phase 0 scope in CLAUDE.md). Actuation is deterministic OS control only
(`open`, AppleScript via `osascript`) — no vision computer-use model yet.

Every subprocess is spawned via asyncio and registered with the CancelToken so a
barge-in can kill it mid-flight instead of waiting for it to return.
"""

from __future__ import annotations

import asyncio
import html
import platform
import re
import urllib.request
from typing import Optional

from ..state import CancelToken

IS_MACOS = platform.system() == "Darwin"

# Canned content for the offline demo (`demo:` URLs, used by `python -m aria
# --simulate`). Lets the *real* task + cancellation code path run deterministically
# with no network or Mac required.
_DEMO_TEXT = (
    "Morning briefing. Markets are up half a percent in early trading. "
    "Your portfolio is green, led by your index funds. "
    "Three new emails since last night, none urgent. "
    "First meeting is at 10am with the design team."
)


async def _cancellable_sleep(seconds: float, token: Optional[CancelToken]) -> None:
    """Sleep in small slices, checking the cancel token between them.

    Gives barge-in a clean cancellation boundary mid-step rather than only
    between steps — useful for both the demo and real interrupt handling.
    """
    slept = 0.0
    step = 0.05
    while slept < seconds:
        token and token.raise_if_cancelled()
        await asyncio.sleep(min(step, seconds - slept))
        slept += step


async def _run(cmd: list[str], token: Optional[CancelToken] = None, timeout: float = 15.0) -> tuple[int, str, str]:
    """Run a subprocess, cancellable via the token, returning (rc, stdout, stderr)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if token is not None:
        token.register_proc(proc)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        raise
    return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")


async def open_url(url: str, token: Optional[CancelToken] = None) -> None:
    """Open ``url`` in the user's default browser (the visible action they asked for)."""
    if url.startswith("demo:"):
        await _cancellable_sleep(0.7, token)  # simulate browser launch latency
        return
    if IS_MACOS:
        await _run(["open", url], token=token)
    else:
        # Non-mac dev: there may be no display. Opening is best-effort; the read
        # path (fetch) does not depend on it.
        try:
            await _run(["xdg-open", url], token=token, timeout=3.0)
        except Exception:
            pass


# --- Reading the visible text -------------------------------------------------

# AppleScript to pull innerText from the front tab of common browsers. Requires
# the user to enable "Allow JavaScript from Apple Events" in the browser.
_CHROME_JS = (
    'tell application "Google Chrome" to execute front window\'s active tab '
    'javascript "document.body.innerText"'
)
_SAFARI_JS = 'tell application "Safari" to do JavaScript "document.body.innerText" in front document'


async def _read_via_browser(token: Optional[CancelToken]) -> Optional[str]:
    """Try to read the front browser tab's visible text. Returns None on failure."""
    for script in (_CHROME_JS, _SAFARI_JS):
        token and token.raise_if_cancelled()
        try:
            rc, out, _err = await _run(["osascript", "-e", script], token=token, timeout=10.0)
        except Exception:
            continue
        if rc == 0 and out.strip():
            return out.strip()
    return None


def _strip_html(raw: str) -> str:
    """Very small HTML-to-text reduction for the fetch fallback."""
    raw = re.sub(r"(?is)<(script|style|head|nav|footer)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(r"(?s)<[^>]+>", " ", raw)
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n\s*", "\n\n", text)
    return text.strip()


async def _read_via_fetch(url: str, token: Optional[CancelToken]) -> Optional[str]:
    """Fetch the URL and extract readable text (no special permission needed)."""

    def _blocking() -> str:
        req = urllib.request.Request(url, headers={"User-Agent": "Aria/0.0 (+phase0)"})
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - user-supplied dashboard URL
            charset = resp.headers.get_content_charset() or "utf-8"
            return resp.read(400_000).decode(charset, "replace")

    token and token.raise_if_cancelled()
    try:
        raw = await asyncio.to_thread(_blocking)
    except Exception:
        return None
    return _strip_html(raw) or None


async def read_top_of_page(
    url: str,
    *,
    method: str = "browser",
    max_chars: int = 1200,
    token: Optional[CancelToken] = None,
) -> str:
    """Return the text near the top of the page, for reading aloud.

    ``method`` of "browser" reads the real rendered tab (most faithful) and
    falls back to "fetch" if scripting is blocked. "fetch" skips the browser
    read entirely.
    """
    if url.startswith("demo:"):
        await _cancellable_sleep(1.3, token)  # simulate the read taking a moment
        return _DEMO_TEXT[:max_chars]

    text: Optional[str] = None
    if method == "browser" and IS_MACOS:
        text = await _read_via_browser(token)
    if text is None:
        text = await _read_via_fetch(url, token)
    if not text:
        return "I opened the page, but I couldn't read any text from it."

    # "Top of the page": trim to a sentence-ish boundary near max_chars.
    text = text[: max_chars + 200]
    if len(text) > max_chars:
        cut = text.rfind(". ", 0, max_chars)
        text = text[: cut + 1] if cut > max_chars // 2 else text[:max_chars]
    return text.strip()
