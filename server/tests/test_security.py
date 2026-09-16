"""Security regression tests for server/main.py + server/session_store.py:
per-browser workspaces, WS attach/live caps, idle timeout, upload limits,
headers. No network: fakes only, no API keys in env."""
from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from server import main
from server.session_store import SessionStore


def counting_checker_factory(calls: list[str]):
    def checker(sentence: str, clauses: list[dict]) -> dict:
        calls.append(sentence)
        return {"verdict": "unclear", "clause_id": None, "confidence": 0.0, "latency_ms": 0.0, "model": "fake", "error": None}

    return checker


class _Base(unittest.TestCase):
    def setUp(self) -> None:
        main.store = SessionStore()
        self.a = TestClient(main.app)
        self.b = TestClient(main.app)

    def tearDown(self) -> None:
        main.app.dependency_overrides.clear()

    def ready(self, client: TestClient) -> str:
        self.assertEqual(client.post("/api/contract/demo").status_code, 201)
        self.assertEqual(client.post("/api/consent", json={"accepted": True}).status_code, 200)
        resp = client.post("/api/session/start")
        self.assertEqual(resp.status_code, 201, resp.text)
        return resp.json()["session_id"]


class WorkspaceIsolationTest(_Base):
    def test_cookie_flags(self) -> None:
        resp = self.a.post("/api/contract/demo")
        cookie = resp.headers["set-cookie"].lower()
        self.assertIn("cc_ws=", cookie)
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=strict", cookie)
        self.assertNotIn("secure", cookie)  # plain http dev
        https = self.b.post("/api/contract/demo", headers={"x-forwarded-proto": "https"})
        self.assertIn("secure", https.headers["set-cookie"].lower())

    def test_second_client_cannot_see_first_clients_contract(self) -> None:
        self.a.post("/api/contract/demo")
        self.assertEqual(self.a.get("/api/contract").status_code, 200)
        self.assertEqual(self.b.get("/api/contract").status_code, 404)

    def test_second_client_cannot_overwrite_first_clients_contract(self) -> None:
        self.a.post("/api/contract/demo")
        before = self.a.get("/api/contract").json()
        fake = [{"section_number": "1", "title": "Evil", "literal_text": "evil"}]
        with mock.patch.object(main, "extract_clauses_safe", mock.AsyncMock(return_value=fake)):
            resp = self.b.post("/api/contract", files={"file": ("x.pdf", b"%PDF-1.4 x", "application/pdf")})
        self.assertEqual(resp.status_code, 201, resp.text)
        self.assertEqual(self.a.get("/api/contract").json(), before)
        self.assertEqual(self.b.get("/api/contract").json()["clauses"], fake)

    def test_consent_not_shared(self) -> None:
        self.a.post("/api/consent", json={"accepted": True})
        self.b.post("/api/contract/demo")
        self.assertEqual(self.b.post("/api/session/start").status_code, 409)

    def test_consent_must_be_strict_bool(self) -> None:
        self.assertEqual(self.a.post("/api/consent", json={"accepted": "yes"}).status_code, 422)

    def test_other_client_cannot_end_or_read_or_attach_session(self) -> None:
        sid = self.ready(self.a)
        self.assertEqual(self.b.post(f"/api/session/{sid}/end").status_code, 404)
        self.assertEqual(self.b.get(f"/api/session/{sid}/report").status_code, 404)
        with self.b.websocket_connect(f"/ws/session/{sid}") as ws:
            self.assertEqual(ws.receive_json()["type"], "error")
            with self.assertRaises(WebSocketDisconnect) as cm:
                ws.receive_json()
        self.assertEqual(cm.exception.code, 1008)

    def test_live_session_uses_contract_snapshot(self) -> None:
        sid = self.ready(self.a)
        fake = [{"section_number": "3.1", "title": "Swapped", "literal_text": "swapped"}]
        with self.a.websocket_connect(f"/ws/session/{sid}") as ws:
            ws.receive_json()  # status
            with mock.patch.object(main, "extract_clauses_safe", mock.AsyncMock(return_value=fake)):
                self.a.post("/api/contract", files={"file": ("x.pdf", b"%PDF-1.4 x", "application/pdf")})
            ws.send_json({"type": "ask", "section_number": "3.1"})
            msg = ws.receive_json()
        self.assertEqual(msg["type"], "clause")
        self.assertNotEqual(msg["literal_text"], "swapped")

    def test_workspace_and_session_caps(self) -> None:
        store = SessionStore(max_workspaces=3, max_sessions=2)
        ids = [store.new_workspace().workspace_id for _ in range(5)]
        self.assertEqual(len(store.workspaces), 3)
        self.assertIsNone(store.get_workspace(ids[0]))
        ws = store.get_workspace(ids[-1])
        ws.contract, ws.consent = [], True
        s1 = store.start_session(ws)
        s1.ended_at = s1.started_at
        store.start_session(ws)
        store.start_session(ws)
        self.assertEqual(len(store.sessions), 2)
        self.assertNotIn(s1.session_id, store.sessions)  # oldest ended evicted first


