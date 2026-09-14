"""
PROTOTYPE / SPIKE - throwaway. Do not import from this file or build on it.
Answers 3 empirical questions about AssemblyAI's Voice Agent API in single
WebSocket sessions (one session per test). See mattpocock-skills:prototype.

Run:  python spike_voice_agent.py [--audio-dir PATH] [--only Q1,Q2,Q3]
                                   [--sample-rate-override N] [--omit-input-format]
Needs env var ASSEMBLYAI_API_KEY. Without it: prints a message, exits 2,
makes ZERO network calls (checked before anything network-related runs).

REQUIRED INPUT WAV FORMAT (so the harness agent generates matching files):
    PCM16, mono, ANY integer sample rate -- the WAV's own rate is read and
    sent explicitly as session.update's input.format.sample_rate, so a
    16kHz file (e.g. matching AssemblyAI Streaming v3's default, which is
    what the harness agent's spikes/harness/FORMAT.md chose) works fine; the
    24kHz figure quoted elsewhere is only the API's default when the format
    field is *omitted*.
    Source: https://www.assemblyai.com/docs/voice-agents/voice-agent-api/api-spec/create-agent
    ("sample_rate": integer, example 24000; "Defaults to PCM at 24 kHz if omitted")
    Bit depth/channels are NOT configurable per that schema (encoding is
    audio/pcm|audio/pcmu|audio/pcma only) -- mono 16-bit is assumed to match
    AssemblyAI Streaming v3's stated default (harness FORMAT.md), unverified
    for the Voice Agent API specifically.
    Files expected: rep_pitch.wav, monitor_question.wav in --audio-dir
    (default: <this file>/../harness/audio).
    If a WAV isn't mono 16-bit, the script exits loudly instead of silently
    resampling -- fix the generator, not this script.

--sample-rate-override N: asserts the WAV's actual rate equals N and, if so,
    writes N (not the WAV's own rate -- though by that assertion they're
    identical) into session.update's declared sample_rate. If the WAV's
    actual rate differs, the run REFUSES TO START (exits before any network
    call) rather than silently sending a rate that doesn't match the audio.
--omit-input-format: sends no "input" block in session.update at all
    (Q2/Q3 only; Q1 never sends one).

Protocol details below are cited to the specific doc page they came from.
Anything not directly quoted/shown by WebFetch on those pages is marked
`# UNVERIFIED:` with a note on why the choice was made.

Docs consulted (2026-09-13, via WebFetch):
  - https://www.assemblyai.com/docs/voice-agents/voice-agent-api
  - https://www.assemblyai.com/docs/voice-agents/voice-agent-api/events-reference
  - https://www.assemblyai.com/docs/voice-agents/voice-agent-api/tools
  - https://www.assemblyai.com/docs/voice-agents/voice-agent-api/browser-integration
  - https://www.assemblyai.com/docs/voice-agents/voice-agent-api/api-spec/create-agent

Session setup handshake (live-verified 2026-09-13, see
spikes/protocol/PROTOCOL.md "Event names audit" and "Live-run doc check
(2026-09-13)"): events-reference says session.update is sent "before
session.ready" and that input.audio should start "only after" session.ready
-- but all 3 live sessions got session.updated first (undocumented ordering;
session.updated is documented only as the ack for a *later*, mid-conversation
session.update). open_session() below loops on recv() until the real
session.ready, a session.error (-> SessionSetupError), or
SESSION_READY_TIMEOUT_S elapses (-> SessionSetupTimeout) -- callers only get
`ws` after that loop exits cleanly, so "never send input before ready" is
structurally enforced here, not left to caller discipline.

Cost guard: hard 90s wall-clock cap per test, enforced end-to-end -- an
absolute deadline (session-open time + HARD_CAP_S) is computed once per test
and checked both by stream_wav (per audio chunk) and by drain (asyncio.
wait_for). session.end is always sent in `finally`, websocket always closed,
elapsed + est. cost ($4.50/hr) always printed -- even on timeout/exception.
SESSION_READY_TIMEOUT_S (10s) is well inside HARD_CAP_S (90s), so the setup
wait never extends a test's worst-case wall time beyond what
harness/run_spikes.py already derives from HARD_CAP_S.
"""
import argparse
import asyncio
import base64
import contextlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
import wave
from contextlib import asynccontextmanager
from pathlib import Path

import websockets
import websockets.exceptions

# ---- verified endpoints (browser-integration page, quoted verbatim) ----
TOKEN_URL = "https://agents.assemblyai.com/v1/token"  # GET, Authorization: Bearer <key>
WS_URL_BASE = "wss://agents.assemblyai.com/v1/ws"  # ?token=<token>, no Authorization header

DEFAULT_OUTPUT_SAMPLE_RATE = 24000  # verified: create-agent api-spec, "Defaults to PCM at 24 kHz if omitted"
SAMPLE_WIDTH_BYTES = 2  # PCM16 -- assumed, see header comment
CHANNELS = 1

COST_PER_SEC = 4.50 / 3600.0
HARD_CAP_S = 90
CONNECT_TIMEOUT_S = 15  # matches token-fetch/session.ready timeouts already used below
CLEANUP_TIMEOUT_S = 3  # bounds session.end send + ws.close() so a silent/unresponsive peer can't extend a run past HARD_CAP_S
NEGATIVE_CONTROL_WINDOW_S = 3  # Q1: fixed silent window before injecting, to rule out an auto-greeting-on-connect confound
SESSION_READY_TIMEOUT_S = 10  # setup handshake (session.update -> ... -> session.ready) bound; counted inside HARD_CAP_S, not on top of it

ALL_TEST_IDS = ["Q1", "Q2", "Q3"]

# --- Q2 --q2-variant configs (verbatim from protocol/PROBE_A_SPEC.md P1/P2/P3) ---
Q2_SYSTEM_PROMPT_BASE = (  # baseline + P1 silence_only + P2 turn_extreme
    "You are ClauseCatcher. Stay completely silent and do not "
    "respond to anything unless the speaker directly addresses "
    "you by name, 'ClauseCatcher'. Ordinary conversation not "
    "directed at you gets no reply at all."
)
Q2_SYSTEM_PROMPT_STRONG = (  # P3 strong_prompt -- name-exception removed, per spec
    "You are a silent note-taking system, not a conversational participant. "
    "You must never produce any audio or text reply to anything the speaker "
    "says, under any circumstances — this includes if the speaker "
    "addresses you by name or asks you a direct question. Your only "
    "permitted output is when the system sends you an explicit instruction "
    "via a separate channel. If you are ever unsure whether to speak, the "
    "answer is: do not speak."
)
# PROBE_A_SPEC.md Addendum 2026-09-14 (Candidate A, corrected rerun): the
# original 1600/1600 values got a live 2026-09-14 session.error rejection
# ("min_silence must be strictly less than max_silence") before session.ready.
# Per https://www.assemblyai.com/docs/api-reference/specs/voice-agent-api.yaml
# TurnDetection: min_silence/max_silence are both `int` ms, range 50-10000,
# and min_silence MUST be strictly less than max_silence (server-enforced,
# confirmed by that rejection); interruption_delay is prose-only (not in the
# YAML schema), documented range 0-1000ms. vad_threshold/interrupt_response
# unchanged from the original PROTOCOL.md-documented extremes.
Q2_TURN_DETECTION_EXTREME = {
    "vad_threshold": 1.0,
    "min_silence": 1000,
    "max_silence": 10000,
    "interrupt_response": False,
    "interruption_delay": 1000,
}
Q2_VARIANT_WAV = {  # which wav (inside --audio-dir) each variant streams
    "baseline": "rep_pitch.wav",
    "silence_only": "silence_12s.wav",
    "turn_extreme": "rep_pitch.wav",
    "strong_prompt": "rep_pitch.wav",
}
Q2_VARIANTS = tuple(Q2_VARIANT_WAV)


