"""Contract tests for the ClauseCatcher spike harness result format.

run_spikes.py expects every spike script to drop {"id","pass","est_cost_usd",
"detail"} objects (ids Q1/Q2/Q3 for voice_agent, T1/T2 for two_path) into its
own out/*.json. These tests verify that contract two ways:

  1. Statically, via `ast` on the spike source files -- NOT by importing them.
     Both spike modules `import websockets` at module level (third-party, may
     not be installed here) and this suite must make zero network calls and
     must never set ASSEMBLYAI_API_KEY, so ast parsing is the only safe way to
     inspect what dict shape each spike actually builds.
  2. Against run_spikes.collect_results() (a plain, importable, network-free
     function) and a line-for-line replica of its cumulative-cost/cap-check
     loop, run on fixture JSON written to a tempfile.TemporaryDirectory --
     never into spikes/*/out/.

LIMITATION (see TestAggregationLogic): run_spikes.main()'s abort/warn logic is
inline in main(), which is gated by check_api_key() requiring
ASSEMBLYAI_API_KEY. Since this suite must never set that variable, main()
itself cannot be exercised end-to-end here; the aggregation loop is tested via
a verbatim replica instead. If that loop changes in run_spikes.py, the replica
below needs a matching update.

Run: python test_results_contract.py
"""
import ast
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPIKES_DIR = HERE.parent
VOICE_AGENT_SRC = SPIKES_DIR / "voice_agent" / "spike_voice_agent.py"
TWO_PATH_SRC = SPIKES_DIR / "two_path" / "spike_two_path.py"

sys.path.insert(0, str(HERE))
import run_spikes  # noqa: E402 -- stdlib-only at module level, main() not invoked on import


_UNRESOLVED = object()  # sentinel: dict value we couldn't resolve to a literal


# --- ast helpers -------------------------------------------------------------

def _const_str(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _literal_assignments(tree):
    """[(lineno, name, str_value), ...] for every simple `name = "literal"`
    (plain or annotated) assignment anywhere in the module, source order."""
    out = []
    for node in ast.walk(tree):
        target = value_node = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            target, value_node = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target, value_node = node.target, node.value
        if target is None or value_node is None:
            continue
        s = _const_str(value_node)
        if s is not None:
            out.append((node.lineno, target.id, s))
    out.sort(key=lambda t: t[0])
    return out


def _resolve(name, lineno, assignments):
    """Nearest literal assignment to `name` at or before `lineno` (best-effort
    scope approximation: these spike files never reuse a result-id variable
    name across two different functions before the dict literal that reads it)."""
    best = _UNRESOLVED
    for a_lineno, a_name, a_val in assignments:
        if a_name == name and a_lineno <= lineno:
            best = a_val
    return best


def _result_shaped_dicts(source: str):
    """Every ast.Dict literal in `source` that looks like a spike result entry:
    string-literal keys, has "pass" + "est_cost_usd", and carries an identifier
    field under either "id" (correct) or "test" (the documented bug) -- this
    excludes unrelated dict-shaped `.update()` fragments that only carry a
    subset of fields and no identifier."""
    tree = ast.parse(source)
    assignments = _literal_assignments(tree)
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Dict):
            continue
        keys = {}
        skip = False
        for k, v in zip(node.keys, node.values):
            ks = _const_str(k) if k is not None else None
            if ks is None:  # e.g. **spread key -- not a literal we can check
                skip = True
                break
            if isinstance(v, ast.Constant):
                keys[ks] = v.value
            elif isinstance(v, ast.Name):
                keys[ks] = _resolve(v.id, node.lineno, assignments)
            else:
                keys[ks] = _UNRESOLVED
        if skip:
            continue
        if {"pass", "est_cost_usd"} <= keys.keys() and ("id" in keys or "test" in keys):
            found.append(keys)
    return found


# --- 1. static contract check ------------------------------------------------

