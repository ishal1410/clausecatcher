"""AlertSpeaker -- the Voice Agent session that SPEAKS a contract alert or
clause answer verbatim (ADR-0001). Owns exactly one AssemblyAI Voice Agent
websocket session per instance.

PROVEN LIVE 2026-09-15 (spikes/voice_agent/out/probe_gate_20260915T051527Z.json):
the only reliable way to make the agent speak text word for word is to open
a session at 24 kHz audio/pcm, send it NO rep audio, and send ONLY
`{"type": "reply.create", "instructions": "Say exactly the following text
and nothing else, word for word: " + text}` -- no `conversation.message`.
conversation.message content is ignored by the agent for this purpose, and
tool calling picked the wrong clause in earlier probes, so this class
registers no tools and never sends conversation.message.

Adapted (not imported) from the verified pieces of
spikes/voice_agent/alert_agent.py and spikes/voice_agent/spike_voice_agent.py:
token fetch, WS URL, the session.update -> wait-for-session.ready handshake
(session.updated may arrive first, undocumented ordering), bounded
sends/recv, cleanup (session.end + close_timeout), a single background
reader task, and normalize_for_match / _grade_match / similarity (kept
verbatim, same rules). This module is a real package member
(server/__init__.py), so nothing here uses the spikes' importlib-from-path
trick -- it's plain copied logic.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import re
import time
import urllib.request
from difflib import SequenceMatcher
from typing import Awaitable, Callable

import websockets
import websockets.exceptions

# ---- AssemblyAI Voice Agent protocol constants (adapted from spike_voice_agent.py) ----
TOKEN_URL = "https://agents.assemblyai.com/v1/token"
WS_URL_BASE = "wss://agents.assemblyai.com/v1/ws"

COST_PER_SEC = 4.50 / 3600.0   # verified Voice Agent pricing
SESSION_MAX_S = 900            # hard cap on time inside one open()..close() session -- billing safety
CONNECT_TIMEOUT_S = 15
SESSION_READY_TIMEOUT_S = 10
CLEANUP_TIMEOUT_S = 3
SEND_TIMEOUT_S = 5
REPLY_DONE_TIMEOUT_S = 20      # bound on waiting for reply.done for one say_exactly() call

SYSTEM_PROMPT = (
    "You are ClauseCatcher's voice. When instructed to say text, say "
    "exactly that text and nothing else."
)

_SAY_EXACTLY_PREFIX = "Say exactly the following text and nothing else, word for word: "


def get_token(api_key: str, expires_in_seconds: int = 300) -> str:
    """GET https://agents.assemblyai.com/v1/token -- Authorization: Bearer
    header, expires_in_seconds query param, response {"token": "..."}."""
    url = f"{TOKEN_URL}?expires_in_seconds={expires_in_seconds}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["token"]


def _classify_setup_event(evt: dict) -> str:
    """Classify one event seen during session setup (before session.ready).
    "ready" -> stop waiting; "error" -> caller should raise; "wait" ->
    anything else (e.g. session.updated -- keep waiting)."""
    t = evt.get("type")
    if t == "session.ready":
        return "ready"
    if t in ("session.error", "error"):
        return "error"
    return "wait"


class VoiceSetupError(Exception):
    """Raised by AlertSpeaker.open() when the session never reaches
    session.ready: token-fetch failure, connect failure, a session.error
    event, or a session.ready timeout. Never carries the api_key or token."""


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
    but NOT inside "160 days". Empty reference -> False. similarity is
    difflib SequenceMatcher's ratio on the two normalized strings, rounded
    to 3 decimals -- lets a near-verbatim paraphrase (fails literal_spoken)
    still be graded."""
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


def build_alert_text(clause: dict) -> str:
    return f"Contract alert: section {clause['section_number']} says: {clause['literal_text']}"


def build_clause_answer_text(clause: dict) -> str:
    return f"Section {clause['section_number']}, {clause['title']}: {clause['literal_text']}"


