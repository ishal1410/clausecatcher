"""
alert_agent.py -- Voice Agent wrapper for ClauseCatcher's compliance-alert
path (ADR-0001, Option B). Owns exactly the Voice Agent session that SPEAKS
an alert (built from the contract's literal text upstream, never from this
file) and answers monitor Q&A via the client-side `lookup_clause` tool.

This session must NEVER receive rep audio. Per PROTOCOL.md's "Reply-control
doc check" section, there is no documented listen-only/no-auto-reply mode
for the Voice Agent API -- the only safe design is to never feed it rep
audio at all. It is driven purely by `conversation.message` + `reply.create`
injections (Q1 mechanism, PROTOCOL.md) built by the caller (spikes/chain/
spike_chain.py) from Streaming STT v3 finalized turns. `ask(question_wav=...)`
is the one place this class sends `input.audio` -- that is the MONITOR's own
question audio, a different mic feed entirely, not rep audio.

Reuses (imports, never copies) verified protocol plumbing from
spikes/voice_agent/spike_voice_agent.py: TOKEN_URL/get_token, WS_URL_BASE,
SessionSetupError/SessionSetupTimeout, classify_setup_event, load_wav,
stream_wav -- and the session.update -> wait-for-session.ready handshake
those imply. That module isn't a package (no __init__.py anywhere under
spikes/), so it's loaded via importlib.util.spec_from_file_location, the
same technique voice_agent/test_session_ready.py already uses. Its own
constants are read, never mutated; spike_voice_agent.py itself is not edited.

conversation.message `role`: PROTOCOL.md's events-reference field table
documents exactly two values, "user" | "system", with no documented
behavioral difference between them -- but role="system" is UNPROVEN live.
The only live-proven injection shape (Q1, 2026-09-13, spike_voice_agent.py)
is role="user" + reply.create, which spoke the injected text with 0
user-transcript echo. speak() therefore defaults ALERT_ROLE to "user";
callers that need a different role (e.g. once "system" is itself
live-verified) pass `alert_role=` to the constructor. Every speak()/ask()
result records which role was actually used (`role`) so callers/tests never
have to assume it.

Cost guard: HARD_SESSION_CAP_S bounds total time inside one open()..close()
session (the background reader task self-terminates at that deadline); every
`await` in this file is itself individually bounded (asyncio.wait_for or a
bounded recv/send helper). est_cost_usd = elapsed-since-open * $4.50/hr
(verified Voice Agent pricing, PROTOCOL.md "Billing figures").
"""
from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import json
import re
import time
import wave
from pathlib import Path

import websockets
import websockets.exceptions

_VOICE_AGENT_SPIKE = Path(__file__).resolve().parent / "spike_voice_agent.py"


