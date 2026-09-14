#!/usr/bin/env python3
"""Runner for the ClauseCatcher API spikes.

Checks ASSEMBLYAI_API_KEY is set (no network call -- just an env var read),
then runs the voice_agent and two_path spike scripts as subprocesses (if they
exist yet -- other agents own those folders), collects their out/*.json
results, enforces a $1.00 total budget cap, and prints a PASS/FAIL table for:
  Q1 proactive speech, Q2 single-session silence, Q3 client-side tool call,
  T1 keyterm WER, T2 claim-check latency.

Result file contract (what a spike script must write):
  <spike_dir>/out/*.json containing either a single object or a list of
  objects shaped like:
    {"id": "Q1", "pass": true, "est_cost_usd": 0.02, "detail": "..."}
"""
import argparse
import ast
import json
import math
import os
import shlex
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPIKES_DIR = HERE.parent
BUDGET_CAP_USD = 1.00

SPIKES = [
    ("voice_agent", SPIKES_DIR / "voice_agent" / "spike_voice_agent.py"),
    ("two_path", SPIKES_DIR / "two_path" / "spike_two_path.py"),
]

# --- per-spike worst-case time/cost, derived FROM the spike source files ---
#
# These used to be hand-copied constants (VOICE_AGENT_TEST_CAP_S=90 etc.)
# that went stale the moment a spike's own constants changed -- e.g. the
# CONNECT_TIMEOUT_S / CLEANUP_TIMEOUT_S guards added after this file was
# first written. Instead, every number below is read straight out of each
# spike's module-level constants with `ast` at runtime -- never imported
# (both spikes `import websockets` and open real network sessions; ast.parse
# never executes anything) -- so this file can't drift from what it's timing.
VOICE_AGENT_SRC = SPIKES_DIR / "voice_agent" / "spike_voice_agent.py"
TWO_PATH_SRC = SPIKES_DIR / "two_path" / "spike_two_path.py"

VOICE_AGENT_NUM_TESTS = 3  # Q1/Q2/Q3, one session each -- main_async in spike_voice_agent.py
TWO_PATH_NUM_RUNS = 2      # run 1 (plain) + run 2 (keyterms) -- main_async in spike_two_path.py
SUBPROCESS_OVERHEAD_S = 60  # interpreter startup / import time; not a spike constant, kept fixed


def _eval_numeric(node: ast.AST):
    """Evaluate an ast expression node if it's a plain number literal or
    simple arithmetic between number literals (e.g. `4.50 / 3600`, the shape
    both spikes use for their per-second cost rate). Returns None for
    anything else -- this is intentionally restricted (no eval())."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        val = _eval_numeric(node.operand)
        if val is None:
            return None
        return -val if isinstance(node.op, ast.USub) else val
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left, right = _eval_numeric(node.left), _eval_numeric(node.right)
        if left is None or right is None:
            return None
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        return left / right  # ast.Div
    return None


def read_constants(path: Path) -> dict:
    """Parse `path` with ast (never import it) and return {name: float} for
    every module-level `NAME = <literal-or-simple-arithmetic>` assignment in
    the file. A value that isn't a resolvable number (string, call, etc.) is
    skipped, not included -- callers that need a specific name must check
    for it themselves (see _require below) rather than assume it's present."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = {}
    for node in tree.body:  # module level only -- not inside functions/classes
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target, value_node = node.targets[0].id, node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
            target, value_node = node.target.id, node.value
        else:
            continue
        val = _eval_numeric(value_node)
        if val is not None:
            found[target] = float(val)
    return found


def _require(constants: dict, names: list, src_path: Path) -> dict:
    """Return {name: value} for `names` out of `constants`, or fail loudly
    (exit 2) if any are missing -- never silently fall back to a guess."""
    missing = [n for n in names if n not in constants]
    if missing:
        print(f"FATAL: {src_path} is missing required constant(s) {missing} -- cannot "
              f"derive a safe spike timeout/cost without them. Add them to the spike "
              f"source as plain module-level `NAME = <number>` assignments, or update "
              f"the formula in run_spikes.py if they were intentionally renamed/removed.")
        sys.exit(2)
    return {n: constants[n] for n in names}


