"""
Tests for spikes/chain/spike_chain.py's ChainRunner (the per-turn
check-fn -> alert wiring) and its --dry-run / missing-key CLI paths.

Local-only, zero real network: ChainRunner.on_turn/_speak_alert are
exercised directly against a FakeAlertAgent test double (no websocket at
all) -- AlertAgent's own websocket/protocol behavior is already covered by
voice_agent/test_alert_agent.py. This suite is about the CHAIN's wiring
(exactly one speak() per contradiction, literal clause text from the
contract, no speak() on consistent/unclear, monotonic per-turn timings,
check_fn exceptions don't crash the stream) plus the CLI's --dry-run/no-key
contracts via real subprocesses (fast: --dry-run and the missing-key path
both exit before touching the network).

Run:
    env -u ASSEMBLYAI_API_KEY python -m unittest test_chain -v
"""
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.pop("ASSEMBLYAI_API_KEY", None)

HERE = Path(__file__).resolve().parent
CHAIN_SRC = HERE / "spike_chain.py"

_spec = importlib.util.spec_from_file_location("spike_chain_under_test", CHAIN_SRC)
chain = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chain)


class FakeAlertAgent:
    """Records every speak() call; no websocket, no network at all. Mirrors
    only the subset of AlertAgent's interface ChainRunner actually uses."""

    def __init__(self, *_args, **_kwargs):
        self.speak_calls: list[str] = []
        self.opened = False
        self.closed = False
        self.est_cost_usd = 0.0001

    async def open(self):
        self.opened = True
        return {"connect_ms": 1, "ready_ms": 2}

    async def speak(self, text: str) -> dict:
        self.speak_calls.append(text)
        return {
            "inject_ms": 1, "first_audio_ms": 5, "done_ms": 20,
            "agent_transcript": text, "audio_chunks": 1, "errors": [], "role": "system",
        }

    async def close(self):
        self.closed = True


def make_turn(order: int, transcript: str, t_end: float) -> tuple[dict, float]:
    return {"type": "Turn", "turn_order": order, "end_of_turn": True, "transcript": transcript}, t_end


TEST_CLAUSES = [{"id": "4.2", "text": "Auto-renews unless 60 days notice."}]


