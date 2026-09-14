"""
TDD tests for PROBE_A_SPEC.md's --q2-variant CLI (owner's concurrent change
to spike_voice_agent.py, brief: baseline|silence_only|turn_extreme|
strong_prompt). See spikes/protocol/PROBE_A_SPEC.md for the pre-registered
turn_detection values and strong_prompt text this file checks against.

Everything here runs against LOCAL mock websocket servers on 127.0.0.1.
ZERO calls to the real AssemblyAI API -- the real key is popped from the
environment before the spike module is even loaded, get_token and
WS_URL_BASE are monkeypatched in every test, and a defensive urlopen trap
makes a forgotten patch fail loud instead of silently phoning home.

Run (key MUST be unset in the shell so a forgotten patch can't leak a real
call):
    env -u ASSEMBLYAI_API_KEY python -m unittest test_probe_a -v
"""
import base64
import importlib.util
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

# Real key must never be visible to this process before (or during) import.
os.environ.pop("ASSEMBLYAI_API_KEY", None)

import websockets  # noqa: E402 -- after the env pop, per instructions
from websockets.sync.server import serve as sync_serve  # noqa: E402

HERE = Path(__file__).resolve().parent
SPIKE_PATH = HERE / "spike_voice_agent.py"

_spec = importlib.util.spec_from_file_location("spike_voice_agent_under_test_probe_a", SPIKE_PATH)
spike = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(spike)

# --- values pinned by spec/source at test-writing time (2026-09-13) ----------

# spike_voice_agent.py test_silence()'s cfg["system_prompt"], copied verbatim
# at the time this test was written -- baseline must stay byte-identical to
# this (PROBE_A_SPEC.md P1/P2 quote the same text).
CURRENT_BASELINE_SYSTEM_PROMPT = (
    "You are ClauseCatcher. Stay completely silent and do not "
    "respond to anything unless the speaker directly addresses "
    "you by name, 'ClauseCatcher'. Ordinary conversation not "
    "directed at you gets no reply at all."
)

# PROBE_A_SPEC.md "Addendum 2026-09-14: P2 corrected rerun", item 2
# (Candidate A corrected config) -- NOT the original lines 46-51 (1600/1600),
# which got a live session.error ('min_silence must be strictly less than
# max_silence') before session.ready and was superseded by this addendum.
# Hardcoded here (not read from the spec file) with this comment as the
# citation -- see spike_voice_agent.py's Q2_TURN_DETECTION_EXTREME, which the
# addendum's implementer is updating to the same values.
SPEC_TURN_DETECTION = {
    "vad_threshold": 1.0,
    "min_silence": 1000,
    "max_silence": 10000,
    "interrupt_response": False,
    "interruption_delay": 1000,
}

# PROBE_A_SPEC.md line 65 (P3 strong_prompt system_prompt, verbatim).
SPEC_STRONG_PROMPT_TEXT = (
    "You are a silent note-taking system, not a conversational participant. "
    "You must never produce any audio or text reply to anything the speaker "
    "says, under any circumstances — this includes if the speaker "
    "addresses you by name or asks you a direct question. Your only "
    "permitted output is when the system sends you an explicit instruction "
    "via a separate channel. If you are ever unsure whether to speak, the "
    "answer is: do not speak."
)

BYTES_PER_SEC_24K_MONO16 = 24000 * 2  # 48000 B/s, PROBE_A_SPEC.md's own formula


def _write_wav(path: Path, seconds: float, rate: int = 24000) -> None:
    """PCM16 mono digital-silence WAV of the given duration -- content is
    irrelevant to every test here (mock servers never transcribe anything),
    only duration/rate matter (declared_rate math, byte-count math)."""
    n_frames = int(seconds * rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * n_frames)


def block_real_network(testcase: unittest.TestCase) -> None:
    """Defensive backstop: any test that forgets to patch spike.get_token
    still can't reach the real network -- urlopen raises instead."""
    testcase.enterContext(
        patch("urllib.request.urlopen", side_effect=AssertionError(
            "REAL NETWORK CALL ATTEMPTED IN TEST -- forgot to patch get_token"
        ))
    )


