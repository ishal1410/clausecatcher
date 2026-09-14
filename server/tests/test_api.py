"""Tests for server/main.py. unittest + fastapi.testclient (sync, no extra deps)."""
from __future__ import annotations

import importlib
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from server import main
from server.session_store import SessionStore

FAKE_PDF = Path(__file__).resolve().parents[2] / "spikes" / "harness" / "fake_contract.pdf"

CLAUSES_AVAILABLE = importlib.util.find_spec("server.clauses") is not None


def contradiction_checker(sentence: str, clauses: list[dict]) -> dict:
    return {"verdict": "contradiction", "clause_id": "3.1", "confidence": 0.9, "latency_ms": 1.0, "model": "fake", "error": None}


def bad_clause_checker(sentence: str, clauses: list[dict]) -> dict:
    return {"verdict": "contradiction", "clause_id": "99.9", "confidence": 0.9, "latency_ms": 1.0, "model": "fake", "error": None}


def raising_checker(sentence: str, clauses: list[dict]) -> dict:
    raise RuntimeError("boom")


class ClauseCatcherApiTest(unittest.TestCase):
    def setUp(self) -> None:
        main.store = SessionStore()  # fresh state per test; routes read this global at call time
        self.client = TestClient(main.app)

    def tearDown(self) -> None:
        main.app.dependency_overrides.clear()

    def _ready_session(self) -> str:
        resp = self.client.post("/api/contract/demo")
        self.assertEqual(resp.status_code, 201, resp.text)
        resp = self.client.post("/api/consent", json={"accepted": True})
        self.assertEqual(resp.status_code, 200, resp.text)
        resp = self.client.post("/api/session/start")
        self.assertEqual(resp.status_code, 201, resp.text)
        return resp.json()["session_id"]

    # -- basic routes ---------------------------------------------------
    def test_health(self) -> None:
        resp = self.client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})

    def test_demo_contract_load(self) -> None:
        resp = self.client.post("/api/contract/demo")
        self.assertEqual(resp.status_code, 201)
        clauses = resp.json()["clauses"]
        self.assertTrue(any(c["section_number"] == "3.1" for c in clauses))

        resp = self.client.get("/api/contract")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["clauses"], clauses)

    def test_session_start_409_without_consent(self) -> None:
        self.client.post("/api/contract/demo")
        resp = self.client.post("/api/session/start")
        self.assertEqual(resp.status_code, 409)

    def test_session_start_409_without_contract(self) -> None:
        self.client.post("/api/consent", json={"accepted": True})
        resp = self.client.post("/api/session/start")
        self.assertEqual(resp.status_code, 409)

    def test_bad_pdf_upload_422(self) -> None:
        resp = self.client.post(
            "/api/contract",
            files={"file": ("notes.txt", b"hello", "text/plain")},
        )
        self.assertEqual(resp.status_code, 422)

    def test_pdf_upload_happy_path(self) -> None:
        if not CLAUSES_AVAILABLE:
            self.skipTest("server/clauses.py not present yet (owned by another agent)")
        pdf_bytes = FAKE_PDF.read_bytes()
        resp = self.client.post(
            "/api/contract",
            files={"file": ("fake_contract.pdf", pdf_bytes, "application/pdf")},
        )
        self.assertEqual(resp.status_code, 201, resp.text)
        clauses = resp.json()["clauses"]
        self.assertTrue(len(clauses) > 0)
        for c in clauses:
            self.assertIn("section_number", c)
            self.assertIn("title", c)
            self.assertIn("literal_text", c)

    # -- websocket --------------------------------------------------------
    def test_ws_contradiction_produces_alert_with_literal_text(self) -> None:
        session_id = self._ready_session()
        main.app.dependency_overrides[main.get_claim_checker] = lambda: contradiction_checker
        with self.client.websocket_connect(f"/ws/session/{session_id}") as ws:
            ws.send_json({"type": "transcript", "text": "we'll knock ten percent off"})
            msg = ws.receive_json()
        self.assertEqual(msg["type"], "alert")
        self.assertEqual(msg["section_number"], "3.1")
        expected_clause = next(c for c in main.store.contract if c["section_number"] == "3.1")
        self.assertEqual(msg["literal_text"], expected_clause["literal_text"])

    def test_ws_unknown_clause_id_no_alert(self) -> None:
        session_id = self._ready_session()
        main.app.dependency_overrides[main.get_claim_checker] = lambda: bad_clause_checker
        with self.client.websocket_connect(f"/ws/session/{session_id}") as ws:
            ws.send_json({"type": "transcript", "text": "some claim"})
            # Prove no alert was sent for the transcript above: the next
            # response we get back is the reply to this ask, not an alert.
            ws.send_json({"type": "ask", "section_number": "3.1"})
            msg = ws.receive_json()
        self.assertEqual(msg["type"], "clause")

    def test_ws_checker_raises_no_alert_socket_stays_open(self) -> None:
        session_id = self._ready_session()
        main.app.dependency_overrides[main.get_claim_checker] = lambda: raising_checker
        with self.client.websocket_connect(f"/ws/session/{session_id}") as ws:
            ws.send_json({"type": "transcript", "text": "some claim"})
            ws.send_json({"type": "ask", "section_number": "3.1"})
            msg = ws.receive_json()
        self.assertEqual(msg["type"], "clause")

    def test_ws_ask_returns_clause(self) -> None:
        session_id = self._ready_session()
        with self.client.websocket_connect(f"/ws/session/{session_id}") as ws:
            ws.send_json({"type": "ask", "section_number": "4.2"})
            msg = ws.receive_json()
        self.assertEqual(msg["type"], "clause")
        self.assertEqual(msg["section_number"], "4.2")

    def test_ws_ask_unknown_section_returns_error(self) -> None:
        session_id = self._ready_session()
        with self.client.websocket_connect(f"/ws/session/{session_id}") as ws:
            ws.send_json({"type": "ask", "section_number": "999"})
            msg = ws.receive_json()
        self.assertEqual(msg["type"], "error")

    # -- report -------------------------------------------------------------
    def test_report_contents_after_end(self) -> None:
        session_id = self._ready_session()
        main.app.dependency_overrides[main.get_claim_checker] = lambda: contradiction_checker
        with self.client.websocket_connect(f"/ws/session/{session_id}") as ws:
            ws.send_json({"type": "transcript", "text": "we'll knock ten percent off"})
            ws.receive_json()  # alert

        resp = self.client.post(f"/api/session/{session_id}/end")
        self.assertEqual(resp.status_code, 200)
        report = resp.json()
        self.assertEqual(report["transcript_count"], 1)
        self.assertEqual(len(report["contradictions"]), 1)
        self.assertEqual(report["contradictions"][0]["section_number"], "3.1")
        self.assertIn("3.1", report["contract_clauses_referenced"])
        self.assertIsNotNone(report["started_at"])
        self.assertIsNotNone(report["ended_at"])

        resp2 = self.client.get(f"/api/session/{session_id}/report")
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.json(), report)


if __name__ == "__main__":
    unittest.main()
