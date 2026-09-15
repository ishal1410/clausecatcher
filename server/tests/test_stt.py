"""Tests for server/stt.py. unittest (IsolatedAsyncioTestCase) + a local
websockets.serve() mock server -- no real network, no AssemblyAI calls.
ASSEMBLYAI_API_KEY must be unset when running these (asserted in setUp so a
stray env var can never sneak a real call through)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import unittest
import urllib.parse
from pathlib import Path

import websockets

from server import stt

assert os.environ.get("ASSEMBLYAI_API_KEY") is None, (
    "ASSEMBLYAI_API_KEY must be unset to run server/tests/test_stt.py (mocks only, never real AssemblyAI)"
)

FAKE_CONTRACT_JSON = Path(__file__).resolve().parents[2] / "spikes" / "harness" / "fake_contract.json"
FAKE_API_KEY = "sk-test-secret-should-never-be-logged"


class _MockServer:
    """Local websocket server. `script` is a list of actions run in order right
    after a client connects: ("send", dict_or_bytes) or ("sleep", seconds).
    After the script runs, it drains incoming frames (recording binary frames
    and text messages) until the client disconnects or sends Terminate."""

    def __init__(self, script: list[tuple] | None = None):
        self.script = script or []
        self.request_path: str | None = None
        self.request_headers = None
        self.binary_received: list[bytes] = []
        self.text_received: list[dict] = []

    async def _handler(self, ws) -> None:
        self.request_path = ws.request.path
        self.request_headers = ws.request.headers
        for kind, payload in self.script:
            if kind == "send":
                await ws.send(payload if isinstance(payload, (bytes, bytearray)) else json.dumps(payload))
            elif kind == "sleep":
                await asyncio.sleep(payload)
        try:
            async for raw in ws:
                if isinstance(raw, (bytes, bytearray)):
                    self.binary_received.append(bytes(raw))
                else:
                    msg = json.loads(raw)
                    self.text_received.append(msg)
                    if msg.get("type") == "Terminate":
                        return
        except websockets.exceptions.ConnectionClosed:
            pass

    async def __aenter__(self) -> "_MockServer":
        self._server = await websockets.serve(self._handler, "127.0.0.1", 0)
        port = self._server.sockets[0].getsockname()[1]
        self.url = f"ws://127.0.0.1:{port}"
        return self

    async def __aexit__(self, *exc_info) -> None:
        self._server.close()
        await self._server.wait_closed()


BEGIN = {"type": "Begin", "id": "sess_test", "expires_at": 0}


class StreamingTranscriberTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self._orig_begin_timeout = stt.BEGIN_TIMEOUT_S
        self._orig_connect_timeout = stt.CONNECT_TIMEOUT_S

    def tearDown(self) -> None:
        stt.BEGIN_TIMEOUT_S = self._orig_begin_timeout
        stt.CONNECT_TIMEOUT_S = self._orig_connect_timeout

    async def test_start_waits_for_begin(self) -> None:
        async with _MockServer([("send", BEGIN)]) as server:
            transcriber = stt.StreamingTranscriber(
                FAKE_API_KEY, on_turn=_noop_on_turn, ws_url=server.url
            )
            await transcriber.start()
            self.assertIsNotNone(transcriber._ws)
            await transcriber.stop()

    async def test_setup_failure_connection_refused(self) -> None:
        # Nothing listens on this port -> connection refused.
        transcriber = stt.StreamingTranscriber(
            FAKE_API_KEY, on_turn=_noop_on_turn, ws_url="ws://127.0.0.1:1"
        )
        with self.assertRaises(stt.SttSetupError):
            await transcriber.start()

    async def test_setup_failure_no_begin(self) -> None:
        stt.BEGIN_TIMEOUT_S = 0.3
        async with _MockServer([("sleep", 1.0)]) as server:  # never sends Begin in time
            transcriber = stt.StreamingTranscriber(
                FAKE_API_KEY, on_turn=_noop_on_turn, ws_url=server.url
            )
            with self.assertRaises(stt.SttSetupError):
                await transcriber.start()

    async def test_setup_failure_wrong_first_message(self) -> None:
        async with _MockServer([("send", {"type": "Termination"})]) as server:
            transcriber = stt.StreamingTranscriber(
                FAKE_API_KEY, on_turn=_noop_on_turn, ws_url=server.url
            )
            with self.assertRaises(stt.SttSetupError):
                await transcriber.start()

    async def test_query_string_and_auth_header(self) -> None:
        keyterms = ["50 seats", "60 days"]
        async with _MockServer([("send", BEGIN)]) as server:
            transcriber = stt.StreamingTranscriber(
                FAKE_API_KEY,
                on_turn=_noop_on_turn,
                keyterms=keyterms,
                sample_rate=16000,
                ws_url=server.url,
            )
            await transcriber.start()
            await transcriber.stop()

        self.assertEqual(server.request_headers.get("Authorization"), FAKE_API_KEY)
        query = urllib.parse.parse_qs(server.request_path.split("?", 1)[1])
        self.assertEqual(query["sample_rate"], ["16000"])
        self.assertEqual(query["encoding"], ["pcm_s16le"])
        self.assertEqual(query["speech_model"], [stt.DEFAULT_SPEECH_MODEL])
        self.assertEqual(json.loads(query["keyterms_prompt"][0]), keyterms)

    async def test_audio_forwarded_in_order(self) -> None:
        async with _MockServer([("send", BEGIN)]) as server:
            transcriber = stt.StreamingTranscriber(
                FAKE_API_KEY, on_turn=_noop_on_turn, ws_url=server.url
            )
            await transcriber.start()
            chunks = [b"\x01\x02", b"\x03\x04", b"\x05\x06\x07\x08"]
            for chunk in chunks:
                await transcriber.send_audio(chunk)
            await transcriber.stop()
            await asyncio.sleep(0.05)  # let the server task drain what was already sent

        self.assertEqual(server.binary_received, chunks)

    async def test_send_audio_buffers_odd_byte(self) -> None:
        async with _MockServer([("send", BEGIN)]) as server:
            transcriber = stt.StreamingTranscriber(
                FAKE_API_KEY, on_turn=_noop_on_turn, ws_url=server.url
            )
            await transcriber.start()
            await transcriber.send_audio(b"\x01\x02\x03")  # odd -> \x03 buffered
            await transcriber.send_audio(b"\x04\x05")  # \x03 prepended -> \x03\x04\x05, \x05 buffered
            await transcriber.send_audio(b"")  # no-op, must not touch the buffer
            await transcriber.send_audio(b"\x06")  # \x05 prepended -> \x05\x06
            await transcriber.stop()
            await asyncio.sleep(0.05)

        self.assertEqual(server.binary_received, [b"\x01\x02", b"\x03\x04", b"\x05\x06"])

    async def test_turn_partial_and_final(self) -> None:
        calls: list[tuple[str, bool]] = []

        async def on_turn(text: str, end_of_turn: bool) -> None:
            calls.append((text, end_of_turn))

        script = [
            ("send", BEGIN),
            ("send", {"type": "Turn", "end_of_turn": False, "transcript": "hello"}),
            ("send", {"type": "Turn", "end_of_turn": False, "transcript": "hello"}),  # unchanged -> throttled
            ("send", {"type": "Turn", "end_of_turn": False, "transcript": "hello there"}),
            ("send", {"type": "Turn", "end_of_turn": True, "transcript": "hello there."}),
        ]
        async with _MockServer(script) as server:
            transcriber = stt.StreamingTranscriber(FAKE_API_KEY, on_turn=on_turn, ws_url=server.url)
            await transcriber.start()
            await asyncio.sleep(0.2)
            await transcriber.stop()

        self.assertEqual(
            calls,
            [("hello", False), ("hello there", False), ("hello there.", True)],
        )
        self.assertEqual(transcriber.stats["turns"], 1)
        self.assertEqual(transcriber.stats["partials"], 2)

    async def test_on_turn_raising_does_not_stop_later_turns(self) -> None:
        calls: list[tuple[str, bool]] = []

        async def flaky_on_turn(text: str, end_of_turn: bool) -> None:
            if len(calls) == 0:
                calls.append((text, end_of_turn))
                raise RuntimeError("boom")
            calls.append((text, end_of_turn))

        script = [
            ("send", BEGIN),
            ("send", {"type": "Turn", "end_of_turn": True, "transcript": "first"}),
            ("send", {"type": "Turn", "end_of_turn": True, "transcript": "second"}),
        ]
        async with _MockServer(script) as server:
            transcriber = stt.StreamingTranscriber(FAKE_API_KEY, on_turn=flaky_on_turn, ws_url=server.url)
            with self.assertLogs(stt.logger, level="ERROR") as log_ctx:
                await transcriber.start()
                await asyncio.sleep(0.2)
                await transcriber.stop()

        self.assertEqual(calls, [("first", True), ("second", True)])
        log_text = "\n".join(log_ctx.output)
        self.assertIn("boom", log_text)
        self.assertNotIn(FAKE_API_KEY, log_text)

    async def test_stop_sends_terminate_and_is_idempotent(self) -> None:
        async with _MockServer([("send", BEGIN)]) as server:
            transcriber = stt.StreamingTranscriber(FAKE_API_KEY, on_turn=_noop_on_turn, ws_url=server.url)
            await transcriber.start()
            await transcriber.stop()
            await transcriber.stop()  # idempotent: must not raise or resend
            await asyncio.sleep(0.05)

        terminate_msgs = [m for m in server.text_received if m.get("type") == "Terminate"]
        self.assertEqual(len(terminate_msgs), 1)

    async def test_send_audio_backpressure_times_out_and_counts_drop(self) -> None:
        async with _MockServer([("send", BEGIN)]) as server:
            transcriber = stt.StreamingTranscriber(FAKE_API_KEY, on_turn=_noop_on_turn, ws_url=server.url)
            await transcriber.start()

            async def hang_forever(*_args, **_kwargs):
                await asyncio.Event().wait()

            transcriber._ws.send = hang_forever  # simulate a peer that never reads

            start = asyncio.get_running_loop().time()
            await transcriber.send_audio(b"\x01\x02")
            elapsed = asyncio.get_running_loop().time() - start

            await transcriber.stop()

        self.assertLess(elapsed, stt.SEND_TIMEOUT_S + 0.5)
        self.assertEqual(transcriber.stats["chunks_dropped"], 1)
        self.assertEqual(transcriber.stats["bytes_sent"], 0)

    async def test_no_api_key_in_logs_on_setup_failure(self) -> None:
        with self.assertLogs(level="DEBUG") as log_ctx:
            logging.getLogger("clausecatcher.stt").debug("marker so assertLogs has at least one record")
            transcriber = stt.StreamingTranscriber(
                FAKE_API_KEY, on_turn=_noop_on_turn, ws_url="ws://127.0.0.1:1"
            )
            with self.assertRaises(stt.SttSetupError) as err_ctx:
                await transcriber.start()
        self.assertNotIn(FAKE_API_KEY, "\n".join(log_ctx.output))
        self.assertNotIn(FAKE_API_KEY, str(err_ctx.exception))


async def _noop_on_turn(text: str, end_of_turn: bool) -> None:
    return None


class KeytermsFromClausesTest(unittest.TestCase):
    def setUp(self) -> None:
        data = json.loads(FAKE_CONTRACT_JSON.read_text(encoding="utf-8"))
        self.clauses = data["clauses"]

    def test_bounds(self) -> None:
        terms = stt.keyterms_from_clauses(self.clauses)
        self.assertLessEqual(len(terms), 100)
        for term in terms:
            self.assertLessEqual(len(term), 50)

    def test_contains_expected_terms(self) -> None:
        terms = stt.keyterms_from_clauses(self.clauses)
        for expected in ("50 seats", "60 days", "24/7", "Premium Support Addendum"):
            self.assertIn(expected, terms, terms)

    def test_contains_titles(self) -> None:
        terms = stt.keyterms_from_clauses(self.clauses)
        self.assertIn("Pricing & Seat Cap", terms)

    def test_dedupes(self) -> None:
        terms = stt.keyterms_from_clauses(self.clauses + self.clauses)  # duplicated input
        self.assertEqual(len(terms), len(set(t.lower() for t in terms)))

    def test_empty_input(self) -> None:
        self.assertEqual(stt.keyterms_from_clauses([]), [])


if __name__ == "__main__":
    unittest.main()