def parse_only_count(spike_args_str: str, valid_ids: tuple = ("Q1", "Q2", "Q3")):
    """Parse a --spike-args string for a `--only VALUE` (or `--only=VALUE`)
    token and return how many of `valid_ids` it names -- used to scale
    voice_agent's derived budget down when fewer than all 3 tests are
    selected. Returns None if no --only flag is present (caller should then
    assume all tests run, i.e. no scaling). Unrecognized names in VALUE are
    not counted -- this only ever scales the budget DOWN, never up, so an
    unrecognized id must not inflate the count."""
    if not spike_args_str:
        return None
    tokens = shlex.split(spike_args_str)
    for i, tok in enumerate(tokens):
        if tok == "--only" and i + 1 < len(tokens):
            value = tokens[i + 1]
        elif tok.startswith("--only="):
            value = tok.split("=", 1)[1]
        else:
            continue
        names = [n.strip() for n in value.split(",") if n.strip()]
        return sum(1 for n in names if n in valid_ids)
    return None


def scale_voice_agent_budget(worst_s: float, cost_usd: float, per_test_s: float, k: int, n: int) -> tuple:
    """Scale a derived (all-n-tests) worst-case wall time / cost down to K of
    N tests. Ceils the scaled time (a timeout must never be rounded DOWN)
    and never lets it drop below one full test's own worst case
    (per_test_s) -- running fewer tests still needs at least one full
    test's timeout margin, per the "never below one full test worst case +
    overhead" rule (SUBPROCESS_OVERHEAD_S is added on top by the caller).
    Cost is scaled the same way and rounded up to 4dp so float truncation
    can't make the pre-launch budget check under-count spend. k<=0 or k>=n
    is clamped to n (unscaled) -- a nonsensical/absent --only value must
    never scale the budget down below the safe default."""
    if k is None or k <= 0 or k >= n:
        return worst_s, cost_usd
    factor = k / n
    scaled_worst_s = max(math.ceil(worst_s * factor), per_test_s)
    scaled_cost = math.ceil(cost_usd * factor * 10000) / 10000.0
    return scaled_worst_s, scaled_cost


def _derive_voice_agent(spike_args_str: str = "") -> tuple:
    """voice_agent: 3 tests (Q1/Q2/Q3), one session each. Per-test worst-case
    wall time = CONNECT_TIMEOUT_S (session open) + HARD_CAP_S (the session's
    own absolute deadline) + CLEANUP_TIMEOUT_S (session.end + close teardown
    in open_session's `finally`) + SESSION_READY_TIMEOUT_S if the spike
    source defines it yet (a separate session.ready wait some in-flight
    voice_agent work is adding; included when present, logged and skipped
    when not -- never a hard failure, per _require's all-or-nothing being
    reserved for the constants this formula has always needed).
    NEGATIVE_CONTROL_WINDOW_S is deliberately NOT added on top: reading
    test_proactive in spike_voice_agent.py, both its control-window deadline
    and its main drain deadline are computed as `min(..., t0 + HARD_CAP_S)`
    -- the control window eats into HARD_CAP_S, it never extends past it.
    Cost = the same per-test worst-case seconds x COST_PER_SEC (billed
    seconds conservatively include connect time too, not just the
    session-open window, since a stalled connect still burns wall clock).
    If spike_args_str carries `--only <K of Q1,Q2,Q3>`, the result is scaled
    to K/3 of the full 3-test budget via scale_voice_agent_budget()."""
    c = read_constants(VOICE_AGENT_SRC)
    r = _require(c, ["CONNECT_TIMEOUT_S", "HARD_CAP_S", "CLEANUP_TIMEOUT_S", "COST_PER_SEC"], VOICE_AGENT_SRC)
    per_test_s = r["CONNECT_TIMEOUT_S"] + r["HARD_CAP_S"] + r["CLEANUP_TIMEOUT_S"]
    if "SESSION_READY_TIMEOUT_S" in c:
        per_test_s += c["SESSION_READY_TIMEOUT_S"]
    else:
        print(f"  note: {VOICE_AGENT_SRC.name} has no SESSION_READY_TIMEOUT_S constant yet "
              f"-- not included in the per-test worst case.")
    worst_s = per_test_s * VOICE_AGENT_NUM_TESTS
    cost_usd = worst_s * r["COST_PER_SEC"]

    k = parse_only_count(spike_args_str)
    worst_s, cost_usd = scale_voice_agent_budget(worst_s, cost_usd, per_test_s, k, VOICE_AGENT_NUM_TESTS)
    return worst_s, cost_usd


