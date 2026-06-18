# Aria — Phase 0

A local, **headless** macOS voice agent. You talk to it; it performs **one** screen
task end-to-end while staying conversational. Phase 0 exists to prove the core loop
feels right — see [`CLAUDE.md`](./CLAUDE.md) for the full product brief and scope.

> **The one task:** you say *"open my dashboard and read me the top of the page"* →
> Aria opens your browser to a URL and reads the visible content aloud. Strictly
> read-only — it never sends, buys, or deletes anything.

### What it proves (the whole point of Phase 0)
1. **Instant acknowledgment** — Aria speaks within ~half a second, *before* the task finishes.
2. **Async execution** — the screen task runs in the background; the voice loop never blocks.
3. **Progress narration** — "opening it now… got it, reading…" masks actuation latency.
4. **Barge-in** — speak any time and Aria stops talking; an in-flight task is **cancelled cleanly** (nothing half-finished).

---

## Stack

| Layer | Choice |
|---|---|
| Voice I/O | **xAI Grok Voice Agent API** (realtime speech-to-speech, server-VAD barge-in, native tool-calling). It is OpenAI-Realtime-spec compatible. |
| Orchestrator | Python + `asyncio` — the live session, background dispatch, narration, and interrupt/cancel state machine. This is the real work. |
| Actuation | Deterministic OS control only: `open` a URL + AppleScript/`osascript` to read the page. **No vision computer-use model** (that's a later phase). |

Provider access is behind a small swappable interface (`aria/voice/base.py`), so the
OpenAI-compatible schema isn't locked to xAI.

---

## Setup

Requires **macOS** and **Python 3.10+**. Headphones are recommended (Phase 0 skips
acoustic echo cancellation, so an open speaker can make Aria hear herself).

```bash
# 1. Install dependencies (a virtualenv is recommended)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Configure your key + dashboard URL
cp .env.example .env
#    then edit .env and set:
#      XAI_API_KEY=...           (from https://console.x.ai)
#      ARIA_DASHBOARD_URL=...     (whatever "my dashboard" should open)
```

`sounddevice` bundles PortAudio on macOS; no extra system install is needed.

---

## Run

```bash
python -m aria             # live voice — speak into your mic, Aria replies in voice
```

Two extra modes help you try it without a full mic setup:

```bash
python -m aria --simulate  # offline scripted demo of the whole loop — no key, mic, or audio needed
python -m aria --text      # type commands instead of speaking (still uses the real Grok session + actuation)
```

`--simulate` is the fastest way to see the loop — it plays out an ask → ack →
narration → **mid-task barge-in → clean cancel** → ask again → full read, all on
the real orchestrator code:

```
  [you · 🎙]    open my dashboard and read me the top of the page
  [aria · 🔊]   Opening your dashboard now.
  [aria · 🔊]   Opening it now…
  [aria · 🔊]   Got it — it's up. Reading you the top.
  [you · 🎙]    (cutting in) wait — stop
  [barge-in] you spoke — stopping and cancelling the task cleanly
  ...
```

### Tests

The core loop is covered by a fast, hardware-free test suite (orchestrator
ack/narration ordering, barge-in cancellation with no content leak, Grok event
parsing, actuation):

```bash
pip install -r requirements-dev.txt
pytest
```

---

## macOS permissions to grant

The first time you run live, macOS will prompt for these. All are granted under
**System Settings → Privacy & Security**:

1. **Microphone** — for your terminal app (Terminal / iTerm). Required to hear you.
2. **Automation** — the first time Aria scripts your browser to read a page, macOS
   asks to let your terminal control "Google Chrome" / "Safari". Click **OK**.
3. **(Only for the `browser` read method)** Allow JavaScript from Apple Events:
   - **Safari:** enable Develop menu (Settings → Advanced → *Show features for web
     developers*), then **Develop → Allow JavaScript from Apple Events**.
   - **Chrome:** **View → Developer → Allow JavaScript from Apple Events**.

If you'd rather not enable #3, set `ARIA_READ_METHOD=fetch` in `.env`. Aria will
still open the page in your browser (so you see it), but it reads the text by
fetching the URL instead of scripting the tab. `browser` mode automatically falls
back to `fetch` if scripting is blocked.

---

## Configuration (`.env`)

| Variable | Default | Meaning |
|---|---|---|
| `XAI_API_KEY` | _(required)_ | xAI key for the Grok Voice Agent API |
| `ARIA_DASHBOARD_URL` | `https://news.ycombinator.com` | what "my dashboard" opens |
| `ARIA_VOICE` | `eve` | Grok voice name |
| `ARIA_MODEL` | `grok-voice-latest` | realtime voice model |
| `ARIA_READ_METHOD` | `browser` | `browser` (read the real tab) or `fetch` (no extra permission) |
| `ARIA_READ_MAX_CHARS` | `1200` | how much of the top of the page to read |
| `ARIA_GREETING` | _(built-in)_ | spoken greeting on startup; empty disables it |
| `ARIA_LOG_FILE` | `aria-actions.jsonl` | local audit trail (JSONL); empty disables it |

### Audit trail & privacy

Aria appends what it heard as intent and what it did to a local **JSON Lines**
file (`aria-actions.jsonl` by default) — the brief treats action logging as a
safety requirement, and it's the most useful way to see what the live session
actually did. It's **local-first**: the file lives on your machine, you own it,
and you can delete it any time (or set `ARIA_LOG_FILE=` to turn it off). Nothing
about the log is sent anywhere.

---

## Project layout

```
aria/
  __main__.py          entry point — live / --text / --simulate
  config.py            settings from .env
  orchestrator.py      THE GLUE: session, async dispatch, narration, barge-in state machine
  state.py             state enum + cancellation tokens
  voice/
    base.py            swappable VoiceProvider interface
    grok_realtime.py   xAI Grok Voice Agent provider (WebSocket)
    fake.py            offline scripted provider for --simulate
  audio/io.py          mic capture + speaker playback (lazy sounddevice)
  tasks/
    registry.py        tool schema exposed to the model
    read_dashboard.py  the one task: open URL + read top of page
  actuation/macos.py   osascript helpers (open URL, read visible text) + fetch fallback
```

## Scope discipline

This is **Phase 0 only**. No intent library, no vision computer-use, no window
tiling, no memory. Just the one read-only task, done well, to prove the
async + narration + barge-in loop feels like a real assistant.
