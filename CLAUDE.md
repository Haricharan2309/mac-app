# CLAUDE.md — Persistent Project Context

> This file is the durable context for the project. It is read at the start of every
> session so the agent keeps the product vision and current scope across sessions.
> The original product brief is reproduced verbatim in **Part B** below. **Part A** is
> the operational summary of what we are building *right now*.

---

# PART A — CURRENT WORKING SCOPE (read this first)

## What we are building NOW: Phase 0 only
A **local macOS voice agent** that runs **headless from the terminal (no GUI)**. The user
speaks to it, and it performs **ONE screen task end-to-end** while staying conversational.

**Do NOT build the full product.** Phase 1+ (intent library, vision computer-use, window
tiling, memory, proactivity) are explicitly out of scope for now.

## The one task to make work
> User says: *"open my dashboard and read me the top of the page"*
> → agent opens the browser to a URL and reads the visible content aloud.

Keep it **low-risk** — nothing that sends, buys, or deletes anything. Read-only.

## Non-negotiable behaviors (this is the entire point of Phase 0)
1. **Instant voice acknowledgment** (<500ms), *before* the task finishes.
2. **Async background execution** — the screen task runs in the background, not blocking voice.
3. **Voice progress narration** as it works ("opening it now… got it, reading…").
4. **Barge-in / interrupt** — user can speak at any moment: agent stops talking, and if a
   task is mid-run it **cancels cleanly with no half-finished state**.

> The core principle: **Voice is real-time; actuation is slow.** Reconcile with
> **async + narration + barge-in**. Optimize for the *feel* of the loop, not features.

## Stack constraints for Phase 0
- **Voice I/O:** a realtime speech-to-speech API with native tool-calling + barge-in.
  Candidates: OpenAI Realtime / Gemini Live / Grok Voice. **Provider must be confirmed
  with the user before wiring it up — do not assume; ask which API keys are needed.**
- **Orchestrator:** Python + asyncio (FastAPI only if a local server genuinely helps).
  This is the core: live voice session, background task dispatch, progress→voice narration,
  interrupt/cancel semantics.
- **Actuation:** **deterministic OS control only** (AppleScript / `osascript` / shell /
  `open` URLs). **Do NOT use a vision computer-use model yet** — that is a later phase.

## Deliverables for Phase 0
- Clean repo structure, `requirements.txt` (or `pyproject.toml`), and a `.env` for keys.
- A single command to run it (e.g. `python -m aria`).
- A README covering setup and the macOS permissions to grant (Microphone, plus any
  Accessibility/Automation prompts).

## Process / working agreement
1. **First**: propose architecture + file layout, confirm the voice provider, and list the
   exact API keys/accounts needed. **Then wait for the user.** (Do not wire up the provider
   until confirmed.)
2. Then implement **incrementally**, keeping it runnable at every step.
3. Optimize for the **FEEL** of the conversational loop, not for features.

## Git / workflow
- Develop on branch: `claude/quirky-feynman-xjufw8`.
- Commit with clear messages; push with `git push -u origin <branch>`.
- Do **not** open a pull request unless explicitly asked.

---

# PART B — ORIGINAL PRODUCT BRIEF (verbatim)

# Project Brief — "Aria"
### A voice-first AI agent that operates your computer in real time, hands-free
*(working codename — rename freely)*

---

## One-line description

A JARVIS-style desktop agent you talk to naturally. As you speak, it perceives your screen(s), operates your apps, and runs multi-step tasks **on the go** — acknowledging instantly, narrating as it works, and letting you interrupt or redirect mid-task. Conversation and execution happen **at the same time**, hands-free.

---

## 1. The end goal (vision)

An ambient, always-available desktop copilot that feels like a competent human assistant sitting at your machine — one you can speak to in plain language while you keep working or thinking.

You shouldn't have to issue step-by-step commands, stop to watch it, or touch the keyboard. You express **intent** ("how's the market looking?", "prep me for the 3pm client call", "clean up these tabs and pull the contract") and Aria infers the full set of actions, executes them across real applications, arranges your workspace, and tells you what it's doing — all while staying in live conversation with you.

The north star: **the gap between a thought and it happening on your screen collapses to a sentence.**

