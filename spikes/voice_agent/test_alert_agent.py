"""
Tests for alert_agent.AlertAgent against LOCAL mock websocket servers on
127.0.0.1. ZERO calls to the real AssemblyAI API -- the real key is popped
from the environment before alert_agent (and its reused spike_voice_agent
module) is even loaded, and token_fetch is always a stub/dummy in every
test, plus a defensive urlopen trap so a forgotten stub fails loud instead
of silently phoning home.

Run:
    env -u ASSEMBLYAI_API_KEY python -m unittest test_alert_agent -v
"""
import asyncio
import importlib.util
import json
import os
import tempfile
import unittest
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

os.environ.pop("ASSEMBLYAI_API_KEY", None)

import websockets  # noqa: E402 -- after the env pop, per instructions

HERE = Path(__file__).resolve().parent
ALERT_AGENT_PATH = HERE / "alert_agent.py"

_spec = importlib.util.spec_from_file_location("alert_agent_under_test", ALERT_AGENT_PATH)
alert_agent_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(alert_agent_mod)
AlertAgent = alert_agent_mod.AlertAgent

CLAUSES = [
    {"id": "4.2", "text": "Auto-renews 12 months unless written notice 60 days before term ends."},
    {"id": "5.3", "text": "30-day recoverable archive then permanent deletion."},
]

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


def make_wav(rate: int = 24000, channels: int = 1, width: int = 2) -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    f.close()
    p = Path(f.name)
    with wave.open(str(p), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(b"\x00" * width * channels * int(0.1 * rate))
    return p


def make_tiny_wav() -> Path:
    return make_wav()


class AsyncMockedNetworkTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        block_real_network(self)


def fast_agent(ws_url: str, clauses=CLAUSES) -> AlertAgent:
    """AlertAgent wired to the local mock server with a dummy token_fetch --
    never touches urllib/real network."""
    return AlertAgent(
        DUMMY_KEY, clauses,
        ws_url=ws_url, token_fetch=lambda api_key: "dummy-token",
    )


# --- open(): session.ready gate --------------------------------------------

class TestOpen(AsyncMockedNetworkTestCase):
    async def test_open_waits_for_session_ready_not_session_updated(self):
        ready_sent_at = {}

        async def handler(ws):
            raw = await ws.recv()
            msg = json.loads(raw)
            assert msg["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.updated"}))
            await asyncio.sleep(0.2)
            ready_sent_at["sent"] = True
            await ws.send(json.dumps({"type": "session.ready"}))
            await asyncio.sleep(0.3)  # stay open long enough for close() to round-trip

        async with mock_ws_server(handler) as ws_url:
            agent = fast_agent(ws_url)
            info = await asyncio.wait_for(agent.open(), timeout=5)
            await agent.close()

        self.assertIn("sent", ready_sent_at)
        self.assertIn("connect_ms", info)
        self.assertIn("ready_ms", info)
        self.assertGreaterEqual(info["ready_ms"], info["connect_ms"])

    async def test_session_error_before_ready_raises_setup_error(self):
        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.error", "code": "internal_error", "message": "boom"}))
            await asyncio.sleep(0.2)

        async with mock_ws_server(handler) as ws_url:
            agent = fast_agent(ws_url)
            with self.assertRaises(alert_agent_mod._sva.SessionSetupError):
                await asyncio.wait_for(agent.open(), timeout=5)
            await agent.close()  # must not raise even though open() never finished

    async def test_no_session_ready_times_out(self):
        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            try:
                await asyncio.wait_for(ws.wait_closed(), timeout=5)
            except asyncio.TimeoutError:
                pass

        async with mock_ws_server(handler) as ws_url:
            agent = fast_agent(ws_url)
            with patch.object(alert_agent_mod, "SESSION_READY_TIMEOUT_S", 1):
                with self.assertRaises(alert_agent_mod._sva.SessionSetupTimeout):
                    await asyncio.wait_for(agent.open(), timeout=5)
            await agent.close()