class TestChainRunnerContradiction(unittest.IsolatedAsyncioTestCase):
    async def test_contradiction_triggers_exactly_one_speak_with_literal_clause_text(self):
        def fake_check(sentence, clauses, *, client=None, model=None):
            return {"verdict": "contradiction", "clause_id": "4.2", "confidence": 0.9,
                     "latency_ms": 3.0, "model": "fake", "error": None}

        with patch.object(chain, "CLAUSES", TEST_CLAUSES), \
             patch.object(chain, "CLAUSE_TEXT_BY_ID", {"4.2": TEST_CLAUSES[0]["text"]}):
            runner = chain.ChainRunner(fake_check, "dummy-key", cold=False, agent_factory=FakeAlertAgent)
            await runner.open_warm_agent()
            msg, t_end = make_turn(1, "renewal auto renews without notice", time.monotonic())
            runner.on_turn(msg, t_end)
            self.assertEqual(len(runner.speak_tasks), 1)
            await asyncio.gather(*runner.speak_tasks)

        self.assertEqual(
            runner.warm_agent.speak_calls,
            [f"Compliance alert: clause 4.2. {TEST_CLAUSES[0]['text']}"],
        )
        self.assertEqual(len(runner.turn_metrics), 1)
        metric = runner.turn_metrics[0]
        self.assertTrue(metric["alert_spoken"])
        self.assertIn(TEST_CLAUSES[0]["text"], metric["alert_text"])

    async def test_consistent_and_unclear_trigger_no_speak(self):
        def make_check(verdict_value, clause_id):
            def fn(sentence, clauses, *, client=None, model=None):
                return {"verdict": verdict_value, "clause_id": clause_id, "confidence": 0.5,
                         "latency_ms": 1.0, "model": "fake", "error": None}
            return fn

        with patch.object(chain, "CLAUSES", TEST_CLAUSES), \
             patch.object(chain, "CLAUSE_TEXT_BY_ID", {"4.2": TEST_CLAUSES[0]["text"]}):
            for check_fn in (make_check("consistent", "4.2"), make_check("unclear", None)):
                runner = chain.ChainRunner(check_fn, "dummy-key", cold=False, agent_factory=FakeAlertAgent)
                await runner.open_warm_agent()
                msg, t_end = make_turn(1, "renewal requires sixty days notice", time.monotonic())
                runner.on_turn(msg, t_end)
                self.assertEqual(runner.speak_tasks, [])
                self.assertEqual(runner.warm_agent.speak_calls, [])
                self.assertEqual(len(runner.turn_metrics), 1)
                self.assertFalse(runner.turn_metrics[0]["alert_spoken"])

    async def test_timings_are_monotonic(self):
        def fake_check(sentence, clauses, *, client=None, model=None):
            return {"verdict": "contradiction", "clause_id": "4.2", "confidence": 0.9,
                     "latency_ms": 2.0, "model": "fake", "error": None}

        with patch.object(chain, "CLAUSES", TEST_CLAUSES), \
             patch.object(chain, "CLAUSE_TEXT_BY_ID", {"4.2": TEST_CLAUSES[0]["text"]}):
            runner = chain.ChainRunner(fake_check, "dummy-key", cold=False, agent_factory=FakeAlertAgent)
            await runner.open_warm_agent()
            msg, t_end = make_turn(1, "renewal auto renews", time.monotonic())
            runner.on_turn(msg, t_end)
            await asyncio.gather(*runner.speak_tasks)

        metric = runner.turn_metrics[0]
        self.assertGreaterEqual(metric["stt_final_to_check_done_ms"], 0)
        self.assertIsNotNone(metric["check_done_to_first_audio_ms"])
        self.assertGreaterEqual(metric["check_done_to_first_audio_ms"], 0)
        self.assertIsNotNone(metric["total_ms"])
        self.assertGreaterEqual(metric["total_ms"], metric["stt_final_to_check_done_ms"])

    async def test_check_fn_exception_does_not_crash_and_is_recorded(self):
        def bad_check(sentence, clauses, *, client=None, model=None):
            raise RuntimeError("boom")

        with patch.object(chain, "CLAUSES", TEST_CLAUSES):
            runner = chain.ChainRunner(bad_check, "dummy-key", cold=False, agent_factory=FakeAlertAgent)
            await runner.open_warm_agent()
            msg, t_end = make_turn(1, "anything", time.monotonic())
            runner.on_turn(msg, t_end)  # must not raise

        self.assertEqual(runner.speak_tasks, [])
        self.assertEqual(runner.turn_metrics[0]["check_error"], "RuntimeError: boom")
        self.assertEqual(runner.turn_metrics[0]["verdict"], "unclear")

    async def test_cold_mode_opens_and_closes_a_fresh_agent_per_alert(self):
        created: list[FakeAlertAgent] = []

        def factory(api_key, clauses):
            a = FakeAlertAgent()
            created.append(a)
            return a

        def fake_check(sentence, clauses, *, client=None, model=None):
            return {"verdict": "contradiction", "clause_id": "4.2", "confidence": 0.9,
                     "latency_ms": 1.0, "model": "fake", "error": None}

        with patch.object(chain, "CLAUSES", TEST_CLAUSES), \
             patch.object(chain, "CLAUSE_TEXT_BY_ID", {"4.2": TEST_CLAUSES[0]["text"]}):
            runner = chain.ChainRunner(fake_check, "dummy-key", cold=True, agent_factory=factory)
            self.assertIsNone(await runner.open_warm_agent())  # cold: no warm session pre-opened
            self.assertIsNone(runner.warm_agent)
            msg, t_end = make_turn(1, "renewal auto renews", time.monotonic())
            runner.on_turn(msg, t_end)
            await asyncio.gather(*runner.speak_tasks)

        self.assertEqual(len(created), 1)
        self.assertTrue(created[0].opened)
        self.assertTrue(created[0].closed)
        self.assertEqual(created[0].speak_calls, [f"Compliance alert: clause 4.2. {TEST_CLAUSES[0]['text']}"])
        self.assertEqual(len(runner.cold_agent_costs), 1)

    async def test_unknown_clause_id_in_verdict_speaks_nothing(self):
        """Contradiction verdict names a clause_id not in the contract --
        build_alert_text returns None, nothing gets spoken (never fabricate
        alert text for a clause the contract doesn't have)."""
        def fake_check(sentence, clauses, *, client=None, model=None):
            return {"verdict": "contradiction", "clause_id": "99.9", "confidence": 0.9,
                     "latency_ms": 1.0, "model": "fake", "error": None}

        with patch.object(chain, "CLAUSES", TEST_CLAUSES), \
             patch.object(chain, "CLAUSE_TEXT_BY_ID", {"4.2": TEST_CLAUSES[0]["text"]}):
            runner = chain.ChainRunner(fake_check, "dummy-key", cold=False, agent_factory=FakeAlertAgent)
            await runner.open_warm_agent()
            msg, t_end = make_turn(1, "something", time.monotonic())
            runner.on_turn(msg, t_end)

        self.assertEqual(runner.speak_tasks, [])
        self.assertEqual(runner.warm_agent.speak_calls, [])