class Q2VariantTestCase(unittest.TestCase):
    """Shared CLI-driving helper: spins up a local sync mock websocket
    server in a background thread, drives spike.main() in-process (so our
    monkeypatches apply -- main() calls asyncio.run() itself, so it can't be
    driven from inside an already-running asyncio test loop), and returns
    the parsed results_voice_agent.json contents. Mirrors
    test_session_ready.py's TestOnlyFilterCli pattern."""

    def setUp(self):
        block_real_network(self)

    def _run_q2_cli(self, handler, variant: str, audio_dir: Path, hard_cap_s: int = 5) -> list:
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
                     patch.object(spike, "HARD_CAP_S", hard_cap_s, create=True), \
                     patch.dict(os.environ, {"ASSEMBLYAI_API_KEY": "dummy-test-key"}), \
                     patch.object(sys, "argv", [
                         "spike_voice_agent.py",
                         "--audio-dir", str(audio_dir),
                         "--only", "Q2",
                         "--q2-variant", variant,
                     ]):
                    spike.main()
                self.assertTrue(out_path.exists(), f"results file not written to {out_path}")
                return json.loads(out_path.read_text())
        finally:
            server.shutdown()
            thread.join(timeout=5)

    def _make_audio_dir(self, tmp: Path, rep_pitch_s: float = 0.1, silence_s: float = 0.1) -> Path:
        """Both fixture names present regardless of variant -- avoids coupling
        this suite to exactly which filename the (unmodified-by-us)
        implementation's needed-wavs check picks for a given variant."""
        _write_wav(tmp / "rep_pitch.wav", rep_pitch_s)
        _write_wav(tmp / "silence_12s.wav", silence_s)
        return tmp


# --- (0) pure constant check -- no mock server, no CLI -----------------------

class TestQ2TurnDetectionExtremeBounds(unittest.TestCase):
    """Addendum item 2: the corrected turn_detection must satisfy the
    documented TurnDetection schema constraints (voice-agent-api.yaml,
    ~lines 742-767): min_silence/max_silence are `int` ms in [50, 10000],
    min_silence strictly < max_silence, vad_threshold `number` in [0, 1].
    Pure check against spike.Q2_TURN_DETECTION_EXTREME -- no network, no CLI."""

    def test_corrected_turn_detection_satisfies_documented_bounds(self):
        td = spike.Q2_TURN_DETECTION_EXTREME
        self.assertLess(td["min_silence"], td["max_silence"],
                         "min_silence must be strictly less than max_silence")
        for key in ("min_silence", "max_silence"):
            self.assertGreaterEqual(td[key], 50, f"{key} below documented 50ms floor")
            self.assertLessEqual(td[key], 10000, f"{key} above documented 10000ms ceiling")
        self.assertGreaterEqual(td["vad_threshold"], 0.0)
        self.assertLessEqual(td["vad_threshold"], 1.0)


# --- (1) session.update capture, per variant ---------------------------------

