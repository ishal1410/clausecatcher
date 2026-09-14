"""
probe_gate.py -- single-process live gating probe for the user's ≤$0.30
morning approval window (PROBE_B_SPEC.md B3 + B4). Exercises
alert_agent.AlertAgent exactly as tomorrow's demo will:

  Phase 1 (cold, N=2): open() -> speak(alert for clause 3.1) -> close(),
      each a fresh session -- measures cold connect/ready/inject->audio.
  Phase 2 (warm, N=1 session): open() once, idle 3s, speak() clause 6.1
      then 3.1, then in the SAME session ask(question_text=... clause 4.2)
      and, if harness/audio_24k/monitor_question.wav exists and is 24 kHz,
      ask(question_wav=...) once. Then close().

Total wall clock is hard-capped at HARD_CAP_S via asyncio.wait_for wrapping
the whole run -- a backstop on top of AlertAgent's own per-call/per-session
timeouts (see alert_agent.py: SESSION_READY_TIMEOUT_S, REPLY_TIMEOUT_S,
TOOL_WAIT_TIMEOUT_S, HARD_SESSION_CAP_S).

Reuses (imports, never copies) alert_agent.AlertAgent the same way
spike_chain.py does: importlib.util.spec_from_file_location, since
spikes/ isn't a package.

Cost: printed as a worst-case estimate BEFORE any network call (--dry-run
or live), and totalled at the end from each AlertAgent's own
est_cost_usd (session-open-time * $4.50/hr, verified pricing,
PROTOCOL.md "Billing figures") -- never a separate/duplicated estimate.

NEVER calls AssemblyAI or Gemini during --dry-run. ASSEMBLYAI_API_KEY
missing (and not --dry-run) -> exit 2, zero network calls.

Run:
    python probe_gate.py --dry-run
    env ASSEMBLYAI_API_KEY=... python probe_gate.py
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
import wave
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPIKES_DIR = HERE.parent
ALERT_AGENT_SRC = HERE / "alert_agent.py"
FAKE_CONTRACT_PATH = SPIKES_DIR / "harness" / "fake_contract.json"
MONITOR_WAV_PATH = SPIKES_DIR / "harness" / "audio_24k" / "monitor_question.wav"
OUT_DIR = HERE / "out"

HARD_CAP_S = 180  # whole-run wall-clock cap (task requirement)
COST_PER_SEC = 4.50 / 3600.0  # matches alert_agent.COST_PER_SEC -- verified Voice Agent pricing
REQUIRED_WAV_RATE = 24000

COLD_SECTION = "3.1"
WARM_SECTIONS = ("6.1", "3.1")
MONITOR_QUESTION_TEXT = "What does clause 4.2 say?"
MONITOR_SECTION = "4.2"

# Worst-case per-op wall-clock estimates -- reused from PROBE_B_SPEC.md's own
# priced figures rather than invented: B3 "cold 3x20s=60s", warm
# "5x(5s speak+5s idle)"; B4 "4 runs x 15s=60s".
COLD_RUN_EST_S = 20
WARM_OPEN_EST_S = 2
WARM_IDLE_S = 3
SPEAK_EST_S = 5
ASK_EST_S = 15
WARM_CLOSE_EST_S = 1

B3_THRESHOLD_QUOTE = (
    'PROBE_B_SPEC.md B3 -- "PASS (per run): literal text present AND '
    'inject->first reply.audio <= 2000 ms." "FAIL: text missing or latency > 2000 ms." '
    '"INVALID: no session.ready within 10s, or session.error before ready -> rerun once; '
    'still invalid -> record, don\'t count."'
)
B4_THRESHOLD_QUOTE = (
    'PROBE_B_SPEC.md B4 -- "PASS: correct section_number called AND literal text spoken back." '
    '"FAIL: wrong/no section_number, or text missing." '
    '"INVALID: no session.ready, or tool.call never fires -> rerun once -> still invalid -> '
    'record, don\'t count."'
)


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_clauses() -> tuple[list[dict], dict]:
    """fake_contract.json's own shape ({"section_number","title",
    "literal_text"}) is exactly what AlertAgent._clause_lookup_map already
    accepts (see alert_agent.py) -- passed straight through, no reshaping."""
    data = json.loads(FAKE_CONTRACT_PATH.read_text(encoding="utf-8"))
    clauses = data["clauses"]
    text_map = {c["section_number"]: c["literal_text"] for c in clauses}
    return clauses, text_map


def build_alert_text(section_number: str, text_map: dict) -> str | None:
    """Alert text is ALWAYS the contract's literal text, fetched by id --
    never LLM-generated (PROBE_B_SPEC.md B3). Returns None if section_number
    isn't in the contract."""
    text = text_map.get(section_number)
    if text is None:
        return None
    return f"Contract alert: section {section_number} says: {text}"


