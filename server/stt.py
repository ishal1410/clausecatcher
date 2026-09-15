"""AssemblyAI Streaming STT v3 client for ClauseCatcher.

Talks to wss://streaming.assemblyai.com/v3/ws exactly as verified in
spikes/two_path/spike_two_path.py (raw API key in the `Authorization` header,
no "Bearer " prefix; sample_rate/encoding/speech_model/keyterms_prompt as
query params; JSON Begin/Turn/Termination messages in, binary PCM16 frames
out, `{"type":"Terminate"}` to close). See spikes/protocol/PROTOCOL.md for the
source citations behind those facts.

sample_rate finding (why it's a constructor arg, not hardcoded): PROTOCOL.md
and spike_two_path.py's header both cite the Streaming v3 websocket spec page
listing `sample_rate` as a query param, "int, 8000-96000, default 16000" --
16000 (what the browser actually sends) is inside that documented range and
is the documented default. This is a different API from AssemblyAI's Voice
Agent API, which PROTOCOL.md separately notes requires 24 kHz -- that
constraint does not apply here since we never touch the Voice Agent path.

Turn formatting: the Turn message carries `turn_is_formatted` (a
server-reported flag), not a client-settable "format_turns" request param --
neither PROTOCOL.md nor the spike surfaced one. PROTOCOL.md quotes the docs
directly on what a finalized Turn contains: "the session emits a Turn message
with `end_of_turn: true` (fully formatted, punctuation/casing/entities
rendered)". So the `transcript` field on an end_of_turn Turn is already the
formatted text -- on_turn is fed that field as-is, for both partials and
finals, with no extra formatting step.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
import urllib.parse
from typing import Any, Awaitable, Callable

import websockets

logger = logging.getLogger("clausecatcher.stt")

AAI_WS_URL = "wss://streaming.assemblyai.com/v3/ws"
DEFAULT_SPEECH_MODEL = "universal-3-5-pro"
COST_PER_HOUR_USD = 0.45  # universal-3-5-pro worst-case rate (PROTOCOL.md pricing)

# All bounds below are module-level so tests can shrink them (e.g.
# `stt.BEGIN_TIMEOUT_S = 0.2`) before calling start()/send_audio() -- methods
# read these names at call time, not at import/class-definition time.
CONNECT_TIMEOUT_S = 15
BEGIN_TIMEOUT_S = 15
SEND_TIMEOUT_S = 1.0
CLOSE_TIMEOUT_S = 3
READER_POLL_S = 5.0  # bounds each recv() in the reader loop so SESSION_MAX_S is enforceable
SESSION_MAX_S = 900


class SttSetupError(Exception):
    """start() failed: connect refused/timed out, or no Begin within BEGIN_TIMEOUT_S."""


class StreamingTranscriber:
    def __init__(
        self,
        api_key: str,
        *,
        on_turn: Callable[[str, bool], Awaitable[None]],
        keyterms: list[str] | None = None,
        sample_rate: int = 16000,
        speech_model: str = DEFAULT_SPEECH_MODEL,
        ws_url: str | None = None,
    ) -> None:
        self._api_key = api_key
        self._on_turn = on_turn
        self._keyterms = keyterms
        self._sample_rate = sample_rate
        self._speech_model = speech_model
        self._ws_url = ws_url or AAI_WS_URL

        self._ws: Any = None
        self._reader_task: asyncio.Task | None = None
        self._buf = bytearray()  # odd trailing byte carried across send_audio calls
        self._last_partial: str | None = None
        self._start_monotonic: float | None = None
        self._end_monotonic: float | None = None
        self._stats = {"bytes_sent": 0, "chunks_dropped": 0, "turns": 0, "partials": 0}

    async def start(self) -> None:
        query = {
            "sample_rate": str(self._sample_rate),
            "encoding": "pcm_s16le",
            "speech_model": self._speech_model,
        }
        if self._keyterms:
            query["keyterms_prompt"] = json.dumps(self._keyterms)
        url = f"{self._ws_url}?{urllib.parse.urlencode(query)}"

        try:
            self._ws = await asyncio.wait_for(
                websockets.connect(
                    url,
                    additional_headers={"Authorization": self._api_key},
                    close_timeout=CLOSE_TIMEOUT_S,
                ),
                timeout=CONNECT_TIMEOUT_S,
            )
        except Exception as exc:  # noqa: BLE001 - any connect failure is a setup failure
            raise SttSetupError(f"connect failed: {exc}") from exc

        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=BEGIN_TIMEOUT_S)
            msg = json.loads(raw)
        except Exception as exc:  # noqa: BLE001
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
            raise SttSetupError(f"did not receive Begin: {exc}") from exc
        if msg.get("type") != "Begin":
            with contextlib.suppress(Exception):
                await self._ws.close()
            self._ws = None
            raise SttSetupError(f"expected Begin, got {msg.get('type')!r}")

        self._start_monotonic = time.monotonic()
        self._reader_task = asyncio.create_task(self._reader_loop())

    async def send_audio(self, pcm16: bytes) -> None:
        if not pcm16:
            return
        data = bytes(self._buf) + pcm16
        self._buf = bytearray()
        if len(data) % 2:
            self._buf = bytearray(data[-1:])
            data = data[:-1]
        if not data:
            return
        if self._ws is None:
            self._stats["chunks_dropped"] += 1
            return
        try:
            await asyncio.wait_for(self._ws.send(data), timeout=SEND_TIMEOUT_S)
            self._stats["bytes_sent"] += len(data)
        except Exception:  # noqa: BLE001 - backpressure/closed socket: drop and count, never raise
            self._stats["chunks_dropped"] += 1

    async def _reader_loop(self) -> None:
        while True:
            if self._start_monotonic is not None and time.monotonic() - self._start_monotonic > SESSION_MAX_S:
                # Can't `await self.stop()` from inside the task stop() cancels --
                # that would cancel/await ourselves. Hand cleanup to a new task instead.
                asyncio.create_task(self.stop())
                return
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=READER_POLL_S)
            except asyncio.TimeoutError:
                continue
            except (websockets.exceptions.ConnectionClosed, Exception):
                return
            if isinstance(raw, (bytes, bytearray)):
                continue
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("type")
            if mtype == "Turn":
                transcript = msg.get("transcript", "")
                end_of_turn = bool(msg.get("end_of_turn"))
                if end_of_turn:
                    self._stats["turns"] += 1
                    await self._safe_on_turn(transcript, True)
                elif transcript != self._last_partial:
                    self._last_partial = transcript
                    self._stats["partials"] += 1
                    await self._safe_on_turn(transcript, False)
            elif mtype == "Termination":
                return

    async def _safe_on_turn(self, text: str, end_of_turn: bool) -> None:
        try:
            await self._on_turn(text, end_of_turn)
        except Exception:  # noqa: BLE001 - a bad callback must never kill the reader
            logger.exception("on_turn raised (end_of_turn=%s)", end_of_turn)

    async def stop(self) -> None:
        if self._ws is None:
            return  # idempotent: already stopped (or never started)
        ws, self._ws = self._ws, None
        if self._end_monotonic is None:
            self._end_monotonic = time.monotonic()

        task, self._reader_task = self._reader_task, None
        if task is not None:
            task.cancel()
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await task

        with contextlib.suppress(Exception):
            await asyncio.wait_for(ws.send(json.dumps({"type": "Terminate"})), timeout=CLOSE_TIMEOUT_S)
        with contextlib.suppress(Exception):
            await asyncio.wait_for(ws.close(), timeout=CLOSE_TIMEOUT_S)

    @property
    def est_cost_usd(self) -> float:
        if self._start_monotonic is None:
            return 0.0
        end = self._end_monotonic if self._end_monotonic is not None else time.monotonic()
        elapsed = max(0.0, end - self._start_monotonic)
        return (elapsed / 3600.0) * COST_PER_HOUR_USD

    @property
    def stats(self) -> dict:
        return dict(self._stats)


# --- keyterms_from_clauses ---------------------------------------------------

MAX_KEYTERMS = 100
MAX_KEYTERM_LEN = 50

# ponytail: regex heuristics, not NLP. keyterms_prompt is a recognition-accuracy
# hint (docs: "improve recognition accuracy for"), not a hard match requirement,
# so false positives/negatives here are cheap -- upgrade to real NLP extraction
# if keyterm quality is ever measured directly.
_NUMBER_WORD_RE = re.compile(r"\b\d+\s+[a-zA-Z]+\b")
_NUMBER_HYPHEN_WORD_RE = re.compile(r"\b\d+-[a-zA-Z]+\b")
_NUMBER_SLASH_RE = re.compile(r"\b\d+/\d+\b")
_PROPER_PHRASE_RE = re.compile(r"\b(?:[A-Z][a-zA-Z]*\s+){1,4}[A-Z][a-zA-Z]*\b")


def keyterms_from_clauses(clauses: list[dict]) -> list[str]:
    """Build a keyterms_prompt list (AssemblyAI cap: 100 terms) from contract
    clauses: each clause's title, plus distinctive numbers/phrases pulled out
    of literal_text (e.g. "50 seats", "60 days", "24/7", "Premium Support
    Addendum"). Deduped case-insensitively, order preserved, each term capped
    to 50 chars.
    """
    seen: set[str] = set()
    terms: list[str] = []

    def add(term: str) -> None:
        term = term.strip()[:MAX_KEYTERM_LEN]
        if term and term.lower() not in seen:
            seen.add(term.lower())
            terms.append(term)

    for clause in clauses:
        title = clause.get("title")
        if title:
            add(title)
        text = clause.get("literal_text") or ""
        for pattern in (_NUMBER_WORD_RE, _NUMBER_HYPHEN_WORD_RE, _NUMBER_SLASH_RE, _PROPER_PHRASE_RE):
            for match in pattern.findall(text):
                add(match)

    return terms[:MAX_KEYTERMS]