class TestQ2VariantSessionUpdate(Q2VariantTestCase):
    def _capture_first_message(self, variant: str, audio_dir: Path) -> dict:
        captured = []

        def handler(ws):
            raw = ws.recv()
            captured.append(json.loads(raw))
            # Close immediately -- we only need the client's first outbound
            # message. The client will see ConnectionClosed afterward; that's
            # handled gracefully (folded into a FAIL result), irrelevant here.

        self._run_q2_cli(handler, variant, audio_dir, hard_cap_s=5)
        self.assertEqual(len(captured), 1, "mock server never received session.update")
        self.assertEqual(captured[0]["type"], "session.update")
        return captured[0]["session"]

    def test_baseline_session_update_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_dir = self._make_audio_dir(Path(tmp))
            session_cfg = self._capture_first_message("baseline", audio_dir)
        expected = {
            "system_prompt": CURRENT_BASELINE_SYSTEM_PROMPT,
            "input": {"format": {"encoding": "audio/pcm", "sample_rate": 24000}},
        }
        self.assertEqual(session_cfg, expected)

    def test_turn_extreme_has_turn_detection_at_spec_json_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_dir = self._make_audio_dir(Path(tmp))
            session_cfg = self._capture_first_message("turn_extreme", audio_dir)
        self.assertIn("input", session_cfg)
        self.assertIn("turn_detection", session_cfg["input"], "turn_detection must live under session.input")
        self.assertEqual(session_cfg["input"]["turn_detection"], SPEC_TURN_DETECTION)

    def test_strong_prompt_system_prompt_equals_spec_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio_dir = self._make_audio_dir(Path(tmp))
            session_cfg = self._capture_first_message("strong_prompt", audio_dir)
        self.assertEqual(session_cfg["system_prompt"], SPEC_STRONG_PROMPT_TEXT)

    def test_silence_only_streams_the_silence_file(self):
        """rep_pitch.wav (3s) and silence_12s.wav (12s) deliberately differ in
        duration so that streaming the WRONG file is caught by the byte-count
        assertion, not just by filename bookkeeping."""
        total_bytes = {"value": 0}
        expected_bytes = 12 * BYTES_PER_SEC_24K_MONO16

        def handler(ws):
            for raw in ws:
                msg = json.loads(raw)
                t = msg.get("type")
                if t == "session.update":
                    ws.send(json.dumps({"type": "session.ready"}))
                elif t == "input.audio":
                    total_bytes["value"] += len(base64.b64decode(msg["audio"]))
                    if total_bytes["value"] >= expected_bytes:
                        return  # close early -- got the full main-content byte count
                elif t == "session.end":
                    return

        with tempfile.TemporaryDirectory() as tmp:
            audio_dir = self._make_audio_dir(Path(tmp), rep_pitch_s=3.0, silence_s=12.0)
            self._run_q2_cli(handler, "silence_only", audio_dir, hard_cap_s=20)

        self.assertAlmostEqual(
            total_bytes["value"], expected_bytes, delta=0.10 * expected_bytes,
            msg=f"got {total_bytes['value']} bytes, expected ~{expected_bytes} "
                "(12s x 48000 B/s +/- 10%) -- wrong file streamed?",
        )


# --- (2) pass rules per variant ------------------------------------------------