class WebSocketAbuseTest(_Base):
    def test_ended_session_ws_rejected(self) -> None:
        sid = self.ready(self.a)
        self.a.post(f"/api/session/{sid}/end")
        with self.a.websocket_connect(f"/ws/session/{sid}") as ws:
            self.assertEqual(ws.receive_json()["type"], "error")
            with self.assertRaises(WebSocketDisconnect) as cm:
                ws.receive_json()
        self.assertEqual(cm.exception.code, 1008)

    def test_second_socket_on_same_session_rejected(self) -> None:
        sid = self.ready(self.a)
        with self.a.websocket_connect(f"/ws/session/{sid}") as ws1:
            ws1.receive_json()  # status
            with self.a.websocket_connect(f"/ws/session/{sid}") as ws2:
                self.assertEqual(ws2.receive_json()["type"], "error")
                with self.assertRaises(WebSocketDisconnect) as cm:
                    ws2.receive_json()
        self.assertEqual(cm.exception.code, 1008)

    def test_live_cap_enforced_and_released(self) -> None:
        with mock.patch.dict(os.environ, {"CLAUSECATCHER_MAX_LIVE_WS": "1"}):
            sid1, sid2 = self.ready(self.a), self.ready(self.a)
            with self.a.websocket_connect(f"/ws/session/{sid1}") as ws1:
                ws1.receive_json()
                with self.a.websocket_connect(f"/ws/session/{sid2}") as ws2:
                    msg = ws2.receive_json()
                    self.assertEqual(msg, {"type": "error", "message": "demo busy, try again shortly"})
                    with self.assertRaises(WebSocketDisconnect) as cm:
                        ws2.receive_json()
                self.assertEqual(cm.exception.code, 1013)
            self.assertEqual(main.store.live_ws, 0)
            with self.a.websocket_connect(f"/ws/session/{sid2}") as ws2:  # busy reject did not burn it
                self.assertEqual(ws2.receive_json()["type"], "status")

    def test_idle_timeout_ends_session(self) -> None:
        sid = self.ready(self.a)
        with mock.patch.dict(os.environ, {"CLAUSECATCHER_IDLE_TIMEOUT_S": "0.2"}):
            with self.a.websocket_connect(f"/ws/session/{sid}") as ws:
                ws.receive_json()
                msg = ws.receive_json()
        self.assertEqual(msg["type"], "session_ended")
        self.assertEqual(msg["reason"], "idle")
        self.assertIsNotNone(msg["report"]["ended_at"])
        self.assertEqual(main.store.live_ws, 0)

    def test_hard_cap_ends_session(self) -> None:
        sid = self.ready(self.a)
        with mock.patch.dict(os.environ, {"CLAUSECATCHER_SESSION_CAP_S": "0.2"}):
            with self.a.websocket_connect(f"/ws/session/{sid}") as ws:
                ws.receive_json()
                msg = ws.receive_json()
        self.assertEqual(msg["reason"], "time_limit")

    def test_paid_upstreams_refused_by_kill_switch_and_budget(self) -> None:
        opened: list[str] = []

        def factory(**kwargs):
            opened.append("x")
            raise AssertionError("paid upstream must not be constructed")

        main.app.dependency_overrides[main.get_stt_factory] = lambda: factory
        main.app.dependency_overrides[main.get_voice_factory] = lambda: factory
        env = {"ASSEMBLYAI_API_KEY": "fake-never-used", "CLAUSECATCHER_PAID_DISABLED": "1"}
        with mock.patch.dict(os.environ, env):
            with self.a.websocket_connect(f"/ws/session/{self.ready(self.a)}") as ws:
                frames = [ws.receive_json(), ws.receive_json()]
        self.assertIn({"type": "status", "stt": "disabled", "voice": "disabled"}, frames)
        main.store.spent_usd = 5.0
        env = {"ASSEMBLYAI_API_KEY": "fake-never-used", "CLAUSECATCHER_BUDGET_USD": "3"}
        with mock.patch.dict(os.environ, env):
            with self.a.websocket_connect(f"/ws/session/{self.ready(self.a)}") as ws:
                frames = [ws.receive_json(), ws.receive_json()]
        self.assertIn({"type": "status", "stt": "disabled", "voice": "disabled"}, frames)
        self.assertEqual(opened, [])

    def test_claim_checks_truncated_and_capped_per_session(self) -> None:
        calls: list[str] = []
        main.app.dependency_overrides[main.get_claim_checker] = lambda: counting_checker_factory(calls)
        sid = self.ready(self.a)
        with mock.patch.dict(os.environ, {"CLAUSECATCHER_MAX_CHECKS": "2"}):
            with self.a.websocket_connect(f"/ws/session/{sid}") as ws:
                ws.receive_json()
                for _ in range(4):
                    ws.send_json({"type": "transcript", "text": "word " * 500})
                ws.send_json({"type": "stop"})
                report = ws.receive_json()["report"]
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(len(c) <= 400 for c in calls))
        self.assertEqual(report["claim_check_calls"], 2)
        self.assertEqual(report["transcript_count"], 4)

    def test_origin_allowlist(self) -> None:
        sid = self.ready(self.a)
        with mock.patch.dict(os.environ, {"CLAUSECATCHER_ALLOWED_ORIGINS": "https://good.example"}):
            with self.assertRaises(WebSocketDisconnect):
                with self.a.websocket_connect(f"/ws/session/{sid}", headers={"origin": "https://evil.example"}) as ws:
                    ws.receive_json()
            with self.a.websocket_connect(f"/ws/session/{sid}", headers={"origin": "https://good.example"}) as ws:
                self.assertEqual(ws.receive_json()["type"], "status")