def build_q2_session_cfg(variant: str, declared_rate: int | None) -> dict:
    """Pure builder for Q2's session.update `session` dict, keyed by
    --q2-variant. `declared_rate=None` means --omit-input-format (no "input"
    block at all). "baseline" is byte-identical to the pre-spec config (same
    system_prompt, same input.format, no turn_detection) -- see
    PROBE_A_SPEC.md for the exact JSON P1/P2/P3 must match."""
    system_prompt = Q2_SYSTEM_PROMPT_STRONG if variant == "strong_prompt" else Q2_SYSTEM_PROMPT_BASE
    cfg = {"system_prompt": system_prompt}
    if declared_rate is not None:
        cfg["input"] = {"format": {"encoding": "audio/pcm", "sample_rate": declared_rate}}
        if variant == "turn_extreme":
            cfg["input"]["turn_detection"] = dict(Q2_TURN_DETECTION_EXTREME)
    return cfg


def _q2_grade(variant: str, reply_starts: int, transcript_user_count: int,
              input_processed: bool, error_events: list, stream_error: str | None = None) -> tuple[bool, bool]:
    """Pure Q2 pass/invalid grading, keyed by --q2-variant. PROBE_A_SPEC.md
    PASS rules: silence_only = 0 reply.started (and no errors); turn_extreme/
    strong_prompt = 0 reply.started AND >=1 transcript.user, else INVALID
    (spec: "no transcript.user for a rep-speech variant" -- rerun, don't
    count). "baseline" predates the spec and keeps the original
    input_processed-based rule for backward compatibility. Returns
    (passed, invalid); invalid is never True for a setup failure -- those
    are graded separately and keep their own 'setup error'/'no session.ready'
    detail text untouched (see test_session_ready.py's exact-prefix checks)."""
    if error_events or stream_error:
        return False, False
    if variant == "silence_only":
        return reply_starts == 0, False
    if variant in ("turn_extreme", "strong_prompt"):
        if transcript_user_count < 1:
            return False, True
        return reply_starts == 0, False
    return reply_starts == 0 and input_processed, False  # baseline


def _q2_spec_grade(setup_failed: bool, invalid: bool, passed: bool) -> str:
    """PROBE_A_SPEC.md Addendum item 5: PASS/FAIL/INVALID, distinct from the
    harness's raw `pass` bool (which prints FAIL for a setup failure that the
    spec defines as INVALID -- see addendum note). INVALID = setup_failed
    (SessionSetupError/SessionSetupTimeout before session.ready) OR `invalid`
    (the rep-speech-variant 0-transcript.user case _q2_grade already flags).
    Otherwise PASS/FAIL exactly follow `passed`."""
    if setup_failed or invalid:
        return "INVALID"
    return "PASS" if passed else "FAIL"


def _truncate_strings(obj, limit: int = 500):
    """Recursively truncate any string longer than `limit` chars inside a
    JSON-safe structure (dict/list/str/other) -- used so a raw
    session.update/session.updated payload dropped into evidence never
    bloats the results JSON with e.g. a huge echoed field. Non-string leaves
    pass through unchanged."""
    if isinstance(obj, str):
        return obj if len(obj) <= limit else obj[:limit] + f"...<truncated {len(obj) - limit} chars>"
    if isinstance(obj, dict):
        return {k: _truncate_strings(v, limit) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_truncate_strings(v, limit) for v in obj]
    return obj


# literal clause text the tool must echo back verbatim (Q3)
CLAUSE_4_2_TEXT = (
    "Clause 4.2: This agreement automatically renews for successive "
    "one-year terms unless either party provides written notice of "
    "non-renewal at least sixty (60) days before the end of the "
    "then-current term."
)

SCRIPT_DIR = Path(__file__).resolve().parent
OUT_DIR = SCRIPT_DIR / "out"
OUT_PATH = OUT_DIR / "results_voice_agent.json"


class SessionSetupError(Exception):
    """Raised by open_session when session.error arrives before
    session.ready. Carries the raw error event plus every setup event seen
    so far, so the caller can build a result without re-parsing str(e)."""

    def __init__(self, evt: dict, setup_events: list):
        self.evt = evt
        self.setup_events = list(setup_events)
        code = evt.get("code", "?")
        message = evt.get("message", "?")
        super().__init__(f"setup error: {code} {message}")


class SessionSetupTimeout(Exception):
    """Raised by open_session when session.ready never arrives within
    SESSION_READY_TIMEOUT_S. Carries the setup events actually seen (so the
    detail can show what the server sent instead, e.g. session.updated)."""

    def __init__(self, setup_events: list, timeout_s: float):
        self.setup_events = list(setup_events)
        types = [e[1] for e in self.setup_events]
        super().__init__(f"no session.ready within {timeout_s:g}s; setup_events={types}")


def get_token(api_key: str, expires_in_seconds: int = 300) -> str:
    """GET https://agents.assemblyai.com/v1/token -- verified via WebFetch on
    browser-integration page: Authorization: Bearer header, expires_in_seconds
    query param (1-600), response {"token": "..."}."""
    url = f"{TOKEN_URL}?expires_in_seconds={expires_in_seconds}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())["token"]


def load_wav(path: Path) -> tuple[bytes, int]:
    """Read a WAV, return (raw PCM frames, sample_rate). Exits loudly if the
    file isn't mono 16-bit -- sample rate is NOT checked here, it's read and
    passed through to session.update instead (see header comment)."""
    with wave.open(str(path), "rb") as w:
        rate, width, channels = w.getframerate(), w.getsampwidth(), w.getnchannels()
        if (width, channels) != (SAMPLE_WIDTH_BYTES, CHANNELS):
            sys.exit(
                f"FATAL: {path.name} is {width*8}bit/{channels}ch, "
                f"need 16bit/{CHANNELS}ch (see header comment). "
                "Fix the WAV generator, not this script."
            )
        return w.readframes(w.getnframes()), rate