def monitor_wav_usable() -> bool:
    """Local-file-only check (no network): the wav exists and is 24 kHz --
    PROBE_B_SPEC.md B4 Path 1 requires 24 kHz. False (not an exception) on
    any read problem -- a missing/bad fixture just skips that one step."""
    if not MONITOR_WAV_PATH.exists():
        return False
    try:
        with wave.open(str(MONITOR_WAV_PATH), "rb") as w:
            return w.getframerate() == REQUIRED_WAV_RATE
    except wave.Error:
        return False


def worst_case_cost_plan() -> dict:
    wav_included = monitor_wav_usable()
    cold_s = 2 * COLD_RUN_EST_S
    warm_s = (
        WARM_OPEN_EST_S + WARM_IDLE_S + 2 * SPEAK_EST_S + ASK_EST_S
        + (ASK_EST_S if wav_included else 0) + WARM_CLOSE_EST_S
    )
    total_s = cold_s + warm_s
    return {
        "cold_runs": 2,
        "cold_s_each_est": COLD_RUN_EST_S,
        "warm_s_est": warm_s,
        "warm_ask_wav_included": wav_included,
        "worst_case_wall_s": total_s,
        "worst_case_cost_usd": round(total_s * COST_PER_SEC, 4),
        "hard_cap_s": HARD_CAP_S,
    }


# ---- grading: pure functions, no I/O -- quoted thresholds above -----------

def grade_b3(setup_ok: bool, literal_spoken: bool, first_audio_ms) -> str:
    if not setup_ok:
        return "INVALID"
    if first_audio_ms is None or not literal_spoken or first_audio_ms > 2000:
        return "FAIL"
    return "PASS"


def grade_b4(setup_ok: bool, tool_called: bool, section_number_correct: bool, literal_spoken: bool) -> str:
    if not setup_ok or not tool_called:
        return "INVALID"
    if not (section_number_correct and literal_spoken):
        return "FAIL"
    return "PASS"


def grade_all(result: dict) -> dict:
    b3_rows = []
    for i, c in enumerate(result["cold_runs"], start=1):
        speak = c.get("speak") or {}
        b3_rows.append({
            "label": f"cold_{i}_speak_{c.get('section_number')}",
            "verdict": grade_b3(c["setup_ok"], speak.get("literal_spoken", False), speak.get("first_audio_ms")),
        })
    warm = result["warm_run"]
    for s in warm.get("speaks", []):
        b3_rows.append({
            "label": f"warm_speak_{s.get('section_number')}",
            "verdict": grade_b3(warm["setup_ok"], s.get("literal_spoken", False), s.get("first_audio_ms")),
        })

    b4_rows = []
    for label, step in (("warm_ask_text_4.2", warm.get("ask_text")), ("warm_ask_wav_4.2", warm.get("ask_wav"))):
        if step is None:
            continue
        section_ok = str((step.get("tool_args") or {}).get("section_number")) == MONITOR_SECTION
        b4_rows.append({
            "label": label,
            "verdict": grade_b4(warm["setup_ok"], step.get("tool_called", False), section_ok,
                                 step.get("literal_spoken", False)),
        })
    return {"b3": b3_rows, "b4": b4_rows}


# ---- the two phases ---------------------------------------------------

async def run_cold(agent_cls, api_key: str, clauses: list, text_map: dict, section_number: str, clock) -> dict:
    agent = agent_cls(api_key, clauses, clock=clock)
    step = {"section_number": section_number, "setup_ok": False, "open": None, "speak": None,
            "errors": [], "est_cost_usd": 0.0}
    try:
        try:
            step["open"] = await agent.open()
            step["setup_ok"] = True
        except Exception as e:
            step["errors"].append(f"open failed: {type(e).__name__}: {e}")
            return step
        alert_text = build_alert_text(section_number, text_map)
        step["speak"] = await agent.speak(alert_text)
    finally:
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await agent.close()
        step["est_cost_usd"] = agent.est_cost_usd
    return step


