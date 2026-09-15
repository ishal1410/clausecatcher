"""
Tests for probe_gate.py. ZERO calls to the real AssemblyAI API: the real key
is popped from the environment before import, --dry-run is exercised with a
socket-connect trap (not just "no key set"), and the JSON-building code path
(run_cold/run_warm) is exercised against a FakeAlertAgent test double -- no
websocket at all, same pattern as spikes/chain/test_chain.py.

Run:
    env -u ASSEMBLYAI_API_KEY python -m unittest test_probe_gate -v
"""
import asyncio
import importlib.util
import io
import json
import os
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

os.environ.pop("ASSEMBLYAI_API_KEY", None)

HERE = Path(__file__).resolve().parent
PROBE_GATE_PATH = HERE / "probe_gate.py"

_spec = importlib.util.spec_from_file_location("probe_gate_under_test", PROBE_GATE_PATH)
probe_gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(probe_gate)

SPEAK_MODES = ("legacy", "no_instructions", "say_exactly", "message_and_say_exactly")


# --- --dry-run: no network at all -------------------------------------------

class TestDryRun(unittest.TestCase):
    def test_dry_run_prints_plan_with_no_network_call(self):
        buf = io.StringIO()
        with patch("socket.socket.connect", side_effect=AssertionError(
            "REAL NETWORK CALL ATTEMPTED IN --dry-run"
        )):
            with redirect_stdout(buf):
                probe_gate.main(["--dry-run"])

        plan = json.loads(buf.getvalue())
        self.assertIn("worst_case_cost_usd", plan)
        self.assertIn("worst_case_wall_s", plan)
        self.assertIn("hard_cap_s", plan)
        self.assertEqual(plan["hard_cap_s"], probe_gate.HARD_CAP_S)
        self.assertGreater(plan["worst_case_cost_usd"], 0)

    def test_dry_run_plan_lists_four_modes_cold_and_extra_delay_step(self):
        buf = io.StringIO()
        with patch("socket.socket.connect", side_effect=AssertionError(
            "REAL NETWORK CALL ATTEMPTED IN --dry-run"
        )):
            with redirect_stdout(buf):
                probe_gate.main(["--dry-run"])

        plan = json.loads(buf.getvalue())
        blob = json.dumps(plan).lower()

        for mode in SPEAK_MODES:
            self.assertIn(mode, blob, f"mode {mode!r} missing from dry-run plan: {plan}")

        # exactly one cold open+speak run (spec: "plus one cold open+speak").
        self.assertEqual(plan.get("cold_runs"), 1, plan)

        # the extra no_instructions replay with inject_delay_ms=800
        # (top-ranked debug variant) must be visible in the plan itself, not
        # just silently folded into the cost estimate.
        self.assertIn("800", blob, f"inject_delay_ms=800 step not reflected in plan: {plan}")

        if probe_gate.monitor_wav_usable():
            self.assertTrue(plan.get("warm_ask_wav_included"), plan)
        else:
            self.assertFalse(plan.get("warm_ask_wav_included"), plan)

    def test_dry_run_plan_step_order_has_delay800_first_then_one_ask_each(self):
        buf = io.StringIO()
        with patch("socket.socket.connect", side_effect=AssertionError(
            "REAL NETWORK CALL ATTEMPTED IN --dry-run"
        )):
            with redirect_stdout(buf):
                probe_gate.main(["--dry-run"])

        plan = json.loads(buf.getvalue())
        order = plan["warm_step_order"]

        # decision-first: the delay800 variant is FIRST, not last, so a
        # cap-driven cut of the warm sequence never drops the top-ranked
        # debug variant.
        self.assertEqual(order[0], "warm_speak_no_instructions_delay800", order)

        # then the remaining modes, each exactly once, in declared order.
        speak_labels = order[1:1 + len(probe_gate.SPEAK_MODE_SEQUENCE)]
        self.assertEqual(speak_labels, [f"warm_speak_{m}" for m in probe_gate.SPEAK_MODE_SEQUENCE])

        # exactly one ask_text and (if the fixture is usable) one ask_wav --
        # never one pair per mode.
        self.assertEqual(order.count("warm_ask_text"), 1, order)
        if probe_gate.monitor_wav_usable():
            self.assertEqual(order.count("warm_ask_wav"), 1, order)
            self.assertEqual(order[-1], "warm_ask_wav", order)
        else:
            self.assertNotIn("warm_ask_wav", order)
            self.assertEqual(order[-1], "warm_ask_text", order)

    def test_warm_worst_case_estimate_is_under_the_session_cap(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            probe_gate.main(["--dry-run"])
        plan = json.loads(buf.getvalue())
        self.assertLess(plan["warm_s_est"], probe_gate.WARM_SESSION_CAP_S, plan)

    def test_dry_run_needs_no_api_key(self):
        self.assertNotIn("ASSEMBLYAI_API_KEY", os.environ)
        buf = io.StringIO()
        with redirect_stdout(buf):
            probe_gate.main(["--dry-run"])  # must not raise / must not exit 2
        json.loads(buf.getvalue())  # valid JSON

    def test_missing_key_without_dry_run_exits_2(self):
        with self.assertRaises(SystemExit) as ctx:
            with redirect_stdout(io.StringIO()):
                probe_gate.main([])
        self.assertEqual(ctx.exception.code, 2)


# --- grading: pure function truth table -------------------------------------

class TestGradeB3(unittest.TestCase):
    def test_truth_table(self):
        cases = [
            # (setup_ok, literal_spoken, first_audio_ms) -> verdict
            (True, True, 1500, "PASS"),
            (True, True, 2000, "PASS"),   # boundary: <= 2000 passes
            (True, True, 2001, "FAIL"),
            (True, False, 500, "FAIL"),   # text missing
            (True, True, None, "FAIL"),   # no audio ever arrived
            (False, True, 500, "INVALID"),  # setup never completed
        ]
        for setup_ok, literal_spoken, first_audio_ms, expected in cases:
            with self.subTest(setup_ok=setup_ok, literal_spoken=literal_spoken, first_audio_ms=first_audio_ms):
                self.assertEqual(probe_gate.grade_b3(setup_ok, literal_spoken, first_audio_ms), expected)


class TestGradeB4(unittest.TestCase):
    def test_truth_table(self):
        cases = [
            # (setup_ok, tool_called, section_number_correct, literal_spoken) -> verdict
            (True, True, True, True, "PASS"),
            (True, True, False, True, "FAIL"),   # wrong section_number
            (True, True, True, False, "FAIL"),   # text not spoken back
            (True, False, False, False, "INVALID"),  # tool.call never fired
            (False, True, True, True, "INVALID"),    # session never got ready
        ]
        for setup_ok, tool_called, section_ok, literal_spoken, expected in cases:
            with self.subTest(setup_ok=setup_ok, tool_called=tool_called,
                               section_ok=section_ok, literal_spoken=literal_spoken):
                self.assertEqual(
                    probe_gate.grade_b4(setup_ok, tool_called, section_ok, literal_spoken), expected
                )


# --- results never contain the API key --------------------------------------

class FakeAlertAgent:
    """Mirrors only the subset of AlertAgent's interface run_cold/run_warm
    use -- no websocket, no network at all (same pattern as
    spikes/chain/test_chain.py's FakeAlertAgent)."""

    def __init__(self, api_key, clauses, *, clock=None, **_kwargs):
        self.api_key = api_key
        self.est_cost_usd = 0.0011

    async def open(self):
        return {"connect_ms": 3, "ready_ms": 9}

    async def speak(self, text, *, mode="no_instructions", inject_delay_ms=0):
        return {
            "inject_ms": 1, "first_audio_ms": 400, "done_ms": 900,
            "agent_transcript": text, "audio_chunks": 3, "errors": [],
            "role": "user", "literal_spoken": True, "mode": mode,
            "inject_delay_ms": inject_delay_ms, "similarity": 0.873,
        }

    async def ask(self, question_text=None, question_wav=None):
        return {
            "tool_called": True, "tool_args": {"section_number": "4.2"},
            "tool_result_sent": True, "first_audio_ms": 300,
            "agent_transcript": "answer", "literal_spoken": True, "errors": [],
            "similarity": 0.912,
        }

    async def close(self):
        return None


# --- run_cold/run_warm: mode-driven steps -----------------------------------
#
# These reference probe_gate's own declared constants (COLD_MODE,
# SPEAK_MODE_SEQUENCE, EXTRA_DELAY_MODE, EXTRA_DELAY_MS) rather than
# hardcoding an assumed order, since probe_gate is free to run modes in
# whatever sequence it declares.

class TestRunColdAndRunWarmModes(unittest.TestCase):
    def test_run_cold_speaks_once_in_cold_mode(self):
        async def _run():
            clauses, text_map = probe_gate._load_clauses()
            return await probe_gate.run_cold(
                FakeAlertAgent, "key", clauses, text_map, "3.1", time.monotonic
            )

        step = asyncio.run(_run())
        self.assertEqual(step["speak"]["mode"], probe_gate.COLD_MODE)

    def test_run_warm_puts_delay800_first_then_one_ask_text_and_one_ask_wav(self):
        async def _run():
            clauses, text_map = probe_gate._load_clauses()
            return await probe_gate.run_warm(FakeAlertAgent, "key", clauses, text_map, time.monotonic)

        warm = asyncio.run(_run())
        steps = warm["steps"]

        speak_steps = [s for s in steps if s.get("kind") == "b3"]
        n = len(probe_gate.SPEAK_MODE_SEQUENCE)
        # top-ranked debug variant (delay800) runs FIRST, not last, so a
        # cap-driven cut of the warm sequence never drops it.
        self.assertEqual(speak_steps[0]["mode"], probe_gate.EXTRA_DELAY_MODE)
        self.assertEqual(speak_steps[0]["inject_delay_ms"], probe_gate.EXTRA_DELAY_MS)
        self.assertEqual([s["mode"] for s in speak_steps[1:]], list(probe_gate.SPEAK_MODE_SEQUENCE))
        self.assertEqual(len(speak_steps), n + 1)

        b4_steps = [s for s in steps if s.get("kind") == "b4"]
        ask_text_steps = [s for s in b4_steps if s["label"] == "warm_ask_text"]
        self.assertEqual(len(ask_text_steps), 1, b4_steps)
        self.assertTrue(ask_text_steps[0]["tool_called"])

        ask_wav_steps = [s for s in b4_steps if s["label"] == "warm_ask_wav"]
        if probe_gate.monitor_wav_usable():
            self.assertEqual(len(ask_wav_steps), 1, b4_steps)
        else:
            self.assertEqual(len(ask_wav_steps), 0, b4_steps)

        # exactly one ask_text and one ask_wav total -- never one pair per mode.
        self.assertEqual(len(b4_steps), 1 + (1 if probe_gate.monitor_wav_usable() else 0))


# --- grade_all(): every step graded, similarity threaded through -----------

class TestGradeAllLabelsAndSimilarity(unittest.TestCase):
    def _sample_result(self):
        return {
            "cold_runs": [{
                "section_number": "3.1", "mode": "no_instructions", "setup_ok": True,
                "speak": {"literal_spoken": True, "first_audio_ms": 500,
                          "mode": "no_instructions", "similarity": 0.99},
            }],
            "warm_run": {
                "setup_ok": True,
                "steps": [
                    {"label": "speak_legacy", "kind": "b3", "mode": "legacy",
                     "literal_spoken": True, "first_audio_ms": 400, "similarity": 0.91},
                    {"label": "ask_text_legacy", "kind": "b4",
                     "tool_called": True, "tool_args": {"section_number": "4.2"},
                     "literal_spoken": True, "similarity": 0.88},
                    {"label": "speak_no_instructions_delay800", "kind": "b3",
                     "mode": "no_instructions", "inject_delay_ms": 800,
                     "literal_spoken": True, "first_audio_ms": 600, "similarity": 0.95},
                ],
            },
        }

    def test_labels_and_verdicts_pass_through_from_steps(self):
        grading = probe_gate.grade_all(self._sample_result())
        b3_labels = [row["label"] for row in grading["b3"]]
        self.assertIn("cold_speak_3.1_no_instructions", b3_labels)
        self.assertIn("speak_legacy", b3_labels)
        self.assertIn("speak_no_instructions_delay800", b3_labels)
        b4_labels = [row["label"] for row in grading["b4"]]
        self.assertIn("ask_text_legacy", b4_labels)

    def test_grading_rows_carry_similarity_through(self):
        grading = probe_gate.grade_all(self._sample_result())
        for row in grading["b3"] + grading["b4"]:
            self.assertIn("similarity", row)
            self.assertIsInstance(row["similarity"], float)


class TestPrintSummaryShowsSimilarity(unittest.TestCase):
    def test_print_summary_prints_similarity_value(self):
        result = TestGradeAllLabelsAndSimilarity()._sample_result()
        result["grading"] = probe_gate.grade_all(result)
        result["total_est_cost_usd"] = 0.01
        result["elapsed_total_s"] = 1.0

        buf = io.StringIO()
        with redirect_stdout(buf):
            probe_gate.print_summary(result)

        self.assertIn("similarity=", buf.getvalue())


class TestNoKeyLeak(unittest.TestCase):
    def test_run_cold_and_run_warm_results_never_contain_the_api_key(self):
        secret_key = "sk-super-secret-value-must-never-leak-98765"

        async def _run():
            clauses, text_map = probe_gate._load_clauses()
            cold = await probe_gate.run_cold(
                FakeAlertAgent, secret_key, clauses, text_map, "3.1", time.monotonic
            )
            warm = await probe_gate.run_warm(
                FakeAlertAgent, secret_key, clauses, text_map, time.monotonic
            )
            return cold, warm

        cold, warm = asyncio.run(_run())
        result = {
            "cold_runs": [cold, cold],
            "warm_run": warm,
            "total_est_cost_usd": cold["est_cost_usd"] * 2 + warm["est_cost_usd"],
        }
        result["grading"] = probe_gate.grade_all(result)
        blob = json.dumps(result, default=str)
        self.assertNotIn(secret_key, blob)


if __name__ == "__main__":
    unittest.main()