def save_wav(path: Path, pcm: bytes, sample_rate: int = DEFAULT_OUTPUT_SAMPLE_RATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(CHANNELS)
        w.setsampwidth(SAMPLE_WIDTH_BYTES)
        w.setframerate(sample_rate)
        w.writeframes(pcm)


def classify_setup_event(evt: dict) -> str:
    """Pure classification of one event seen during session setup (before
    session.ready), used by open_session's wait loop and exercised directly
    by --selftest. Returns "ready" (stop waiting, proceed), "error"
    (session.error/error -- caller should raise), or "wait" (anything else,
    e.g. session.updated -- keep waiting). See events-reference + the
    "error" vs "session.error" note in PROTOCOL.md's event-names audit."""
    t = evt.get("type")
    if t == "session.ready":
        return "ready"
    if t in ("session.error", "error"):
        return "error"
    return "wait"


def _compact_event_log(entries: list, cap: int = 2000) -> list:
    """entries: [[t_ms, type], ...] in chronological order. Collapses a run
    of consecutive reply.audio entries into one summary
    {"type": "reply.audio", "count", "first_ms", "last_ms"} -- a single
    reply can be hundreds of audio chunks, which would otherwise bloat the
    evidence JSON for no diagnostic value. Caps the result at `cap` entries
    (keeps the head, appends a truncation marker) since this feeds a JSON
    results file, not a log stream."""
    out = []
    audio_first = audio_last = None
    audio_count = 0

    def flush_audio():
        if audio_count:
            out.append({"type": "reply.audio", "count": audio_count,
                        "first_ms": audio_first, "last_ms": audio_last})

    for t_ms, etype in entries:
        if etype == "reply.audio":
            audio_count += 1
            audio_last = t_ms
            if audio_first is None:
                audio_first = t_ms
            continue
        flush_audio()
        audio_first = audio_last = None
        audio_count = 0
        out.append([t_ms, etype])
    flush_audio()

    if len(out) > cap:
        out = out[:cap] + [{"truncated": True, "total": len(out)}]
    return out


@asynccontextmanager
async def open_session(api_key: str, session_cfg: dict, label: str):
    """One session, start to finish. Always sends session.end + closes the
    socket + prints elapsed/cost, even on exception/timeout/cancellation --
    including a token-fetch, connect, or setup failure/timeout, which is why
    `ws` acquisition is now INSIDE the try: the finally must run (and print)
    no matter which step fails.

    Setup handshake: after sending session.update, this loops on recv()
    until session.ready (classify_setup_event -> "ready"), a session.error
    (-> raises SessionSetupError), or SESSION_READY_TIMEOUT_S elapses (->
    raises SessionSetupTimeout). Any other event (e.g. the live-observed
    session.updated) is recorded and waited past. input.audio/
    conversation.message are never sent before session.ready is reached --
    callers only get `ws` via `yield` after this loop exits cleanly, so
    that's enforced structurally here, not by caller discipline.

    Yields (ws, setup_events, ready_at): setup_events is every event seen
    during the loop as [ms_since_connect, type]; ready_at is time.time()
    when session.ready arrived, for callers to timestamp their own events
    relative to it.
    """
    start = time.time()
    ws = None
    setup_events: list = []
    try:
        token = get_token(api_key)
        ws = await asyncio.wait_for(
            websockets.connect(
                f"{WS_URL_BASE}?token={token}",
                # both explicit: the library's own open_timeout default (10s)
                # otherwise fires before this wait_for's CONNECT_TIMEOUT_S
                # (15s) ever gets a chance to, making that constant a lie.
                open_timeout=CONNECT_TIMEOUT_S,
                close_timeout=CLEANUP_TIMEOUT_S,
            ),
            timeout=CONNECT_TIMEOUT_S,
        )
        # UNVERIFIED: events-reference shows session.update nested under
        # {"type": "session.update", "session": {...}} -- confirmed verbatim
        # on that page, used as-is.
        await ws.send(json.dumps({"type": "session.update", "session": session_cfg}))

        ready_deadline = start + SESSION_READY_TIMEOUT_S
        while True:
            remaining = ready_deadline - time.time()
            if remaining <= 0:
                raise SessionSetupTimeout(setup_events, SESSION_READY_TIMEOUT_S)
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=remaining)
            except asyncio.TimeoutError:
                raise SessionSetupTimeout(setup_events, SESSION_READY_TIMEOUT_S)
            evt = json.loads(raw)
            # 3rd element (full raw evt) is additive -- SessionSetupTimeout's
            # `e[1]` type access and every existing 2-element construction
            # elsewhere in this file still work unchanged. Needed so Q2 can
            # recover session.updated's full payload, which every live run
            # so far has shown arriving during setup, before session.ready.
            setup_events.append([round((time.time() - start) * 1000), evt.get("type"), evt])
            outcome = classify_setup_event(evt)
            if outcome == "ready":
                break
            if outcome == "error":
                raise SessionSetupError(evt, setup_events)
            print(f"[{label}] setup: got {evt.get('type')!r}, still waiting for session.ready")
        ready_at = time.time()
        yield ws, setup_events, ready_at
    finally:
        if ws is not None:
            # Both cleanup steps are bounded and swallow everything, including
            # asyncio.CancelledError (a BaseException -- contextlib.suppress
            # with only Exception in the tuple does NOT catch it), so a
            # cancelled test or an unresponsive/already-dead peer can't skip
            # teardown or block it past CLEANUP_TIMEOUT_S.
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await asyncio.wait_for(
                    ws.send(json.dumps({"type": "session.end"})),  # verified: events-reference
                    timeout=CLEANUP_TIMEOUT_S,
                )
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await ws.close()  # close_timeout=CLEANUP_TIMEOUT_S set on connect() above
        elapsed = time.time() - start
        cost = elapsed * COST_PER_SEC
        print(f"[{label}] elapsed={elapsed:.1f}s est_cost=${cost:.4f}")


async def stream_wav(ws, pcm: bytes, sample_rate: int, label: str, deadline: float) -> dict:
    """Chunk PCM into ~100ms frames and send as input.audio, then a short
    trailing silence so server-side VAD has something to detect end-of-speech
    on. Stops sending once `deadline` (absolute time.time() cutoff, set by
    the caller to session-open-time + HARD_CAP_S) passes -- the caller then
    falls straight through to open_session's `finally`, which still sends
    session.end and closes within CLEANUP_TIMEOUT_S on top of that budget.

    Returns {"sent_bytes", "deadline_hit", "error"} so the caller can put
    what actually happened into its evidence/pass-grading instead of only
    inferring it from downstream event counts:
      - deadline_hit=True: the deadline was reached (either between chunks,
        or the send itself didn't complete before it) -- not itself a
        failure, just a fact for evidence.
      - error=<str>: the peer went away mid-send (ConnectionClosed/OSError)
        -- a real failure the caller should grade as FAIL with this detail,
        never a crash.

    Each `ws.send` is itself wrapped in asyncio.wait_for bounded by the
    remaining time to `deadline`: a peer that never reads (backpressure) or
    a plain network stall would otherwise let a single `await ws.send(...)`
    block past the deadline with no timeout at all, which is what let a
    HARD_CAP_S=6 run measure 12.27s wall under a mock server that never
    reads.
    # UNVERIFIED: chunk size (100ms), send cadence (real-time sleep), and the
    # trailing-silence padding are NOT specified anywhere in the fetched docs
    # -- they're a pragmatic choice to mimic a live mic feed. The message
    # shape itself (type: input.audio, audio: base64 PCM16) IS verified
    # (events-reference page).
    """
    chunk_bytes = int(sample_rate * 0.1) * SAMPLE_WIDTH_BYTES  # 100ms
    silence = b"\x00" * chunk_bytes * 5  # 500ms trailing silence
    sent = 0
    for data in (pcm, silence):
        for i in range(0, len(data), chunk_bytes):
            remaining = deadline - time.time()
            if remaining <= 0:
                print(f"[{label}] stream_wav hit deadline, stopped early after {sent} bytes")
                return {"sent_bytes": sent, "deadline_hit": True, "error": None}
            chunk = data[i : i + chunk_bytes]
            msg = json.dumps({
                "type": "input.audio",
                "audio": base64.b64encode(chunk).decode("ascii"),
            })
            try:
                await asyncio.wait_for(ws.send(msg), timeout=max(0.05, remaining))
            except asyncio.TimeoutError:
                print(f"[{label}] stream_wav send blocked past deadline, stopped early after {sent} bytes")
                return {"sent_bytes": sent, "deadline_hit": True, "error": None}
            except (websockets.exceptions.ConnectionClosed, OSError) as e:
                detail = f"{type(e).__name__}: {e}"
                print(f"[{label}] stream_wav: peer went away mid-send ({detail}), stopped after {sent} bytes")
                return {"sent_bytes": sent, "deadline_hit": False, "error": detail}
            sent += len(chunk)
            await asyncio.sleep(0.1)
    print(f"[{label}] streamed {len(pcm)} bytes audio + 500ms silence")
    return {"sent_bytes": sent, "deadline_hit": False, "error": None}


