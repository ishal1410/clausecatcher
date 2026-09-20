"""Tests for the STT/voice wiring in server/main.py's websocket handler
(fakes injected via FastAPI dependency_overrides -- no network, no real
AssemblyAI/Gemini calls anywhere in this file), plus a ported subset of
spikes/claim_check/test_claim_check.py's safety cases against the
server/claim_check.py port.
"""
from __future__ import annotations

import base64
import json
import os
import unittest

from fastapi.testclient import TestClient

from server import claim_check
from server import main
from server.session_store import SessionStore

CLAUSES = [
    {"section_number": "3.1", "title": "Pricing", "literal_text": "Flat $48,000, no discounting."},
    {"section_number": "4.2", "title": "Renewal", "literal_text": "Auto-renews unless 60 days notice."},
]


def contradiction_checker(sentence: str, clauses: list[dict]) -> dict:
    return {"verdict": "contradiction", "clause_id": "3.1", "confidence": 0.9, "latency_ms": 1.0, "model": "fake", "error": None}


# ---------------------------------------------------------------------------
# Fakes matching server/stt.py and server/voice.py's documented interfaces.
# send_audio() recognizes a "TURN:<text>" marker prefix to drive on_turn from
# inside the server's own event loop (via the normal binary-frame path),
# instead of reaching across threads/loops from the test.
# ---------------------------------------------------------------------------
class FakeStreamingTranscriber:
    def __init__(self, api_key, *, on_turn, keyterms=None, sample_rate=16000, speech_model=None, ws_url=None):
        self.api_key = api_key
        self.on_turn = on_turn
        self.keyterms = keyterms
        self.received_audio: list[bytes] = []
        self.started = False
        self.stopped = False
        self.est_cost_usd = 0.011
        self.stats: dict = {}

    async def start(self) -> None:
        self.started = True

    async def send_audio(self, pcm16: bytes) -> None:
        self.received_audio.append(pcm16)
        if pcm16.startswith(b"TURN:"):
            await self.on_turn(pcm16[len(b"TURN:"):].decode("utf-8"), True)

    async def stop(self) -> None:
        self.stopped = True


class FakeAlertSpeaker:
    def __init__(self, api_key, *, on_audio, on_event=None, ws_url=None, token_fetch=None):
        self.api_key = api_key
        self.on_audio = on_audio
        self.on_event = on_event
        self.said: list[str] = []
        self.is_open = False
        self.est_cost_usd = 0.022
        self.raise_on_speak = False
        self.emit_audio = False

    async def open(self) -> None:
        self.is_open = True

    async def say_exactly(self, text: str) -> dict:
        self.said.append(text)
        if self.emit_audio:
            await self.on_audio(b"\x00\x01", 24000)
        if self.raise_on_speak:
            raise RuntimeError("speaker boom")
        return {
            "text": text,
            "first_audio_ms": 1.0,
            "done_ms": 2.0,
            "agent_transcript": text,
            "literal_spoken": text,
            "similarity": 1.0,
            "errors": [],
        }

    async def close(self) -> None:
        self.is_open = False


class _FactoryBox:
    """Captures the fake instance(s) a factory override creates so a test can
    assert on them after the fact -- the instance is built server-side inside
    the websocket handler, not by the test itself."""

    def __init__(self, fake_cls):
        self.fake_cls = fake_cls
        self.instances: list = []

    def provider(self):
        def factory(**kwargs):
            fake = self.fake_cls(**kwargs)
            self.instances.append(fake)
            return fake

        return factory


