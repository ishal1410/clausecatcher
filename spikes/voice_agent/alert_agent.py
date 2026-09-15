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
from difflib import SequenceMatcher
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
REPLY_TIMEOUT_S = 20          # unused by speak()/ask() reading windows now (see REPLY_DONE_TIMEOUT_S) -- kept so old callers/tests referencing it don't hit AttributeError
TOOL_WAIT_TIMEOUT_S = 15      # bound on waiting for a tool.call to arrive after ask()
REPLY_DONE_TIMEOUT_S = 15     # bound on waiting for reply.done for ONE reply -- speak() uses it once; ask() re-arms a fresh window after tool.result triggers the next (spoken-answer) reply, instead of counting down from call start
STREAM_DEADLINE_MARGIN_S = 5.0  # safety margin (seconds) added on top of measured audio+silence duration when computing ask(question_wav=...)'s stream_wav deadline

ALERT_ROLE = "user"  # see module docstring: the only live-proven injection role (Q1); override via alert_role= kwarg

REQUIRED_ASK_WAV_RATE = 24000  # ask(question_wav=...) refuses anything else -- see module docstring / ask()

SYSTEM_PROMPT = (
    "You are a terse compliance assistant. When given a compliance alert, "
    "read it back verbatim -- word for word, no additions, no commentary. "
    "When asked about a contract clause, call the lookup_clause tool with "
    "its id and read back exactly what it returns. When lookup_clause "
    "returns text, speak that returned text exactly as written, word for "
    "word; do not summarize or rephrase."
)

SPEAK_MODES = ("legacy", "no_instructions", "say_exactly", "message_and_say_exactly")

_LEGACY_INSTRUCTIONS = "Read the compliance alert you were just given verbatim, word for word."
_SAY_EXACTLY_PREFIX = "Say exactly the following text and nothing else, word for word: "

# ---- number-word -> digit conversion (normalize_for_match) ----------------
# Covers 0-100 plus basic hundred/thousand compounds -- see normalize_for_match.
_ONES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
    "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16, "seventeen": 17,
    "eighteen": 18, "nineteen": 19,
}
_TENS = {
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1000}
_NUMBER_WORDS = set(_ONES) | set(_TENS) | set(_SCALES)


def _words_to_number(tokens: list[str], start: int):
    """Parse a number-word run starting at tokens[start]. Returns
    (value, next_index) or None. Stops after one ones/teen word per tens
    group so "twenty four seven" parses as 24 then 7, not 20+4+7 -- matches
    the spoken-idiom case ("24/7") rather than a single number."""
    if tokens[start] not in _NUMBER_WORDS:
        return None
    i = start
    total = 0
    current = 0
    matched = False
    has_ones = False
    while i < len(tokens):
        w = tokens[i]
        if w in _ONES:
            if has_ones:
                break
            current += _ONES[w]
            has_ones = True
            matched = True
            i += 1
        elif w in _TENS:
            if has_ones:
                break
            current += _TENS[w]
            matched = True
            i += 1
        elif w in _SCALES:
            current = (current or 1) * _SCALES[w]
            total += current
            current = 0
            has_ones = False
            matched = True
            i += 1
        else:
            break
    if not matched:
        return None
    return total + current, i


def normalize_for_match(s: str) -> str:
    """Normalize text for verbatim/near-verbatim matching (literal_spoken +
    similarity). lowercase; punctuation stripped (replaced with a space,
    except a "." kept when it sits between two digits, e.g. "4.2"); "%" ->
    " percent " (so "%"/"percent" both normalize to the word "percent");
    number words 0-100 plus hundred/thousand compounds converted to digits
    ("twelve"->"12", "sixty"->"60", "twenty four"->"24"); "N point N"/
    "N dot N" -> "N.N" (e.g. "four point two"->"4.2"); "24/7" and "twenty
    four seven" both -> "24 7"; whitespace collapsed."""
    s = s.lower().replace("%", " percent ")
    out = []
    for i, ch in enumerate(s):
        if ch.isalnum() or ch.isspace():
            out.append(ch)
        elif ch == "." and 0 < i < len(s) - 1 and s[i - 1].isdigit() and s[i + 1].isdigit():
            out.append(ch)
        else:
            out.append(" ")
    s = re.sub(r"\s+", " ", "".join(out)).strip()

    tokens = s.split(" ") if s else []
    result_tokens = []
    i = 0
    while i < len(tokens):
        parsed = _words_to_number(tokens, i)
        if parsed is not None:
            value, next_i = parsed
            result_tokens.append(str(value))
            i = next_i
        else:
            result_tokens.append(tokens[i])
            i += 1
    s = " ".join(result_tokens)
    s = re.sub(r"(\d+) (?:point|dot) (\d+)", r"\1.\2", s)
    return re.sub(r"\s+", " ", s).strip()