async def drain(ws, deadline: float, on_event=None) -> list[dict]:
    """Collect every server event until `deadline` (time.time() cutoff).
    on_event(evt) may be called per event for side effects (e.g. auto-reply
    to tool.call, or timestamping into a caller-owned event_log); returning
    True from it stops the drain early.

    Extra fix (verifier finding #5): `ws.recv()` was already timeout-bounded
    but not guarded against the peer disappearing mid-drain
    (ConnectionClosed/OSError) -- that would otherwise propagate straight out
    of every caller uncaught. Treated the same as a clean timeout: stop
    draining, return whatever events were already collected (the callers'
    existing pass-logic already fails correctly on a short/empty event list;
    no separate error channel needed here)."""
    events = []
    while time.time() < deadline:
        remaining = deadline - time.time()
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, remaining))
        except asyncio.TimeoutError:
            break
        except (websockets.exceptions.ConnectionClosed, OSError) as e:
            print(f"drain: peer went away mid-drain ({type(e).__name__}: {e}), stopping")
            break
        evt = json.loads(raw)
        events.append(evt)
        if on_event and on_event(evt):
            break
    return events


# --- pure grading logic (no I/O -- exercised directly by --selftest) --------

def _q1_pass(reply_started: bool, audio_chunks: list, user_speech: bool,
             error_events: list, control_reply_started: bool) -> bool:
    return (reply_started and bool(audio_chunks) and not user_speech
            and not error_events and not control_reply_started)


def _q3_pass(saw_tool_call: bool, sent_tool_result: bool, clause_in_transcript: bool,
             error_events: list, tool_result_send_errors: list,
             stream_error: str | None = None) -> bool:
    return (saw_tool_call and sent_tool_result and clause_in_transcript
            and not error_events and not tool_result_send_errors and not stream_error)


def _failed_result(result_id: str, elapsed: float, detail: str) -> dict:
    """Runner-contract dict ({"id","pass","est_cost_usd","detail"}) for a test
    that crashed before it could build its own result (see main_async).
    est_cost_usd is always elapsed-based, never hardcoded 0, since a socket
    may well have opened (and been billed) before the crash. Built without
    "id"/"test" as dict-literal keys on purpose -- see harness/
    test_results_contract.py's ast-based check, which counts every dict
    literal carrying both "pass" and "est_cost_usd" plus an "id"/"test" key
    as one of exactly 3 expected Q1/Q2/Q3 result shapes; assigning those two
    keys by subscript here keeps this helper from being double-counted."""
    d = {"pass": False, "est_cost_usd": round(elapsed * COST_PER_SEC, 4)}
    d["id"] = result_id
    d["test"] = result_id
    d["detail"] = detail
    return d


def _selftest() -> None:
    """Offline asserts for the pure grading functions + _failed_result's
    contract shape. No network, no event loop, no ASSEMBLYAI_API_KEY use."""
    assert _q1_pass(True, ["chunk"], False, [], False) is True
    assert _q1_pass(True, ["chunk"], True, [], False) is False  # preceding user speech
    assert _q1_pass(True, [], False, [], False) is False  # no audio
    assert _q1_pass(False, ["chunk"], False, [], False) is False  # no reply.started
    assert _q1_pass(True, ["chunk"], False, [{"type": "error"}], False) is False  # session error
    assert _q1_pass(True, ["chunk"], False, [], True) is False  # control window also replied

    # _q2_grade: (passed, invalid) truth table, per PROBE_A_SPEC.md
    assert _q2_grade("baseline", 0, 0, True, []) == (True, False)
    assert _q2_grade("baseline", 1, 0, True, []) == (False, False)  # unsolicited reply
    assert _q2_grade("baseline", 0, 0, False, []) == (False, False)  # input never processed
    assert _q2_grade("baseline", 0, 0, True, [{"type": "session.error"}]) == (False, False)
    assert _q2_grade("baseline", 0, 0, True, [], "ConnectionClosedError: boom") == (False, False)

    assert _q2_grade("silence_only", 0, 0, False, []) == (True, False)  # no speech in this variant at all
    assert _q2_grade("silence_only", 1, 0, False, []) == (False, False)  # unsolicited reply
    assert _q2_grade("silence_only", 0, 0, False, [{"type": "error"}]) == (False, False)

    assert _q2_grade("turn_extreme", 0, 1, True, []) == (True, False)
    assert _q2_grade("turn_extreme", 1, 1, True, []) == (False, False)  # replied despite speech seen
    assert _q2_grade("turn_extreme", 0, 0, True, []) == (False, True)  # INVALID: no transcript.user
    assert _q2_grade("strong_prompt", 0, 1, True, []) == (True, False)
    assert _q2_grade("strong_prompt", 0, 0, True, []) == (False, True)  # INVALID
    assert _q2_grade("strong_prompt", 0, 0, True, [{"type": "error"}]) == (False, False)  # error wins over INVALID

    # _q2_spec_grade: PASS/FAIL/INVALID mapping, per PROBE_A_SPEC.md addendum item 5
    assert _q2_spec_grade(True, False, False) == "INVALID"  # setup error (SessionSetupError)
    assert _q2_spec_grade(True, False, True) == "INVALID"  # setup timeout (SessionSetupTimeout) -- setup_failed wins regardless of `passed`
    p, inv = _q2_grade("turn_extreme", 0, 0, True, [])  # rep-speech variant, 0 transcript.user
    assert _q2_spec_grade(False, inv, p) == "INVALID"
    p, inv = _q2_grade("turn_extreme", 1, 1, True, [])  # replied despite transcripts seen -> FAIL
    assert _q2_spec_grade(False, inv, p) == "FAIL"
    p, inv = _q2_grade("turn_extreme", 0, 1, True, [])  # 0 replies, transcripts present -> PASS
    assert _q2_spec_grade(False, inv, p) == "PASS"
    p, inv = _q2_grade("silence_only", 0, 0, False, [])  # silence_only, 0 replies -> PASS
    assert _q2_spec_grade(False, inv, p) == "PASS"

    # build_q2_session_cfg: variant -> expected config shape
    baseline_cfg = build_q2_session_cfg("baseline", 24000)
    assert baseline_cfg["system_prompt"] == Q2_SYSTEM_PROMPT_BASE
    assert baseline_cfg["input"] == {"format": {"encoding": "audio/pcm", "sample_rate": 24000}}
    assert "turn_detection" not in baseline_cfg["input"]

    silence_cfg = build_q2_session_cfg("silence_only", 24000)
    assert silence_cfg == baseline_cfg  # same config, only the streamed wav differs (Q2_VARIANT_WAV)

    turn_cfg = build_q2_session_cfg("turn_extreme", 24000)
    assert turn_cfg["system_prompt"] == Q2_SYSTEM_PROMPT_BASE
    assert turn_cfg["input"]["turn_detection"] == Q2_TURN_DETECTION_EXTREME

    strong_cfg = build_q2_session_cfg("strong_prompt", 24000)
    assert strong_cfg["system_prompt"] == Q2_SYSTEM_PROMPT_STRONG
    assert "turn_detection" not in strong_cfg["input"]

    omitted_cfg = build_q2_session_cfg("turn_extreme", None)  # --omit-input-format
    assert "input" not in omitted_cfg

    assert set(Q2_VARIANT_WAV) == set(Q2_VARIANTS)
    assert Q2_VARIANT_WAV["silence_only"] == "silence_12s.wav"
    assert Q2_VARIANT_WAV["baseline"] == Q2_VARIANT_WAV["turn_extreme"] == Q2_VARIANT_WAV["strong_prompt"] == "rep_pitch.wav"

    # _truncate_strings: long strings shortened, structure/short values untouched
    assert _truncate_strings("short") == "short"
    long_val = "x" * 600
    truncated = _truncate_strings(long_val, limit=500)
    assert truncated.startswith("x" * 500) and truncated != long_val and len(truncated) < len(long_val)
    nested = _truncate_strings({"a": ["ok", long_val], "b": 5})
    assert nested["a"][0] == "ok" and nested["a"][1] != long_val and nested["b"] == 5

    assert _q3_pass(True, True, True, [], []) is True
    assert _q3_pass(False, True, True, [], []) is False  # no tool.call
    assert _q3_pass(True, False, True, [], []) is False  # tool.result never sent
    assert _q3_pass(True, True, False, [], []) is False  # clause text not echoed verbatim
    assert _q3_pass(True, True, True, [{"type": "error"}], []) is False
    assert _q3_pass(True, True, True, [], ["send failed"]) is False
    assert _q3_pass(True, True, True, [], [], "OSError: boom") is False  # peer died mid-stream

    fr = _failed_result("Q1", 12.3, "exception: RuntimeError: boom")
    assert fr["id"] == "Q1" and fr["test"] == "Q1"
    assert fr["pass"] is False
    assert fr["est_cost_usd"] == round(12.3 * COST_PER_SEC, 4)
    assert fr["detail"] == "exception: RuntimeError: boom"
    assert set(fr) == {"pass", "est_cost_usd", "id", "test", "detail"}

    assert classify_setup_event({"type": "session.ready"}) == "ready"
    assert classify_setup_event({"type": "session.updated"}) == "wait"
    assert classify_setup_event({"type": "session.error", "code": "internal_error"}) == "error"
    assert classify_setup_event({"type": "error"}) == "error"  # undocumented alias, PROTOCOL.md
    assert classify_setup_event({"type": "reply.started"}) == "wait"

    setup_err = SessionSetupError({"code": "internal_error", "message": "boom"}, [[0, "session.updated"]])
    assert str(setup_err) == "setup error: internal_error boom"
    assert setup_err.setup_events == [[0, "session.updated"]]

    setup_timeout = SessionSetupTimeout([[0, "session.updated"]], 10)
    assert str(setup_timeout).startswith("no session.ready within 10s; setup_events=")
    assert "session.updated" in str(setup_timeout)

    log = _compact_event_log([[0, "session.ready"], [10, "reply.audio"], [20, "reply.audio"],
                               [30, "reply.audio"], [40, "reply.done"]])
    assert log == [
        [0, "session.ready"],
        {"type": "reply.audio", "count": 3, "first_ms": 10, "last_ms": 30},
        [40, "reply.done"],
    ]
    assert _compact_event_log([]) == []
    big = [[i, "x"] for i in range(2500)]
    capped = _compact_event_log(big, cap=2000)
    assert len(capped) == 2001  # 2000 kept + 1 truncation marker
    assert capped[-1] == {"truncated": True, "total": 2500}

    print("selftest: all asserts passed")