class SessionFlowTest(unittest.TestCase):
    def setUp(self) -> None:
        main.store = SessionStore()
        self.client = TestClient(main.app)
        self._old_env: dict[str, str | None] = {}

    def tearDown(self) -> None:
        main.app.dependency_overrides.clear()
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _set_env(self, key: str, value: str) -> None:
        self._old_env.setdefault(key, os.environ.get(key))
        os.environ[key] = value

    def _ready_session(self) -> str:
        resp = self.client.post("/api/contract/demo")
        self.assertEqual(resp.status_code, 201, resp.text)
        resp = self.client.post("/api/consent", json={"accepted": True})
        self.assertEqual(resp.status_code, 200, resp.text)
        resp = self.client.post("/api/session/start")
        self.assertEqual(resp.status_code, 201, resp.text)
        return resp.json()["session_id"]

    def _wire_fakes(self, checker=contradiction_checker):
        stt_box = _FactoryBox(FakeStreamingTranscriber)
        voice_box = _FactoryBox(FakeAlertSpeaker)
        main.app.dependency_overrides[main.get_claim_checker] = lambda: checker
        main.app.dependency_overrides[main.get_stt_factory] = stt_box.provider
        main.app.dependency_overrides[main.get_voice_factory] = voice_box.provider
        self._set_env("ASSEMBLYAI_API_KEY", "fake-key-for-test-only-never-used-on-network")
        return stt_box, voice_box

    def _drain_until(self, ws, msg_type: str, limit: int = 10) -> tuple[dict, list[dict]]:
        collected = []
        for _ in range(limit):
            msg = ws.receive_json()
            if msg["type"] == msg_type:
                return msg, collected
            collected.append(msg)
        raise AssertionError(f"never saw a {msg_type!r} message; got {collected}")

    # -- connected path: status, binary audio, finalized turn -----------
    def test_status_connected_when_key_present_with_fakes(self) -> None:
        session_id = self._ready_session()
        self._wire_fakes()
        with self.client.websocket_connect(f"/ws/session/{session_id}") as ws:
            status = ws.receive_json()
        self.assertEqual(status, {"type": "status", "stt": "connected", "voice": "connected", "claim_check": "ready"})

    def test_binary_audio_frames_reach_fake_stt(self) -> None:
        session_id = self._ready_session()
        stt_box, _voice_box = self._wire_fakes()
        with self.client.websocket_connect(f"/ws/session/{session_id}") as ws:
            ws.receive_json()  # status
            ws.send_bytes(b"\x01\x02\x03\x04")
            ws.send_json({"type": "stop"})
            ws.receive_json()  # session_ended
        self.assertIn(b"\x01\x02\x03\x04", stt_box.instances[0].received_audio)

    def test_finalized_turn_alerts_and_speaks_literal_alert_text(self) -> None:
        session_id = self._ready_session()
        _stt_box, voice_box = self._wire_fakes()
        clause = None
        with self.client.websocket_connect(f"/ws/session/{session_id}") as ws:
            ws.receive_json()  # status
            ws.send_bytes(b"TURN:we'll knock ten percent off right now")
            self.assertEqual(ws.receive_json(), {"type": "transcript", "text": "we'll knock ten percent off right now", "final": True})
            alert = ws.receive_json()
            self.assertEqual(alert["type"], "alert")
            self.assertEqual(alert["section_number"], "3.1")
            clause = next(c for c in self.client.get("/api/contract").json()["clauses"] if c["section_number"] == "3.1")
            self.assertEqual(alert["literal_text"], clause["literal_text"])
            ws.send_json({"type": "stop"})
            ended = ws.receive_json()
        self.assertEqual(ended["type"], "session_ended")
        speaker = voice_box.instances[0]
        self.assertIn(main.build_alert_text(clause), speaker.said)
        report = ended["report"]
        self.assertEqual(report["contradictions"][0]["literal_spoken"], main.build_alert_text(clause))
        self.assertGreater(report["est_cost_usd"], 0.0)

    def test_alert_dedupe_within_20s(self) -> None:
        session_id = self._ready_session()
        self._wire_fakes()
        with self.client.websocket_connect(f"/ws/session/{session_id}") as ws:
            ws.receive_json()  # status
            ws.send_bytes(b"TURN:we'll knock ten percent off right now")
            ws.receive_json()  # transcript
            first = ws.receive_json()
            self.assertEqual(first["type"], "alert")
            # same clause again, well inside the 20s dedupe window -> suppressed
            ws.send_bytes(b"TURN:we will still knock ten percent off")
            self.assertEqual(ws.receive_json()["type"], "transcript")
            # prove it: the very next message is the ask reply, not a 2nd alert
            ws.send_json({"type": "ask", "section_number": "4.2"})
            second = ws.receive_json()
        self.assertEqual(second["type"], "clause")

    def test_ask_speaks_clause_answer_text(self) -> None:
        session_id = self._ready_session()
        _stt_box, voice_box = self._wire_fakes()
        with self.client.websocket_connect(f"/ws/session/{session_id}") as ws:
            ws.receive_json()  # status
            ws.send_json({"type": "ask", "section_number": "4.2"})
            clause_msg = ws.receive_json()
            self.assertEqual(clause_msg["type"], "clause")
            ws.send_json({"type": "stop"})
            ws.receive_json()  # session_ended (also drains the speak task)
        clause = next(c for c in self.client.get("/api/contract").json()["clauses"] if c["section_number"] == "4.2")
        self.assertIn(main.build_clause_answer_text(clause), voice_box.instances[0].said)

    def test_ask_unknown_section_error_no_speak(self) -> None:
        session_id = self._ready_session()
        _stt_box, voice_box = self._wire_fakes()
        with self.client.websocket_connect(f"/ws/session/{session_id}") as ws:
            ws.receive_json()  # status
            ws.send_json({"type": "ask", "section_number": "999"})
            msg = ws.receive_json()
            ws.send_json({"type": "stop"})
            ws.receive_json()
        self.assertEqual(msg["type"], "error")
        self.assertEqual(voice_box.instances[0].said, [])

    def test_agent_audio_forwarded_as_base64_with_sample_rate_24000(self) -> None:
        session_id = self._ready_session()
        _stt_box, voice_box = self._wire_fakes()
        with self.client.websocket_connect(f"/ws/session/{session_id}") as ws:
            ws.receive_json()  # status
            voice_box.instances  # not yet created before first ask below
            ws.send_json({"type": "ask", "section_number": "4.2"})
            clause_msg, _skipped = self._drain_until(ws, "clause")
            self.assertEqual(clause_msg["type"], "clause")
            voice_box.instances[0].emit_audio = True
            ws.send_json({"type": "ask", "section_number": "3.1"})
            audio_msg, _skipped2 = self._drain_until(ws, "agent_audio")
            ws.send_json({"type": "stop"})
            ws.receive_json()
        self.assertEqual(audio_msg["sample_rate"], 24000)
        self.assertEqual(base64.b64decode(audio_msg["pcm16_b64"]), b"\x00\x01")

    def test_speaker_say_exactly_error_does_not_crash_socket(self) -> None:
        session_id = self._ready_session()
        _stt_box, voice_box = self._wire_fakes()
        with self.client.websocket_connect(f"/ws/session/{session_id}") as ws:
            ws.receive_json()  # status
            ws.send_bytes(b"TURN:we'll knock ten percent off right now")
            self.assertEqual(ws.receive_json(), {"type": "transcript", "text": "we'll knock ten percent off right now", "final": True})
            alert = ws.receive_json()
            self.assertEqual(alert["type"], "alert")
            voice_box.instances[0].raise_on_speak = True
            ws.send_json({"type": "ask", "section_number": "4.2"})
            clause_msg = ws.receive_json()
            self.assertEqual(clause_msg["type"], "clause")  # socket still alive
            ws.send_json({"type": "stop"})
            ended = ws.receive_json()
        self.assertEqual(ended["type"], "session_ended")

    def test_no_key_status_disabled_transcript_seam_still_alerts(self) -> None:
        session_id = self._ready_session()
        main.app.dependency_overrides[main.get_claim_checker] = lambda: contradiction_checker
        os.environ.pop("ASSEMBLYAI_API_KEY", None)
        with self.client.websocket_connect(f"/ws/session/{session_id}") as ws:
            status = ws.receive_json()
            self.assertEqual(
                status, {"type": "status", "stt": "disabled", "voice": "disabled", "claim_check": "ready"}
            )
            ws.send_json({"type": "transcript", "text": "we'll knock ten percent off"})
            alert = ws.receive_json()
        self.assertEqual(alert["type"], "alert")
        self.assertEqual(alert["section_number"], "3.1")

    def test_short_sentence_skips_claim_check(self) -> None:
        session_id = self._ready_session()
        calls: list[str] = []

        def counting_checker(sentence: str, clauses: list[dict]) -> dict:
            calls.append(sentence)
            return contradiction_checker(sentence, clauses)

        main.app.dependency_overrides[main.get_claim_checker] = lambda: counting_checker
        with self.client.websocket_connect(f"/ws/session/{session_id}") as ws:
            ws.receive_json()  # status
            ws.send_json({"type": "transcript", "text": "too short"})  # 2 words
            ws.send_json({"type": "ask", "section_number": "4.2"})
            msg = ws.receive_json()
        self.assertEqual(msg["type"], "clause")
        self.assertEqual(calls, [])