class AlertSpeaker:
    """One Voice Agent API session used only to SPEAK alert/clause text
    verbatim. Registers no tools; never sends conversation.message (see
    module docstring). say_exactly() calls are serialized with a lock so
    alerts never overlap on the wire."""

    def __init__(
        self,
        api_key: str,
        *,
        on_audio: Callable[[bytes, int], Awaitable[None]],
        on_event: Callable[[dict], Awaitable[None]] | None = None,
        ws_url: str | None = None,
        token_fetch: Callable[[str], str] | None = None,
    ):
        self.api_key = api_key
        self.on_audio = on_audio
        self.on_event = on_event
        self.ws_url = ws_url or WS_URL_BASE
        self.token_fetch = token_fetch or get_token
        self.clock = time.monotonic

        self.ws = None
        self._reader_task: asyncio.Task | None = None
        self._cap_task: asyncio.Task | None = None
        self._dispatch_queues: list[asyncio.Queue] = []
        self._lock = asyncio.Lock()
        self._closed = False
        self._session_start: float | None = None
        self._closed_at: float | None = None

    # ---- internal helpers ---------------------------------------------

    async def _send(self, payload: dict, timeout: float = SEND_TIMEOUT_S) -> None:
        await asyncio.wait_for(self.ws.send(json.dumps(payload)), timeout=timeout)

    async def _read_loop(self) -> None:
        """The single background task that ever calls ws.recv(). Fans every
        parsed event out to each currently-registered dispatch queue (one
        per in-flight say_exactly() call). Self-terminates at
        SESSION_MAX_S from session open, as a fallback safety net alongside
        the explicit _session_cap_watchdog close(). On an abrupt disconnect
        it pushes a synthetic "_connection_closed" event to every queue
        before exiting, so an in-flight say_exactly() sees it as an error
        instead of hanging until its own timeout."""
        hard_deadline = self._session_start + SESSION_MAX_S
        while True:
            remaining = hard_deadline - self.clock()
            if remaining <= 0:
                break
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=max(0.1, remaining))
            except asyncio.TimeoutError:
                continue
            except (websockets.exceptions.ConnectionClosed, OSError) as e:
                evt = {"type": "_connection_closed", "detail": f"{type(e).__name__}: {e}"}
                for q in list(self._dispatch_queues):
                    with contextlib.suppress(Exception):
                        q.put_nowait(evt)
                break
            try:
                evt = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            for q in list(self._dispatch_queues):
                with contextlib.suppress(Exception):
                    q.put_nowait(evt)

    async def _session_cap_watchdog(self) -> None:
        """Auto-closes the session once it has been open SESSION_MAX_S
        seconds -- demo safety so a forgotten open session can't run up
        billing. close() is idempotent, so this races harmlessly with a
        caller-initiated close()."""
        deadline = self._session_start + SESSION_MAX_S
        remaining = deadline - self.clock()
        if remaining > 0:
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await asyncio.sleep(remaining)
        if not self._closed:
            with contextlib.suppress(Exception):
                await self.close()

    # ---- session lifecycle ---------------------------------------------

    async def open(self) -> dict:
        """Connect, send session.update, wait for session.ready (never
        session.updated, which may arrive first -- undocumented ordering).
        Returns {connect_ms, ready_ms}, both measured from the start of
        open(). Raises VoiceSetupError on any setup failure; never sends
        input before session.ready."""
        t0 = self.clock()
        self._session_start = t0
        try:
            token = self.token_fetch(self.api_key)
        except Exception as e:
            raise VoiceSetupError(f"token fetch failed: {type(e).__name__}: {e}") from e

        try:
            self.ws = await asyncio.wait_for(
                websockets.connect(
                    f"{self.ws_url}?token={token}",
                    open_timeout=CONNECT_TIMEOUT_S,
                    close_timeout=CLEANUP_TIMEOUT_S,
                ),
                timeout=CONNECT_TIMEOUT_S,
            )
        except Exception as e:
            raise VoiceSetupError(f"connect failed: {type(e).__name__}: {e}") from e
        connect_ms = round((self.clock() - t0) * 1000)

        session_cfg = {
            "system_prompt": SYSTEM_PROMPT,
            "input": {"format": {"encoding": "audio/pcm", "sample_rate": 24000}},
        }
        try:
            await self._send({"type": "session.update", "session": session_cfg})
        except Exception as e:
            raise VoiceSetupError(f"session.update send failed: {type(e).__name__}: {e}") from e

        setup_events: list = []
        ready_deadline = t0 + SESSION_READY_TIMEOUT_S
        while True:
            remaining = ready_deadline - self.clock()
            if remaining <= 0:
                types = [e[1] for e in setup_events]
                raise VoiceSetupError(
                    f"no session.ready within {SESSION_READY_TIMEOUT_S:g}s; setup_events={types}"
                )
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                types = [e[1] for e in setup_events]
                raise VoiceSetupError(
                    f"no session.ready within {SESSION_READY_TIMEOUT_S:g}s; setup_events={types}"
                )
            except Exception as e:
                raise VoiceSetupError(f"setup failed: {type(e).__name__}: {e}") from e
            try:
                evt = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue
            setup_events.append([round((self.clock() - t0) * 1000), evt.get("type")])
            outcome = _classify_setup_event(evt)
            if outcome == "ready":
                break
            if outcome == "error":
                raise VoiceSetupError(f"setup error: {evt.get('code', '?')} {evt.get('message', '?')}")
        ready_ms = round((self.clock() - t0) * 1000)

        self._reader_task = asyncio.create_task(self._read_loop())
        self._cap_task = asyncio.create_task(self._session_cap_watchdog())
        return {"connect_ms": connect_ms, "ready_ms": ready_ms}

    async def close(self) -> None:
        """Bounded, idempotent cleanup: cancel the watchdog and reader,
        send session.end, close the socket. Every step is individually
        timeout-bounded and exception-suppressed, including
        asyncio.CancelledError, so a cancelled caller or an unresponsive
        peer can't skip or block teardown."""
        if self._closed:
            return
        self._closed = True
        self._closed_at = self.clock()
        if self._cap_task is not None:
            self._cap_task.cancel()
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await asyncio.wait_for(self._cap_task, timeout=CLEANUP_TIMEOUT_S)
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

    @property
    def is_open(self) -> bool:
        return self.ws is not None and not self._closed

    # ---- actions ---------------------------------------------------------

    async def say_exactly(self, text: str) -> dict:
        """Speak `text` verbatim: send ONLY
        {"type": "reply.create", "instructions": <say-exactly prefix> + text}
        -- no conversation.message. Streams every reply.audio chunk to
        on_audio(pcm16_bytes, 24000) as it arrives, in order. Fires
        on_event({"type": "agent_speaking", "state": "start"/"end", "text"})
        around the call, when on_event is set. Waits for reply.done bounded
        by REPLY_DONE_TIMEOUT_S. Never raises (VoiceSetupError is only
        raised by open()) -- any failure (send error, timeout, decode
        error, on_audio error, abrupt disconnect) is appended to the
        returned errors list instead. Only events between this call's own
        reply.create and its reply.done are ever forwarded, since the
        dispatch queue is registered right before the send and removed
        right after -- so an auto-reply that should never happen (no rep
        audio is ever sent) also can't leak into an unrelated alert."""
        result = {
            "text": text, "first_audio_ms": None, "done_ms": None,
            "agent_transcript": "", "literal_spoken": False, "similarity": 0.0,
            "errors": [],
        }
        async with self._lock:
            if not self.is_open:
                result["errors"].append("say_exactly() called before open() or after close()")
                return result

            t0 = self.clock()
            q: asyncio.Queue = asyncio.Queue()
            self._dispatch_queues.append(q)
            speaking_started = False
            try:
                try:
                    await self._send({"type": "reply.create", "instructions": _SAY_EXACTLY_PREFIX + text})
                except Exception as e:
                    result["errors"].append(f"send failed: {type(e).__name__}: {e}")
                    return result

                if self.on_event is not None:
                    speaking_started = True
                    with contextlib.suppress(Exception):
                        await self.on_event({"type": "agent_speaking", "state": "start", "text": text})

                transcript_final = None
                transcript_deltas: list[str] = []
                deadline = t0 + REPLY_DONE_TIMEOUT_S
                while True:
                    remaining = deadline - self.clock()
                    if remaining <= 0:
                        result["errors"].append(f"timed out waiting for reply.done after {REPLY_DONE_TIMEOUT_S}s")
                        break
                    try:
                        evt = await asyncio.wait_for(q.get(), timeout=remaining)
                    except asyncio.TimeoutError:
                        result["errors"].append(f"timed out waiting for reply.done after {REPLY_DONE_TIMEOUT_S}s")
                        break
                    etype = evt.get("type")
                    if etype == "reply.audio":
                        if result["first_audio_ms"] is None:
                            result["first_audio_ms"] = round((self.clock() - t0) * 1000)
                        data = evt.get("data") or ""
                        if data:
                            try:
                                pcm = base64.b64decode(data)
                            except Exception as e:
                                result["errors"].append(f"audio decode failed: {type(e).__name__}: {e}")
                            else:
                                try:
                                    await self.on_audio(pcm, 24000)
                                except Exception as e:
                                    result["errors"].append(f"on_audio failed: {type(e).__name__}: {e}")
                    elif etype == "transcript.agent":
                        transcript_final = evt.get("text", "")
                    elif etype == "transcript.agent.delta":
                        transcript_deltas.append(evt.get("delta") or evt.get("text") or "")
                    elif etype == "_connection_closed":
                        result["errors"].append(evt.get("detail", "connection closed"))
                        break
                    elif etype in ("session.error", "error"):
                        result["errors"].append(evt)
                    elif etype == "reply.done":
                        result["done_ms"] = round((self.clock() - t0) * 1000)
                        break
                result["agent_transcript"] = (
                    transcript_final if transcript_final is not None else "".join(transcript_deltas)
                )
            finally:
                with contextlib.suppress(ValueError):
                    self._dispatch_queues.remove(q)
                result["literal_spoken"], result["similarity"] = _grade_match(text, result["agent_transcript"])
                if speaking_started:
                    with contextlib.suppress(Exception):
                        await self.on_event({"type": "agent_speaking", "state": "end", "text": text})
            return result