class TestSpikeResultDictShape(unittest.TestCase):
    """ast-only: no import of the spike modules, no network."""

    def _check(self, src_path: Path, expected_ids: list[str]):
        dicts = _result_shaped_dicts(src_path.read_text(encoding="utf-8"))
        self.assertEqual(
            len(dicts), len(expected_ids),
            f"expected {len(expected_ids)} result-shaped dict literal(s) in "
            f"{src_path.name}, found {len(dicts)}: {dicts}",
        )
        seen_ids = []
        for d in dicts:
            with self.subTest(dict_literal=d):
                if "id" not in d and "test" in d:
                    self.fail(
                        f"result dict uses key 'test' (value={d['test']!r}) "
                        "instead of the required 'id' key -- run_spikes.py's "
                        "collect_results() only reads res.get('id'); a "
                        f"'test' key is silently ignored. Full dict: {d}"
                    )
                self.assertIn("id", d, f"result dict is missing the required 'id' key: {d}")
                self.assertIn("detail", d, f"result dict is missing the required 'detail' key: {d}")
                if d["id"] is not _UNRESOLVED:
                    seen_ids.append(d["id"])
        self.assertEqual(
            sorted(seen_ids), sorted(expected_ids),
            f"expected ids {expected_ids}, statically resolved: {seen_ids} "
            f"(order/duplicates aside; unresolved ids, if any, are omitted from this list)",
        )

    def test_voice_agent_result_dicts_use_id_key_with_q1_q2_q3(self):
        self._check(VOICE_AGENT_SRC, ["Q1", "Q2", "Q3"])

    def test_two_path_result_dicts_use_id_key_with_t1_t2(self):
        self._check(TWO_PATH_SRC, ["T1", "T2"])


# --- 2. runner aggregation ----------------------------------------------------