async def test_proactive(api_key: str) -> dict:
    """Q1: after session.ready, we first hold a NEGATIVE_CONTROL_WINDOW_S
    silent window (nothing injected) to rule out an auto-greeting-on-connect
    confounding the result, then inject a flag via conversation.message and
    trigger reply.create -- PASS if reply.started/reply.audio arrive with NO
    preceding user speech (we never send input.audio at all) AND the control
    window produced no reply AND the injection did.
    conversation.message uses "role": "user" -- PROTOCOL.md's only documented
    example (line 43, repeated line 57) uses role "user"; role "system" is
    NOT shown anywhere in PROTOCOL.md for this event.
    Both message types verified verbatim on events-reference page.

    If session setup itself fails (session.error before session.ready, or a
    SESSION_READY_TIMEOUT_S timeout), this test FAILS with detail set to
    that setup failure -- the body above never runs, so every other field
    stays at its "nothing happened" default."""
    label = "Q1_proactive"
    t0 = time.time()
    cfg = {"system_prompt": "You are ClauseCatcher, a contract clause assistant."}
    audio_chunks = []
    saw_reply_started = False
    saw_user_speech = False
    agent_text = ""
    error_events: list[dict] = []
    control_reply_started = False
    control_audio_chunks = 0
    control_events: list[dict] = []
    events: list[dict] = []
    setup_events: list = []
    event_log: list = []
    setup_fail_detail = None

    try:
        async with open_session(api_key, cfg, label) as (ws, setup_events, ready_at):
            def on_control_event(evt):
                nonlocal control_reply_started, control_audio_chunks
                t = evt.get("type")
                event_log.append([round((time.time() - ready_at) * 1000), t])
                if t == "reply.started":
                    control_reply_started = True
                if t == "reply.audio":
                    control_audio_chunks += 1
                if t in ("session.error", "error"):
                    error_events.append(evt)
                return False  # run out the whole control window, never stop early

            control_deadline = min(time.time() + NEGATIVE_CONTROL_WINDOW_S, t0 + HARD_CAP_S)
            control_events = await drain(ws, control_deadline, on_control_event)

            await ws.send(json.dumps({
                "type": "conversation.message",
                "role": "user",
                "content": "FLAG: greet the user proactively right now, in one short sentence.",
            }))
            await ws.send(json.dumps({"type": "reply.create"}))

            def on_event(evt):
                nonlocal saw_reply_started, saw_user_speech, agent_text
                t = evt.get("type")
                event_log.append([round((time.time() - ready_at) * 1000), t])
                if t in ("input.speech.started", "transcript.user", "transcript.user.delta"):
                    saw_user_speech = True
                if t == "reply.started":
                    saw_reply_started = True
                if t == "reply.audio":
                    audio_chunks.append(evt.get("data", ""))
                if t == "transcript.agent":
                    agent_text = evt.get("text", "")
                if t in ("session.error", "error"):
                    error_events.append(evt)
                return t == "reply.done"

            deadline = min(time.time() + 60, t0 + HARD_CAP_S)
            events = await drain(ws, deadline, on_event)
    except (SessionSetupError, SessionSetupTimeout) as e:
        setup_fail_detail = str(e)
        setup_events = e.setup_events

    if audio_chunks:
        pcm = b"".join(base64.b64decode(c) for c in audio_chunks if c)
        save_wav(OUT_DIR / "proactive.wav", pcm)

    if setup_fail_detail is not None:
        passed = False
        detail = setup_fail_detail
    else:
        passed = _q1_pass(saw_reply_started, audio_chunks, saw_user_speech, error_events, control_reply_started)
        detail = (f"reply_started={saw_reply_started} audio_chunks={len(audio_chunks)} "
                  f"preceding_user_speech={saw_user_speech} session_errors={len(error_events)} "
                  f"control_window_s={NEGATIVE_CONTROL_WINDOW_S} "
                  f"control_reply_started={control_reply_started} "
                  f"control_audio_chunks={control_audio_chunks}")
    elapsed = time.time() - t0
    print(f"[{label}] agent said: {agent_text!r} session_errors={len(error_events)} "
          f"control_reply_started={control_reply_started} setup_fail={setup_fail_detail!r}")
    return {
        "id": "Q1",  # runner contract (see spike_two_path.py): id/pass/est_cost_usd/detail
        "test": label,
        "pass": passed,
        "detail": detail,
        "evidence": {
            "reply_started": saw_reply_started,
            "reply_audio_chunks": len(audio_chunks),
            "preceding_user_speech": saw_user_speech,
            "agent_transcript": agent_text,
            "session_error_count": len(error_events),
            "session_errors": error_events,
            "control_window_s": NEGATIVE_CONTROL_WINDOW_S,
            "control_reply_started": control_reply_started,
            "control_audio_chunks": control_audio_chunks,
            "control_raw_event_types": [e.get("type") for e in control_events],
            "raw_event_types": [e.get("type") for e in events],
            "setup_events": setup_events,
            "setup_fail_detail": setup_fail_detail,
            "event_log": _compact_event_log(event_log),
        },
        "elapsed_s": round(elapsed, 1),
        "est_cost_usd": round(elapsed * COST_PER_SEC, 4),
    }


