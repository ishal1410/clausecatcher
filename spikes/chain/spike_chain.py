"""
spike_chain.py -- end-to-end ClauseCatcher latency-chain spike (ADR-0001,
Option B). Streams harness/audio_24k/rep_pitch.wav in real time to
AssemblyAI Streaming STT v3, runs a claim-check on every finalized turn, and
on a "contradiction" verdict speaks a compliance alert -- built from the
CONTRACT's literal text, never from LLM output -- through a Voice Agent
session (alert_agent.AlertAgent). See ecc:latency-critical-systems: the hot
path measured here is

    rep speech -> Streaming STT v3 finalized turn -> claim-check
    -> AlertAgent.speak() -> agent's first reply.audio

Per turn this records: stt_final->check_done ms, check_done->first_audio ms,
total ms (plus the check_fn's own self-reported latency_ms, kept separately
since it can differ slightly from the wall-clock delta measured here).

Ownership: this file and test_chain.py are new (spikes/chain/). Nothing
under spikes/two_path, spikes/voice_agent, spikes/harness, or
spikes/protocol is edited here -- their functions/constants are imported
and reused (importlib.util.spec_from_file_location -- none of these
directories are packages), never copied or mutated:
  - two_path/spike_two_path.py: stream_path_a (with its on_turn hook),
    FAKE_CLAUSES/FAKE_KEYTERMS (loaded from harness/fake_contract.json),
    check_claim + _pick_overall_verdict (reused, offline, for --fake-check).
  - voice_agent/alert_agent.py: AlertAgent.

check_fn: by default, lazily imports check_claim from
spikes/claim_check/claim_check.py (owned by another, concurrently-running
agent) with signature
    check_claim(sentence, clauses, *, client=None, model=None)
    -> dict{verdict, clause_id, confidence, latency_ms, model, error}
If that module doesn't exist/import cleanly yet, this script exits 2 with a
clear message -- UNLESS --fake-check is given, which swaps in an offline
keyword-matcher (reusing two_path.check_claim: zero network, zero LLM calls)
with the same dict shape.

NEVER calls AssemblyAI or Gemini during --dry-run or --fake-check runs.
Real runs (no --fake-check, no --dry-run) DO call the real AssemblyAI
Streaming + Voice Agent APIs and, via the real check_claim, presumably an
LLM -- this build never invokes that path; see the final report for exact
future commands + cost estimates, not run here.
ASSEMBLYAI_API_KEY missing (and not --dry-run) -> exit 2, zero network calls.

Run examples (NOT executed by this build):
    python spike_chain.py --dry-run
    env ASSEMBLYAI_API_KEY=... python spike_chain.py --fake-check
    env ASSEMBLYAI_API_KEY=... python spike_chain.py
    env ASSEMBLYAI_API_KEY=... python spike_chain.py --cold
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib.util
import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPIKES_DIR = HERE.parent
TWO_PATH_SRC = SPIKES_DIR / "two_path" / "spike_two_path.py"
ALERT_AGENT_SRC = SPIKES_DIR / "voice_agent" / "alert_agent.py"
CLAIM_CHECK_SRC = SPIKES_DIR / "claim_check" / "claim_check.py"
WAV_PATH = SPIKES_DIR / "harness" / "audio_24k" / "rep_pitch.wav"

OUT_DIR = HERE / "out"
OUT_PATH = OUT_DIR / "results_chain.json"

HARD_CAP_S = 120             # whole-run wall-clock cap (STT stream + all alert speaks)
STT_MAX_SECONDS = 60         # bound passed to stream_path_a (its own RUN_MAX_SECONDS is 60 too)
ALERT_WAIT_TIMEOUT_S = 25    # bound on awaiting in-flight speak tasks after streaming ends
STT_COST_PER_HOUR_USD = 0.45          # verified Streaming (Universal-3.5 Pro Realtime), PROTOCOL.md
VOICE_AGENT_COST_PER_HOUR_USD = 4.50  # verified Voice Agent pricing, PROTOCOL.md


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_stp = _load_module(TWO_PATH_SRC, "_spike_two_path_reuse")
_alert_agent_mod = _load_module(ALERT_AGENT_SRC, "_alert_agent_reuse")
AlertAgent = _alert_agent_mod.AlertAgent


def _load_raw_contract_clauses() -> list[dict]:
    """The real spikes/claim_check/claim_check.py expects clauses shaped
    exactly like harness/fake_contract.json itself: {"section_number",
    "title","literal_text"} (it does `c["section_number"]`/`c["literal_text"]`
    directly -- confirmed by reading that file, not assumed). This is a
    DIFFERENT shape from two_path's FAKE_CLAUSES ({"id","text","keywords"}),
    which is what AlertAgent/build_alert_text and the --fake-check matcher
    use. Read-only reuse of the harness fixture; falls back to reshaping
    FAKE_CLAUSES if the harness file is somehow missing."""
    path = SPIKES_DIR / "harness" / "fake_contract.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            clauses = data.get("clauses", [])
            if clauses:
                return clauses
        except (json.JSONDecodeError, OSError):
            pass
    return [{"section_number": c["id"], "title": c["id"], "literal_text": c["text"]} for c in _stp.FAKE_CLAUSES]


CLAUSES = _stp.FAKE_CLAUSES              # {"id","text","keywords"} -- AlertAgent, build_alert_text, --fake-check matcher
CONTRACT_CLAUSES = _load_raw_contract_clauses()  # {"section_number","title","literal_text"} -- real check_claim's shape
KEYTERMS = _stp.FAKE_KEYTERMS             # contract-derived keyterms_prompt, reused verbatim from two_path
CLAUSE_TEXT_BY_ID = {c["id"]: c["text"] for c in CLAUSES}


def _fake_check_fn(sentence, clauses, *, client=None, model=None) -> dict:
    """Offline check_fn for --fake-check: reuses two_path's keyword matcher
    (check_claim + _pick_overall_verdict) -- zero network, zero LLM calls.
    Same dict shape real check_claim is specified to return."""
    t0 = time.monotonic()
    verdicts = _stp.check_claim(sentence, clauses)
    overall = _stp._pick_overall_verdict(verdicts)
    return {
        "verdict": overall["verdict"],
        "clause_id": overall["clause_id"],
        "confidence": 1.0 if overall["verdict"] != "unclear" else 0.0,
        "latency_ms": (time.monotonic() - t0) * 1000,
        "model": "fake-keyword-matcher",
        "error": None,
    }


def _load_default_check_fn():
    """Lazily import check_claim from spikes/claim_check/claim_check.py.
    Returns None if that file doesn't exist or fails to import -- the
    caller (main()) decides whether that's fatal."""
    if not CLAIM_CHECK_SRC.exists():
        return None
    try:
        mod = _load_module(CLAIM_CHECK_SRC, "_claim_check_reuse")
        return mod.check_claim
    except Exception:
        return None