# --- speak() ----------------------------------------------------------------

class TestSpeak(AsyncMockedNetworkTestCase):
    async def test_speak_sends_message_then_reply_create_and_measures_first_audio(self):
        received_types = []

        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            async for raw in ws:
                m = json.loads(raw)
                received_types.append(m["type"])
                if m["type"] == "conversation.message":
                    self.assertEqual(m["role"], "user")
                    self.assertIn("clause 4.2", m["content"])
                elif m["type"] == "reply.create":
                    await ws.send(json.dumps({"type": "reply.started"}))
                    await ws.send(json.dumps({"type": "reply.audio", "data": "AAAA"}))
                    await ws.send(json.dumps({"type": "reply.audio", "data": "BBBB"}))
                    await ws.send(json.dumps({"type": "transcript.agent", "text": "Compliance alert: clause 4.2."}))
                    await ws.send(json.dumps({"type": "reply.done"}))
                elif m["type"] == "session.end":
                    break

        async with mock_ws_server(handler) as ws_url:
            agent = fast_agent(ws_url)
            await agent.open()
            result = await asyncio.wait_for(
                agent.speak("Compliance alert: clause 4.2. Auto-renews unless notice given."),
                timeout=5,
            )
            await agent.close()

        self.assertEqual(received_types[:2], ["conversation.message", "reply.create"])
        self.assertEqual(result["role"], "user")
        self.assertIsNotNone(result["inject_ms"])
        self.assertIsNotNone(result["first_audio_ms"])
        self.assertIsNotNone(result["done_ms"])
        self.assertGreaterEqual(result["done_ms"], result["first_audio_ms"])
        self.assertGreaterEqual(result["first_audio_ms"], result["inject_ms"])
        self.assertEqual(result["audio_chunks"], 2)
        self.assertEqual(result["agent_transcript"], "Compliance alert: clause 4.2.")
        self.assertEqual(result["errors"], [])
        # transcript ("...clause 4.2.") is shorter than the injected text
        # ("...clause 4.2. Auto-renews...") -- not a verbatim echo -> False.
        self.assertFalse(result["literal_spoken"])

    async def test_speak_literal_spoken_true_when_transcript_echoes_verbatim(self):
        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            async for raw in ws:
                m = json.loads(raw)
                if m["type"] == "reply.create":
                    await ws.send(json.dumps({"type": "reply.audio", "data": "AAAA"}))
                    # punctuation/case/whitespace differ from the injected
                    # text but normalize equal -- still counts as verbatim.
                    await ws.send(json.dumps({
                        "type": "transcript.agent",
                        "text": "Contract  alert: Section 3.1 says NO automatic or verbal discounting!",
                    }))
                    await ws.send(json.dumps({"type": "reply.done"}))
                elif m["type"] == "session.end":
                    break

        async with mock_ws_server(handler) as ws_url:
            agent = fast_agent(ws_url)
            await agent.open()
            result = await asyncio.wait_for(
                agent.speak("Contract alert: section 3.1 says: no automatic or verbal discounting."),
                timeout=5,
            )
            await agent.close()

        self.assertTrue(result["literal_spoken"])

    async def test_alert_role_configurable_via_constructor(self):
        seen_role = {}

        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            async for raw in ws:
                m = json.loads(raw)
                if m["type"] == "conversation.message":
                    seen_role["role"] = m["role"]
                elif m["type"] == "reply.create":
                    await ws.send(json.dumps({"type": "reply.done"}))
                elif m["type"] == "session.end":
                    break

        async with mock_ws_server(handler) as ws_url:
            agent = AlertAgent(
                DUMMY_KEY, CLAUSES, ws_url=ws_url,
                token_fetch=lambda api_key: "dummy-token", alert_role="system",
            )
            await agent.open()
            result = await asyncio.wait_for(agent.speak("alert text"), timeout=5)
            await agent.close()

        self.assertEqual(seen_role["role"], "system")
        self.assertEqual(result["role"], "system")