async def test_silence(api_key: str, wav_path: Path, sample_rate_override: int | None = None,
                        omit_input_format: bool = False, q2_variant: str = "baseline") -> dict:
    """Q2 (single-session variant): system_prompt tells the agent to stay
    silent unless addressed as 'ClauseCatcher' (or, for q2_variant
    "strong_prompt", a stronger "never speak" prompt with no name-exception
    at all -- see PROBE_A_SPEC.md). Stream `wav_path` (caller picks the file
    per Q2_VARIANT_WAV -- silence for "silence_only", the rep pitch
    otherwise). PASS rule is variant-dependent, see _q2_grade.

    Server events are read CONCURRENTLY with streaming via a background
    reader task started right after session.ready, so event_log timestamps
    are real arrival times (not all clustered at the point stream_wav
    happens to return) -- see mock proof (b). The task is bounded by the
    session's overall `deadline` (same cutoff stream_wav uses) and, after
    streaming finishes, is given a further short tail window before being
    cancelled and safely awaited.

    Setup failure (session.error before session.ready, or a
    SESSION_READY_TIMEOUT_S timeout) FAILS this test with detail set to that
    setup failure, same as test_proactive."""
    label = "Q2_silence"
    t0 = time.time()
    deadline = t0 + HARD_CAP_S  # one absolute cutoff for the whole session-open
    pcm, rate = load_wav(wav_path)
    declared_rate = None if omit_input_format else (
        sample_rate_override if sample_rate_override is not None else rate
    )
    cfg = build_q2_session_cfg(q2_variant, declared_rate)
    reply_starts = 0
    reply_audio_counts: list[int] = []  # one entry per reply.started, incremented by reply.audio
    agent_texts: list[str] = []
    user_texts: list[str] = []
    session_updated_payloads: list = []  # filled from setup_events once open_session yields
    # positive evidence the input was actually processed -- these three
    # event names are the ones this file already treats as verified
    # user-speech signals (see test_proactive's saw_user_speech check).
    input_evidence = {
        "transcript.user": 0,
        "transcript.user.delta": 0,
        "input.speech.started": 0,
    }
    error_events: list[dict] = []
    events: list[dict] = []
    setup_events: list = []
    event_log: list = []
    setup_fail_detail = None
    stream_info = {"sent_bytes": 0, "deadline_hit": False, "error": None}

    try:
        async with open_session(api_key, cfg, label) as (ws, setup_events, ready_at):
            # session.updated seen during setup (live-observed on every run
            # so far, before session.ready -- see PROTOCOL.md) -- setup_events
            # entries are [ms, type, evt] (see open_session).
            session_updated_payloads = [
                _truncate_strings(e[2]) for e in setup_events
                if len(e) > 2 and e[1] == "session.updated"
            ]

            def on_event(evt):
                nonlocal reply_starts
                t = evt.get("type")
                events.append(evt)
                event_log.append([round((time.time() - ready_at) * 1000), t])
                if t in input_evidence:
                    input_evidence[t] += 1
                if t == "transcript.user":
                    user_texts.append(evt.get("text", ""))
                if t == "transcript.agent":
                    agent_texts.append(evt.get("text", ""))
                if t == "reply.started":
                    reply_starts += 1
                    reply_audio_counts.append(0)
                if t == "reply.audio":
                    if reply_audio_counts:
                        reply_audio_counts[-1] += 1
                    else:
                        reply_audio_counts.append(1)  # audio with no preceding reply.started seen
                if t == "session.updated":
                    session_updated_payloads.append(_truncate_strings(evt))
                if t in ("session.error", "error"):
                    error_events.append(evt)
                return False  # never stop early -- we're counting for the whole window

            # Reader task starts right after session.ready (this point) so
            # event_log times are the real arrival times, concurrent with
            # stream_wav below -- not all read out afterward in one burst.
            reader_task = asyncio.create_task(drain(ws, deadline, on_event))
            stream_info = await stream_wav(ws, pcm, rate, label, deadline)
            # Post-stream: keep draining for a short tail window (same 10s
            # budget the old sequential code used), then stop the reader.
            tail_deadline = min(time.time() + 10, deadline)
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await asyncio.wait_for(reader_task, timeout=max(0.01, tail_deadline - time.time()))
            if not reader_task.done():
                reader_task.cancel()
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await reader_task
    except (SessionSetupError, SessionSetupTimeout) as e:
        setup_fail_detail = str(e)
        setup_events = e.setup_events
        session_updated_payloads = [
            _truncate_strings(e2[2]) for e2 in setup_events
            if len(e2) > 2 and e2[1] == "session.updated"
        ]

    input_processed = sum(input_evidence.values()) > 0
    transcript_user_count = input_evidence["transcript.user"]
    if setup_fail_detail is not None:
        passed = False
        invalid = False  # not the _q2_grade invalid path -- setup_failed covers this case in spec_grade
        detail = setup_fail_detail
    else:
        passed, invalid = _q2_grade(q2_variant, reply_starts, transcript_user_count,
                                     input_processed, error_events, stream_info["error"])
        base_detail = (f"variant={q2_variant} unsolicited reply.started count={reply_starts} "
                       f"transcript_user_count={transcript_user_count} "
                       f"input_processed={input_processed} session_errors={len(error_events)} "
                       f"stream_error={stream_info['error']!r} "
                       f"wav={wav_path} wav_rate={rate} "
                       f"declared_rate={declared_rate if declared_rate is not None else 'omitted'}")
        detail = f"INVALID: {base_detail}" if invalid else base_detail
    # PROBE_A_SPEC.md addendum item 5: spec_grade disambiguates the harness's
    # raw `pass` bool (prints FAIL for a pre-ready setup failure) from the
    # spec-correct PASS/FAIL/INVALID classification. Appended at the END of
    # `detail` only -- test_session_ready.py/test_probe_a.py assert on
    # `detail`'s PREFIX (startswith "setup error" / contains "no session.ready"
    # / startswith "INVALID:"), which an end-append never disturbs.
    spec_grade = _q2_spec_grade(setup_fail_detail is not None, invalid, passed)
    detail = f"{detail} spec_grade={spec_grade}"
    elapsed = time.time() - t0
    print(f"[{label}] spec_grade={spec_grade} variant={q2_variant} unsolicited reply.started count={reply_starts} "
          f"input_evidence={input_evidence} session_errors={len(error_events)} "
          f"stream_error={stream_info['error']!r} setup_fail={setup_fail_detail!r}")
    return {
        "id": "Q2",  # runner contract (see spike_two_path.py): id/pass/est_cost_usd/detail
        "test": label,
        "pass": passed,
        "detail": detail,
        "evidence": {
            "spec_grade": spec_grade,
            "variant": q2_variant,
            "session_update_sent": {"type": "session.update", "session": cfg},  # no secrets: token/key never enter cfg
            "reply_started_count": reply_starts,
            "reply_audio_counts_per_reply": reply_audio_counts,
            "agent_transcripts": agent_texts,
            "user_transcripts": user_texts,
            "session_updated_payloads": session_updated_payloads,
            "input_evidence_counts": input_evidence,
            "session_error_count": len(error_events),
            "session_errors": error_events,
            "stream_sent_bytes": stream_info["sent_bytes"],
            "stream_deadline_hit": stream_info["deadline_hit"],
            "stream_error": stream_info["error"],
            "raw_event_types": [e.get("type") for e in events],
            "setup_events": setup_events,
            "setup_fail_detail": setup_fail_detail,
            "event_log": _compact_event_log(event_log),
            "wav_path": str(wav_path),
            "wav_actual_rate": rate,
            "declared_rate": declared_rate if declared_rate is not None else "omitted",
        },
        "elapsed_s": round(elapsed, 1),
        "est_cost_usd": round(elapsed * COST_PER_SEC, 4),
    }