def build_alert_text(clause_id, clauses=None) -> str | None:
    """Alert text is ALWAYS the contract's literal text -- never LLM output.
    Returns None if clause_id isn't in the contract (nothing to speak)."""
    lookup = CLAUSE_TEXT_BY_ID if clauses is None else {c["id"]: c["text"] for c in clauses}
    text = lookup.get(str(clause_id))
    if text is None:
        return None
    return f"Compliance alert: clause {clause_id}. {text}"


class ChainRunner:
    """Owns per-turn state for one streaming run: check-fn dispatch, verdict
    metrics, and the fire-and-forget AlertAgent.speak() tasks a contradiction
    schedules. two_path's on_turn hook (see spike_two_path.py's
    _run_session) is a *synchronous* callback, so a contradiction can't
    `await speak()` inline -- it schedules an asyncio.Task instead, same
    pattern spike_voice_agent.py's test_tool_call already uses for async
    tool.result sends triggered from a sync event callback."""

    def __init__(self, check_fn, api_key, cold: bool, clock=time.monotonic, agent_factory=None,
                 check_clauses=None):
        self.check_fn = check_fn
        self.api_key = api_key
        self.cold = cold
        self.clock = clock
        self.agent_factory = agent_factory or AlertAgent
        # Clauses passed to check_fn -- may be a different shape than
        # AlertAgent's (id/text) clauses; see _load_raw_contract_clauses.
        self.check_clauses = check_clauses if check_clauses is not None else CLAUSES
        self.turn_metrics: list[dict] = []
        self.speak_tasks: list[asyncio.Task] = []
        self.warm_agent = None
        self.cold_agent_costs: list[float] = []

    async def open_warm_agent(self):
        """Pre-opens one AlertAgent session used for every alert (the
        default "warm" mode). --cold skips this -- each alert opens (and
        closes) its own session instead, inside _speak_alert."""
        if self.cold:
            return None
        self.warm_agent = self.agent_factory(self.api_key, CLAUSES)
        return await self.warm_agent.open()

    def on_turn(self, turn_msg: dict, turn_end_ts: float) -> None:
        """Sync callback handed to stream_path_a's on_turn=. Must never
        raise -- an exception here would otherwise propagate out of
        _run_session's recv loop and kill the whole STT stream mid-run, so
        a check_fn failure is caught and recorded instead."""
        sentence = turn_msg.get("transcript", "")
        if not sentence.strip():
            return
        t_check_start = self.clock()
        try:
            verdict = self.check_fn(sentence, self.check_clauses)
        except Exception as e:
            verdict = {
                "verdict": "unclear", "clause_id": None, "confidence": 0.0,
                "latency_ms": (self.clock() - t_check_start) * 1000,
                "model": None, "error": f"{type(e).__name__}: {e}",
            }
        t_check_done = self.clock()
        metric = {
            "turn_order": turn_msg.get("turn_order"),
            "transcript": sentence,
            "verdict": verdict.get("verdict"),
            "clause_id": verdict.get("clause_id"),
            "confidence": verdict.get("confidence"),
            "check_model": verdict.get("model"),
            "check_error": verdict.get("error"),
            "check_fn_latency_ms": verdict.get("latency_ms"),
            "stt_final_to_check_done_ms": (t_check_done - turn_end_ts) * 1000,
            "check_done_to_first_audio_ms": None,
            "total_ms": None,
            "alert_spoken": False,
        }
        self.turn_metrics.append(metric)
        if verdict.get("verdict") == "contradiction" and verdict.get("clause_id") is not None:
            alert_text = build_alert_text(verdict["clause_id"])
            if alert_text is not None:
                task = asyncio.create_task(self._speak_alert(metric, alert_text, t_check_done))
                self.speak_tasks.append(task)

    async def _speak_alert(self, metric: dict, alert_text: str, t_check_done: float) -> None:
        agent = self.warm_agent
        opened_here = False
        try:
            if agent is None:  # --cold: open a fresh session per alert
                agent = self.agent_factory(self.api_key, CLAUSES)
                await agent.open()
                opened_here = True
            t_before_speak = self.clock()
            speak_result = await agent.speak(alert_text)
            metric["alert_spoken"] = True
            metric["alert_text"] = alert_text
            metric["speak_result"] = speak_result
            gap_ms = (t_before_speak - t_check_done) * 1000  # captures --cold's open()/ready overhead too
            if speak_result.get("first_audio_ms") is not None:
                metric["check_done_to_first_audio_ms"] = gap_ms + speak_result["first_audio_ms"]
                metric["total_ms"] = metric["stt_final_to_check_done_ms"] + metric["check_done_to_first_audio_ms"]
        except Exception as e:
            metric.setdefault("errors", []).append(f"{type(e).__name__}: {e}")
        finally:
            if opened_here:
                with contextlib.suppress(Exception, asyncio.CancelledError):
                    await agent.close()
                with contextlib.suppress(Exception):
                    self.cold_agent_costs.append(agent.est_cost_usd)

    async def finish(self, deadline: float) -> None:
        """Await every in-flight speak task, bounded by `deadline` (absolute
        time.monotonic() cutoff) -- a hung alert must not hang the run."""
        if not self.speak_tasks:
            return
        remaining = max(0.01, deadline - self.clock())
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await asyncio.wait_for(asyncio.gather(*self.speak_tasks, return_exceptions=True), timeout=remaining)
        for t in self.speak_tasks:
            if not t.done():
                t.cancel()

    async def close(self) -> None:
        if self.warm_agent is not None:
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await self.warm_agent.close()


