"""
TDD tests for the session.ready gate in spike_voice_agent.py (SPEC, owner's
concurrent change): open_session must send session.update then loop recv
until session.ready -- ignoring session.updated, failing setup cleanly on
session.error, and timing out on SESSION_READY_TIMEOUT_S if session.ready
never arrives. NEVER send input.audio/conversation.message before
session.ready.

Everything here runs against LOCAL mock websocket servers on 127.0.0.1.
ZERO calls to the real AssemblyAI API. The real key is popped from the
environment before the spike module is even loaded, and get_token is
monkeypatched (plus a defensive urlopen trap) in every network-touching
test so a forgotten patch fails loud instead of silently phoning home.

Run (key MUST be unset in the shell so a forgotten patch can't leak a real
call):
    env -u ASSEMBLYAI_API_KEY python -m unittest test_session_ready -v
"""
import asyncio
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import wave
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

# Real key must never be visible to this process before (or during) import.
os.environ.pop("ASSEMBLYAI_API_KEY", None)

import websockets  # noqa: E402 -- after the env pop, per instructions
from websockets.sync.server import serve as sync_serve  # noqa: E402

HERE = Path(__file__).resolve().parent
SPIKE_PATH = HERE / "spike_voice_agent.py"
HARNESS_AUDIO_DIR = HERE.parent / "harness" / "audio"
REP_PITCH_WAV = HARNESS_AUDIO_DIR / "rep_pitch.wav"

# A short synthetic PCM16/mono/16kHz WAV for the mock-server Q2 tests below.
# Deliberately NOT the real (~23.5s) harness rep_pitch.wav: test_silence
# shares one `deadline` between stream_wav and the post-stream drain(), so a
# short clip lets stream_wav finish naturally (not get deadline-truncated)
# while still leaving budget for drain() to see the mock's reply -- avoids
# coupling this suite's runtime to the harness fixture's length.
_tiny_wav_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
_tiny_wav_file.close()
TINY_WAV_PATH = Path(_tiny_wav_file.name)
with wave.open(str(TINY_WAV_PATH), "wb") as _w:
    _w.setnchannels(1)
    _w.setsampwidth(2)
    _w.setframerate(16000)
    _w.writeframes(b"\x00\x00" * int(0.3 * 16000))  # 0.3s of silence

_spec = importlib.util.spec_from_file_location("spike_voice_agent_under_test", SPIKE_PATH)
spike = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(spike)


def block_real_network(testcase: unittest.TestCase) -> None:
    """Defensive backstop: any test that forgets to patch spike.get_token
    still can't reach the real network -- urlopen raises instead."""
    testcase.enterContext(
        patch("urllib.request.urlopen", side_effect=AssertionError(
            "REAL NETWORK CALL ATTEMPTED IN TEST -- forgot to patch get_token"
        ))
    )


@asynccontextmanager
async def mock_ws_server(handler):
    """Local-only websocket server on an OS-assigned port. Bounded
    wait_closed so a stuck handler can't hang the suite."""
    server = await websockets.serve(handler, "127.0.0.1", 0)
    try:
        port = server.sockets[0].getsockname()[1]
        yield f"ws://127.0.0.1:{port}"
    finally:
        server.close()
        await asyncio.wait_for(server.wait_closed(), timeout=5)


class AsyncMockedNetworkTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        block_real_network(self)


# --- (a) no frames before session.ready, even when session.updated arrives first ----

class TestSessionReadyGate(AsyncMockedNetworkTestCase):
    async def test_no_frames_sent_before_session_ready(self):
        """Server sends session.updated, waits 0.5s, THEN session.ready.
        Client (via open_session) must not have sent anything by the time
        session.ready goes out -- this reproduces the 2026-09-13 live-run
        bug where the old code proceeded on session.updated."""
        ready_sent_at = {}
        frames = []  # every input.audio/conversation.message frame, with its TRUE arrival time

        async def handler(ws):
            raw = await ws.recv()
            msg = json.loads(raw)
            assert msg["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.updated"}))

            async def send_ready_later():
                await asyncio.sleep(0.5)
                ready_sent_at["t"] = time.monotonic()
                await ws.send(json.dumps({"type": "session.ready"}))

            sender_task = asyncio.create_task(send_ready_later())
            # A single `async for` reader records each frame's real arrival
            # time as it's delivered -- concurrent with sender_task's sleep,
            # since that's a separate task. (Classifying "early" via an
            # asyncio.Event flag instead of a timestamp comparison is racy:
            # the event isn't set until just after the ready send completes,
            # so a frame that is genuinely POST-ready can still be observed
            # while the flag reads False -- caught in an earlier version of
            # this test as a false failure.)
            try:
                async for raw in ws:
                    m = json.loads(raw)
                    if m["type"] in ("input.audio", "conversation.message"):
                        frames.append((m["type"], time.monotonic()))
                    elif m["type"] == "session.end":
                        break
            except websockets.exceptions.ConnectionClosed:
                pass
            await sender_task

        async with mock_ws_server(handler) as ws_url:
            with patch.object(spike, "get_token", return_value="dummy-token"), \
                 patch.object(spike, "WS_URL_BASE", ws_url):

                async def run():
                    async with spike.open_session("dummy-key", {"system_prompt": "x"}, "test") as (
                        ws, _setup_events, _ready_at,
                    ):
                        # If open_session returned too early (pre-fix bug),
                        # these land before the server sends session.ready.
                        await ws.send(json.dumps({
                            "type": "conversation.message", "role": "user", "content": "hi",
                        }))
                        await ws.send(json.dumps({"type": "input.audio", "audio": "AAAA"}))
                        await asyncio.sleep(0.1)  # give the server time to receive them

                await asyncio.wait_for(run(), timeout=5)

        self.assertIn("t", ready_sent_at, "mock server never got to send session.ready")
        early_frames = [(t, ts) for t, ts in frames if ts < ready_sent_at["t"]]
        self.assertEqual(
            early_frames, [],
            f"expected ZERO input.audio/conversation.message frames before "
            f"session.ready was sent at {ready_sent_at['t']}, got: {early_frames} "
            f"(all frames seen: {frames})",
        )