def _grade_match(reference_text: str, transcript: str):
    """(literal_spoken, similarity): literal_spoken is True iff the
    normalized reference_text's tokens (whitespace-split) appear as a
    contiguous subsequence of the normalized transcript's tokens -- token-
    boundary aware, so "60 days" matches inside "we give 60 days notice"
    but NOT inside "160 days" (substring-only containment would wrongly
    match both; digits are single tokens after normalize_for_match, so
    "160" != "60" and "4.25"/"14.2" != "4.2"). Empty reference -> False.
    similarity is difflib SequenceMatcher's ratio on the two normalized
    strings, rounded to 3 decimals -- lets a near-verbatim paraphrase
    (fails literal_spoken) still be graded."""
    norm_ref = normalize_for_match(reference_text)
    norm_transcript = normalize_for_match(transcript)
    ref_tokens = norm_ref.split()
    transcript_tokens = norm_transcript.split()
    n = len(ref_tokens)
    spoken = bool(ref_tokens) and any(
        transcript_tokens[i:i + n] == ref_tokens
        for i in range(len(transcript_tokens) - n + 1)
    )
    similarity = round(SequenceMatcher(None, norm_ref, norm_transcript).ratio(), 3)
    return spoken, similarity


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

    async def speak(self, text: str, *, mode: str = "no_instructions", inject_delay_ms: int = 0) -> dict:
        """Inject `text` and trigger a reply, per `mode` (see SPEAK_MODES /
        module docstring for what each mode sends live-verified 2026-09-14):
          - "legacy": conversation.message(role=alert_role) + reply.create
            with the old generic "read it back" instructions -- kept only
            for comparison, this is the shape that made the agent say
            "Please provide the compliance alert..." (content ignored).
          - "no_instructions": conversation.message(role=alert_role) +
            reply.create with NO instructions key (the only live-proven
            injection shape, Q1).
          - "say_exactly": no conversation.message at all; reply.create
            alone, `text` embedded in its instructions.
          - "message_and_say_exactly": both -- conversation.message AND the
            say_exactly-style reply.create instructions.
        `inject_delay_ms` sleeps that many ms between the conversation.message
        send and the reply.create send (probing whether reply.create can
        race ahead of conversation.message landing in context -- there is no
        documented ack event for conversation.message to wait on instead).
        Ignored for "say_exactly" (no message is sent, nothing to delay
        after). Never sends audio. Returns {inject_ms, first_audio_ms,
        done_ms, agent_transcript, audio_chunks, errors, role, mode,
        inject_delay_ms, literal_spoken, similarity} -- all *_ms relative to
        the start of this call. literal_spoken/similarity come from
        _grade_match(text, agent_transcript) (see normalize_for_match). A
        send failure (e.g. peer already closed) is recorded in `errors` and
        returned, never raised. Keeps reading until reply.done for the
        reply this call triggered, bounded by REPLY_DONE_TIMEOUT_S."""
        if mode not in SPEAK_MODES:
            raise ValueError(f"unknown speak() mode {mode!r} -- must be one of {SPEAK_MODES}")
        t0 = self.clock()
        result = {
            "inject_ms": None, "first_audio_ms": None, "done_ms": None,
            "agent_transcript": "", "audio_chunks": 0, "errors": [], "role": self.alert_role,
            "mode": mode, "inject_delay_ms": inject_delay_ms,
            "literal_spoken": False, "similarity": 0.0,
        }
        sends_message = mode in ("legacy", "no_instructions", "message_and_say_exactly")
        q: asyncio.Queue = asyncio.Queue()
        self._dispatch_queues.append(q)
        try:
            try:
                if sends_message:
                    await self._send({"type": "conversation.message", "role": self.alert_role, "content": text})
                    if inject_delay_ms:
                        await asyncio.sleep(inject_delay_ms / 1000.0)
                if mode == "legacy":
                    await self._send({"type": "reply.create", "instructions": _LEGACY_INSTRUCTIONS})
                elif mode == "no_instructions":
                    await self._send({"type": "reply.create"})
                else:  # say_exactly, message_and_say_exactly
                    await self._send({"type": "reply.create", "instructions": _SAY_EXACTLY_PREFIX + text})
            except Exception as e:
                result["errors"].append(f"send failed: {type(e).__name__}: {e}")
                return result
            result["inject_ms"] = round((self.clock() - t0) * 1000)

            transcript_final = None
            transcript_deltas: list[str] = []
            deadline = t0 + REPLY_DONE_TIMEOUT_S
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
                    transcript_final = evt.get("text", "")
                elif etype == "transcript.agent.delta":
                    transcript_deltas.append(evt.get("delta") or evt.get("text") or "")
                elif etype in ("session.error", "error"):
                    result["errors"].append(evt)
                elif etype == "reply.done":
                    result["done_ms"] = round((self.clock() - t0) * 1000)
                    break
            result["agent_transcript"] = transcript_final if transcript_final is not None else "".join(transcript_deltas)
        finally:
            self._dispatch_queues.remove(q)
            result["literal_spoken"], result["similarity"] = _grade_match(text, result["agent_transcript"])
        return result

    async def ask(self, question_text: str | None = None, question_wav=None) -> dict:
        """Answer a monitor question. Either inject `question_text` (via
        conversation.message role="user" + reply.create) or stream
        `question_wav` (the monitor's own spoken question; NOT rep audio).
        `question_wav` MUST be 24000 Hz mono 16-bit PCM -- checked locally
        (no network) before anything is sent; a mismatch is recorded in
        `errors` and returned immediately. Handles the resulting tool.call
        by sending back the literal clause text for section_number from
        `clauses` (unknown section_number -> "No such clause"), then keeps
        reading for the NEXT reply.done -- the tool.result-triggered reply
        that actually speaks the answer -- instead of the original
        call-start deadline, which live-measured 2026-09-14 could expire
        before that second reply arrived ("spoken answer... arrived after
        ask() stopped reading"). Each reply.done wait is bounded by its own
        fresh REPLY_DONE_TIMEOUT_S window. Returns {tool_called, tool_args,
        tool_result_sent, first_audio_ms, agent_transcript, literal_spoken,
        similarity, errors}. literal_spoken/similarity come from
        _grade_match(clause_text_sent, agent_transcript) -- stay at their
        defaults (False / 0.0) if the tool was never called."""
        t0 = self.clock()
        result = {
            "tool_called": False, "tool_args": None, "tool_result_sent": False,
            "first_audio_ms": None, "agent_transcript": "", "literal_spoken": False,
            "similarity": 0.0, "errors": [],
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
                    # stream_wav's deadline is compared against time.time()
                    # (wall clock) INSIDE spike_voice_agent.py, so it must be
                    # computed from time.time() here too, at send time --
                    # never from self.clock()/t0 (which defaults to
                    # time.monotonic(), an unrelated epoch on this platform).
                    # That clock mismatch is exactly what made ask(question_wav=...)
                    # send 0 bytes live 2026-09-14 ("stream_wav hit deadline,
                    # stopped early after 0 bytes"): a monotonic-based deadline
                    # compared against time.time() looked already-expired.
                    audio_duration_s = len(pcm) / (rate * _sva.SAMPLE_WIDTH_BYTES * _sva.CHANNELS)
                    stream_deadline = time.time() + audio_duration_s + 0.5 + STREAM_DEADLINE_MARGIN_S
                    stream_info = await _sva.stream_wav(self.ws, pcm, rate, "AlertAgent.ask", stream_deadline)
                    if stream_info.get("error"):
                        result["errors"].append(f"stream failed: {stream_info['error']}")
                        return result
            except Exception as e:
                result["errors"].append(f"send failed: {type(e).__name__}: {e}")
                return result

            transcript_final = None
            transcript_deltas: list[str] = []
            # Tracks whether any reply.audio/transcript.agent(.delta) has
            # arrived since tool.result was sent. A tool.call's own
            # "interactive" reply can complete (its own bare reply.done,
            # carrying no content) BEFORE we've even sent tool.result back --
            # see TestAskWaitsForReplyDoneAfterToolResult. That reply.done
            # must be ignored; only a reply.done that arrives WITH content
            # (or, when no tool was called at all, the first reply.done
            # outright) ends the wait.
            content_since_tool_result = False
            deadline = t0 + REPLY_DONE_TIMEOUT_S
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
                        # tool.result triggers the NEXT reply (the spoken
                        # answer) -- reset the transcript accumulator and
                        # re-arm a fresh REPLY_DONE_TIMEOUT_S window for it
                        # instead of continuing to count down from t0.
                        transcript_final = None
                        transcript_deltas = []
                        content_since_tool_result = False
                        deadline = self.clock() + REPLY_DONE_TIMEOUT_S
                    except Exception as e:
                        result["errors"].append(f"tool.result send failed: {type(e).__name__}: {e}")
                elif etype == "reply.audio":
                    content_since_tool_result = True
                    if result["first_audio_ms"] is None:
                        result["first_audio_ms"] = round((self.clock() - t0) * 1000)
                elif etype == "transcript.agent":
                    transcript_final = evt.get("text", "")
                    content_since_tool_result = True
                elif etype == "transcript.agent.delta":
                    transcript_deltas.append(evt.get("delta") or evt.get("text") or "")
                    content_since_tool_result = True
                elif etype in ("session.error", "error"):
                    result["errors"].append(evt)
                elif etype == "reply.done":
                    if result["tool_called"] and not content_since_tool_result:
                        # bare reply.done from the transition-phase reply --
                        # not the answer; keep reading for the real one.
                        continue
                    break
            result["agent_transcript"] = transcript_final if transcript_final is not None else "".join(transcript_deltas)
        finally:
            self._dispatch_queues.remove(q)
            if tool_clause_text is not None:
                result["literal_spoken"], result["similarity"] = _grade_match(tool_clause_text, result["agent_transcript"])
        return result
