"""
spike_two_path.py -- ClauseCatcher "two-connection architecture" spike, Path A only.

Path A: AssemblyAI Streaming STT v3 websocket (this file).
Path B: see ../voice_agent/spike_voice_agent.py (owned by another agent, not touched here).

Protocol sources (WebFetch'd 2026-09-13, cited inline where a detail comes from
one specific page):
  [1] https://www.assemblyai.com/docs/streaming
  [2] https://www.assemblyai.com/docs/speech-to-text/universal-streaming
  [3] https://www.assemblyai.com/docs/streaming/api-spec/streaming-websocket
  [4] https://www.assemblyai.com/docs/streaming/getting-started/transcribe-streaming-audio

VERIFIED (seen consistently across >=2 of the pages above, or checked directly
against the installed websockets==16.1.1 API rather than the docs):
  - WS URL: wss://streaming.assemblyai.com/v3/ws                         [1][2][4]
  - Auth: header {"Authorization": <raw API key>} -- NO "Bearer " prefix [1][4]
  - Query params: sample_rate (int, 8000-96000, default 16000),
    encoding (pcm_s16le default | pcm_mulaw | opus | ogg_opus | aac),
    speech_model, keyterms_prompt (JSON-encoded array in the query string,
    max 100 terms, e.g. '["AssemblyAI","Krabby Patty"]')               [1][2][3]
  - Server "Begin":  {"type":"Begin","id":str,"expires_at":int}          [1][4]
  - Server "Turn":   {"type":"Turn","turn_order":int,"end_of_turn":bool,
      "turn_is_formatted":bool,"end_of_turn_confidence":float,
      "transcript":str,
      "words":[{"text":str,"start":ms,"end":ms,"confidence":float,
                "word_is_final":bool}, ...]}                            [1][2][3]
  - Server "Termination": {"type":"Termination","audio_duration_seconds":...,
      "session_duration_seconds":...}                                   [1]
  - Client "Terminate": {"type":"Terminate"}                            [1][2][3]
  - websockets==16.1.1: pass headers via `additional_headers=` on
    websockets.connect() -- confirmed against the installed library's
    connect() signature directly, not the AssemblyAI docs.

# UNVERIFIED: UpdateConfiguration's field list (prompt, min_turn_silence,
# max_turn_silence, continuous_partials, vad_threshold, interruption_delay,
# agent_context, mode, end_of_turn_confidence_threshold, language_codes,
# session_heartbeat) surfaced on ONE page only [3] and isn't cross-confirmed.
# We send only {"type":"UpdateConfiguration","keyterms_prompt":[...]} as a
# no-op smoke test (keyterms_prompt is already set at connect time via the
# query string, which IS cross-confirmed) -- if the server ignores/rejects
# extra fields that's fine, this is a protocol smoke test, not a feature.
# UNVERIFIED: "ForceEndpoint" client message -- surfaced once [3], unused here.
# UNVERIFIED: exact speech_model catalog -- "universal-3-5-pro" is the only
# value seen in AssemblyAI's own examples [2][4]; other names may exist.
# UNVERIFIED: recommended audio chunk cadence -- docs show a 4096-byte example
# for a *different* encoding [4] and don't state a PCM cadence; we pace PCM
# sends at 50ms chunks as a reasonable real-time simulation.

Hard cost guards:
  - max 60s wall-clock per streaming run (RUN_MAX_SECONDS)
  - Terminate is always sent and the socket always closed, in `finally`
  - elapsed time + a worst-case cost estimate ($0.45/hr) are always printed
  - missing ASSEMBLYAI_API_KEY -> clear message, exit(2), zero network calls
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import re
import sys
import time
import urllib.parse
import wave
from pathlib import Path

import websockets

# --- constants -----------------------------------------------------------

AAI_WS_URL = "wss://streaming.assemblyai.com/v3/ws"
DEFAULT_SPEECH_MODEL = "universal-3-5-pro"  # UNVERIFIED: see header note
RUN_MAX_SECONDS = 60
CONNECT_TIMEOUT_S = 15  # bounds websockets.connect(); a stalled handshake must not hang forever
# Bounds ws.close()'s closing handshake (websockets.connect() defaults close_timeout to 10s,
# during which ws.close() blocks waiting for the peer's Close-frame ack) and the Terminate
# send in stream_path_a's finally -- an unresponsive peer must not extend a run past the cap.
CLEANUP_TIMEOUT_S = 3
WORST_CASE_HOURLY_USD = 0.45
WER_PASS_MAX = 0.15  # T1 pass threshold on wer_with_keyterms

HARNESS_DIR = Path(__file__).resolve().parent.parent / "harness"
HARNESS_AUDIO_DIR = HARNESS_DIR / "audio"
WAV_PATH = HARNESS_AUDIO_DIR / "rep_pitch.wav"
TXT_PATH = HARNESS_AUDIO_DIR / "rep_pitch.txt"
CONTRACT_JSON_PATH = HARNESS_DIR / "fake_contract.json"  # harness's real fixture, read-only
OUT_DIR = Path(__file__).resolve().parent / "out"
OUT_PATH = OUT_DIR / "results_two_path.json"

# Fake contract term list, loaded as keyterms_prompt (task spec).
FAKE_KEYTERMS = ["NimbusCRM", "Premium Support Addendum", "fifty seats", "sixty days"]

# Naive keyword sets per clause section, for the T2 stub matcher below.
_KEYWORDS_BY_SECTION = {
    "3.1": ["seat", "seats", "discount", "price", "pricing"],
    "4.2": ["renew", "renewal", "notice", "cancel", "terminate"],
    "5.3": ["data", "delete", "deleted", "retention", "retain", "archive"],
    "6.1": ["support", "24/7", "hours", "help desk", "sla"],
}

# Fallback clause text if the harness hasn't written fake_contract.json yet
# (this spike only *reads* the harness's fixtures, never writes them).
_FALLBACK_CLAUSES = [
    {"id": "3.1", "text": "Section 3.1 Pricing: capped at 50 seats; no verbal "
     "discounts permitted, all discounts require a written amendment.",
     "keywords": _KEYWORDS_BY_SECTION["3.1"]},
    {"id": "4.2", "text": "Section 4.2 Renewal: the contract renews automatically "
     "unless either party gives 60 days written notice.",
     "keywords": _KEYWORDS_BY_SECTION["4.2"]},
    {"id": "5.3", "text": "Section 5.3 Data Retention: customer data is deleted "
     "within 30 days of contract termination.",
     "keywords": _KEYWORDS_BY_SECTION["5.3"]},
    {"id": "6.1", "text": "Section 6.1 Support: standard support hours are "
     "Monday-Friday 9am-6pm ET; 24/7 support requires the Premium Support Addendum.",
     "keywords": _KEYWORDS_BY_SECTION["6.1"]},
]


def _load_clauses() -> list[dict]:
    """Load the 4 fake clauses from the harness's fake_contract.json if present
    (read-only -- this spike doesn't own that file), else fall back to a local
    copy with the same section numbers/keywords so offline selftest still works."""
    if CONTRACT_JSON_PATH.exists():
        try:
            data = json.loads(CONTRACT_JSON_PATH.read_text(encoding="utf-8"))
            clauses = [
                {
                    "id": c.get("section_number"),
                    "text": c.get("literal_text", ""),
                    "keywords": _KEYWORDS_BY_SECTION.get(c.get("section_number"), []),
                }
                for c in data.get("clauses", [])
            ]
            if clauses:
                return clauses
        except (json.JSONDecodeError, OSError):
            pass
    return _FALLBACK_CLAUSES


FAKE_CLAUSES = _load_clauses()

_SPELLED_NUMBERS = {
    "fifty five": 55, "fifty-five": 55, "fifty": 50,
    "sixty": 60, "thirty": 30, "ninety": 90,
}


# --- T2: naive claim-check stub (no LLM) ----------------------------------

def check_claim(sentence: str, clauses: list[dict]) -> list[dict]:
    """Naive keyword/number matcher against `clauses`. No LLM call.

    ponytail: literal keyword + regex-number matching only; false negatives on
    paraphrase are expected. Upgrade to an embedding/LLM check when accuracy
    on unseen phrasing matters -- this is a latency/wiring smoke test, not an
    accuracy claim.

    Returns a list of {"clause_id", "clause_text", "verdict"} for every
    clause whose keywords appear in `sentence`, verdict in
    {"contradiction", "consistent", "unclear"}. If no clause's keywords
    match, returns a single unclear/None entry.
    """
    s = sentence.lower()
    numbers = [int(n) for n in re.findall(r"\b(\d+)\b", s)]
    for phrase, val in _SPELLED_NUMBERS.items():
        if phrase in s:
            numbers.append(val)

    results = []
    for clause in clauses:
        if not any(kw in s for kw in clause["keywords"]):
            continue
        cid = clause["id"]
        verdict = "unclear"
        if cid == "3.1":
            if "verbal" in s and "discount" in s:
                verdict = "contradiction"
            elif any(n > 50 for n in numbers):
                verdict = "contradiction"
            elif any(n <= 50 for n in numbers):
                verdict = "consistent"
        elif cid == "4.2":
            if numbers:
                verdict = "consistent" if 60 in numbers else "contradiction"
        elif cid == "5.3":
            if numbers:
                verdict = "consistent" if 30 in numbers else "contradiction"
        elif cid == "6.1":
            has_247 = any(p in s for p in ("24/7", "24 7", "around the clock", "any time", "anytime"))
            has_premium = "premium" in s
            if has_247 and not has_premium:
                verdict = "contradiction"
            elif has_247 and has_premium:
                verdict = "consistent"
            elif any(p in s for p in ("monday", "weekday", "9 to 6", "9-6")):
                verdict = "consistent"
        results.append({"clause_id": cid, "clause_text": clause["text"], "verdict": verdict})

    if not results:
        return [{"clause_id": None, "clause_text": None, "verdict": "unclear"}]
    return results


def _pick_overall_verdict(verdicts: list[dict]) -> dict:
    severity = {"contradiction": 2, "consistent": 1, "unclear": 0}
    return max(verdicts, key=lambda v: severity.get(v["verdict"], 0))


# --- T1: word error rate (stdlib Levenshtein on words) ---------------------

def _levenshtein_words(ref: list[str], hyp: list[str]) -> int:
    n, m = len(ref), len(hyp)
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, m + 1):
            temp = dp[j]
            dp[j] = prev if ref[i - 1] == hyp[j - 1] else 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    return dp[m]


def _load_reference_text() -> str:
    """rep_pitch.txt lines are "label: spoken text" (see harness/make_audio.py);
    only the text after the label was actually synthesized into rep_pitch.wav,
    so strip the label before using this as the WER reference."""
    if not TXT_PATH.exists():
        return ""
    spoken = []
    for line in TXT_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        _, _, text = line.partition(":")
        spoken.append(text.strip() if text else line)
    return " ".join(spoken)


def word_error_rate(reference_text: str, hypothesis_text: str) -> float:
    """Simple word-level WER = edit_distance(ref_words, hyp_words) / len(ref_words)."""
    ref = reference_text.lower().split()
    hyp = hypothesis_text.lower().split()
    if not ref:
        return 0.0  # ponytail: undefined when ref is empty; treat as no error rather than div-by-zero
    return _levenshtein_words(ref, hyp) / len(ref)


def t1_pass(wer_plain: float | None, wer_kt: float | None) -> bool:
    """T1 passes iff both WER values were actually computed (reference text was
    available) AND the keyterms run's WER is within WER_PASS_MAX. A missing
    reference (both None, see _load_reference_text) fails closed."""
    if wer_plain is None or wer_kt is None:
        return False
    return wer_kt <= WER_PASS_MAX


# --- Path A: AssemblyAI streaming session -----------------------------------

async def _run_session(ws, frames: bytes, sample_rate: int, sample_width: int,
                        hard_deadline: float, on_turn, finalized_turns: list) -> None:
    chunk_bytes = max(int(sample_rate * sample_width * 0.05), sample_width)  # ~50ms of audio

    async def sender():
        offset = 0
        while offset < len(frames):
            remaining = hard_deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                await asyncio.wait_for(ws.send(frames[offset:offset + chunk_bytes]), timeout=max(0.1, remaining))
            except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                break
            offset += chunk_bytes
            await asyncio.sleep(0.05)

    sender_task = asyncio.create_task(sender())
    grace_deadline = None
    try:
        while True:
            deadline = grace_deadline if grace_deadline is not None else hard_deadline
            now = time.monotonic()
            if now >= deadline:
                break
            # Bounded receive: a silent server (no message, no close) must not hang
            # this loop forever -- that would skip `finally` below and leave the
            # websocket (and AssemblyAI's billing clock) open indefinitely.
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, deadline - now))
            except asyncio.TimeoutError:
                break
            except websockets.exceptions.ConnectionClosed:
                break
            if isinstance(raw, bytes):
                continue
            msg = json.loads(raw)
            mtype = msg.get("type")
            if mtype == "Turn" and msg.get("end_of_turn"):
                turn_end_ts = time.monotonic()
                finalized_turns.append(msg)
                if on_turn:
                    on_turn(msg, turn_end_ts)
            elif mtype == "Termination":
                break
            if sender_task.done() and grace_deadline is None:
                grace_deadline = time.monotonic() + 2.0  # ponytail: fixed flush window, not a real signal
    finally:
        sender_task.cancel()
        # asyncio.CancelledError is a BaseException (not Exception, since
        # Python 3.8) -- suppress(Exception) alone does NOT catch it, so the
        # cancellation we just requested would otherwise escape this
        # function, escape stream_path_a's finally, and even escape
        # main_async's `except Exception` handler on every run where the
        # sender is still active when the deadline/loop ends (the common
        # case), turning a clean bounded exit into an unhandled crash.
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await sender_task


async def stream_path_a(wav_path: Path, api_key: str, keyterms_prompt: list[str] | None,
                         speech_model: str, max_seconds: int, on_turn=None,
                         cost_sink: list[float] | None = None) -> tuple[list[dict], float]:
    """Stream `wav_path` to AssemblyAI Streaming STT v3 and return (finalized_turns, elapsed_s)."""
    with wave.open(str(wav_path), "rb") as wf:
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        frames = wf.readframes(wf.getnframes())

    if channels != 1 or sample_width != 2:
        # ponytail: audioop is gone in 3.13 and we're pinned to 3.12 here anyway;
        # rather than resample in-process, require the harness to hand us the
        # right format. Upgrade to a resampler if a non-conforming fixture shows up.
        raise ValueError(
            f"{wav_path} must be mono 16-bit PCM; got channels={channels} "
            f"sample_width_bytes={sample_width}"
        )

    query = {"sample_rate": str(sample_rate), "encoding": "pcm_s16le", "speech_model": speech_model}
    if keyterms_prompt:
        query["keyterms_prompt"] = json.dumps(keyterms_prompt)
    url = f"{AAI_WS_URL}?{urllib.parse.urlencode(query)}"

    finalized_turns: list[dict] = []
    start = time.monotonic()
    hard_deadline = start + max_seconds

    ws = None
    try:
        # Bounded connect: a stalled handshake must not hang forever. Elapsed
        # time here still lands in cost_sink below even if it never produces
        # an open session, so it isn't invisible to the caller's budget.
        ws = await asyncio.wait_for(
            websockets.connect(
                url, additional_headers={"Authorization": api_key}, close_timeout=CLEANUP_TIMEOUT_S
            ),
            timeout=CONNECT_TIMEOUT_S,
        )
        if keyterms_prompt:
            # UNVERIFIED smoke test of UpdateConfiguration -- see header note.
            with contextlib.suppress(Exception):
                await ws.send(json.dumps({"type": "UpdateConfiguration", "keyterms_prompt": keyterms_prompt}))
        await _run_session(ws, frames, sample_rate, sample_width, hard_deadline, on_turn, finalized_turns)
    finally:
        # Hard cost guard: always Terminate + close an open socket, regardless
        # of how we got here (normal finish, timeout, or exception).
        if ws is not None:
            # Both calls are bounded: an unresponsive peer (the exact "silent
            # server" case this guard exists for) must not add its own delay
            # on top of the run cap. ws.close() already carries close_timeout
            # via websockets.connect() above; the Terminate send gets the same
            # bound explicitly since asyncio.wait_for's timeout is a subclass
            # of Exception and is swallowed by suppress() same as any other.
            with contextlib.suppress(Exception):
                await asyncio.wait_for(ws.send(json.dumps({"type": "Terminate"})), timeout=CLEANUP_TIMEOUT_S)
            with contextlib.suppress(Exception):
                await ws.close()
        # Record elapsed wall time on every path (including exceptions) so a
        # caller that catches an error here can still add real, already-billed
        # time to its cost estimate instead of silently reporting $0.
        if cost_sink is not None:
            cost_sink.append(time.monotonic() - start)

    return finalized_turns, time.monotonic() - start


# --- main --------------------------------------------------------------------

async def main_async(api_key: str) -> None:
    reference_text = _load_reference_text()
    if not reference_text:
        print(f"WARNING: {TXT_PATH} missing/empty; WER will be reported as null.", file=sys.stderr)

    overall_start = time.monotonic()
    # Result-file contract (see ../harness/README.md): a list of
    # {"id","pass","est_cost_usd","detail"} objects, ids "T1" and "T2".
    t1_result: dict = {"id": "T1", "pass": False, "est_cost_usd": 0.0, "detail": "not run"}
    t2_result: dict = {"id": "T2", "pass": False, "est_cost_usd": 0.0, "detail": "not run"}
    error = None
    run_costs: list[float] = []  # elapsed seconds per stream_path_a call, appended even on error
    try:
        print("=== Run 1/2: WITHOUT keyterms_prompt ===")
        turns_plain, elapsed_plain = await stream_path_a(
            WAV_PATH, api_key, None, DEFAULT_SPEECH_MODEL, RUN_MAX_SECONDS, cost_sink=run_costs
        )
        transcript_plain = " ".join(t.get("transcript", "") for t in turns_plain)
        wer_plain = word_error_rate(reference_text, transcript_plain) if reference_text else None
        print(f"  turns={len(turns_plain)} elapsed={elapsed_plain:.2f}s wer={wer_plain}")

        print("=== Run 2/2: WITH keyterms_prompt (+ T2 claim-check per turn) ===")
        t2_log: list[dict] = []

        def on_turn(turn_msg: dict, turn_end_ts: float) -> None:
            sentence = turn_msg.get("transcript", "")
            verdicts = check_claim(sentence, FAKE_CLAUSES)
            overall = _pick_overall_verdict(verdicts)
            latency_ms = (time.monotonic() - turn_end_ts) * 1000
            print(
                f"  [T2] turn_order={turn_msg.get('turn_order')} verdict={overall['verdict']} "
                f"clause={overall['clause_id']} latency_ms={latency_ms:.2f}"
            )
            print(f"       transcript: {sentence!r}")
            print(f"       clause_text: {overall['clause_text']!r}")
            t2_log.append({
                "turn_order": turn_msg.get("turn_order"),
                "transcript": sentence,
                "verdict": overall["verdict"],
                "clause_id": overall["clause_id"],
                "clause_text": overall["clause_text"],
                "latency_ms": latency_ms,
            })

        turns_kt, elapsed_kt = await stream_path_a(
            WAV_PATH, api_key, FAKE_KEYTERMS, DEFAULT_SPEECH_MODEL, RUN_MAX_SECONDS, on_turn=on_turn,
            cost_sink=run_costs,
        )
        transcript_kt = " ".join(t.get("transcript", "") for t in turns_kt)
        wer_kt = word_error_rate(reference_text, transcript_kt) if reference_text else None
        print(f"  turns={len(turns_kt)} elapsed={elapsed_kt:.2f}s wer={wer_kt}")

        # T1's own cost = the two WER runs (run 1 + run 2); T2 rides for free on
        # run 2's connection so its own est_cost_usd is 0 to avoid double-counting
        # in run_spikes.py's cumulative budget sum across all result entries.
        cost_plain = (elapsed_plain / 3600.0) * WORST_CASE_HOURLY_USD
        cost_kt = (elapsed_kt / 3600.0) * WORST_CASE_HOURLY_USD
        if not reference_text:
            t1_detail = f"FAIL: {TXT_PATH} missing/empty, cannot compute WER"
        else:
            t1_detail = (
                f"wer_without_keyterms={wer_plain} wer_with_keyterms={wer_kt} "
                f"(pass requires both WER known and wer_with_keyterms<={WER_PASS_MAX}) "
                f"(reference_chars={len(reference_text)})"
            )
        t1_result.update({
            "pass": t1_pass(wer_plain, wer_kt),
            "est_cost_usd": cost_plain + cost_kt,
            "detail": t1_detail,
            "wer_without_keyterms": wer_plain,
            "wer_with_keyterms": wer_kt,
            "transcript_without_keyterms": transcript_plain,
            "transcript_with_keyterms": transcript_kt,
            "elapsed_s_without_keyterms": elapsed_plain,
            "elapsed_s_with_keyterms": elapsed_kt,
        })

        # T2 PASS = every finalized turn in the keyterms run got a verdict + latency.
        t2_pass = len(turns_kt) > 0 and len(t2_log) == len(turns_kt)
        t2_result.update({
            "pass": t2_pass,
            "est_cost_usd": 0.0,  # piggybacked on the run counted under T1
            "detail": f"{len(t2_log)}/{len(turns_kt)} finalized turns got a verdict+latency"
                      if turns_kt else "no finalized turns in the keyterms run",
            "turns": t2_log,
        })
    except Exception as exc:  # noqa: BLE001 -- spike: surface any failure into results.json too
        error = f"{type(exc).__name__}: {exc}"
        print(f"Path A run failed: {error}", file=sys.stderr)
        if t1_result["detail"] == "not run":
            # A run that opened (or attempted to open) a websocket before
            # failing still consumed real, billable time -- recover it from
            # run_costs so est_cost_usd doesn't silently read $0 on error.
            recovered_cost = sum((e / 3600.0) * WORST_CASE_HOURLY_USD for e in run_costs)
            t1_result["detail"] = error
            t1_result["est_cost_usd"] = recovered_cost
        if t2_result["detail"] == "not run":
            t2_result["detail"] = error
    finally:
        elapsed_total = time.monotonic() - overall_start
        est_cost_total = (elapsed_total / 3600.0) * WORST_CASE_HOURLY_USD
        print(
            f"\nElapsed total: {elapsed_total:.2f}s | "
            f"Est. cost (worst case ${WORST_CASE_HOURLY_USD}/hr): ${est_cost_total:.4f}"
        )
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        OUT_PATH.write_text(json.dumps([t1_result, t2_result], indent=2, default=str), encoding="utf-8")
        print(f"Results written to {OUT_PATH}")

    if error:
        sys.exit(1)


def main() -> None:
    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        print(
            "ASSEMBLYAI_API_KEY is not set. Path A (AssemblyAI Streaming STT v3) needs a "
            "real API key -- get one at https://www.assemblyai.com/dashboard/signup and "
            "`export ASSEMBLYAI_API_KEY=...`. No network call was made.",
            file=sys.stderr,
        )
        sys.exit(2)
    if not WAV_PATH.exists():
        print(
            f"Missing harness fixture: {WAV_PATH} (owned by the harness spike, not created "
            "here). No network call was made.",
            file=sys.stderr,
        )
        sys.exit(2)
    asyncio.run(main_async(api_key))


# --- offline self-test (no network, no key needed) --------------------------

def _selftest() -> None:
    # word_error_rate
    assert word_error_rate("the cat sat on the mat", "the cat sat on the mat") == 0.0
    assert abs(word_error_rate("the cat sat on the mat", "the cat sat on a mat") - 1 / 6) < 1e-9
    assert word_error_rate("", "anything at all") == 0.0
    assert word_error_rate("one two three", "") == 1.0

    # t1_pass: threshold logic
    assert t1_pass(0.0, 0.0) is True
    assert t1_pass(0.5, WER_PASS_MAX) is True  # boundary: <= passes
    assert t1_pass(0.5, WER_PASS_MAX + 0.01) is False  # just over threshold
    assert t1_pass(None, 0.0) is False  # missing reference (both None per _load_reference_text)
    assert t1_pass(0.0, None) is False
    assert t1_pass(None, None) is False

    # check_claim: contradictions
    r = check_claim("we can do fifty five seats no problem", FAKE_CLAUSES)
    assert any(v["clause_id"] == "3.1" and v["verdict"] == "contradiction" for v in r), r
    r = check_claim("I can give you a verbal discount today", FAKE_CLAUSES)
    assert any(v["clause_id"] == "3.1" and v["verdict"] == "contradiction" for v in r), r
    r = check_claim("our support is available 24/7 for everyone", FAKE_CLAUSES)
    assert any(v["clause_id"] == "6.1" and v["verdict"] == "contradiction" for v in r), r
    r = check_claim("data is kept for ninety days after you leave", FAKE_CLAUSES)
    assert any(v["clause_id"] == "5.3" and v["verdict"] == "contradiction" for v in r), r

    # check_claim: consistent
    r = check_claim("renewal requires sixty days notice", FAKE_CLAUSES)
    assert any(v["clause_id"] == "4.2" and v["verdict"] == "consistent" for v in r), r
    r = check_claim("24/7 support is included with the premium support addendum", FAKE_CLAUSES)
    assert any(v["clause_id"] == "6.1" and v["verdict"] == "consistent" for v in r), r

    # check_claim: unclear / no match
    r = check_claim("the weather is nice today", FAKE_CLAUSES)
    assert r == [{"clause_id": None, "clause_text": None, "verdict": "unclear"}], r

    # _pick_overall_verdict severity ordering
    picked = _pick_overall_verdict([
        {"clause_id": "a", "clause_text": "x", "verdict": "unclear"},
        {"clause_id": "b", "clause_text": "y", "verdict": "contradiction"},
        {"clause_id": "c", "clause_text": "z", "verdict": "consistent"},
    ])
    assert picked["clause_id"] == "b", picked

    print("selftest OK")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
        sys.exit(0)
    main()
