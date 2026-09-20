"""The claim-check leg must be visible on the wire.

Demo-day bug (docs/submission/DEMO_DAY_BUGS.md finding 1): with no Gemini key,
a spent quota or CLAUSECATCHER_PAID_DISABLED=1, the app still reported
"Lines checked 1 / Contradictions 0 / On-contract" and a green "GEMINI CHECK -
ready" pill. Nothing had been checked. These tests pin the contract that lets
the UI tell "checked and clean" apart from "never checked".

No network: the real checker is never invoked here (checker_state() makes no
call, and every socket test injects a fake or runs against the stub).

Each socket test ends with a frame that is guaranteed to come back (a `clause`
reply or `session_ended`) and asserts on everything received before it, so a
missing check_error fails the test instead of blocking on receive.
"""
from __future__ import annotations

import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from server import claim_check, main
from server.session_store import SessionStore

NO_KEYS = {
    "GEMINI_API_KEY": "",
    "GOOGLE_API_KEY": "",
    "CLAUSECATCHER_CLAIM_CHECK": "",
    "CLAUSECATCHER_PAID_DISABLED": "",
}
LINE = "we can knock ten percent off the price"


def _clean_env(**overrides: str) -> dict:
    env = dict(NO_KEYS)
    env.update(overrides)
    return {k: v for k, v in env.items() if v}


def clean_checker(sentence: str, clauses: list[dict]) -> dict:
    return {"verdict": "consistent", "clause_id": "3.1", "confidence": 0.9, "latency_ms": 1.0, "model": "fake", "error": None}


def erroring_checker(sentence: str, clauses: list[dict]) -> dict:
    return {"verdict": "unclear", "clause_id": None, "confidence": 0.0, "latency_ms": 1.0, "model": "fake", "error": "429 quota exceeded"}


def raising_checker(sentence: str, clauses: list[dict]) -> dict:
    raise RuntimeError("boom")


class CheckerStateTest(unittest.TestCase):
    """claim_check.checker_state(): the state of the leg without making a call."""

    def test_no_key_is_disabled(self) -> None:
        with mock.patch.dict(os.environ, _clean_env(), clear=True):
            self.assertEqual(claim_check.checker_state(), "disabled")

    def test_configured_is_ready(self) -> None:
        env = _clean_env(GEMINI_API_KEY="fake-never-called", CLAUSECATCHER_CLAIM_CHECK="gemini")
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(claim_check.checker_state(), "ready")

    def test_kill_switch_beats_a_configured_key(self) -> None:
        env = _clean_env(
            GEMINI_API_KEY="fake-never-called",
            CLAUSECATCHER_CLAIM_CHECK="gemini",
            CLAUSECATCHER_PAID_DISABLED="1",
        )
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(claim_check.checker_state(), "disabled")

    def test_process_call_cap_reached_is_error(self) -> None:
        env = _clean_env(
            GEMINI_API_KEY="fake-never-called",
            CLAUSECATCHER_CLAIM_CHECK="gemini",
            CLAUSECATCHER_MAX_GEMINI_CALLS="0",
        )
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(claim_check.checker_state(), "error")

    def test_injected_checker_is_ready(self) -> None:
        with mock.patch.dict(os.environ, _clean_env(), clear=True):
            self.assertEqual(claim_check.checker_state(clean_checker), "ready")