# --- (b)/(c)/(d) exercised through the real Q2 test function + _run_test -----------

class TestQ2SetupBehavior(AsyncMockedNetworkTestCase):
    async def test_session_error_during_setup_fails_cleanly(self):
        """session.error right after session.update -> Q2 result is a clean
        FAIL with detail startswith 'setup error', no exception escapes."""

        async def handler(ws):
            raw = await ws.recv()
            msg = json.loads(raw)
            assert msg["type"] == "session.update"
            await ws.send(json.dumps({
                "type": "session.error",
                "code": "internal_error",
                "message": "mock: setup failed",
            }))
            await asyncio.sleep(0.2)  # let the client see it before we hang up

        async with mock_ws_server(handler) as ws_url:
            with patch.object(spike, "get_token", return_value="dummy-token"), \
                 patch.object(spike, "WS_URL_BASE", ws_url), \
                 patch.object(spike, "HARD_CAP_S", 3, create=True):
                result = await asyncio.wait_for(
                    spike._run_test(spike.test_silence, "Q2", "dummy-key", TINY_WAV_PATH),
                    timeout=10,
                )

        self.assertEqual(result["id"], "Q2")
        self.assertFalse(result["pass"])
        self.assertTrue(
            result["detail"].startswith("setup error"),
            f"expected detail to start with 'setup error', got: {result['detail']!r}",
        )

    async def test_no_session_ready_times_out(self):
        """Server never sends session.ready -> the call must return within
        SESSION_READY_TIMEOUT_S (patched to 1) + CLEANUP_TIMEOUT_S + 1.5s,
        with a FAIL result whose detail mentions 'no session.ready'."""

        async def handler(ws):
            raw = await ws.recv()
            msg = json.loads(raw)
            assert msg["type"] == "session.update"
            # Never reply further. Just sit until the client gives up/closes.
            try:
                await asyncio.wait_for(ws.wait_closed(), timeout=8)
            except asyncio.TimeoutError:
                pass

        bound_s = 1 + spike.CLEANUP_TIMEOUT_S + 1.5
        async with mock_ws_server(handler) as ws_url:
            with patch.object(spike, "get_token", return_value="dummy-token"), \
                 patch.object(spike, "WS_URL_BASE", ws_url), \
                 patch.object(spike, "SESSION_READY_TIMEOUT_S", 1, create=True), \
                 patch.object(spike, "HARD_CAP_S", 5, create=True):
                t0 = time.monotonic()
                try:
                    result = await asyncio.wait_for(
                        spike._run_test(spike.test_silence, "Q2", "dummy-key", TINY_WAV_PATH),
                        timeout=bound_s + 2,  # test-harness slack on top of the real bound
                    )
                except asyncio.TimeoutError:
                    self.fail(
                        f"test_silence did not return within {bound_s}s + slack -- "
                        "open_session isn't enforcing SESSION_READY_TIMEOUT_S yet"
                    )
                elapsed = time.monotonic() - t0

        self.assertLessEqual(
            elapsed, bound_s,
            f"took {elapsed:.1f}s, expected <= {bound_s}s "
            "(SESSION_READY_TIMEOUT_S + CLEANUP_TIMEOUT_S + 1.5)",
        )
        self.assertEqual(result["id"], "Q2")
        self.assertFalse(result["pass"])
        self.assertIn("no session.ready", result["detail"])

    async def test_happy_path_has_monotonic_event_log(self):
        """session.ready immediately, one transcript.user event, no reply ->
        Q2 passes and evidence carries an event_log of [[t_ms, type], ...]
        with non-decreasing t_ms."""

        async def handler(ws):
            raw = await ws.recv()
            msg = json.loads(raw)
            assert msg["type"] == "session.update"
            await ws.send(json.dumps({"type": "session.ready"}))
            sent_transcript = False
            try:
                async for raw in ws:
                    m = json.loads(raw)
                    if m["type"] == "input.audio" and not sent_transcript:
                        await ws.send(json.dumps({"type": "transcript.user", "text": "hello"}))
                        sent_transcript = True
                    elif m["type"] == "session.end":
                        break
            except websockets.exceptions.ConnectionClosed:
                pass

        async with mock_ws_server(handler) as ws_url:
            with patch.object(spike, "get_token", return_value="dummy-token"), \
                 patch.object(spike, "WS_URL_BASE", ws_url), \
                 patch.object(spike, "HARD_CAP_S", 3, create=True):
                # HARD_CAP_S=3: TINY_WAV_PATH's ~0.8s of content+trailing-silence
                # lets stream_wav finish naturally well under that, leaving a
                # real window afterwards for drain() to see the mock's reply
                # (stream_wav and drain share one deadline -- see TINY_WAV_PATH's
                # module comment; a too-small cap here starves drain entirely).
                result = await asyncio.wait_for(
                    spike._run_test(spike.test_silence, "Q2", "dummy-key", TINY_WAV_PATH),
                    timeout=15,
                )

        self.assertEqual(result["id"], "Q2")
        self.assertTrue(result["pass"], f"expected pass, got detail={result.get('detail')!r}")
        evidence = result.get("evidence", {})
        self.assertIn("event_log", evidence, "evidence missing 'event_log' (SPEC: [[t_ms, type], ...])")
        event_log = evidence["event_log"]
        self.assertTrue(event_log, "event_log is empty")
        t_values = [entry[0] for entry in event_log]
        self.assertEqual(t_values, sorted(t_values), "event_log t_ms is not monotonically non-decreasing")