async def main_async(api_key: str, check_fn, cold: bool, check_clauses=None) -> dict:
    t0 = time.monotonic()
    runner = ChainRunner(check_fn, api_key, cold, check_clauses=check_clauses)
    est_costs = {"stt_usd": 0.0, "voice_agent_usd": 0.0}
    error = None
    warm_open_info = None
    try:
        warm_open_info = await runner.open_warm_agent()

        run_costs: list[float] = []
        finalized_turns, _elapsed_stt = await _stp.stream_path_a(
            WAV_PATH, api_key, KEYTERMS, _stp.DEFAULT_SPEECH_MODEL, STT_MAX_SECONDS,
            on_turn=runner.on_turn, cost_sink=run_costs,
        )
        est_costs["stt_usd"] = sum((e / 3600.0) * STT_COST_PER_HOUR_USD for e in run_costs)

        finish_deadline = min(time.monotonic() + ALERT_WAIT_TIMEOUT_S, t0 + HARD_CAP_S)
        await runner.finish(finish_deadline)
    except Exception as e:  # noqa: BLE001 -- spike: surface any failure into results.json too
        error = f"{type(e).__name__}: {e}"
    finally:
        if runner.warm_agent is not None:
            est_costs["voice_agent_usd"] += runner.warm_agent.est_cost_usd
        est_costs["voice_agent_usd"] += sum(runner.cold_agent_costs)
        await runner.close()

    elapsed_total = time.monotonic() - t0
    result = {
        "ok": error is None,
        "error": error,
        "elapsed_total_s": round(elapsed_total, 2),
        "cold": cold,
        "warm_open": warm_open_info,
        "turns": runner.turn_metrics,
        "est_cost_usd": {
            "streaming_stt": round(est_costs["stt_usd"], 4),
            "voice_agent": round(est_costs["voice_agent_usd"], 4),
            "total": round(est_costs["stt_usd"] + est_costs["voice_agent_usd"], 4),
        },
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    return result


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--fake-check", action="store_true",
                    help="offline keyword-matcher check_fn (no claim_check.py import, no network, no LLM)")
    p.add_argument("--cold", action="store_true",
                    help="open a fresh AlertAgent session per alert instead of one pre-opened warm session")
    p.add_argument("--dry-run", action="store_true",
                    help="print the run plan and exit -- no API key required, zero network calls")
    return p.parse_args(argv)