class TestBuildAlertText(unittest.TestCase):
    def test_uses_literal_contract_text_not_llm_output(self):
        clauses = [{"id": "4.2", "text": "Auto-renews unless 60 days notice."}]
        text = chain.build_alert_text("4.2", clauses=clauses)
        self.assertEqual(text, "Compliance alert: clause 4.2. Auto-renews unless 60 days notice.")

    def test_unknown_clause_returns_none(self):
        self.assertIsNone(chain.build_alert_text("99.9", clauses=[{"id": "4.2", "text": "x"}]))


class TestClauseShapes(unittest.TestCase):
    """Regression guard: the real check_claim.py indexes clauses by
    `c["section_number"]`/`c["literal_text"]` (verified by reading that
    file), a DIFFERENT shape than CLAUSES ({"id","text"}), which AlertAgent
    and build_alert_text use. Mixing these up is a silent KeyError at first
    real (non-fake-check) run -- this pins both shapes so it fails here
    instead."""

    def test_contract_clauses_shape_matches_real_check_claim_expectations(self):
        self.assertTrue(chain.CONTRACT_CLAUSES)
        for c in chain.CONTRACT_CLAUSES:
            self.assertIn("section_number", c)
            self.assertIn("literal_text", c)

    def test_alert_clauses_shape_matches_alert_agent_expectations(self):
        self.assertTrue(chain.CLAUSES)
        for c in chain.CLAUSES:
            self.assertIn("id", c)
            self.assertIn("text", c)

    def test_same_clause_ids_in_both_shapes(self):
        contract_ids = {str(c["section_number"]) for c in chain.CONTRACT_CLAUSES}
        alert_ids = {str(c["id"]) for c in chain.CLAUSES}
        self.assertEqual(contract_ids, alert_ids)


class TestCliDryRunAndKeyCheck(unittest.TestCase):
    def test_dry_run_prints_plan_and_makes_no_network_call(self):
        env = dict(os.environ)
        env.pop("ASSEMBLYAI_API_KEY", None)
        proc = subprocess.run(
            [sys.executable, str(CHAIN_SRC), "--dry-run"],
            env=env, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(proc.returncode, 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        plan = json.loads(proc.stdout)
        self.assertIn("wav_path", plan)
        self.assertIn("check_fn", plan)
        self.assertIn("clause_ids", plan)

    def test_dry_run_with_fake_check_names_fake_check_fn_in_plan(self):
        env = dict(os.environ)
        env.pop("ASSEMBLYAI_API_KEY", None)
        proc = subprocess.run(
            [sys.executable, str(CHAIN_SRC), "--dry-run", "--fake-check"],
            env=env, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(proc.returncode, 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        plan = json.loads(proc.stdout)
        self.assertEqual(plan["check_fn"], "fake-keyword-matcher")

    def test_missing_api_key_without_dry_run_exits_2(self):
        env = dict(os.environ)
        env.pop("ASSEMBLYAI_API_KEY", None)
        proc = subprocess.run(
            [sys.executable, str(CHAIN_SRC), "--fake-check"],
            env=env, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(proc.returncode, 2, f"stdout={proc.stdout!r} stderr={proc.stderr!r}")

    def test_missing_claim_check_without_fake_check_exits_2(self):
        """spikes/claim_check/claim_check.py doesn't exist yet (owned by
        another, concurrently-running agent) -- default (no --fake-check)
        must exit 2 with a clear message, never silently fall back."""
        if chain.CLAIM_CHECK_SRC.exists():
            self.skipTest("claim_check.py now exists -- this exit-2 path is no longer reachable")
        env = dict(os.environ)
        env["ASSEMBLYAI_API_KEY"] = "dummy-not-used-because-we-exit-first"
        proc = subprocess.run(
            [sys.executable, str(CHAIN_SRC)],
            env=env, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(proc.returncode, 2, f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        self.assertIn("claim_check.py", proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main()