Long-term, this extends to multi-monitor orchestration (tiling the right context onto the right screen), proactive briefings (a morning rundown without being asked), and persistent personal memory (it knows your projects, your portfolio, your calendar, your habits). The same engine serves two very different users — a power user automating real work, and a non-technical person who just wants their computer to do things for them. Section 7 treats the everyday-person case explicitly, because the priorities there invert.

---

## 2. What we're solving (the problem)

Today you can get *one* of two things, never both:

**A) Computer-use agents** (Claude computer use, OpenAI Operator/CUA, Gemini Computer Use, NeuralAgent) can actually drive a screen — click, type, scroll, fill forms. But the interaction model is **turn-based and typed**: you write a task, hit go, and *wait and watch* while it grinds. No live conversation, no interruption, no "actually, do this instead" mid-flight.

**B) Voice assistants** (Siri, Alexa, Windows Voice Access, macOS Voice Control) are conversational and hands-free, but **command-based and shallow**: "open Chrome," "set a timer," "scroll down." They execute literal, single-step instructions. They don't infer intent and they don't do real multi-step work across your actual apps.

Aria targets the four gaps between them:

- **The interaction-model gap.** Computer-use is "type → wait → watch." Voice control is "shallow commands." Nobody offers *conversational, concurrent* operation of your real desktop.
- **The intent-vs-command gap.** Current tools need explicit steps. Aria infers full intent from casual speech: "how's the market?" → opens your dashboard, pulls live prices and relevant news, reads you a spoken analysis, and arranges it on screen — from one sentence.
- **The hands-free-friction gap.** Everyday computing is endless mechanical context-switching: alt-tabbing, hunting for windows, copy-pasting between apps. Aria does the mechanical layer while you stay heads-up and talking.
- **The concurrency gap.** You shouldn't freeze and stare while it works. Conversation and execution should **overlap** — you keep talking, it keeps doing, and the two stay in sync.

---

## 3. What we're building (the product)

A persistent voice agent running on your machine that:

1. **Listens continuously** (wake word or push-to-talk) and converses in natural, full-duplex speech — you can talk over it and interrupt.
2. **Understands intent**, not just commands — translating casual speech into a plan of multiple actions.
3. **Operates your screen(s)** — opening and navigating apps, clicking, typing, scrolling, copying between apps, filling forms, and arranging windows.
4. **Runs tasks concurrently with conversation** — it acknowledges instantly, executes in the background, and **narrates progress** back to you in voice.
5. **Stays interruptible and steerable** — "no, the other file," "skip that," "actually open Q2" all land mid-task and re-route execution.

### The core architectural principle (the thing that makes it feel like JARVIS)

This is the insight the whole product hinges on:

> **Voice is real-time. Computer-use is slow.**
>
> Natural conversation needs sub-500ms responsiveness. But operating a screen is a perceive → reason → act loop that takes *seconds per action*. If the agent goes silent and grinds a 30-second screen task while you wait, the magic dies — it feels like a sluggish macro, not JARVIS.

Aria reconciles this with an **async + narration + barge-in** loop:

- The **voice layer responds instantly** — "On it, pulling up your dashboard now."
- The **screen task runs asynchronously** in the background.
- The agent **narrates progress** into the conversation as it goes — "prices are up, grabbing the news now."
- You can **interrupt and redirect** at any moment, and the running task adapts.

Narration is doing double duty here: it's not just status, it's *latency masking*. It's the same trick games use when an elevator ride or a slow corridor hides a level load — the talking fills the dead air of slow actuation so the agent never feels frozen. Get this right and 20 seconds of computer-use feels like a conversation; get it wrong and it feels broken.

This concurrent, conversational loop is precisely what turn-based products (Operator, NeuralAgent, raw computer use) do *not* do. **It is both the differentiator and the central engineering challenge.**

---

## 4. System architecture

Four parts: three layers plus the orchestration glue that ties them together.

**Layer 1 — Voice I/O (ears & mouth).**
Real-time speech-to-speech with full-duplex streaming and barge-in (interruption). This is largely a solved component — use a realtime voice model (e.g. Gemini Flash Live, OpenAI GPT-Realtime, xAI Grok Voice, or a self-hosted option like Step-Audio / Moshi). Native tool-calling in these models means the intent brain can partly live *inside* this layer, cutting latency hops.

**Layer 2 — Intent & orchestration brain.**
Turns spoken intent into a plan: which tools to call, in what order, and how to synthesize the results into a spoken response. Handles multi-step reasoning and decides when to talk vs. when to act. Before planning, it can hit the memory store (Layer 4) for fast context retrieval.