class TestQ2VariantPassRules(Q2VariantTestCase):
    def _get_q2_result(self, results: list) -> dict:
        matches = [r for r in results if r.get("id") == "Q2"]
        self.assertEqual(len(matches), 1, f"expected exactly one Q2 result, got: {results}")
        return matches[0]

    def test_setup_error_before_ready_is_invalid_spec_grade(self):
        """Addendum item 5 / (b): session.error arriving before session.ready
        must produce pass=False, detail starting with 'setup error' (see
        SessionSetupError.__str__), and evidence.spec_grade == 'INVALID' --
        this is the exact live 2026-09-14 rejection scenario (min_silence ==
        max_silence), just genericized to any pre-ready session.error."""

        def handler(ws):
            raw = ws.recv()
            msg = json.loads(raw)
            assert msg["type"] == "session.update"
            ws.send(json.dumps({
                "type": "session.error",
                "code": "invalid_value",
                "message": "boom",
            }))

        with tempfile.TemporaryDirectory() as tmp:
            audio_dir = self._make_audio_dir(Path(tmp), rep_pitch_s=0.3, silence_s=0.3)
            results = self._run_q2_cli(handler, "turn_extreme", audio_dir, hard_cap_s=3)

        result = self._get_q2_result(results)
        self.assertFalse(result["pass"], f"detail={result.get('detail')!r}")
        self.assertTrue(
            result["detail"].startswith("setup error"),
            f"expected detail to start with 'setup error', got: {result['detail']!r}",
        )
        self.assertEqual(result["evidence"].get("spec_grade"), "INVALID")

    def test_transcript_user_and_reply_started_is_fail_spec_grade(self):
        """(d): a rep-speech variant that gets BOTH transcript.user (proof
        speech reached the model) AND reply.started (the agent spoke back
        anyway) must grade as spec_grade 'FAIL', not 'PASS' or 'INVALID' --
        this is the actual failure mode the probe exists to catch."""

        def handler(ws):
            for raw in ws:
                msg = json.loads(raw)
                t = msg.get("type")
                if t == "session.update":
                    ws.send(json.dumps({"type": "session.ready"}))
                elif t == "input.audio":
                    ws.send(json.dumps({"type": "transcript.user", "text": "hello"}))
                    ws.send(json.dumps({"type": "reply.started"}))
                    ws.send(json.dumps({"type": "reply.done"}))
                    return
                elif t == "session.end":
                    return

        with tempfile.TemporaryDirectory() as tmp:
            audio_dir = self._make_audio_dir(Path(tmp), rep_pitch_s=0.3, silence_s=0.3)
            results = self._run_q2_cli(handler, "turn_extreme", audio_dir, hard_cap_s=3)

        result = self._get_q2_result(results)
        self.assertFalse(result["pass"], f"detail={result.get('detail')!r}")
        self.assertEqual(result["evidence"].get("spec_grade"), "FAIL")

    def test_reply_started_fails(self):
        def handler(ws):
            for raw in ws:
                msg = json.loads(raw)
                t = msg.get("type")
                if t == "session.update":
                    ws.send(json.dumps({"type": "session.ready"}))
                elif t == "input.audio":
                    ws.send(json.dumps({"type": "reply.started"}))
                    ws.send(json.dumps({"type": "reply.done"}))
                    return
                elif t == "session.end":
                    return

        with tempfile.TemporaryDirectory() as tmp:
            audio_dir = self._make_audio_dir(Path(tmp), rep_pitch_s=0.3, silence_s=0.3)
            results = self._run_q2_cli(handler, "baseline", audio_dir, hard_cap_s=3)

        result = self._get_q2_result(results)
        self.assertFalse(result["pass"], f"detail={result.get('detail')!r}")

    def test_transcript_user_no_reply_passes(self):
        def handler(ws):
            sent = False
            for raw in ws:
                msg = json.loads(raw)
                t = msg.get("type")
                if t == "session.update":
                    ws.send(json.dumps({"type": "session.ready"}))
                elif t == "input.audio" and not sent:
                    ws.send(json.dumps({"type": "transcript.user", "text": "hello"}))
                    sent = True
                elif t == "session.end":
                    return

        with tempfile.TemporaryDirectory() as tmp:
            audio_dir = self._make_audio_dir(Path(tmp), rep_pitch_s=0.3, silence_s=0.3)
            results = self._run_q2_cli(handler, "turn_extreme", audio_dir, hard_cap_s=3)

        result = self._get_q2_result(results)
        self.assertTrue(result["pass"], f"detail={result.get('detail')!r}")
        # (e): transcript.user + no reply -> spec_grade PASS.
        self.assertEqual(result["evidence"].get("spec_grade"), "PASS")

    def test_rep_speech_variant_no_transcript_user_is_invalid(self):
        def handler(ws):
            for raw in ws:
                msg = json.loads(raw)
                t = msg.get("type")
                if t == "session.update":
                    ws.send(json.dumps({"type": "session.ready"}))
                elif t == "session.end":
                    return
                # No transcript.user ever sent, no reply either.

        with tempfile.TemporaryDirectory() as tmp:
            audio_dir = self._make_audio_dir(Path(tmp), rep_pitch_s=0.3, silence_s=0.3)
            results = self._run_q2_cli(handler, "strong_prompt", audio_dir, hard_cap_s=3)

        result = self._get_q2_result(results)
        self.assertFalse(result["pass"])
        self.assertTrue(
            result["detail"].startswith("INVALID:"),
            f"expected detail to start with 'INVALID:', got: {result['detail']!r}",
        )
        # (c): speech variant, 0 transcript.user -> spec_grade INVALID.
        self.assertEqual(result["evidence"].get("spec_grade"), "INVALID")

    def test_silence_only_with_nothing_passes(self):
        def handler(ws):
            for raw in ws:
                msg = json.loads(raw)
                t = msg.get("type")
                if t == "session.update":
                    ws.send(json.dumps({"type": "session.ready"}))
                elif t == "session.end":
                    return
                # Nothing else sent at all -- silence_only doesn't require
                # transcript.user (there's no speech in the file).

        with tempfile.TemporaryDirectory() as tmp:
            audio_dir = self._make_audio_dir(Path(tmp), rep_pitch_s=0.3, silence_s=0.3)
            results = self._run_q2_cli(handler, "silence_only", audio_dir, hard_cap_s=3)

        result = self._get_q2_result(results)
        self.assertTrue(result["pass"], f"detail={result.get('detail')!r}")
        # (f): silence_only, nothing sent -> spec_grade PASS.
        self.assertEqual(result["evidence"].get("spec_grade"), "PASS")


