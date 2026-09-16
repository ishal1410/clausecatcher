"""Security regressions for server.voice: socket leak on failed open(),
blocking token fetch, prompt-injection guards in say_exactly, token-in-URL
leakage in error text. All network is a local 127.0.0.1 fake."""
import asyncio
import json
import os
import threading
import unittest
from unittest.mock import patch

os.environ.pop("ASSEMBLYAI_API_KEY", None)

from server import voice  # noqa: E402
from server.tests.test_voice import AsyncMockedNetworkTestCase, fast_speaker, mock_ws_server  # noqa: E402
from server.voice import AlertSpeaker, VoiceSetupError  # noqa: E402
from websockets.protocol import State  # noqa: E402


def _server_records_close(closed: dict, after_update):
    async def handler(ws):
        raw = await ws.recv()
        assert json.loads(raw)["type"] == "session.update"
        await after_update(ws)
        try:
            await asyncio.wait_for(ws.wait_closed(), timeout=3)
            closed["closed"] = True
        except asyncio.TimeoutError:
            closed["closed"] = False
    return handler


class TestOpenFailureClosesSocket(AsyncMockedNetworkTestCase):
    async def test_ready_timeout_closes_upstream_socket(self):
        closed = {}

        async def never_ready(ws):
            await ws.send(json.dumps({"type": "session.updated"}))

        async with mock_ws_server(_server_records_close(closed, never_ready)) as ws_url:
            with patch.object(voice, "SESSION_READY_TIMEOUT_S", 0.3):
                speaker = fast_speaker(ws_url)
                with self.assertRaises(VoiceSetupError):
                    await asyncio.wait_for(speaker.open(), timeout=5)
            await asyncio.sleep(0.5)
        self.assertTrue(closed.get("closed"), "server never saw the socket closed")
        self.assertFalse(speaker.is_open)
        self.assertIs(speaker.ws.state, State.CLOSED)

    async def test_session_error_closes_upstream_socket(self):
        closed = {}

        async def send_error(ws):
            await ws.send(json.dumps({"type": "session.error", "code": "x", "message": "boom"}))

        async with mock_ws_server(_server_records_close(closed, send_error)) as ws_url:
            speaker = fast_speaker(ws_url)
            with self.assertRaises(VoiceSetupError):
                await asyncio.wait_for(speaker.open(), timeout=5)
            await asyncio.sleep(0.5)
        self.assertTrue(closed.get("closed"), "server never saw the socket closed")
        self.assertFalse(speaker.is_open)
        self.assertIs(speaker.ws.state, State.CLOSED)


class TestTokenFetchOffLoop(AsyncMockedNetworkTestCase):
    async def test_token_fetch_runs_in_worker_thread(self):
        seen = {}

        def fetch(api_key):
            seen["thread"] = threading.get_ident()
            raise RuntimeError("stop here")

        speaker = AlertSpeaker("k", on_audio=lambda p, r: asyncio.sleep(0), token_fetch=fetch)
        with self.assertRaises(VoiceSetupError):
            await speaker.open()
        self.assertNotEqual(seen["thread"], threading.get_ident())


class TestErrorTextHasNoToken(AsyncMockedNetworkTestCase):
    async def test_connect_error_does_not_echo_url_token(self):
        def boom(url, **kw):
            raise OSError(f"cannot reach {url}")

        speaker = AlertSpeaker("k", on_audio=lambda p, r: asyncio.sleep(0),
                               ws_url="ws://127.0.0.1:1", token_fetch=lambda k: "SECRETTOKEN123")
        with patch.object(voice.websockets, "connect", side_effect=boom):
            with self.assertRaises(VoiceSetupError) as cm:
                await speaker.open()
        self.assertNotIn("SECRETTOKEN123", str(cm.exception))
        self.assertIn("OSError", str(cm.exception))


class TestSanitizeSpoken(unittest.TestCase):
    def test_strips_control_zero_width_bidi_and_tag_chars(self):
        dirty = "Pay\x00 now\u200b\u202eevil\u2062\ufeff \U000E0041tag\x7f\n\tend"
        out = voice.sanitize_spoken_text(dirty)
        for bad in ("\x00", "\u200b", "\u202e", "\u2062", "\ufeff", "\U000E0041", "\x7f", "\n", "\t"):
            self.assertNotIn(bad, out)
        self.assertEqual(out, "Pay now evil tag end")

    def test_caps_at_word_boundary_with_ellipsis(self):
        text = ("word " * 300).strip()
        out = voice.sanitize_spoken_text(text)
        self.assertLessEqual(len(out), voice.MAX_SPOKEN_CHARS + 1)
        self.assertTrue(out.endswith("\u2026"))
        self.assertTrue(out[:-1].endswith("word"))

    def test_short_text_unchanged(self):
        self.assertEqual(voice.sanitize_spoken_text("Auto-renews yearly."), "Auto-renews yearly.")


class TestSayExactlySanitizes(AsyncMockedNetworkTestCase):
    async def test_sent_instruction_and_grading_use_sanitized_text(self):
        sent = []
        spoken = "Pay now evil"

        async def handler(ws):
            await ws.recv()
            await ws.send(json.dumps({"type": "session.ready"}))
            sent.append(json.loads(await ws.recv()))
            await ws.send(json.dumps({"type": "transcript.agent", "text": spoken}))
            await ws.send(json.dumps({"type": "reply.done"}))
            await asyncio.sleep(0.2)

        async with mock_ws_server(handler) as ws_url:
            speaker = fast_speaker(ws_url)
            await speaker.open()
            result = await speaker.say_exactly("Pay\u200b now\u202e evil\x00")
            await speaker.close()

        instr = sent[0]["instructions"]
        self.assertEqual(instr, voice._SAY_EXACTLY_PREFIX + "Pay now evil")
        self.assertNotIn("\u202e", instr)
        self.assertEqual(result["text"], "Pay now evil")
        self.assertTrue(result["literal_spoken"])


if __name__ == "__main__":
    unittest.main()