**Layer 3 — Actuation (hands).**
The part that actually touches the machine, split into two complementary mechanisms — bifurcating the hands is the single highest-leverage technical decision in the design:
- **Computer-use model** for open-ended, vision-driven screen tasks (perceive screen → click/type). Use Claude computer use / OpenAI CUA / Gemini Computer Use. Slow, flexible, the fallback.
- **OS-level control** for deterministic actions — launching apps, focusing/typing into fields, window tiling and multi-monitor layout (e.g. yabai / AeroSpace on macOS, FancyZones on Windows), and scripting hooks (AppleScript / Shortcuts / bash). Fast, reliable, and should handle the majority of high-value intents. Asking a vision model to resize a window is expensive and brittle; a native hook does it instantly.

**Layer 4 — The orchestrator (the glue you build).**
An async service (e.g. Python + FastAPI + asyncio) that:
- holds the live voice session,
- dispatches screen tasks to run in the background,
- streams progress events back into the voice channel as narration,
- handles interrupts (cancel / clean up / re-route running tasks),
- manages state, context, and personal memory.

This glue is the actual product. The three layers are increasingly off-the-shelf; **the orchestration of real-time voice + concurrent slow actuation + interruption is the novel work** — and it's where the hard problems in Section 6 live.

Supporting systems: wake-word detection, a personal-context/memory store (projects, portfolio, calendar, preferences), and a **safety/guardrail layer** (confirmation for destructive actions, sandboxing where possible, action logging).

---

## 5. Scope & phasing

**Phase 0 — MVP vertical slice (prove the *feel*).**
Wake word → realtime voice session → **one** background screen task with live narration and barge-in (e.g. "open my trading dashboard and read me VOO," or for a general audience, "find the latest email from X and read it to me"). Goal: validate that the async-narration + interrupt loop feels natural. Weekend-scale. *This is the make-or-break test — if this feels good, the product is real.*

**Phase 1 — Intent library.**
~5–8 high-value, hand-built intents, each a defined tool the brain can route to (market check, meeting prep, morning briefing, "play something chill," send the proposal, summarize this page, inbox triage).

**Phase 2 — Open-ended computer use.**
Add the vision-based computer-use model so Aria can handle arbitrary "do X on screen" requests beyond the hand-built intents.

**Phase 3 — Workspace orchestration.**
Multi-monitor window tiling and layout — "tile everything on screen" — via OS-level window management driven by the agent.

**Phase 4 — Memory & proactivity.**
Persistent personal context and proactive behavior (unprompted morning briefing, surfacing the right context before a meeting).

**Phase 5 — Hardening.**
Robust error recovery, confirmation flows for risky actions, sandboxing, and security review.

### Non-goals (scope discipline)
- **Not a chatbot** — voice and action are the product, not a text window.
- **Not a messaging-app assistant** — that's a different architecture (background daemon over Telegram/Slack). This is real-time, on-device, screen-operating.
- **Not cloud RPA / enterprise workflow automation** — initial focus is a personal, local desktop copilot.
- **Not a wake-word novelty** — the depth is intent + concurrent execution, not "Hey computer, what time is it."

---

## 6. Engineering bottlenecks — the hard realities of the glue (Layer 4)

These are the walls you hit the moment you start building the orchestrator. None are blockers; they *are* the work. Budget your engineering time here, not on the models.

**1. State reconciliation on interrupt.**
Catching a voice interrupt is easy. Cleanly aborting a *running* computer-use task is hard. If the agent is mid-vision-loop — say, about to click "Submit" — and you cut in with "stop, open my email," the orchestrator must kill that execution path *and leave the OS clean*: no half-typed fields, stranded dialog boxes, or phantom inputs. This needs a real state machine with cancellation tokens, defined cleanup/rollback for partial GUI interactions, and a re-sync of "what the screen actually looks like now" before the next action begins. Treat barge-in as a first-class state transition, not an afterthought bolted onto a happy path.

**2. Audio ducking & self-hearing (echo cancellation).**
For full-duplex to work, the system must filter its own narration out of the microphone — otherwise it hears "pulling up the market now" as *your* input and starts talking to itself. You need aggressive acoustic echo cancellation and audio ducking (gating mic processing of its own output) at the audio layer. Unglamorous, but it's the difference between "magical" and "unusable" — and it gets dramatically harder in real rooms with speakers, background noise, and cheap mics.