# ---------------------------------------------------------------------------
# claim_check.py port: subset of spikes/claim_check/test_claim_check.py's
# TestCheckClaim safety cases, run against server/claim_check.py directly.
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, text):
        self.text = text


class _Models:
    def __init__(self, behavior):
        self._behavior = behavior

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


class ClaimCheckPortTest(unittest.TestCase):
    def test_valid_json_maps_to_dict(self) -> None:
        client = _json_client({"verdict": "contradiction", "clause_id": "3.1", "confidence": 0.9})
        out = claim_check.check_claim("we'll discount it", CLAUSES, client=client)
        self.assertEqual(out["verdict"], "contradiction")
        self.assertEqual(out["clause_id"], "3.1")
        self.assertIsNone(out["error"])
        self.assertEqual(out["model"], claim_check.DEFAULT_MODEL)

    def test_clause_id_not_in_contract_becomes_unclear(self) -> None:
        client = _json_client({"verdict": "contradiction", "clause_id": "9.9", "confidence": 0.95})
        out = claim_check.check_claim("x", CLAUSES, client=client)
        self.assertEqual(out["verdict"], "unclear")
        self.assertIsNone(out["clause_id"])

    def test_low_confidence_contradiction_becomes_unclear(self) -> None:
        client = _json_client(
            {"verdict": "contradiction", "clause_id": "3.1", "confidence": claim_check.CONFIDENCE_MIN - 0.01}
        )
        out = claim_check.check_claim("x", CLAUSES, client=client)
        self.assertEqual(out["verdict"], "unclear")

    def test_exception_becomes_unclear_with_error_no_raise(self) -> None:
        client = _raising_client(TimeoutError("timed out"))
        out = claim_check.check_claim("x", CLAUSES, client=client)
        self.assertEqual(out["verdict"], "unclear")
        self.assertIsNone(out["clause_id"])
        self.assertIsNotNone(out["error"])

    def test_bad_json_becomes_unclear_no_raise(self) -> None:
        client = _Client(lambda model, contents, config: _Resp("not json"))
        out = claim_check.check_claim("x", CLAUSES, client=client)
        self.assertEqual(out["verdict"], "unclear")
        self.assertIsNotNone(out["error"])

    def test_confidence_is_clamped(self) -> None:
        client = _json_client({"verdict": "consistent", "clause_id": "3.1", "confidence": 5.0})
        out = claim_check.check_claim("x", CLAUSES, client=client)
        self.assertEqual(out["confidence"], 1.0)

    def test_key_never_appears_in_result(self) -> None:
        fake_key = "AIzaSyFAKE_SECRET_KEY_VALUE_12345"
        client = _json_client({"verdict": "unclear", "clause_id": None, "confidence": 0.1})
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

    # -- coordinator-requested additions ---------------------------------
    def test_default_model_is_a_flash_lite_id_not_2_5_flash(self) -> None:
        # free tier: full "flash" models cap ~20 req/day/project; flash-lite
        # has much higher limits. Never default to gemini-2.5-flash.
        self.assertNotEqual(claim_check.DEFAULT_MODEL, "gemini-2.5-flash")
        self.assertIn("flash-lite", claim_check.DEFAULT_MODEL)

    def test_429_and_404_become_unclear_no_raise(self) -> None:
        for msg in ("429 quota exceeded", "404 model not found"):
            client = _raising_client(RuntimeError(msg))
            out = claim_check.check_claim("x", CLAUSES, client=client)
            self.assertEqual(out["verdict"], "unclear")
            self.assertIsNotNone(out["error"])

    def test_call_stats_increment_on_calls_and_errors(self) -> None:
        before = claim_check.get_call_stats()
        client_ok = _json_client({"verdict": "consistent", "clause_id": "3.1", "confidence": 0.9})
        claim_check.check_claim("x", CLAUSES, client=client_ok)
        client_err = _raising_client(RuntimeError("boom"))
        claim_check.check_claim("x", CLAUSES, client=client_err)
        after = claim_check.get_call_stats()
        self.assertEqual(after["calls"], before["calls"] + 2)
        self.assertEqual(after["errors"], before["errors"] + 1)

    def test_get_claim_checker_gating(self) -> None:
        old_flag = os.environ.pop("CLAUSECATCHER_CLAIM_CHECK", None)
        old_key = os.environ.pop("GEMINI_API_KEY", None)
        try:
            self.assertIs(claim_check.get_claim_checker(), claim_check._stub_claim_checker)
            os.environ["CLAUSECATCHER_CLAIM_CHECK"] = "gemini"
            self.assertIs(claim_check.get_claim_checker(), claim_check._stub_claim_checker)  # no key yet
            os.environ["GEMINI_API_KEY"] = "fake-for-test-only"
            self.assertIs(claim_check.get_claim_checker(), claim_check.check_claim)
        finally:
            if old_flag is None:
                os.environ.pop("CLAUSECATCHER_CLAIM_CHECK", None)
            else:
                os.environ["CLAUSECATCHER_CLAIM_CHECK"] = old_flag
            if old_key is None:
                os.environ.pop("GEMINI_API_KEY", None)
            else:
                os.environ["GEMINI_API_KEY"] = old_key


if __name__ == "__main__":
    unittest.main()
