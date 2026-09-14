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

    async def speak(self, text):
        return {
            "inject_ms": 1, "first_audio_ms": 400, "done_ms": 900,
            "agent_transcript": text, "audio_chunks": 3, "errors": [],
            "role": "user", "literal_spoken": True,
        }

    async def ask(self, question_text=None, question_wav=None):
        return {
            "tool_called": True, "tool_args": {"section_number": "4.2"},
            "tool_result_sent": True, "first_audio_ms": 300,
            "agent_transcript": "answer", "literal_spoken": True, "errors": [],
        }

    async def close(self):
        return None


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