**3. Frame-capture discipline for vision.**
Constantly streaming screenshots to the computer-use model burns tokens, bandwidth, and latency fast. Do **not** run a continuous video feed. The orchestrator should snap a frame only when an open-ended intent genuinely needs a visual status check, and lean on deterministic OS state (the accessibility tree, focused-element queries) the rest of the time. Frame rate is a cost-and-latency dial — tune it deliberately rather than leaving it wide open.

**4. Memory as a fast retrieval tool, not a dump.**
For the JARVIS feel, the intent brain needs sub-second context lookups *before* it plans — "who's the client for the 3pm?" should resolve via one quick tool call. That means a local vector store (Chroma / FAISS or similar) wired into the orchestrator as a retrieval tool the brain can hit mid-conversation, with a clear schema for what's indexed (calendar, contacts, projects, preferences) and tight latency. Memory that's slow or unstructured will stall the conversational loop and kill the illusion.

**De-risking accelerators:** consider **LiveKit** (or similar) to handle the realtime media transport rather than hand-rolling WebRTC/audio plumbing, and **Docker + virtual-display** sandbox patterns to contain vision computer-use during development. Both let you focus effort on the orchestration logic that's actually differentiated.

---

## 7. Designing for the everyday person

The brief so far is implicitly written for a power user — dashboards, client calls, contracts. But the same engine serves a non-technical daily user, and **for them the priorities invert.** The builder's hard problem is the orchestration; the everyday user's hard problem is *adoption* — and adoption is gated by trust, setup friction, and reliability on routine tasks, not by capability breadth. You can engineer the loop perfectly and still lose the user if these aren't right.

### Who they are
Non-technical. Uses the computer for email, browsing, shopping, documents, media, planning, and messaging. Frustrated by mechanical friction — finding files, juggling tabs, filling forms, copy-pasting between apps. Wants it to *just work* and to be trustworthy. Won't read a manual, won't learn syntax, won't debug a permission error.

### Everyday jobs-to-be-done
- **Inbox:** "find the email from my landlord and reply that I'll pay Friday."
- **Errands:** "book a haircut next Saturday morning," "reorder my usual from the pharmacy."
- **Forms:** "fill this out with my usual info."
- **Info:** "summarize this article and read it to me," "find flights to Vegas in March under $300."
- **Home & life:** "find a dinner recipe with what's in my fridge," "find that photo from the beach trip."
- **Comms:** "help me write and send a thank-you note to Aunt Sarah."
- **Money (sensitive — always gated):** "pay my electric bill" → never without an explicit, plain-language confirmation.

### The accessibility wedge (possibly the strongest first market)
For people with motor impairments, RSI, low vision, or elderly users, hands-free *competent* desktop operation isn't a convenience — it's independence. Existing accessibility tools are clunky and command-based; a true intent-based voice agent is a step-change in capability. The value is so high and the bar to beat is so low that this may be the best **beachhead** for an everyday-user product, ahead of the general consumer.

### Key criteria — what must go right (ranked)

1. **Trust is the whole game.** One consequential mistake — wrong email sent, wrong item bought, file deleted, money moved — and trust is gone *permanently*. Non-technical users can't easily diagnose or recover from errors. So: every consequential or irreversible action (send, buy, pay, delete) requires a clear confirmation with a plain-language preview of exactly what's about to happen; a one-word stop; and an easy undo. Never touch money or destructive actions silently. This matters *more* for daily users than for power users, not less.

2. **Setup and permissions must be effortless.** macOS accessibility / screen-recording / automation permissions are a notorious bounce point. A guided, near-one-tap onboarding is an adoption gate, not a nicety. If granting access feels scary or confusing, they quit before the first win.

3. **Nail the boring 80%, every time.** Breadth matters far less than rock-solid consistency on the handful of routine tasks they actually repeat. "Reply to mom" must work every single time. One failure on a routine task erodes confidence out of all proportion. Consistency beats capability.

4. **Fail safe and fail honest.** When unsure or unable, say so plainly and stop — never flail or guess at a consequential action. "I couldn't find that — did you mean the message from Tuesday?" is a good outcome. A confident wrong action is catastrophic.