async def test_tool_call(api_key: str, wav_path: Path, sample_rate_override: int | None = None,
                          omit_input_format: bool = False) -> dict:
    """Q3: register lookup_clause(section_or_topic) client-side tool, stream
    a question about clause 4.2, answer tool.call with the literal clause
    text, PASS if tool.call arrived + agent's final transcript contains that
    literal text verbatim.

    Setup failure (session.error before session.ready, or a
    SESSION_READY_TIMEOUT_S timeout) FAILS this test with detail set to that
    setup failure, same as test_proactive."""
    label = "Q3_tool_call"
    t0 = time.time()
    deadline = t0 + HARD_CAP_S  # one absolute cutoff for the whole session-open
    pcm, rate = load_wav(wav_path)
    declared_rate = None if omit_input_format else (
        sample_rate_override if sample_rate_override is not None else rate
    )
    cfg = {
        "system_prompt": (
            "You are ClauseCatcher. When asked about a contract clause, "
            "call the lookup_clause tool with the section number or topic, "
            "then read back exactly what it returns."
        ),
        "tools": [
            {
                "type": "function",
                "name": "lookup_clause",
                "description": "Look up the literal text of a contract clause by section number or topic.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "section_or_topic": {
                            "type": "string",
                            "description": "Section number (e.g. '4.2') or topic (e.g. 'renewal')",
                        }
                    },
                    "required": ["section_or_topic"],
                },
                # PROTOCOL.md:132-147 (client-side function tool example) sets
                # both fields explicitly; PROTOCOL.md:214-219 documents two
                # execution_mode values with different sequencing --
                # "interactive": agent speaks a transition phrase, emits
                # tool.call, client processes async, then sends tool.result.
                # That matches what this test assumes: it keeps draining
                # events (not silent) while lookup_clause runs, then sends
                # tool.result asynchronously via a background task.
                "execution_mode": "interactive",
                "timeout_seconds": 120,
            }
        ],
    }
    if not omit_input_format:
        # sample_rate override verified configurable: create-agent api-spec
        cfg["input"] = {"format": {"encoding": "audio/pcm", "sample_rate": declared_rate}}
    saw_tool_call = False
    sent_tool_result = False
    tool_result_send_errors: list[str] = []
    observed_tool_call_shape = None  # "flat" | "nested" | None
    agent_text = ""
    error_events: list[dict] = []
    tool_call_tasks: list[asyncio.Task] = []
    events: list[dict] = []
    setup_events: list = []
    event_log: list = []
    setup_fail_detail = None
    stream_info = {"sent_bytes": 0, "deadline_hit": False, "error": None}

    try:
        async with open_session(api_key, cfg, label) as (ws, setup_events, ready_at):
            stream_info = await stream_wav(ws, pcm, rate, label, deadline)

            async def handle_tool_call(evt):
                nonlocal sent_tool_result, observed_tool_call_shape
                # PROTOCOL.md's only documented tool.call shape is FLAT
                # ({"type","call_id","name","arguments"}, PROTOCOL.md:150-158).
                # No nested {"tool": {...}} shape is documented anywhere in
                # PROTOCOL.md. Flat is primary; the nested fallback below is
                # kept purely defensively (server behavior may differ from
                # docs) and is NOT protocol-backed.
                # UNVERIFIED: nested {"tool": {...}} fallback shape -- not in
                # PROTOCOL.md; kept only as a defensive fallback.
                call_id = evt.get("call_id")
                if call_id is not None:
                    observed_tool_call_shape = "flat"
                else:
                    nested = evt.get("tool", {})
                    call_id = nested.get("call_id")
                    observed_tool_call_shape = "nested" if call_id is not None else observed_tool_call_shape
                # Reply shape: using events-reference's flat tool.result verbatim
                # ({"type","call_id","result","is_error"}) as primary -- it's the
                # dedicated reference page, treated as more authoritative than
                # the prose "tools" page's nested example.
                try:
                    await ws.send(json.dumps({
                        "type": "tool.result",
                        "call_id": call_id,
                        "result": CLAUSE_4_2_TEXT,
                        "is_error": False,
                    }))
                    sent_tool_result = True  # only true after the send actually succeeds
                except Exception as e:
                    tool_result_send_errors.append(str(e))

            def on_event(evt):
                nonlocal saw_tool_call, agent_text
                t = evt.get("type")
                event_log.append([round((time.time() - ready_at) * 1000), t])
                if t == "tool.call":
                    saw_tool_call = True
                    tool_call_tasks.append(asyncio.create_task(handle_tool_call(evt)))
                if t == "transcript.agent":
                    agent_text = evt.get("text", "")
                if t in ("session.error", "error"):
                    error_events.append(evt)
                return t == "reply.done"

            drain_deadline = min(time.time() + 45, deadline)
            events = await drain(ws, drain_deadline, on_event)
            # give the in-flight tool.result send + final reply a brief moment
            if saw_tool_call:
                more_drain_deadline = min(time.time() + 15, deadline)
                events += await drain(ws, more_drain_deadline, on_event)
            # make sure every handle_tool_call task actually finished (and its
            # send either succeeded or recorded an error) before we grade it
            if tool_call_tasks:
                await asyncio.gather(*tool_call_tasks, return_exceptions=True)
    except (SessionSetupError, SessionSetupTimeout) as e:
        setup_fail_detail = str(e)
        setup_events = e.setup_events

    clause_verbatim = CLAUSE_4_2_TEXT in agent_text
    if setup_fail_detail is not None:
        passed = False
        detail = setup_fail_detail
    else:
        passed = _q3_pass(saw_tool_call, sent_tool_result, clause_verbatim, error_events,
                           tool_result_send_errors, stream_info["error"])
        detail = (f"tool_call={saw_tool_call} tool_result_sent={sent_tool_result} "
                  f"clause_verbatim_in_transcript={clause_verbatim} "
                  f"session_errors={len(error_events)} "
                  f"tool_call_shape={observed_tool_call_shape} "
                  f"tool_result_send_errors={len(tool_result_send_errors)} "
                  f"stream_error={stream_info['error']!r} "
                  f"wav={wav_path} wav_rate={rate} "
                  f"declared_rate={declared_rate if declared_rate is not None else 'omitted'}")
    elapsed = time.time() - t0
    print(f"[{label}] tool_call={saw_tool_call} agent_transcript={agent_text!r} "
          f"session_errors={len(error_events)} tool_call_shape={observed_tool_call_shape} "
          f"stream_error={stream_info['error']!r} setup_fail={setup_fail_detail!r}")
    return {
        "id": "Q3",  # runner contract (see spike_two_path.py): id/pass/est_cost_usd/detail
        "test": label,
        "pass": passed,
        "detail": detail,
        "evidence": {
            "saw_tool_call": saw_tool_call,
            "sent_tool_result": sent_tool_result,
            "tool_result_send_errors": tool_result_send_errors,
            "observed_tool_call_shape": observed_tool_call_shape,
            "agent_transcript": agent_text,
            "clause_text_verbatim_in_transcript": clause_verbatim,
            "session_error_count": len(error_events),
            "session_errors": error_events,
            "stream_sent_bytes": stream_info["sent_bytes"],
            "stream_deadline_hit": stream_info["deadline_hit"],
            "stream_error": stream_info["error"],
            "raw_event_types": [e.get("type") for e in events],
            "setup_events": setup_events,
            "setup_fail_detail": setup_fail_detail,
            "event_log": _compact_event_log(event_log),
            "wav_path": str(wav_path),
            "wav_actual_rate": rate,
            "declared_rate": declared_rate if declared_rate is not None else "omitted",
        },
        "elapsed_s": round(elapsed, 1),
        "est_cost_usd": round(elapsed * COST_PER_SEC, 4),
    }