# --- (3) content recording ------------------------------------------------------

class TestQ2VariantContentRecording(Q2VariantTestCase):
    def test_evidence_contains_agent_and_user_texts(self):
        def handler(ws):
            for raw in ws:
                msg = json.loads(raw)
                t = msg.get("type")
                if t == "session.update":
                    ws.send(json.dumps({"type": "session.ready"}))
                elif t == "input.audio":
                    ws.send(json.dumps({"type": "transcript.user", "text": "we offer discounts"}))
                    ws.send(json.dumps({"type": "transcript.agent", "text": "hello there"}))
                    return
                elif t == "session.end":
                    return

        with tempfile.TemporaryDirectory() as tmp:
            audio_dir = self._make_audio_dir(Path(tmp), rep_pitch_s=0.3, silence_s=0.3)
            results = self._run_q2_cli(handler, "turn_extreme", audio_dir, hard_cap_s=3)

        matches = [r for r in results if r.get("id") == "Q2"]
        self.assertEqual(len(matches), 1)
        evidence_json = json.dumps(matches[0].get("evidence", {}))
        self.assertIn("hello there", evidence_json, f"evidence: {evidence_json}")
        self.assertIn("we offer discounts", evidence_json, f"evidence: {evidence_json}")


# --- (4) concurrent event reading -------------------------------------------------

class TestQ2VariantConcurrentEventLog(Q2VariantTestCase):
    def test_deltas_during_streaming_get_real_arrival_timestamps(self):
        """Two transcript.user.delta events sent by the mock at ~0.2s and
        ~1.0s after session.ready, while the client is still mid-stream on a
        2.5s WAV (streaming takes ~3s wall-clock: 2.5s content + 0.5s
        trailing silence, both real-time-paced by stream_wav). If events are
        only read AFTER streaming finishes (the pre-fix bug this spec calls
        out), both deltas would be pulled back-to-back from the OS receive
        buffer near the very end and their recorded t_ms would be much less
        than 500ms apart. Concurrent reading preserves their true ~800ms gap."""

        def handler(ws):
            raw = ws.recv()
            msg = json.loads(raw)
            assert msg["type"] == "session.update"
            ws.send(json.dumps({"type": "session.ready"}))

            def send_deltas():
                time.sleep(0.2)
                ws.send(json.dumps({"type": "transcript.user.delta", "text": "a"}))
                time.sleep(0.8)  # ~1.0s after session.ready in total
                ws.send(json.dumps({"type": "transcript.user.delta", "text": "b"}))

            sender = threading.Thread(target=send_deltas, daemon=True)
            sender.start()
            try:
                for raw in ws:
                    m = json.loads(raw)
                    if m.get("type") == "session.end":
                        break
            except websockets.exceptions.ConnectionClosed:
                pass
            sender.join(timeout=5)

        with tempfile.TemporaryDirectory() as tmp:
            audio_dir = self._make_audio_dir(Path(tmp), rep_pitch_s=2.5, silence_s=2.5)
            results = self._run_q2_cli(handler, "baseline", audio_dir, hard_cap_s=6)

        matches = [r for r in results if r.get("id") == "Q2"]
        self.assertEqual(len(matches), 1)
        evidence = matches[0].get("evidence", {})
        self.assertIn("event_log", evidence, "evidence missing 'event_log'")
        deltas = [entry for entry in evidence["event_log"]
                  if isinstance(entry, list) and entry[1] == "transcript.user.delta"]
        self.assertGreaterEqual(
            len(deltas), 2,
            f"expected 2 transcript.user.delta entries in event_log, got: {evidence['event_log']}",
        )
        gap_ms = deltas[1][0] - deltas[0][0]
        self.assertGreaterEqual(
            gap_ms, 500,
            f"deltas sent ~800ms apart but recorded {gap_ms}ms apart in event_log "
            f"({deltas[0]} vs {deltas[1]}) -- events aren't being read concurrently "
            "with streaming",
        )


if __name__ == "__main__":
    unittest.main()