def _plan(args) -> dict:
    return {
        "wav_path": str(WAV_PATH),
        "keyterms": KEYTERMS,
        "clause_ids": [c["id"] for c in CLAUSES],
        "check_fn": "fake-keyword-matcher" if args.fake_check else f"{CLAIM_CHECK_SRC}:check_claim",
        "cold": args.cold,
        "hard_cap_s": HARD_CAP_S,
        "stt_max_seconds": STT_MAX_SECONDS,
        "alert_wait_timeout_s": ALERT_WAIT_TIMEOUT_S,
    }


def main():
    args = parse_args()
    if args.dry_run:
        print(json.dumps(_plan(args), indent=2))
        return

    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        print(
            "ASSEMBLYAI_API_KEY not set. spike_chain.py makes no network calls "
            "without it. Set the env var and re-run (or use --dry-run)."
        )
        sys.exit(2)

    if not WAV_PATH.exists():
        sys.exit(f"FATAL: missing {WAV_PATH} -- harness agent needs to generate it first.")

    if args.fake_check:
        check_fn = _fake_check_fn
        check_clauses = CLAUSES  # {"id","text","keywords"} -- what two_path's matcher expects
    else:
        check_fn = _load_default_check_fn()
        if check_fn is None:
            sys.exit(
                f"FATAL: {CLAIM_CHECK_SRC} not found/importable yet (owned by another, "
                "concurrently-running agent). Pass --fake-check to run this spike without "
                "it, or wait until that file exists."
            )
        check_clauses = CONTRACT_CLAUSES  # {"section_number","title","literal_text"} -- real check_claim's shape

    result = asyncio.run(main_async(api_key, check_fn, args.cold, check_clauses))
    print(f"\nturns={len(result['turns'])} ok={result['ok']} "
          f"est_cost_usd_total=${result['est_cost_usd']['total']:.4f}")
    print(f"results written to {OUT_PATH}")
    if not result["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