class TestCollectResults(unittest.TestCase):
    """run_spikes.collect_results() is a plain importable function -- real
    behavior, fixture files in a tempdir, never spikes/*/out/."""

    def test_merges_single_object_and_list_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            out_dir.mkdir()
            (out_dir / "a.json").write_text(json.dumps(
                {"id": "Q1", "pass": True, "est_cost_usd": 0.01, "detail": "ok"}), encoding="utf-8")
            (out_dir / "b.json").write_text(json.dumps([
                {"id": "Q2", "pass": True, "est_cost_usd": 0.02, "detail": "ok"},
                {"id": "Q3", "pass": False, "est_cost_usd": 0.03, "detail": "no"},
            ]), encoding="utf-8")
            results = run_spikes.collect_results(out_dir)
        self.assertEqual(sorted(r["id"] for r in results), ["Q1", "Q2", "Q3"])

    def test_missing_out_dir_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            results = run_spikes.collect_results(Path(tmp) / "does_not_exist")
        self.assertEqual(results, [])

    def test_skips_unparseable_json_without_raising(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "out"
            out_dir.mkdir()
            (out_dir / "bad.json").write_text("{not json", encoding="utf-8")
            (out_dir / "good.json").write_text(json.dumps(
                {"id": "T1", "pass": True, "est_cost_usd": 0.0, "detail": "ok"}), encoding="utf-8")
            results = run_spikes.collect_results(out_dir)
        self.assertEqual([r["id"] for r in results], ["T1"])


class TestAggregationLogic(unittest.TestCase):
    """See module docstring LIMITATION: this replicates run_spikes.main()'s
    merge + cumulative-cost + cap-check loop verbatim (as of this writing)
    rather than calling main() itself, because main() is gated behind
    check_api_key() and this suite must never set ASSEMBLYAI_API_KEY."""

    BUDGET_CAP_USD = run_spikes.BUDGET_CAP_USD

    @staticmethod
    def _merge_and_sum(list_of_result_lists):
        """Verbatim copy of the body of run_spikes.main()'s per-spike loop:
        merge by id (last write wins) + sum est_cost_usd, and note the index
        of the first spike after which cumulative_cost exceeded the cap."""
        merged = {}
        cumulative_cost = 0.0
        exceeded_after = None
        for i, results in enumerate(list_of_result_lists):
            for res in results:
                rid = res.get("id")
                if rid:
                    merged[rid] = res
                cumulative_cost += float(res.get("est_cost_usd", 0) or 0)
            if cumulative_cost > TestAggregationLogic.BUDGET_CAP_USD and exceeded_after is None:
                exceeded_after = i
        return merged, cumulative_cost, exceeded_after

    def test_all_five_ids_populate_from_fixture_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            voice_out = Path(tmp) / "voice_agent_out"
            two_path_out = Path(tmp) / "two_path_out"
            voice_out.mkdir()
            two_path_out.mkdir()
            (voice_out / "results_voice_agent.json").write_text(json.dumps([
                {"id": "Q1", "pass": True, "est_cost_usd": 0.01, "detail": "d1"},
                {"id": "Q2", "pass": True, "est_cost_usd": 0.02, "detail": "d2"},
                {"id": "Q3", "pass": False, "est_cost_usd": 0.03, "detail": "d3"},
            ]), encoding="utf-8")
            (two_path_out / "results_two_path.json").write_text(json.dumps([
                {"id": "T1", "pass": True, "est_cost_usd": 0.04, "detail": "d4"},
                {"id": "T2", "pass": True, "est_cost_usd": 0.0, "detail": "d5"},
            ]), encoding="utf-8")
            voice_results = run_spikes.collect_results(voice_out)
            two_path_results = run_spikes.collect_results(two_path_out)

        merged, cumulative_cost, exceeded_after = self._merge_and_sum([voice_results, two_path_results])
        self.assertEqual(sorted(merged.keys()), ["Q1", "Q2", "Q3", "T1", "T2"])
        self.assertAlmostEqual(cumulative_cost, 0.01 + 0.02 + 0.03 + 0.04 + 0.0)
        self.assertIsNone(exceeded_after, "cap should not trip on 10 cents of total cost")

    def test_cap_exceeded_triggers_abort_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            voice_out = Path(tmp) / "voice_agent_out"
            two_path_out = Path(tmp) / "two_path_out"
            voice_out.mkdir()
            two_path_out.mkdir()
            (voice_out / "results_voice_agent.json").write_text(json.dumps([
                {"id": "Q1", "pass": True, "est_cost_usd": 0.90, "detail": "expensive"},
            ]), encoding="utf-8")
            (two_path_out / "results_two_path.json").write_text(json.dumps([
                {"id": "T1", "pass": True, "est_cost_usd": 0.50, "detail": "also expensive"},
            ]), encoding="utf-8")
            voice_results = run_spikes.collect_results(voice_out)
            two_path_results = run_spikes.collect_results(two_path_out)

        merged, cumulative_cost, exceeded_after = self._merge_and_sum([voice_results, two_path_results])
        self.assertGreater(cumulative_cost, self.BUDGET_CAP_USD)
        self.assertEqual(
            exceeded_after, 1,
            "cap ($1.00) should trip only after the second spike's results "
            "are folded in ($0.90 alone is under cap, +$0.50 is over)",
        )


class TestRunSpikeTimeoutAndStaleResults(unittest.TestCase):
    """run_spikes.run_spike() against a real (dummy, network-free) child
    subprocess -- proves the timeout result shape and the stale-out/*.json
    cleanup with actual subprocess semantics rather than mocking them."""

    HANG_SCRIPT = "import time\ntime.sleep(30)\n"

    def _make_script(self, tmp, name, body):
        script = Path(tmp) / name
        script.write_text(body, encoding="utf-8")
        (script.parent / "out").mkdir(exist_ok=True)
        return script

    def test_timeout_returns_synthetic_failed_result_per_owned_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = self._make_script(tmp, "hang.py", self.HANG_SCRIPT)
            results = run_spikes.run_spike("two_path", script, timeout_s=2)
        self.assertEqual(
            [r["id"] for r in results], run_spikes.SPIKE_IDS["two_path"],
            "timeout must synthesize one failed result per id this spike owns",
        )
        for r in results:
            self.assertFalse(r["pass"])
            self.assertEqual(r["est_cost_usd"], 0.0)
            self.assertIn("runner timeout", r["detail"])

    def test_stale_out_json_is_deleted_before_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            # a script that exits immediately WITHOUT writing anything --
            # models a spike that sys.exit(2)s before it can write out/*.json.
            script = self._make_script(tmp, "silent_exit.py", "import sys\nsys.exit(2)\n")
            out_dir = script.parent / "out"
            (out_dir / "stale_results.json").write_text(
                json.dumps([{"id": "T1", "pass": True, "est_cost_usd": 0.0, "detail": "stale"}]),
                encoding="utf-8",
            )
            results = run_spikes.run_spike("two_path", script, timeout_s=15)
        self.assertEqual(
            results, [],
            "a stale out/*.json from a previous run must not be reported as this run's result",
        )


class TestSpikeLaunchCheck(unittest.TestCase):
    """run_spikes.spike_launch_check() -- the pre-launch worst-case-cost
    guard (finding #3: a single spike could overspend before the
    between-spikes cumulative_cost check ever ran). Uses a synthetic
    worst-case-cost dict (spike_launch_check now takes it as a parameter,
    see TestDeriveSpikeBudgets below) rather than real spike-derived numbers,
    so this arithmetic is tested independently of what either spike source
    currently contains."""

    def test_launch_allowed_when_projected_cost_within_cap(self):
        worst_case_cost = {"two_path": 0.05}
        should_launch, worst_case, projected = run_spikes.spike_launch_check("two_path", 0.0, worst_case_cost)
        self.assertTrue(should_launch)
        self.assertAlmostEqual(worst_case, 0.05)
        self.assertAlmostEqual(projected, 0.05)

    def test_launch_refused_when_cumulative_plus_worst_case_exceeds_cap(self):
        # already at 99% of cap -- even a small worst-case tips it over.
        worst_case_cost = {"two_path": 0.05}
        cumulative = run_spikes.BUDGET_CAP_USD - 0.001
        should_launch, worst_case, projected = run_spikes.spike_launch_check("two_path", cumulative, worst_case_cost)
        self.assertFalse(should_launch)
        self.assertGreater(projected, run_spikes.BUDGET_CAP_USD)

    def test_unknown_spike_name_defaults_to_zero_worst_case(self):
        should_launch, worst_case, projected = run_spikes.spike_launch_check("nonexistent", 0.5, {})
        self.assertTrue(should_launch)
        self.assertEqual(worst_case, 0.0)
        self.assertEqual(projected, 0.5)


class TestReadConstants(unittest.TestCase):
    """run_spikes.read_constants() / _require() -- ast-only constant
    scraping, exercised against temp files (never spikes/*/out/, never the
    real spike sources) so these are stable regardless of what either real
    spike source currently contains (e.g. mid-edit by another agent)."""

    def _write(self, tmp, body):
        p = Path(tmp) / "fake_spike.py"
        p.write_text(body, encoding="utf-8")
        return p

    def test_resolves_simple_arithmetic_literal(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self._write(tmp, "RATE = 4.50 / 3600\nCAP_S = 90\n")
            found = run_spikes.read_constants(src)
        self.assertAlmostEqual(found["RATE"], 4.50 / 3600)
        self.assertEqual(found["CAP_S"], 90.0)

    def test_ignores_non_numeric_and_function_scoped_assignments(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self._write(tmp, 'NAME = "not a number"\n\ndef f():\n    LOCAL_S = 5\n    return LOCAL_S\n')
            found = run_spikes.read_constants(src)
        self.assertEqual(found, {})

    def test_require_missing_constant_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self._write(tmp, "CONNECT_TIMEOUT_S = 15\n")  # HARD_CAP_S deliberately absent
            found = run_spikes.read_constants(src)
            with self.assertRaises(SystemExit) as cm:
                run_spikes._require(found, ["CONNECT_TIMEOUT_S", "HARD_CAP_S"], src)
        self.assertEqual(cm.exception.code, 2)

    def test_require_all_present_returns_requested_subset(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = self._write(tmp, "A = 1\nB = 2\nC = 3\n")
            found = run_spikes.read_constants(src)
            result = run_spikes._require(found, ["A", "B"], src)
        self.assertEqual(result, {"A": 1.0, "B": 2.0})


class TestDeriveSpikeBudgets(unittest.TestCase):
    """run_spikes.derive_spike_budgets() against the REAL spike source files
    sitting next to this test (not temp fixtures) -- skipped, not failed, if
    a spike's constants aren't complete yet (e.g. voice_agent mid-edit by
    another agent adding CLEANUP_TIMEOUT_S), since this suite must never
    guess or block on that. Once both real spikes have their required
    constants, this is the "derived worst-case table" sanity check."""

    def test_both_real_spikes_derive_under_budget_cap(self):
        try:
            timeout_s, cost_usd = run_spikes.derive_spike_budgets()
        except SystemExit as e:
            self.skipTest(f"a real spike source is missing a required constant right now (exit {e.code})")
        self.assertTrue(timeout_s, "expected at least one real spike script to exist")
        for name in cost_usd:
            self.assertGreater(timeout_s[name], 0)
            self.assertLess(cost_usd[name], run_spikes.BUDGET_CAP_USD,
                             f"{name}'s own worst-case cost should not exceed the cap solo")


class TestSpikeCliArgParsing(unittest.TestCase):
    """run_spikes.parse_args() / selected_spikes() / extra_args_by_name() --
    pure argparse-wrapping functions, no subprocess, no network."""

    def test_default_selects_all_spikes(self):
        args = run_spikes.parse_args([])
        self.assertEqual(selected_names(args), [n for n, _ in run_spikes.SPIKES])
        self.assertEqual(run_spikes.extra_args_by_name(args), {})

    def test_spike_flag_filters_to_one_spike(self):
        args = run_spikes.parse_args(["--spike", "voice_agent"])
        self.assertEqual(selected_names(args), ["voice_agent"])

    def test_spike_args_is_shlex_split_and_scoped_to_selected_spike(self):
        args = run_spikes.parse_args(
            ["--spike", "voice_agent", "--spike-args", "--only Q2 --audio-dir audio_24k"]
        )
        self.assertEqual(
            run_spikes.extra_args_by_name(args),
            {"voice_agent": ["--only", "Q2", "--audio-dir", "audio_24k"]},
        )

    def test_spike_args_without_spike_exits_2(self):
        with self.assertRaises(SystemExit) as cm:
            run_spikes.parse_args(["--spike-args", "--only Q2"])
        self.assertEqual(cm.exception.code, 2)

    def test_dry_run_flag_parses(self):
        args = run_spikes.parse_args(["--dry-run", "--spike", "two_path"])
        self.assertTrue(args.dry_run)

    def test_build_command_appends_extra_args(self):
        cmd = run_spikes.build_command(Path("script.py"), ["--only", "Q2"])
        self.assertEqual(cmd, [sys.executable, "script.py", "--only", "Q2"])

    def test_build_command_with_no_extra_args(self):
        cmd = run_spikes.build_command(Path("script.py"))
        self.assertEqual(cmd, [sys.executable, "script.py"])


def selected_names(args):
    return [n for n, _ in run_spikes.selected_spikes(args)]


class TestParseOnlyCount(unittest.TestCase):
    """run_spikes.parse_only_count() -- pure string parsing."""

    def test_no_only_flag_returns_none(self):
        self.assertIsNone(run_spikes.parse_only_count("--audio-dir audio_24k"))

    def test_empty_string_returns_none(self):
        self.assertIsNone(run_spikes.parse_only_count(""))

    def test_only_space_form_counts_valid_ids(self):
        self.assertEqual(run_spikes.parse_only_count("--only Q2"), 1)
        self.assertEqual(run_spikes.parse_only_count("--only Q1,Q2"), 2)
        self.assertEqual(run_spikes.parse_only_count("--only Q1,Q2,Q3"), 3)

    def test_only_equals_form_counts_valid_ids(self):
        self.assertEqual(run_spikes.parse_only_count("--only=Q2,Q3"), 2)

    def test_unrecognized_ids_are_not_counted(self):
        self.assertEqual(run_spikes.parse_only_count("--only Q2,BOGUS"), 1)

    def test_only_mixed_with_other_flags(self):
        self.assertEqual(
            run_spikes.parse_only_count("--audio-dir audio_24k --only Q2 --omit-input-format"), 1
        )


class TestScaleVoiceAgentBudget(unittest.TestCase):
    """run_spikes.scale_voice_agent_budget() -- pure arithmetic, the K/3
    budget-scaling rule for --only."""

    def test_k_equals_1_of_3_scales_down_to_one_test(self):
        # per_test_s=108 (matches CONNECT_TIMEOUT_S+HARD_CAP_S+CLEANUP_TIMEOUT_S
        # in the real spike as of this writing), worst_s=324, cost=0.405.
        worst_s, cost = run_spikes.scale_voice_agent_budget(324.0, 0.405, 108.0, k=1, n=3)
        self.assertEqual(worst_s, 108.0)
        self.assertAlmostEqual(cost, 0.135)

    def test_k_equals_2_of_3_scales_down_proportionally(self):
        worst_s, cost = run_spikes.scale_voice_agent_budget(324.0, 0.405, 108.0, k=2, n=3)
        self.assertEqual(worst_s, 216.0)
        self.assertAlmostEqual(cost, 0.27)

    def test_k_equals_n_is_unscaled(self):
        worst_s, cost = run_spikes.scale_voice_agent_budget(324.0, 0.405, 108.0, k=3, n=3)
        self.assertEqual(worst_s, 324.0)
        self.assertEqual(cost, 0.405)

    def test_none_k_is_unscaled(self):
        worst_s, cost = run_spikes.scale_voice_agent_budget(324.0, 0.405, 108.0, k=None, n=3)
        self.assertEqual((worst_s, cost), (324.0, 0.405))

    def test_zero_or_negative_k_is_unscaled_not_zeroed(self):
        # a nonsensical --only (no recognized ids) must never scale the
        # budget DOWN to (near-)zero -- fail safe to the full-3 default.
        worst_s, cost = run_spikes.scale_voice_agent_budget(324.0, 0.405, 108.0, k=0, n=3)
        self.assertEqual((worst_s, cost), (324.0, 0.405))

    def test_never_scales_below_one_full_test_worst_case(self):
        # even a tiny per_test_s-independent worst_s can't push the scaled
        # value under per_test_s itself.
        worst_s, _ = run_spikes.scale_voice_agent_budget(9.0, 0.01, 108.0, k=1, n=3)
        self.assertGreaterEqual(worst_s, 108.0)

    def test_scaled_time_is_ceiled_not_truncated(self):
        # per_test_s=100, n=7 -> 100*1/7 truncates to 14 but must ceil to 15,
        # then clamp to per_test_s=100 anyway (still exercises the ceil path
        # via cost, which isn't clamped).
        worst_s, cost = run_spikes.scale_voice_agent_budget(700.0, 0.7, 100.0, k=1, n=7)
        self.assertEqual(worst_s, 100.0)  # clamped up to per_test_s
        self.assertGreaterEqual(cost, 0.1)  # ceil-rounded, never truncated below the true 1/7


class TestDeriveVoiceAgentWithSpikeArgs(unittest.TestCase):
    """run_spikes.derive_spike_budgets() honors spike_args_str_by_name for
    voice_agent's --only scaling, against the real spike source. Skipped if
    that source is mid-edit and missing a required constant (same guard as
    TestDeriveSpikeBudgets)."""

    def test_only_q2_yields_smaller_budget_than_full_run(self):
        try:
            full_timeout, full_cost = run_spikes.derive_spike_budgets()
            scoped_timeout, scoped_cost = run_spikes.derive_spike_budgets(
                {"voice_agent": "--only Q2"}
            )
        except SystemExit as e:
            self.skipTest(f"real voice_agent source missing a required constant (exit {e.code})")
        if "voice_agent" not in full_timeout:
            self.skipTest("voice_agent spike script not present")
        self.assertLess(scoped_timeout["voice_agent"], full_timeout["voice_agent"])
        self.assertLessEqual(scoped_cost["voice_agent"], full_cost["voice_agent"])


if __name__ == "__main__":
    unittest.main()