def _derive_two_path() -> tuple:
    """two_path: 2 runs (plain + keyterms). Per-run worst-case wall time =
    CONNECT_TIMEOUT_S + RUN_MAX_SECONDS + CLEANUP_TIMEOUT_S (Terminate send +
    ws.close(), both bounded by CLEANUP_TIMEOUT_S in stream_path_a's
    `finally`).
    No other module-level grace constant exists in spike_two_path.py to add:
    _run_session's post-sender 2.0s "flush window" (`grace_deadline`) is an
    inline literal inside a function body, not a named module constant, so
    read_constants (module-level only) can't see it -- flagged as unfixed,
    see run_spikes' final report to the user.
    Cost = worst-case seconds x the hourly rate constant, converted to
    per-second."""
    c = read_constants(TWO_PATH_SRC)
    r = _require(c, ["CONNECT_TIMEOUT_S", "RUN_MAX_SECONDS", "CLEANUP_TIMEOUT_S", "WORST_CASE_HOURLY_USD"], TWO_PATH_SRC)
    per_run_s = r["CONNECT_TIMEOUT_S"] + r["RUN_MAX_SECONDS"] + r["CLEANUP_TIMEOUT_S"]
    worst_s = per_run_s * TWO_PATH_NUM_RUNS
    cost_usd = worst_s * (r["WORST_CASE_HOURLY_USD"] / 3600.0)
    return worst_s, cost_usd


_DERIVERS = {"voice_agent": _derive_voice_agent, "two_path": _derive_two_path}


def derive_spike_budgets(spike_args_str_by_name: dict = None) -> tuple:
    """Run every spike's deriver (only for spikes whose script file already
    exists -- a not-yet-written spike has nothing to derive from) and return
    (timeout_s_by_name, worst_case_cost_usd_by_name). Exits 2 (via _require)
    if an existing spike's source is missing a constant this formula needs.

    `spike_args_str_by_name` (optional, defaults to {}) is {name: raw
    --spike-args string}; only voice_agent's deriver reads it (for the
    --only K/3 scaling) since two_path has no analogous per-test selection
    flag in this budget formula."""
    spike_args_str_by_name = spike_args_str_by_name or {}
    timeout_s, cost_usd = {}, {}
    for name, script in SPIKES:
        if not script.exists():
            continue
        if name == "voice_agent":
            worst_s, worst_cost = _derive_voice_agent(spike_args_str_by_name.get(name, ""))
        else:
            worst_s, worst_cost = _DERIVERS[name]()
        timeout_s[name] = worst_s + SUBPROCESS_OVERHEAD_S
        cost_usd[name] = worst_cost
    return timeout_s, cost_usd


# Which EXPECTED_IDS each spike owns, so a timed-out spike can still get a
# failed result recorded per id instead of leaving them at "NO DATA".
SPIKE_IDS = {
    "voice_agent": ["Q1", "Q2", "Q3"],
    "two_path": ["T1", "T2"],
}

EXPECTED_IDS = ["Q1", "Q2", "Q3", "T1", "T2"]
EXPECTED_LABELS = {
    "Q1": "proactive speech",
    "Q2": "single-session silence",
    "Q3": "client-side tool call",
    "T1": "keyterm WER",
    "T2": "claim-check latency",
}


def check_api_key():
    # ponytail: env var read only, no network -- must exit 2 before anything else touches the wire.
    if not os.environ.get("ASSEMBLYAI_API_KEY"):
        print("ASSEMBLYAI_API_KEY is not set. Run:")
        print("  setx ASSEMBLYAI_API_KEY <your key>")
        print("then open a new shell and re-run this script.")
        sys.exit(2)


