"""Offline unittest suite. No network calls anywhere in this file."""
from __future__ import annotations

import json
import socket
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import claim_check  # noqa: E402
import eval_claim_check  # noqa: E402

CLAUSES = [
    {"section_number": "3.1", "title": "Pricing", "literal_text": "Flat $48,000, no discounting."},
    {"section_number": "4.2", "title": "Renewal", "literal_text": "Auto-renews unless 60 days notice."},
]


class _Resp:
    def __init__(self, text):
        self.text = text


class _Models:
    def __init__(self, behavior):
        self._behavior = behavior  # callable(model, contents, config) -> _Resp, or raises

    def generate_content(self, model, contents, config):
        return self._behavior(model, contents, config)


class _Client:
    def __init__(self, behavior):
        self.models = _Models(behavior)


def _json_client(payload):
    return _Client(lambda model, contents, config: _Resp(json.dumps(payload)))


def _raising_client(exc):
    def behavior(model, contents, config):
        raise exc

    return _Client(behavior)


class TestCheckClaim(unittest.TestCase):
    def test_valid_json_maps_to_dict(self):
        client = _json_client({"verdict": "contradiction", "clause_id": "3.1", "confidence": 0.9})
        out = claim_check.check_claim("we'll discount it", CLAUSES, client=client)
        self.assertEqual(out["verdict"], "contradiction")
        self.assertEqual(out["clause_id"], "3.1")
        self.assertAlmostEqual(out["confidence"], 0.9)
        self.assertIsNone(out["error"])
        self.assertIn("latency_ms", out)
        self.assertEqual(out["model"], claim_check.DEFAULT_MODEL)

    def test_clause_id_not_in_contract_becomes_unclear(self):
        client = _json_client({"verdict": "contradiction", "clause_id": "9.9", "confidence": 0.95})
        out = claim_check.check_claim("x", CLAUSES, client=client)
        self.assertEqual(out["verdict"], "unclear")
        self.assertIsNone(out["clause_id"])

    def test_low_confidence_contradiction_becomes_unclear(self):
        client = _json_client(
            {"verdict": "contradiction", "clause_id": "3.1", "confidence": claim_check.CONFIDENCE_MIN - 0.01}
        )
        out = claim_check.check_claim("x", CLAUSES, client=client)
        self.assertEqual(out["verdict"], "unclear")

    def test_high_confidence_contradiction_stays(self):
        client = _json_client(
            {"verdict": "contradiction", "clause_id": "3.1", "confidence": claim_check.CONFIDENCE_MIN + 0.01}
        )
        out = claim_check.check_claim("x", CLAUSES, client=client)
        self.assertEqual(out["verdict"], "contradiction")

    def test_exception_becomes_unclear_with_error_no_raise(self):
        client = _raising_client(TimeoutError("timed out"))
        out = claim_check.check_claim("x", CLAUSES, client=client)
        self.assertEqual(out["verdict"], "unclear")
        self.assertIsNone(out["clause_id"])
        self.assertIsNotNone(out["error"])

    def test_429_like_exception_becomes_unclear_no_raise(self):
        class RateLimitError(Exception):
            pass

        client = _raising_client(RateLimitError("429 quota exceeded"))
        out = claim_check.check_claim("x", CLAUSES, client=client)
        self.assertEqual(out["verdict"], "unclear")
        self.assertIsNotNone(out["error"])

    def test_bad_json_becomes_unclear_no_raise(self):
        client = _Client(lambda model, contents, config: _Resp("not json"))
        out = claim_check.check_claim("x", CLAUSES, client=client)
        self.assertEqual(out["verdict"], "unclear")
        self.assertIsNotNone(out["error"])

    def test_confidence_is_clamped(self):
        client = _json_client({"verdict": "consistent", "clause_id": "3.1", "confidence": 5.0})
        out = claim_check.check_claim("x", CLAUSES, client=client)
        self.assertEqual(out["confidence"], 1.0)

    def test_key_never_appears_in_result(self):
        fake_key = "AIzaSyFAKE_SECRET_KEY_VALUE_12345"
        client = _json_client({"verdict": "unclear", "clause_id": None, "confidence": 0.1})
        # even if a key-shaped string were floating around in env, it must never
        # leak into the returned dict.
        import os

        old = os.environ.get("GEMINI_API_KEY")
        os.environ["GEMINI_API_KEY"] = fake_key
        try:
            out = claim_check.check_claim("x", CLAUSES, client=client)
        finally:
            if old is None:
                os.environ.pop("GEMINI_API_KEY", None)
            else:
                os.environ["GEMINI_API_KEY"] = old
        self.assertNotIn(fake_key, json.dumps(out))


class TestMetrics(unittest.TestCase):
    def test_metrics_hand_computed(self):
        # 4 records: 2 true contradictions (1 caught right clause, 1 caught wrong clause),
        # 1 missed contradiction (predicted consistent), 1 false alarm (expected consistent,
        # predicted contradiction).
        records = [
            {
                "expected_verdict": "contradiction",
                "expected_clause_id": "3.1",
                "predicted": {"verdict": "contradiction", "clause_id": "3.1", "latency_ms": 100.0, "error": None},
            },
            {
                "expected_verdict": "contradiction",
                "expected_clause_id": "4.2",
                "predicted": {"verdict": "contradiction", "clause_id": "3.1", "latency_ms": 200.0, "error": None},
            },
            {
                "expected_verdict": "contradiction",
                "expected_clause_id": "3.1",
                "predicted": {"verdict": "consistent", "clause_id": "3.1", "latency_ms": 300.0, "error": None},
            },
            {
                "expected_verdict": "consistent",
                "expected_clause_id": "4.2",
                "predicted": {"verdict": "contradiction", "clause_id": "4.2", "latency_ms": 400.0, "error": "timeout"},
            },
        ]
        m = eval_claim_check.compute_metrics(records)
        # TP=2, FN=1 -> recall = 2/3
        self.assertAlmostEqual(m["contradiction_recall"], 2 / 3)
        # neg_total=1 (the one "consistent" expected), 1 false alarm -> rate=1.0
        self.assertAlmostEqual(m["false_alarm_rate"], 1.0)
        # of 2 TPs, 1 has correct clause_id -> 0.5
        self.assertAlmostEqual(m["clause_id_accuracy_on_true_positives"], 0.5)
        self.assertEqual(m["error_count"], 1)
        self.assertEqual(m["total"], 4)

    def test_percentile_hand_computed(self):
        data = [10.0, 20.0, 30.0, 40.0]
        self.assertAlmostEqual(eval_claim_check.percentile(data, 50), 25.0)
        self.assertAlmostEqual(eval_claim_check.percentile(data, 0), 10.0)
        self.assertAlmostEqual(eval_claim_check.percentile(data, 100), 40.0)
        self.assertEqual(eval_claim_check.percentile([], 50), 0.0)


class TestNoKeyNoNetwork(unittest.TestCase):
    def test_no_key_exits_2_without_network(self):
        import os

        old_gemini = os.environ.pop("GEMINI_API_KEY", None)
        old_google = os.environ.pop("GOOGLE_API_KEY", None)

        def _trap(*a, **k):
            raise AssertionError("socket used during no-key path — network was attempted")

        real_socket = socket.socket
        socket.socket = _trap
        try:
            rc = eval_claim_check.main([])
            self.assertEqual(rc, 2)
        finally:
            socket.socket = real_socket
            if old_gemini is not None:
                os.environ["GEMINI_API_KEY"] = old_gemini
            if old_google is not None:
                os.environ["GOOGLE_API_KEY"] = old_google


if __name__ == "__main__":
    unittest.main()