class HttpHardeningTest(_Base):
    def test_oversized_upload_413_by_content_length(self) -> None:
        body = b"x" * (main.MAX_PDF_BYTES + 128 * 1024)
        resp = self.a.post("/api/contract", files={"file": ("big.pdf", body, "application/pdf")})
        self.assertEqual(resp.status_code, 413)

    def test_oversized_streamed_upload_413_without_reading_all(self) -> None:
        # Raw ASGI (TestClient pre-buffers bodies): chunked, no Content-Length.
        chunk = b"x" * (256 * 1024)
        total_chunks = (main.MAX_PDF_BYTES // len(chunk)) * 4
        pulled = 0
        sent: list[dict] = []

        async def receive():
            nonlocal pulled
            pulled += 1
            head = b'--zz\r\nContent-Disposition: form-data; name="file"; filename="a.pdf"\r\nContent-Type: application/pdf\r\n\r\n'
            return {"type": "http.request", "body": (head if pulled == 1 else b"") + chunk, "more_body": pulled < total_chunks}

        async def send(message):
            sent.append(message)

        scope = {
            "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
            "scheme": "http", "path": "/api/contract", "raw_path": b"/api/contract", "query_string": b"",
            "root_path": "", "server": ("testserver", 80), "client": ("127.0.0.1", 1),
            "headers": [(b"content-type", b"multipart/form-data; boundary=zz"), (b"transfer-encoding", b"chunked")],
        }
        asyncio.run(main.app(scope, receive, send))
        self.assertEqual(sent[0]["status"], 413)
        self.assertLess(pulled, total_chunks // 2)

    def test_unreadable_pdf_generic_detail(self) -> None:
        err = main.ClauseExtractionError("pypdf internal: /Root xref at 0xdeadbeef")
        with mock.patch.object(main, "extract_clauses_safe", mock.AsyncMock(side_effect=err)):
            resp = self.a.post("/api/contract", files={"file": ("x.pdf", b"%PDF-1.4 x", "application/pdf")})
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["detail"], "unreadable PDF")

    def test_security_headers(self) -> None:
        for path in ("/api/health", "/"):
            resp = self.a.get(path)
            h = resp.headers
            self.assertIn("frame-ancestors 'none'", h["content-security-policy"])
            self.assertEqual(h["x-content-type-options"], "nosniff")
            self.assertEqual(h["x-frame-options"], "DENY")
            self.assertEqual(h["referrer-policy"], "no-referrer")
            self.assertIn("microphone=(self)", h["permissions-policy"])
            self.assertNotIn("strict-transport-security", h)
        https = self.a.get("/api/health", headers={"x-forwarded-proto": "https"})
        self.assertIn("max-age=", https.headers["strict-transport-security"])

    def test_docs_disabled(self) -> None:
        self.assertIsNone(main.app.openapi_url)
        for path in ("/docs", "/redoc", "/openapi.json"):
            resp = self.a.get(path)
            self.assertNotIn("swagger", resp.text.lower())
            self.assertNotIn('"openapi"', resp.text)


if __name__ == "__main__":
    unittest.main()