def collect_results(out_dir: Path):
    results = []
    if not out_dir.is_dir():
        return results
    for f in sorted(out_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            print(f"  WARNING: could not parse {f}: {e}")
            continue
        if isinstance(data, list):
            results.extend(data)
        elif isinstance(data, dict):
            results.append(data)
    return results


def build_command(script: Path, extra_args: list = None) -> list:
    return [sys.executable, str(script)] + list(extra_args or [])


def run_spike(name: str, script: Path, timeout_s: int, extra_args: list = None) -> list:
    """Launch one spike script as a subprocess, enforcing timeout_s.

    Deletes the spike's stale out/*.json first, so a spike that exits early
    (crash, or a killed timeout) can't have this call report a previous run's
    results as if they were fresh.

    `extra_args` (optional) is a list of argv tokens appended after the
    script path -- from --spike-args, shlex-split by the caller.

    On a normal exit, returns whatever collect_results() finds in out/.
    On subprocess.TimeoutExpired, subprocess.run() has already killed the
    child (and waited for it) before raising -- the child process is gone by
    the time we get here. This still can't prove the far side (AssemblyAI)
    closed its session, so it returns a synthetic failed result per id this
    spike owns and prints a billing warning.
    """
    out_dir = script.parent / "out"
    for f in out_dir.glob("*.json"):
        f.unlink()

    cmd = build_command(script, extra_args)
    print(f"[run] {name}: {shlex.join(cmd)} (cwd={script.parent}, timeout {timeout_s}s)")
    try:
        r = subprocess.run(cmd, cwd=str(script.parent), timeout=timeout_s)
        if r.returncode != 0:
            print(f"  WARNING: {name} exited with code {r.returncode}")
        results = collect_results(out_dir)
        if not results:
            print(f"  WARNING: no results found in {out_dir}/*.json")
        return results
    except subprocess.TimeoutExpired:
        print(f"  WARNING: {name} timed out after {timeout_s}s -- child process killed.")
        print(f"  !!! BILLING WARNING: {name} was killed mid-run -- it may have left an "
              f"AssemblyAI session open. Check the AssemblyAI dashboard for ongoing usage. !!!")
        return [
            {"id": rid, "pass": False, "est_cost_usd": 0.0,
             "detail": "runner timeout -- possible unclosed session, check AssemblyAI dashboard"}
            for rid in SPIKE_IDS.get(name, [])
        ]


def spike_launch_check(name: str, cumulative_cost: float, worst_case_cost_usd: dict) -> tuple:
    """Should `name` be launched given `cumulative_cost` spent so far?

    Checks cumulative_cost + this spike's own worst-case cost (looked up in
    `worst_case_cost_usd`, from derive_spike_budgets()) against the cap --
    not just cumulative_cost alone -- so a single expensive spike can be
    refused BEFORE it runs instead of only being caught after it already
    overspent (the between-spikes-only check was finding #3: a spike that
    blows the cap entirely on its own would never trip a check that only
    runs *after* a spike). Returns (should_launch, worst_case_cost,
    projected_cost).
    """
    worst_case = worst_case_cost_usd.get(name, 0.0)
    projected = cumulative_cost + worst_case
    return projected <= BUDGET_CAP_USD, worst_case, projected


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--spike", choices=[n for n, _ in SPIKES], default=None,
        help="run only this spike (default: run every spike that exists)",
    )
    parser.add_argument(
        "--spike-args", default=None,
        help='string of args passed through to the selected spike\'s argv, '
             'shlex-split (e.g. --spike-args "--only Q2 --audio-dir audio_24k"). '
             "Requires --spike.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print the derived plan (spikes, timeouts, costs, exact commands) "
             "and exit 0 -- never requires ASSEMBLYAI_API_KEY, never launches anything",
    )
    args = parser.parse_args(argv)
    if args.spike_args and not args.spike:
        parser.error("--spike-args requires --spike <name>")
    return args


def selected_spikes(args) -> list:
    return [(n, s) for n, s in SPIKES if args.spike is None or n == args.spike]


