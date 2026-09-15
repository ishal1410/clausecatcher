"""Tests for server.voice.AlertSpeaker against LOCAL mock websocket servers
on 127.0.0.1. ZERO calls to the real AssemblyAI API -- the real key is
popped from the environment before server.voice is even imported, and
token_fetch is always a stub in every test, plus a defensive urlopen trap
so a forgotten stub fails loud instead of silently phoning home.

Run:
    python -m unittest server.tests.test_voice -v
(from the repo root, with ASSEMBLYAI_API_KEY unset)
"""
import asyncio
import base64
import json
import os
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

os.environ.pop("ASSEMBLYAI_API_KEY", None)

import websockets  # noqa: E402 -- after the env pop, per instructions

from server import voice  # noqa: E402
from server.voice import AlertSpeaker, VoiceSetupError, build_alert_text, build_clause_answer_text  # noqa: E402

DUMMY_KEY = "dummy-test-key-never-sent-anywhere-real"


def block_real_network(testcase: unittest.TestCase) -> None:
    testcase.enterContext(
        patch("urllib.request.urlopen", side_effect=AssertionError(
            "REAL NETWORK CALL ATTEMPTED IN TEST -- forgot to stub token_fetch"
        ))
    )


@asynccontextmanager
async def mock_ws_server(handler):
    server = await websockets.serve(handler, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        yield f"ws://127.0.0.1:{port}"
    finally:
        server.close()
        await asyncio.wait_for(server.wait_closed(), timeout=5)


def fast_speaker(ws_url: str, *, on_audio=None, on_event=None) -> AlertSpeaker:
    """AlertSpeaker wired to the local mock server with a dummy token_fetch
    -- never touches urllib/real network."""
    return AlertSpeaker(
        DUMMY_KEY,
        on_audio=on_audio or (lambda pcm, rate: asyncio.sleep(0)),
        on_event=on_event,
        ws_url=ws_url,
        token_fetch=lambda api_key: "dummy-token",
    )


async def _send_reply_audio(ws, chunks: list) -> None:
    for c in chunks:
        await ws.send(json.dumps({"type": "reply.audio", "data": base64.b64encode(c).decode("ascii")}))


class AsyncMockedNetworkTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        block_real_network(self)


# ---- open(): session.ready gate --------------------------------------------

class TestOpen(AsyncMockedNetworkTestCase):
    async def test_open_waits_for_session_ready_not_session_updated(self):
        ready_sent_at = {}

        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.updated"}))
            await asyncio.sleep(0.1)
            ready_sent_at["sent"] = True
            await ws.send(json.dumps({"type": "session.ready"}))
            await asyncio.sleep(0.3)  # stay open long enough for close() to round-trip

        async with mock_ws_server(handler) as ws_url:
            speaker = fast_speaker(ws_url)
            info = await asyncio.wait_for(speaker.open(), timeout=5)
            self.assertTrue(speaker.is_open)
            await speaker.close()

        self.assertIn("sent", ready_sent_at)
        self.assertIn("connect_ms", info)
        self.assertIn("ready_ms", info)
        self.assertGreaterEqual(info["ready_ms"], info["connect_ms"])

    async def test_session_error_before_ready_raises_voice_setup_error(self):
        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.error", "code": "internal_error", "message": "boom"}))
            await asyncio.sleep(0.2)

        async with mock_ws_server(handler) as ws_url:
            speaker = fast_speaker(ws_url)
            with self.assertRaises(VoiceSetupError):
                await asyncio.wait_for(speaker.open(), timeout=5)


# ---- say_exactly(): the verbatim-speak contract ----------------------------

class TestSayExactly(AsyncMockedNetworkTestCase):
    async def test_sends_exactly_one_reply_create_no_conversation_message(self):
        sent_messages = []

        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            raw = await ws.recv()
            msg = json.loads(raw)
            sent_messages.append(msg)
            assert msg["type"] == "reply.create"
            await ws.send(json.dumps({"type": "reply.done"}))
            await asyncio.sleep(0.2)

        async with mock_ws_server(handler) as ws_url:
            speaker = fast_speaker(ws_url)
            await speaker.open()
            result = await speaker.say_exactly("Hello world")
            await speaker.close()

        self.assertEqual(result["errors"], [])
        self.assertEqual(len(sent_messages), 1)
        self.assertEqual(
            sent_messages[0],
            {"type": "reply.create", "instructions": voice._SAY_EXACTLY_PREFIX + "Hello world"},
        )

    async def test_reply_audio_chunks_forwarded_in_order_at_24000(self):
        chunks = [b"AAAA", b"BBBB", b"CCCC"]
        forwarded = []

        async def on_audio(pcm, rate):
            forwarded.append((pcm, rate))

        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            await ws.recv()  # reply.create
            await _send_reply_audio(ws, chunks)
            await ws.send(json.dumps({"type": "reply.done"}))
            await asyncio.sleep(0.2)

        async with mock_ws_server(handler) as ws_url:
            speaker = fast_speaker(ws_url, on_audio=on_audio)
            await speaker.open()
            result = await speaker.say_exactly("stream me")
            await speaker.close()

        self.assertEqual(result["errors"], [])
        self.assertEqual(forwarded, [(c, 24000) for c in chunks])
        self.assertIsNotNone(result["first_audio_ms"])

    async def test_agent_speaking_start_and_end_events(self):
        events = []

        async def on_event(evt):
            events.append(evt)

        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            await ws.recv()  # reply.create
            await ws.send(json.dumps({"type": "reply.done"}))
            await asyncio.sleep(0.2)

        async with mock_ws_server(handler) as ws_url:
            speaker = fast_speaker(ws_url, on_event=on_event)
            await speaker.open()
            await speaker.say_exactly("hi")
            await speaker.close()

        speaking_events = [e for e in events if e["type"] == "agent_speaking"]
        self.assertEqual(len(speaking_events), 2)
        self.assertEqual(speaking_events[0]["state"], "start")
        self.assertEqual(speaking_events[1]["state"], "end")
        self.assertEqual(speaking_events[0]["text"], "hi")

    async def test_literal_spoken_true_and_similarity(self):
        text = "Contract alert: section 4.2 says: 60 days notice required."

        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            await ws.recv()  # reply.create
            await ws.send(json.dumps({"type": "transcript.agent", "text": text}))
            await ws.send(json.dumps({"type": "reply.done"}))
            await asyncio.sleep(0.2)

        async with mock_ws_server(handler) as ws_url:
            speaker = fast_speaker(ws_url)
            await speaker.open()
            result = await speaker.say_exactly(text)
            await speaker.close()

        self.assertTrue(result["literal_spoken"])
        self.assertEqual(result["similarity"], 1.0)

    async def test_literal_spoken_false_on_mismatch(self):
        text = "Contract alert: section 4.2 says: 60 days notice required."

        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            await ws.recv()  # reply.create
            await ws.send(json.dumps({"type": "transcript.agent", "text": "I cannot say that."}))
            await ws.send(json.dumps({"type": "reply.done"}))
            await asyncio.sleep(0.2)

        async with mock_ws_server(handler) as ws_url:
            speaker = fast_speaker(ws_url)
            await speaker.open()
            result = await speaker.say_exactly(text)
            await speaker.close()

        self.assertFalse(result["literal_spoken"])
        self.assertLess(result["similarity"], 1.0)

    async def test_concurrent_say_exactly_calls_do_not_interleave(self):
        received_order = []

        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            for _ in range(2):
                raw = await ws.recv()
                msg = json.loads(raw)
                assert msg["type"] == "reply.create"
                received_order.append(msg["instructions"])
                await asyncio.sleep(0.05)
                await ws.send(json.dumps({"type": "reply.audio", "data": base64.b64encode(b"X").decode()}))
                await ws.send(json.dumps({"type": "reply.done"}))
            await asyncio.sleep(0.2)

        async with mock_ws_server(handler) as ws_url:
            speaker = fast_speaker(ws_url)
            await speaker.open()
            r1, r2 = await asyncio.gather(
                speaker.say_exactly("first"), speaker.say_exactly("second")
            )
            await speaker.close()

        self.assertEqual(
            received_order,
            [voice._SAY_EXACTLY_PREFIX + "first", voice._SAY_EXACTLY_PREFIX + "second"],
        )
        self.assertEqual(r1["errors"], [])
        self.assertEqual(r2["errors"], [])

    async def test_timeout_waiting_for_reply_done_returns_error_no_raise(self):
        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            await ws.recv()  # reply.create, never answered
            await asyncio.sleep(2)

        async with mock_ws_server(handler) as ws_url:
            speaker = fast_speaker(ws_url)
            await speaker.open()
            with patch.object(voice, "REPLY_DONE_TIMEOUT_S", 0.3):
                result = await asyncio.wait_for(speaker.say_exactly("never answered"), timeout=5)
            await speaker.close()

        self.assertTrue(result["errors"])
        self.assertIn("timed out", result["errors"][0])

    async def test_abrupt_close_returns_error_no_raise(self):
        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            await ws.recv()  # reply.create
            await ws.close()

        async with mock_ws_server(handler) as ws_url:
            speaker = fast_speaker(ws_url)
            await speaker.open()
            result = await asyncio.wait_for(speaker.say_exactly("dropped"), timeout=5)
            await speaker.close()  # idempotent even though the socket is already gone

        self.assertTrue(result["errors"])


# ---- close() ----------------------------------------------------------------

class TestClose(AsyncMockedNetworkTestCase):
    async def test_close_is_idempotent(self):
        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            await asyncio.sleep(0.3)

        async with mock_ws_server(handler) as ws_url:
            speaker = fast_speaker(ws_url)
            await speaker.open()
            await speaker.close()
            await speaker.close()  # must not raise
            self.assertFalse(speaker.is_open)

    async def test_close_before_open_is_safe(self):
        speaker = fast_speaker("ws://127.0.0.1:1")
        await speaker.close()  # never opened -- must not raise
        self.assertFalse(speaker.is_open)

    async def test_session_cap_auto_closes(self):
        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            await asyncio.sleep(1)

        async with mock_ws_server(handler) as ws_url:
            with patch.object(voice, "SESSION_MAX_S", 0.2):
                speaker = fast_speaker(ws_url)
                await speaker.open()
                self.assertTrue(speaker.is_open)
                await asyncio.sleep(0.5)
                self.assertFalse(speaker.is_open)


# ---- api key never leaks into results ---------------------------------------

class TestKeyNeverLeaks(AsyncMockedNetworkTestCase):
    async def test_api_key_not_in_open_or_say_exactly_results(self):
        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            await ws.recv()  # reply.create
            await ws.send(json.dumps({"type": "reply.done"}))
            await asyncio.sleep(0.2)

        async with mock_ws_server(handler) as ws_url:
            speaker = fast_speaker(ws_url)
            open_info = await speaker.open()
            result = await speaker.say_exactly("hello")
            await speaker.close()

        self.assertNotIn(DUMMY_KEY, json.dumps(open_info))
        self.assertNotIn(DUMMY_KEY, json.dumps(result, default=str))
        self.assertNotIn(DUMMY_KEY, "dummy-token")  # sanity: token itself isn't the key


# ---- pure text-builder functions --------------------------------------------

class TestTextBuilders(unittest.TestCase):
    def test_build_alert_text_exact_string(self):
        clause = {"section_number": "4.2", "title": "Renewal", "literal_text": "Auto-renews yearly."}
        self.assertEqual(
            build_alert_text(clause),
            "Contract alert: section 4.2 says: Auto-renews yearly.",
        )

    def test_build_clause_answer_text_exact_string(self):
        clause = {"section_number": "5.3", "title": "Data Retention", "literal_text": "30-day recoverable archive."}
        self.assertEqual(
            build_clause_answer_text(clause),
            "Section 5.3, Data Retention: 30-day recoverable archive.",
        )


if __name__ == "__main__":
    unittest.main()