# --- ask() --------------------------------------------------------------

class TestAsk(AsyncMockedNetworkTestCase):
    async def test_ask_tool_call_known_clause_sends_literal_text(self):
        sent_tool_results = []

        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            async for raw in ws:
                m = json.loads(raw)
                if m["type"] == "reply.create":
                    await ws.send(json.dumps({
                        "type": "tool.call", "call_id": "call_1", "name": "lookup_clause",
                        "arguments": {"section_number": "4.2"},
                    }))
                elif m["type"] == "tool.result":
                    sent_tool_results.append(m)
                    await ws.send(json.dumps({"type": "reply.audio", "data": "AAAA"}))
                    await ws.send(json.dumps({"type": "transcript.agent", "text": CLAUSES[0]["text"]}))
                    await ws.send(json.dumps({"type": "reply.done"}))
                elif m["type"] == "session.end":
                    break

        async with mock_ws_server(handler) as ws_url:
            agent = fast_agent(ws_url)
            await agent.open()
            result = await asyncio.wait_for(agent.ask(question_text="What does clause 4.2 say?"), timeout=5)
            await agent.close()

        self.assertTrue(result["tool_called"])
        self.assertEqual(result["tool_args"], {"section_number": "4.2"})
        self.assertTrue(result["tool_result_sent"])
        self.assertIsNotNone(result["first_audio_ms"])
        self.assertEqual(len(sent_tool_results), 1)
        self.assertEqual(sent_tool_results[0]["result"], CLAUSES[0]["text"])
        self.assertFalse(sent_tool_results[0]["is_error"])
        # transcript.agent echoed the clause text verbatim -> True.
        self.assertTrue(result["literal_spoken"])

    async def test_ask_tool_call_unknown_clause_answers_no_such_clause(self):
        sent_tool_results = []

        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            async for raw in ws:
                m = json.loads(raw)
                if m["type"] == "reply.create":
                    await ws.send(json.dumps({
                        "type": "tool.call", "call_id": "call_2", "name": "lookup_clause",
                        "arguments": {"section_number": "99.9"},
                    }))
                elif m["type"] == "tool.result":
                    sent_tool_results.append(m)
                    await ws.send(json.dumps({"type": "reply.done"}))
                elif m["type"] == "session.end":
                    break

        async with mock_ws_server(handler) as ws_url:
            agent = fast_agent(ws_url)
            await agent.open()
            result = await asyncio.wait_for(agent.ask(question_text="What does clause 99.9 say?"), timeout=5)
            await agent.close()

        self.assertTrue(result["tool_called"])
        self.assertEqual(sent_tool_results[0]["result"], "No such clause")
        # agent never echoed "no such clause" back (no transcript.agent sent) -> False.
        self.assertFalse(result["literal_spoken"])

    async def test_ask_with_neither_arg_records_error_without_network(self):
        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            await asyncio.sleep(0.2)

        async with mock_ws_server(handler) as ws_url:
            agent = fast_agent(ws_url)
            await agent.open()
            result = await asyncio.wait_for(agent.ask(), timeout=5)
            await agent.close()

        self.assertFalse(result["tool_called"])
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("needs question_text or question_wav", result["errors"][0])

    async def test_ask_wav_wrong_sample_rate_refuses_with_no_network(self):
        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            # No further messages should ever arrive -- ask() must refuse
            # locally before sending anything else.
            await asyncio.sleep(0.3)

        bad_wav = make_wav(rate=16000)
        try:
            async with mock_ws_server(handler) as ws_url:
                agent = fast_agent(ws_url)
                await agent.open()
                result = await asyncio.wait_for(agent.ask(question_wav=str(bad_wav)), timeout=5)
                await agent.close()
        finally:
            bad_wav.unlink(missing_ok=True)

        self.assertFalse(result["tool_called"])
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("24000Hz mono 16-bit", result["errors"][0])
        self.assertIn("16000Hz", result["errors"][0])

    async def test_ask_wav_wrong_channels_refuses_with_no_network(self):
        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            await asyncio.sleep(0.3)

        bad_wav = make_wav(channels=2)
        try:
            async with mock_ws_server(handler) as ws_url:
                agent = fast_agent(ws_url)
                await agent.open()
                result = await asyncio.wait_for(agent.ask(question_wav=str(bad_wav)), timeout=5)
                await agent.close()
        finally:
            bad_wav.unlink(missing_ok=True)

        self.assertFalse(result["tool_called"])
        self.assertEqual(len(result["errors"]), 1)
        self.assertIn("2ch", result["errors"][0])