# --- (e) --sample-rate-override refuses to start on a rate mismatch ----------------

class TestSampleRateOverrideCli(unittest.TestCase):
    def test_rate_mismatch_exits_nonzero(self):
        """rep_pitch.wav is 16kHz (FORMAT.md); --sample-rate-override 24000
        must refuse to start. Real subprocess, key unset, no network -- if
        the process ever tried to phone home with no key it would exit(2)
        for that reason first, which this test can't distinguish from a
        correct rate-mismatch refusal; see the final report note on this."""
        env = dict(os.environ)
        env.pop("ASSEMBLYAI_API_KEY", None)
        cmd = [
            sys.executable, str(SPIKE_PATH),
            "--audio-dir", str(HARNESS_AUDIO_DIR),
            "--sample-rate-override", "24000",
        ]
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=15)
        self.assertNotEqual(proc.returncode, 0, f"stdout={proc.stdout!r} stderr={proc.stderr!r}")
        self.assertNotIn("Traceback", proc.stderr, "should exit cleanly, not crash")


# --- (f) --only Q2 runs exactly one test -------------------------------------------

class TestOnlyFilterCli(unittest.TestCase):
    """Runs spike.main() in-process (so our monkeypatches apply) against a
    background sync websocket server in a thread -- main() calls
    asyncio.run() itself, so it can't be driven from inside an already-
    running asyncio test loop."""

    def test_only_q2_writes_single_result(self):
        block_real_network(self)

        def handler(ws):
            for raw in ws:
                msg = json.loads(raw)
                if msg["type"] == "session.update":
                    ws.send(json.dumps({"type": "session.ready"}))
                elif msg["type"] == "session.end":
                    break

        server = sync_serve(handler, "127.0.0.1", 0)
        port = server.socket.getsockname()[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                out_path = Path(tmp) / "results_voice_agent.json"
                with patch.object(spike, "get_token", return_value="dummy-token"), \
                     patch.object(spike, "WS_URL_BASE", f"ws://127.0.0.1:{port}"), \
                     patch.object(spike, "OUT_PATH", out_path, create=True), \
                     patch.object(spike, "HARD_CAP_S", 2, create=True), \
                     patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "dummy-test-key"}), \
                     patch.object(sys, "argv", [
                         "spike_voice_agent.py",
                         "--audio-dir", str(HARNESS_AUDIO_DIR),
                         "--only", "Q2",
                     ]):
                    try:
                        spike.main()
                    except SystemExit as e:
                        self.fail(
                            f"main() exited (code={e.code}) instead of running "
                            "--only Q2 -- CLI flag not implemented yet"
                        )

                self.assertTrue(out_path.exists(), f"results file not written to {out_path}")
                results = json.loads(out_path.read_text())
                self.assertEqual(
                    [r["id"] for r in results], ["Q2"],
                    f"expected exactly one Q2 result, got ids: {[r.get('id') for r in results]}",
                )
        finally:
            server.shutdown()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