async def run_warm(agent_cls, api_key: str, clauses: list, text_map: dict, clock) -> dict:
    agent = agent_cls(api_key, clauses, clock=clock)
    warm = {"setup_ok": False, "open": None, "idle_s": WARM_IDLE_S, "speaks": [],
            "ask_text": None, "ask_wav": None, "errors": [], "est_cost_usd": 0.0}
    try:
        try:
            warm["open"] = await agent.open()
            warm["setup_ok"] = True
        except Exception as e:
            warm["errors"].append(f"open failed: {type(e).__name__}: {e}")
            return warm
        await asyncio.sleep(WARM_IDLE_S)
        for section_number in WARM_SECTIONS:
            alert_text = build_alert_text(section_number, text_map)
            speak_result = await agent.speak(alert_text)
            warm["speaks"].append({"section_number": section_number, **speak_result})
        warm["ask_text"] = await agent.ask(question_text=MONITOR_QUESTION_TEXT)
        if monitor_wav_usable():
            warm["ask_wav"] = await agent.ask(question_wav=str(MONITOR_WAV_PATH))
    finally:
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await agent.close()
        warm["est_cost_usd"] = agent.est_cost_usd
    return warm


async def main_async(api_key: str) -> dict:
    t0 = time.monotonic()
    clauses, text_map = _load_clauses()
    alert_agent_mod = _load_module(ALERT_AGENT_SRC, "_probe_gate_alert_agent_reuse")
    AlertAgent = alert_agent_mod.AlertAgent

    cold_runs = [
        await run_cold(AlertAgent, api_key, clauses, text_map, COLD_SECTION, time.monotonic)
        for _ in range(2)
    ]
    warm_run = await run_warm(AlertAgent, api_key, clauses, text_map, time.monotonic)

    total_cost = sum(c["est_cost_usd"] for c in cold_runs) + warm_run["est_cost_usd"]
    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "elapsed_total_s": round(time.monotonic() - t0, 2),
        "cold_runs": cold_runs,
        "warm_run": warm_run,
        "total_est_cost_usd": round(total_cost, 4),
    }
    result["grading"] = grade_all(result)
    return result


def print_summary(result: dict) -> None:
    grading = result.get("grading", {"b3": [], "b4": []})
    print("\n--- B3 (Reactive Voice Agent alert: cold + warm) ---")
    print(B3_THRESHOLD_QUOTE)
    for row in grading["b3"]:
        print(f"  {row['label']:<28} {row['verdict']}")
    print("\n--- B4 (Monitor tool call at 24 kHz) ---")
    print(B4_THRESHOLD_QUOTE)
    for row in grading["b4"]:
        print(f"  {row['label']:<28} {row['verdict']}")
    cost = result.get("total_est_cost_usd")
    cost_str = f"${cost:.4f}" if cost is not None else "unknown (aborted)"
    print(f"\ntotal_est_cost_usd={cost_str}  elapsed_total_s={result.get('elapsed_total_s')}")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true",
                    help="print the run plan + worst-case cost and exit -- no key required, zero network calls")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    plan = worst_case_cost_plan()
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return

    api_key = os.environ.get("ASSEMBLYAI_API_KEY")
    if not api_key:
        print(
            "ASSEMBLYAI_API_KEY not set. probe_gate.py makes no network calls "
            "without it. Set the env var and re-run (or use --dry-run)."
        )
        sys.exit(2)

    print(f"worst_case_cost_usd=${plan['worst_case_cost_usd']:.4f} "
          f"worst_case_wall_s={plan['worst_case_wall_s']} hard_cap_s={plan['hard_cap_s']}")

    try:
        result = asyncio.run(asyncio.wait_for(main_async(api_key), timeout=HARD_CAP_S))
    except asyncio.TimeoutError:
        result = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_total_s": HARD_CAP_S,
            "error": f"HARD_CAP_S={HARD_CAP_S}s exceeded -- run aborted",
            "cold_runs": [], "warm_run": {"speaks": [], "setup_ok": False}, "total_est_cost_usd": None,
            "grading": {"b3": [], "b4": []},
        }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUT_DIR / f"probe_gate_{ts}.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print_summary(result)
    print(f"results written to {out_path}")


if __name__ == "__main__":
    main()