def extra_args_by_name(args) -> dict:
    if args.spike and args.spike_args:
        return {args.spike: shlex.split(args.spike_args)}
    return {}


def print_plan(plan: list, timeout_s: dict, worst_case_cost_usd: dict, extra_args: dict):
    for name, script in plan:
        if not script.exists():
            print(f"  {name}: {script} not found yet, skipping.")
            continue
        cmd = build_command(script, extra_args.get(name))
        print(f"  {name}: worst-case {timeout_s[name]:.0f}s wall-clock "
              f"(incl. {SUBPROCESS_OVERHEAD_S}s subprocess overhead), "
              f"${worst_case_cost_usd[name]:.4f}")
        print(f"    command: {shlex.join(cmd)} (cwd={script.parent})")


def main():
    args = parse_args()
    plan = selected_spikes(args)
    extra_args = extra_args_by_name(args)
    spike_args_str_by_name = {args.spike: args.spike_args} if (args.spike and args.spike_args) else {}

    print("Deriving per-spike worst-case wall-clock time and cost from each spike's "
          "own source constants (ast, no import, no network)...")
    timeout_s, worst_case_cost_usd = derive_spike_budgets(spike_args_str_by_name)

    if args.dry_run:
        print_plan(plan, timeout_s, worst_case_cost_usd, extra_args)
        sys.exit(0)

    check_api_key()

    for name, script in plan:
        if name in timeout_s:
            print(f"  {name}: worst-case {timeout_s[name]:.0f}s wall-clock "
                  f"(incl. {SUBPROCESS_OVERHEAD_S}s subprocess overhead), "
                  f"${worst_case_cost_usd[name]:.4f}, "
                  f"command: {shlex.join(build_command(script, extra_args.get(name)))}")
        else:
            print(f"  {name}: {script} not found yet, skipping derivation.")
    print()

    merged = {}  # id -> result dict (last one wins if duplicated)
    cumulative_cost = 0.0

    for name, script in plan:
        if not script.exists():
            print(f"[skip] {name}: {script} not found yet.")
            continue

        should_launch, worst_case, projected = spike_launch_check(name, cumulative_cost, worst_case_cost_usd)
        print(f"[cost-check] {name}: cumulative ${cumulative_cost:.2f} + worst-case "
              f"${worst_case:.2f} = ${projected:.2f} (cap ${BUDGET_CAP_USD:.2f})")
        if not should_launch:
            print(f"[abort] launching {name} could reach ${projected:.2f} > cap "
                  f"${BUDGET_CAP_USD:.2f} -- refusing to launch.")
            continue

        results = run_spike(name, script, timeout_s[name], extra_args.get(name))
        for res in results:
            rid = res.get("id")
            if rid:
                merged[rid] = res
            cumulative_cost += float(res.get("est_cost_usd", 0) or 0)

        if cumulative_cost > BUDGET_CAP_USD:
            print(f"[warn] cumulative est_cost_usd ${cumulative_cost:.2f} "
                  f"exceeds ${BUDGET_CAP_USD:.2f} cap after {name}.")

    print()
    print(f"Cumulative est_cost_usd: ${cumulative_cost:.2f} (cap ${BUDGET_CAP_USD:.2f})")
    print()
    print(f"{'ID':<4} {'CHECK':<24} {'RESULT':<10} DETAIL")
    print("-" * 70)
    any_fail = False
    for rid in EXPECTED_IDS:
        res = merged.get(rid)
        if res is None:
            status = "NO DATA"
            detail = "spike not run / no result written"
            any_fail = True
        else:
            passed = bool(res.get("pass"))
            status = "PASS" if passed else "FAIL"
            detail = str(res.get("detail", ""))
            if not passed:
                any_fail = True
        print(f"{rid:<4} {EXPECTED_LABELS[rid]:<24} {status:<10} {detail}")

    if cumulative_cost > BUDGET_CAP_USD:
        print()
        print(f"BUDGET EXCEEDED: ${cumulative_cost:.2f} > ${BUDGET_CAP_USD:.2f}")
        sys.exit(1)

    sys.exit(1 if any_fail else 0)


if __name__ == "__main__":
    main()