def _load_spike_voice_agent():
    spec = importlib.util.spec_from_file_location("_spike_voice_agent_reuse", _VOICE_AGENT_SPIKE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_sva = _load_spike_voice_agent()

COST_PER_SEC = 4.50 / 3600.0  # verified Voice Agent pricing, PROTOCOL.md "Billing figures"
HARD_SESSION_CAP_S = 90       # hard cap on time spent inside one open()..close() session
CONNECT_TIMEOUT_S = 15
SESSION_READY_TIMEOUT_S = 10
CLEANUP_TIMEOUT_S = 3
SEND_TIMEOUT_S = 5            # bounds every individual ws.send()
REPLY_TIMEOUT_S = 20          # bound on waiting for reply.done after speak()/ask() triggers a reply
TOOL_WAIT_TIMEOUT_S = 15      # bound on waiting for a tool.call to arrive after ask()

ALERT_ROLE = "user"  # see module docstring: the only live-proven injection role (Q1); override via alert_role= kwarg

REQUIRED_ASK_WAV_RATE = 24000  # ask(question_wav=...) refuses anything else -- see module docstring / ask()

SYSTEM_PROMPT = (
    "You are a terse compliance assistant. When given a compliance alert, "
    "read it back verbatim -- word for word, no additions, no commentary. "
    "When asked about a contract clause, call the lookup_clause tool with "
    "its id and read back exactly what it returns."
)


def _normalize(s: str) -> str:
    """lowercase, strip punctuation, collapse whitespace -- used for the
    verbatim (literal_spoken) check so a TTS-introduced comma or double
    space doesn't register as a mismatch."""
    s = re.sub(r"[^\w\s]", "", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def _literal_spoken(literal_text: str, agent_transcript: str) -> bool:
    """True iff the normalized literal_text is a substring of the
    normalized agent_transcript. Empty literal_text is never "spoken"."""
    literal_text = _normalize(literal_text)
    return bool(literal_text) and literal_text in _normalize(agent_transcript)


def _clause_lookup_map(clauses) -> dict:
    """Normalize `clauses` (list of dicts) to {str(id): literal_text}.
    Accepts either the {"id","text"} shape used by spike_two_path.py's
    FAKE_CLAUSES/spike_chain.py, or the raw fake_contract.json shape
    {"section_number","literal_text"}."""
    out = {}
    for c in clauses:
        cid = c.get("id", c.get("section_number"))
        text = c.get("text", c.get("literal_text"))
        if cid is not None:
            out[str(cid)] = text
    return out


class AlertAgent:
    """One Voice Agent API session used only to SPEAK compliance alerts and
    answer monitor questions via lookup_clause. Never fed rep audio (see
    module docstring)."""

    def __init__(self, api_key, clauses, *, ws_url=None, token_fetch=None, clock=time.monotonic,
                 alert_role=None):
        self.api_key = api_key
        self.clause_map = _clause_lookup_map(clauses)
        self.ws_url = ws_url or _sva.WS_URL_BASE
        self.token_fetch = token_fetch or _sva.get_token
        self.clock = clock
        self.alert_role = alert_role or ALERT_ROLE

        self.ws = None
        self._reader_task: asyncio.Task | None = None
        self._dispatch_queues: list[asyncio.Queue] = []
        self.event_log: list = []  # [[ms_since_open, type], ...] -- every event seen, timestamped
        self._closed = False
        self._session_start: float | None = None
        self._closed_at: float | None = None

    # ---- internal helpers ---------------------------------------------

    async def _send(self, payload: dict, timeout: float = SEND_TIMEOUT_S) -> None:
        await asyncio.wait_for(self.ws.send(json.dumps(payload)), timeout=timeout)

    async def _read_loop(self) -> None:
        """The single background task that ever calls ws.recv(). Fans every
        parsed event out to each currently-registered dispatch queue (one per
        in-flight speak()/ask() call) and records it in event_log. Bounded by
        HARD_SESSION_CAP_S from session open -- re-checks the deadline every
        iteration so it can't outlive the session cap even if the peer stays
        silent without closing."""
        hard_deadline = self._session_start + HARD_SESSION_CAP_S
        while True:
            remaining = hard_deadline - self.clock()
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=max(0.1, remaining))
            except asyncio.TimeoutError:
                continue
            except (websockets.exceptions.ConnectionClosed, OSError):
                break
            try:
                evt = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            t_ms = round((self.clock() - self._session_start) * 1000)
            self.event_log.append([t_ms, evt.get("type")])
            for q in list(self._dispatch_queues):
                with contextlib.suppress(Exception):
                    q.put_nowait(evt)

    # ---- session lifecycle ---------------------------------------------

    async def open(self) -> dict:
        """Connect, send session.update, wait for session.ready (never
        session.updated -- see spike_voice_agent.py's classify_setup_event
        and PROTOCOL.md's live-run doc check), start the background reader.
        Returns {connect_ms, ready_ms}, both measured from the start of
        open(). Raises SessionSetupError/SessionSetupTimeout (from the
        reused spike module) on setup failure -- never sends input before
        session.ready, structurally, same as spike_voice_agent.open_session."""
        t0 = self.clock()
        self._session_start = t0
        token = self.token_fetch(self.api_key)
        self.ws = await asyncio.wait_for(
            websockets.connect(
                f"{self.ws_url}?token={token}",
                open_timeout=CONNECT_TIMEOUT_S,
                close_timeout=CLEANUP_TIMEOUT_S,
            ),
            timeout=CONNECT_TIMEOUT_S,
        )
        connect_ms = round((self.clock() - t0) * 1000)

        session_cfg = {
            "system_prompt": SYSTEM_PROMPT,
            "input": {"format": {"encoding": "audio/pcm", "sample_rate": 24000}},
            "tools": [
                {
                    "type": "function",
                    "name": "lookup_clause",
                    "description": "Look up the literal text of a contract clause by its id/section number.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "section_number": {"type": "string", "description": "Clause section number, e.g. '4.2'"}
                        },
                        "required": ["section_number"],
                    },
                    # PROTOCOL.md §3a (tools/client-side-tools): "interactive" =
                    # agent speaks a transition phrase, emits tool.call, client
                    # processes async, then sends tool.result -- matches ask()'s
                    # drain-while-waiting design below.
                    "execution_mode": "interactive",
                    "timeout_seconds": 120,
                }
            ],
        }
        await self._send({"type": "session.update", "session": session_cfg})

        setup_events: list = []
        ready_deadline = t0 + SESSION_READY_TIMEOUT_S
        while True:
            remaining = ready_deadline - self.clock()
            if remaining <= 0:
                raise _sva.SessionSetupTimeout(setup_events, SESSION_READY_TIMEOUT_S)
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                raise _sva.SessionSetupTimeout(setup_events, SESSION_READY_TIMEOUT_S)
            evt = json.loads(raw)
            setup_events.append([round((self.clock() - t0) * 1000), evt.get("type"), evt])
            outcome = _sva.classify_setup_event(evt)
            if outcome == "ready":
                break
            if outcome == "error":
                raise _sva.SessionSetupError(evt, setup_events)
        ready_ms = round((self.clock() - t0) * 1000)

        self._reader_task = asyncio.create_task(self._read_loop())
        return {"connect_ms": connect_ms, "ready_ms": ready_ms}

    async def close(self) -> None:
        """Bounded cleanup: cancel the reader, send session.end, close the
        socket. Every step is individually timeout-bounded and exception-
        suppressed, including asyncio.CancelledError (a BaseException), so a
        cancelled caller or an unresponsive peer can't skip or block
        teardown. Safe to call more than once."""
        if self._closed:
            return
        self._closed = True
        self._closed_at = self.clock()
        if self._reader_task is not None:
            self._reader_task.cancel()
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await asyncio.wait_for(self._reader_task, timeout=CLEANUP_TIMEOUT_S)
        if self.ws is not None:
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await self._send({"type": "session.end"}, timeout=CLEANUP_TIMEOUT_S)
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await asyncio.wait_for(self.ws.close(), timeout=CLEANUP_TIMEOUT_S)

    @property
    def est_cost_usd(self) -> float:
        if self._session_start is None:
            return 0.0
        end = self._closed_at if self._closed_at is not None else self.clock()
        return round((end - self._session_start) * COST_PER_SEC, 4)

    # ---- actions ---------------------------------------------------------

    async def speak(self, text: str) -> dict:
        """Inject `text` via conversation.message (role=self.alert_role) then
        trigger reply.create so the agent reads it back verbatim (per
        SYSTEM_PROMPT). Never sends audio. Returns
        {inject_ms, first_audio_ms, done_ms, agent_transcript, audio_chunks,
        errors, role, literal_spoken} -- all *_ms relative to the start of
        this call. literal_spoken is True iff the normalized `text` is a
        substring of the normalized agent_transcript (see _literal_spoken).
        A send failure (e.g. peer already closed) is recorded in `errors`
        and returned, never raised."""
        t0 = self.clock()
        result = {
            "inject_ms": None, "first_audio_ms": None, "done_ms": None,
            "agent_transcript": "", "audio_chunks": 0, "errors": [], "role": self.alert_role,
            "literal_spoken": False,
        }
        q: asyncio.Queue = asyncio.Queue()
        self._dispatch_queues.append(q)
        try:
            try:
                await self._send({"type": "conversation.message", "role": self.alert_role, "content": text})
                await self._send({
                    "type": "reply.create",
                    "instructions": "Read the compliance alert you were just given verbatim, word for word.",
                })
            except Exception as e:
                result["errors"].append(f"send failed: {type(e).__name__}: {e}")
                return result
            result["inject_ms"] = round((self.clock() - t0) * 1000)

            deadline = t0 + REPLY_TIMEOUT_S
            while True:
                remaining = deadline - self.clock()
                if remaining <= 0:
                    break
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                etype = evt.get("type")
                if etype == "reply.audio":
                    result["audio_chunks"] += 1
                    if result["first_audio_ms"] is None:
                        result["first_audio_ms"] = round((self.clock() - t0) * 1000)
                elif etype == "transcript.agent":
                    result["agent_transcript"] = evt.get("text", "")
                elif etype in ("session.error", "error"):
                    result["errors"].append(evt)
                elif etype == "reply.done":
                    result["done_ms"] = round((self.clock() - t0) * 1000)
                    break
        finally:
            self._dispatch_queues.remove(q)
            result["literal_spoken"] = _literal_spoken(text, result["agent_transcript"])
        return result

    async def ask(self, question_text: str | None = None, question_wav=None) -> dict:
        """Answer a monitor question. Either inject `question_text` (via
        conversation.message role="user" + reply.create) or stream
        `question_wav` (the monitor's own spoken question; NOT rep audio).
        `question_wav` MUST be 24000 Hz mono 16-bit PCM -- checked locally
        (no network) before anything is sent; a mismatch is recorded in
        `errors` and returned immediately. Handles the resulting tool.call
        by sending back the literal clause text for section_number from
        `clauses` (unknown section_number -> "No such clause"). Returns
        {tool_called, tool_args, tool_result_sent, first_audio_ms,
        agent_transcript, literal_spoken, errors}. literal_spoken is True
        iff the normalized clause text sent back via tool.result is a
        substring of the normalized agent_transcript (see _literal_spoken)
        -- stays False if the tool was never called."""
        t0 = self.clock()
        result = {
            "tool_called": False, "tool_args": None, "tool_result_sent": False,
            "first_audio_ms": None, "agent_transcript": "", "literal_spoken": False, "errors": [],
        }
        if question_text is None and question_wav is None:
            result["errors"].append("ask() needs question_text or question_wav")
            return result

        tool_clause_text: str | None = None
        q: asyncio.Queue = asyncio.Queue()
        self._dispatch_queues.append(q)
        try:
            try:
                if question_text is not None:
                    await self._send({"type": "conversation.message", "role": "user", "content": question_text})
                    await self._send({
                        "type": "reply.create",
                        "instructions": "Answer the monitor's question by calling lookup_clause.",
                    })
                else:
                    wav_path = Path(question_wav)
                    with wave.open(str(wav_path), "rb") as w:
                        actual = (w.getframerate(), w.getnchannels(), w.getsampwidth())
                    if actual != (REQUIRED_ASK_WAV_RATE, 1, 2):
                        result["errors"].append(
                            f"question_wav must be {REQUIRED_ASK_WAV_RATE}Hz mono 16-bit PCM, "
                            f"got {actual[0]}Hz/{actual[1]}ch/{actual[2] * 8}bit -- refusing, no network sent"
                        )
                        return result
                    pcm, rate = _sva.load_wav(wav_path)
                    stream_deadline = t0 + REPLY_TIMEOUT_S
                    stream_info = await _sva.stream_wav(self.ws, pcm, rate, "AlertAgent.ask", stream_deadline)
                    if stream_info.get("error"):
                        result["errors"].append(f"stream failed: {stream_info['error']}")
                        return result
            except Exception as e:
                result["errors"].append(f"send failed: {type(e).__name__}: {e}")
                return result

            deadline = t0 + max(REPLY_TIMEOUT_S, TOOL_WAIT_TIMEOUT_S)
            while True:
                remaining = deadline - self.clock()
                if remaining <= 0:
                    break
                try:
                    evt = await asyncio.wait_for(q.get(), timeout=remaining)
                except asyncio.TimeoutError:
                    break
                etype = evt.get("type")
                if etype == "tool.call":
                    result["tool_called"] = True
                    call_id = evt.get("call_id")
                    args = evt.get("arguments") or {}
                    result["tool_args"] = args
                    section_number = str(args.get("section_number", ""))
                    clause_text = self.clause_map.get(section_number, "No such clause")
                    tool_clause_text = clause_text
                    try:
                        await self._send({
                            "type": "tool.result", "call_id": call_id,
                            "result": clause_text, "is_error": False,
                        })
                        result["tool_result_sent"] = True
                    except Exception as e:
                        result["errors"].append(f"tool.result send failed: {type(e).__name__}: {e}")
                elif etype == "reply.audio":
                    if result["first_audio_ms"] is None:
                        result["first_audio_ms"] = round((self.clock() - t0) * 1000)
                elif etype == "transcript.agent":
                    result["agent_transcript"] = evt.get("text", "")
                elif etype in ("session.error", "error"):
                    result["errors"].append(evt)
                elif etype == "reply.done":
                    break
        finally:
            self._dispatch_queues.remove(q)
            if tool_clause_text is not None:
                result["literal_spoken"] = _literal_spoken(tool_clause_text, result["agent_transcript"])
        return result