5. **Obvious, immediate time-savings.** If asking-and-correcting is slower than just doing it themselves, they won't come back. For routine tasks the effort must be *noticeably* lower, and the win has to be felt in the very first session.

6. **Forgive how people actually talk.** No syntax to learn. Handle vague references ("that thing I was just looking at"), mid-sentence changes of mind, and ambiguity by asking natural clarifying questions — not by erroring or by taking a literal command too far.

7. **Understandable privacy.** "It watches my screen and remembers everything" is unsettling to a normal person. A simple, honest, local-first posture — you own and can see/clear its memory, it isn't phoning home — is necessary for comfort, not just compliance.

8. **Work in a messy real environment.** Homes are noisy (kids, TV), mics are cheap, accents vary. Robust audio — echo cancellation, noise handling, accent tolerance — matters more here than in a quiet office. This ties directly to bottleneck #2 above.

9. **Tell them what to ask.** A blank "talk to me" paralyzes non-technical users. Gentle suggestions, examples, and the agent proactively surfacing what it can do drive activation. Power users explore; daily users need a guided start.

### Reframed priority
For a daily-person product, the make-or-break is not raw capability — it's **trust + frictionless setup + flawless routine reliability + graceful failure + felt time-savings.** Build the engine for power-user depth, but if everyday adoption is the goal, these criteria gate everything, and the safe first vertical is probably read-aloud/inbox/summarization (low blast radius) rather than anything that spends money or deletes data.

---

## 8. Success criteria

The product is working — for a power user — when:
- Voice responses feel conversational (sub-500ms acknowledgment; sub-second first audio).
- You can **interrupt mid-task** and it adapts cleanly (no stranded GUI state).
- It **infers intent** from casual speech rather than needing literal step-by-step commands.
- It executes **multi-step screen tasks** across real apps.
- Execution happens **concurrently** with conversation — you're never forced to stop and watch.
- The end-to-end feeling is "talking to a competent assistant who is also driving my computer."

It's working — for an everyday user — when:
- A non-technical person completes a real task in their **first session, unaided**.
- They trust it enough to let it send / buy / pay *with* confirmation — and that trust survives weeks of use.
- They come back the next day, and it has quietly replaced a manual habit.
- When it can't do something, they're never surprised or burned by it.

---

## 9. Constraints & external risks

(Engineering bottlenecks are covered in Section 6; these are the surrounding realities.)

- **Security, permissions & trust.** An agent with screen recording + keyboard/mouse control + shell access is a large attack surface and a trust hurdle. Confirmation gating for destructive/financial actions, least-privilege design, sandboxing where possible, and full action logging are required, not optional.
- **Platform.** Computer use and window management are strongest on macOS today (broad Windows support lands later in 2026). Build Mac-first; keep the OS-control layer swappable per platform.
- **Cost.** Realtime voice plus repeated vision calls add up quickly. The deterministic-first / frame-capture-discipline strategy is also a cost-control strategy.
- **Dependency risk.** Third-party voice and computer-use APIs change, rate-limit, and have outages. Abstract providers behind your own interfaces so you can swap them.
- **The hard part is the glue, not the models.** The layers are commoditizing fast; your moat is the orchestration and the polish that makes the concurrent loop feel human.

---

## 10. Suggested stack (current, swappable)

| Layer | Choice |
|---|---|
| Voice I/O | Realtime speech-to-speech w/ barge-in (Gemini Flash Live / GPT-Realtime / Grok Voice; or self-hosted Step-Audio / Moshi) |
| Realtime media transport | LiveKit or similar (optional accelerator — avoids hand-rolling WebRTC/audio) |
| Intent brain | Native tool-calling inside the voice model, or a separate stronger LLM for complex planning |
| Hands (open-ended) | Claude computer use / OpenAI CUA / Gemini Computer Use |
| Hands (deterministic) | OS-level: app launch, yabai / AeroSpace tiling (macOS), AppleScript / Shortcuts / bash |
| Orchestrator | Python + FastAPI + asyncio (you build this — the real product) |
| Wake word | Lightweight on-device detector (optional in MVP) |
| Memory | Local vector store (Chroma / FAISS) wired as a fast retrieval tool the intent brain calls before planning |
| Sandboxing (dev) | Docker + virtual display for vision computer-use |
| Safety | Confirmation gating, least-privilege, sandboxing, action logging |

---

*Working codename "Aria" — Ambient Real-time Intelligent Assistant. Replace with your own.*