# --- errors / abrupt close never crash --------------------------------------

class TestAbruptCloseAndErrors(AsyncMockedNetworkTestCase):
    async def test_session_error_mid_reply_is_recorded_not_raised(self):
        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            async for raw in ws:
                m = json.loads(raw)
                if m["type"] == "reply.create":
                    await ws.send(json.dumps({"type": "session.error", "code": "internal_error", "message": "mid-reply boom"}))
                elif m["type"] == "session.end":
                    break

        async with mock_ws_server(handler) as ws_url:
            agent = fast_agent(ws_url)
            await agent.open()
            with patch.object(alert_agent_mod, "REPLY_TIMEOUT_S", 2):
                result = await asyncio.wait_for(agent.speak("alert text"), timeout=5)
            await agent.close()

        self.assertEqual(len(result["errors"]), 1)
        self.assertEqual(result["errors"][0]["code"], "internal_error")

    async def test_peer_closes_socket_immediately_after_ready_no_crash(self):
        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            # then just close -- no further messages, no session.end handling needed

        async with mock_ws_server(handler) as ws_url:
            agent = fast_agent(ws_url)
            await agent.open()
            await asyncio.sleep(0.2)  # let the server-side close land
            with patch.object(alert_agent_mod, "REPLY_TIMEOUT_S", 2):
                result = await asyncio.wait_for(agent.speak("alert text"), timeout=5)
            await asyncio.wait_for(agent.close(), timeout=5)  # must not hang or raise

        # Either the send itself failed (recorded in errors) or it succeeded
        # and the reply simply never arrived (all fields stay at defaults) --
        # both are "no crash", which is what this test guards.
        self.assertIsInstance(result["errors"], list)

    async def test_close_is_idempotent(self):
        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            await asyncio.sleep(0.3)

        async with mock_ws_server(handler) as ws_url:
            agent = fast_agent(ws_url)
            await agent.open()
            await agent.close()
            await agent.close()  # second call must be a no-op, not raise


# --- API key hygiene ----------------------------------------------------

class TestKeyNeverInResults(AsyncMockedNetworkTestCase):
    async def test_api_key_string_never_appears_in_any_result_dict(self):
        async def handler(ws):
            raw = await ws.recv()
            assert json.loads(raw)["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            async for raw in ws:
                m = json.loads(raw)
                if m["type"] == "reply.create":
                    await ws.send(json.dumps({"type": "reply.audio", "data": "AAAA"}))
                    await ws.send(json.dumps({"type": "reply.done"}))
                elif m["type"] == "session.end":
                    break

        secret_key = "sk-super-secret-value-must-never-leak-12345"

        async with mock_ws_server(handler) as ws_url:
            agent = AlertAgent(secret_key, CLAUSES, ws_url=ws_url, token_fetch=lambda k: "dummy-token")
            open_info = await agent.open()
            speak_result = await asyncio.wait_for(agent.speak("alert"), timeout=5)
            await agent.close()

        blob = json.dumps({"open": open_info, "speak": speak_result, "cost": agent.est_cost_usd}, default=str)
        self.assertNotIn(secret_key, blob)


if __name__ == "__main__":
    unittest.main()