class WireVisibilityTest(unittest.TestCase):
    def setUp(self) -> None:
        main.store = SessionStore()
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.app.dependency_overrides.clear()

    def _ready_session(self) -> str:
        self.assertEqual(self.client.post("/api/contract/demo").status_code, 201)
        self.assertEqual(self.client.post("/api/consent", json={"accepted": True}).status_code, 200)
        resp = self.client.post("/api/session/start")
        self.assertEqual(resp.status_code, 201, resp.text)
        return resp.json()["session_id"]

    @staticmethod
    def _until(ws, stop_type: str) -> tuple[list[dict], dict]:
        """Everything received before the first `stop_type` frame, plus it."""
        seen: list[dict] = []
        while True:
            msg = ws.receive_json()
            if msg["type"] == stop_type:
                return seen, msg
            seen.append(msg)

    # -- status frame ----------------------------------------------------
    def test_status_frame_says_disabled_when_no_checker_configured(self) -> None:
        sid = self._ready_session()
        with mock.patch.dict(os.environ, _clean_env(), clear=True):
            with self.client.websocket_connect(f"/ws/session/{sid}") as ws:
                status = ws.receive_json()
        self.assertEqual(status["type"], "status")
        self.assertEqual(status["claim_check"], "disabled")

    def test_status_frame_says_ready_when_a_checker_is_configured(self) -> None:
        sid = self._ready_session()
        main.app.dependency_overrides[main.get_claim_checker] = lambda: clean_checker
        with self.client.websocket_connect(f"/ws/session/{sid}") as ws:
            status = ws.receive_json()
        self.assertEqual(status["claim_check"], "ready")

    # -- check_error -----------------------------------------------------
    def _check_errors_for(self, sid: str, lines: int = 1) -> list[dict]:
        with self.client.websocket_connect(f"/ws/session/{sid}") as ws:
            ws.receive_json()  # status
            for _ in range(lines):
                ws.send_json({"type": "transcript", "text": LINE})
            ws.send_json({"type": "ask", "section_number": "3.1"})  # fence
            seen, _clause = self._until(ws, "clause")
        return seen

    def test_unchecked_line_emits_check_error_when_disabled(self) -> None:
        sid = self._ready_session()
        with mock.patch.dict(os.environ, _clean_env(), clear=True):
            seen = self._check_errors_for(sid)
        self.assertEqual([f["type"] for f in seen], ["check_error"])
        self.assertTrue(seen[0]["message"])

    def test_checker_error_result_emits_check_error(self) -> None:
        sid = self._ready_session()
        main.app.dependency_overrides[main.get_claim_checker] = lambda: erroring_checker
        seen = self._check_errors_for(sid)
        self.assertEqual([f["type"] for f in seen], ["check_error"])
        self.assertNotIn("429", seen[0]["message"])  # upstream strings stay server-side

    def test_raising_checker_emits_check_error(self) -> None:
        sid = self._ready_session()
        main.app.dependency_overrides[main.get_claim_checker] = lambda: raising_checker
        seen = self._check_errors_for(sid)
        self.assertEqual([f["type"] for f in seen], ["check_error"])
        self.assertNotIn("boom", seen[0]["message"])

    def test_check_error_is_rate_limited_to_one_per_window(self) -> None:
        sid = self._ready_session()
        main.app.dependency_overrides[main.get_claim_checker] = lambda: erroring_checker
        seen = self._check_errors_for(sid, lines=5)
        self.assertEqual([f["type"] for f in seen], ["check_error"])

    def test_per_session_cap_skip_emits_check_error(self) -> None:
        sid = self._ready_session()
        main.app.dependency_overrides[main.get_claim_checker] = lambda: clean_checker
        with mock.patch.dict(os.environ, {"CLAUSECATCHER_MAX_CHECKS": "1"}):
            seen = self._check_errors_for(sid, lines=2)  # 1 checked, 1 over cap
        self.assertEqual([f["type"] for f in seen], ["check_error"])

    # -- report ----------------------------------------------------------
    def _report_after_one_line(self, sid: str) -> dict:
        with self.client.websocket_connect(f"/ws/session/{sid}") as ws:
            ws.receive_json()  # status
            ws.send_json({"type": "transcript", "text": LINE})
            ws.send_json({"type": "stop"})
            _seen, ended = self._until(ws, "session_ended")
        return ended["report"]

    def test_report_state_disabled_when_nothing_was_checked(self) -> None:
        sid = self._ready_session()
        with mock.patch.dict(os.environ, _clean_env(), clear=True):
            report = self._report_after_one_line(sid)
            self.assertEqual(report["claim_check_state"], "disabled")
            self.assertEqual(report["contradictions"], [])
            # the REST report agrees with the socket's
            self.assertEqual(self.client.get(f"/api/session/{sid}/report").json(), report)

    def test_report_state_ready_when_lines_were_actually_checked(self) -> None:
        sid = self._ready_session()
        main.app.dependency_overrides[main.get_claim_checker] = lambda: clean_checker
        report = self._report_after_one_line(sid)
        self.assertEqual(report["claim_check_state"], "ready")
        self.assertEqual(report["claim_check_calls"], 1)
        self.assertEqual(report["claim_check_errors"], 0)
        self.assertEqual(report["contradictions"], [])

    def test_report_state_error_when_checks_failed(self) -> None:
        sid = self._ready_session()
        main.app.dependency_overrides[main.get_claim_checker] = lambda: erroring_checker
        report = self._report_after_one_line(sid)
        self.assertEqual(report["claim_check_state"], "error")
        self.assertEqual(report["claim_check_errors"], 1)


if __name__ == "__main__":
    unittest.main()