async def _run_test(coro_fn, result_id: str, *args) -> dict:
    """Run one test in isolation. An uncaught exception in Q1 or Q2 used to
    lose ALL three results (and the wall-clock time already billed for them)
    since main_async had no top-level try/except -- see verifier finding #3.
    asyncio.CancelledError is a BaseException and is deliberately NOT caught
    here: cancellation must keep propagating, never get turned into a fake
    failed result. SessionSetupError/SessionSetupTimeout never reach here --
    each test function catches those itself and folds them into its own
    result dict (see e.g. test_proactive's `setup_fail_detail`)."""
    t0 = time.time()
    try:
        return await coro_fn(*args)
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001 -- spike: surface any test failure into results.json too
        elapsed = time.time() - t0
        detail = f"exception: {type(e).__name__}: {e}"
        print(f"[{result_id}] FAILED with exception: {detail}")
        return _failed_result(result_id, elapsed, detail)


async def main_async(api_key: str, audio_dir: Path, selected: list[str],
                      sample_rate_override: int | None, omit_input_format: bool,
                      q2_variant: str = "baseline") -> list[dict]:
    # Appended to (not built as one list literal) and written in `finally` so
    # that even a CancelledError raised while awaiting Q2 or Q3 still leaves
    # the results already collected for the earlier test(s) on disk, instead
    # of losing everything -- see verifier finding #3 and mock proof (c).
    # Only tests in `selected` run (--only) -- results file then contains
    # only those, still contract-shaped (list of {"id","pass",...} dicts).
    results: list[dict] = []
    try:
        if "Q1" in selected:
            results.append(await _run_test(test_proactive, "Q1", api_key))
        if "Q2" in selected:
            results.append(await _run_test(
                test_silence, "Q2", api_key, audio_dir / Q2_VARIANT_WAV[q2_variant],
                sample_rate_override, omit_input_format, q2_variant,
            ))
        if "Q3" in selected:
            results.append(await _run_test(
                test_tool_call, "Q3", api_key, audio_dir / "monitor_question.wav",
                sample_rate_override, omit_input_format,
            ))
    finally:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"\nresults written to {OUT_PATH}")
    return results


def _parse_only(raw: str | None) -> list[str]:
    """--only Q1,Q2 -> ["Q1","Q2"], preserving ALL_TEST_IDS order regardless
    of input order/dupes; None (flag omitted) -> every test, unchanged
    default behavior. Exits loudly on an unknown id -- never silently drops
    or guesses."""
    if raw is None:
        return list(ALL_TEST_IDS)
    requested = {s.strip() for s in raw.split(",") if s.strip()}
    bad = requested - set(ALL_TEST_IDS)
    if bad:
        sys.exit(f"FATAL: --only has unknown id(s) {sorted(bad)}, must be from {ALL_TEST_IDS}")
    return [i for i in ALL_TEST_IDS if i in requested]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audio-dir",
        type=Path,
        default=SCRIPT_DIR.parent / "harness" / "audio",
        help="dir containing rep_pitch.wav and monitor_question.wav",
    )
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help="comma list of tests to run, e.g. 'Q1,Q2' (default: all of Q1,Q2,Q3)",
    )
    parser.add_argument(
        "--sample-rate-override",
        type=int,
        default=None,
        help="assert the WAV's actual rate equals N and declare N as session.update's "
             "input.format.sample_rate; refuses to start (no network) if the WAV's "
             "actual rate differs -- never lies about the rate",
    )
    parser.add_argument(
        "--omit-input-format",
        action="store_true",
        help="send no 'input' block in session.update at all (Q2/Q3 only)",
    )
    parser.add_argument(
        "--q2-variant",
        choices=Q2_VARIANTS,
        default="baseline",
        help="Q2 config variant (see PROBE_A_SPEC.md): baseline=current behavior, "
             "silence_only=P1 (streams silence_12s.wav), turn_extreme=P2 (turn_detection "
             "at documented extremes), strong_prompt=P3 (stronger never-speak system_prompt)",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="run offline pass-logic asserts (no network, no API key needed) and exit",
    )
    args = parser.parse_args()

    if args.selftest:
        _selftest()
        return

    selected = _parse_only(args.only)

    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        print(
            "ASSEMBLYAI_API_KEY not set. This spike makes no network calls "
            "without it. Set the env var and re-run."
        )
        sys.exit(2)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    needed_wavs = []
    if "Q2" in selected:
        needed_wavs.append(Q2_VARIANT_WAV[args.q2_variant])
    if "Q3" in selected:
        needed_wavs.append("monitor_question.wav")
    for name in needed_wavs:
        p = args.audio_dir / name
        if not p.exists():
            sys.exit(f"FATAL: missing {p} -- harness agent needs to generate it first.")

    if args.sample_rate_override is not None:
        for name in needed_wavs:
            p = args.audio_dir / name
            _, actual_rate = load_wav(p)
            if actual_rate != args.sample_rate_override:
                sys.exit(
                    f"FATAL: --sample-rate-override {args.sample_rate_override} != "
                    f"{p}'s actual rate {actual_rate}Hz. Refusing to start -- this "
                    f"script never declares a sample rate that doesn't match the file."
                )

    results = asyncio.run(main_async(
        api_key, args.audio_dir, selected, args.sample_rate_override, args.omit_input_format,
        args.q2_variant,
    ))

    for r in results:
        print(f"  {r['test']}: {'PASS' if r['pass'] else 'FAIL'}")


if __name__ == "__main__":
    main()
