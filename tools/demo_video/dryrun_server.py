"""$0 dry-run server for the demo-video pipeline: the real server.main app with
every paid upstream swapped for a local fake via FastAPI dependency_overrides.

- STT: energy VAD over the real mic PCM (fake-mic WAV -> worklet -> WS). Each
  detected utterance emits growing partials, then the next scripted rep line
  as a final turn. Proves the fake-mic path end to end without AssemblyAI.
- Claim check: keyword rules (discount -> 3.1, 24/7 -> 6.1).
- Voice: streams pre-rendered TTS WAVs (24 kHz PCM16) as agent_audio at ~2x
  realtime, with agent_speaking start/end events, like the real AlertSpeaker.

Paid keys are scrubbed from this process before the app is imported, and a
dummy ASSEMBLYAI_API_KEY is set only so main.py takes its "connected" branch;
it can never reach the network because both factories are overridden.

Usage: python tools/demo_video/dryrun_server.py --port 8801
Env:   DEMO_REP_LINES (json list of str), DEMO_AGENT_AUDIO_DIR (dir of agent_<sha>.wav)
"""
from __future__ import annotations

import argparse
import array
import asyncio
import hashlib
import json
import math
import os
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

for k in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "CLAUSECATCHER_CLAIM_CHECK", "ASSEMBLYAI_API_KEY"):
    os.environ.pop(k, None)
os.environ["ASSEMBLYAI_API_KEY"] = "dry-run-fake-key-never-sent"

from server import main  # noqa: E402

REP_LINES: list[str] = json.loads(os.environ.get("DEMO_REP_LINES", "[]"))
AGENT_DIR = Path(os.environ.get("DEMO_AGENT_AUDIO_DIR", "."))
RMS_SPEECH = 400  # ponytail: fixed threshold; SAPI/edge TTS at 16 kHz sits far above it
SILENCE_CHUNKS_TO_FINAL = 12  # 1.2 s of silence ends a turn (TTS sentence pauses run ~0.7 s)


def agent_wav_name(text: str) -> str:
    return "agent_" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:12] + ".wav"


class FakeSTT:
    turn_index = 0  # shared across sessions: one scripted call per server run

    def __init__(self, *, on_turn, **_kw) -> None:
        self.on_turn = on_turn
        self.speech_chunks = 0
        self.silence = 0
        self.est_cost_usd = 0.0

    async def start(self) -> None: ...

    async def stop(self) -> None: ...

    async def send_audio(self, pcm: bytes) -> None:
        samples = array.array("h", pcm[: len(pcm) // 2 * 2])
        rms = math.sqrt(sum(s * s for s in samples) / len(samples)) if samples else 0
        line = REP_LINES[FakeSTT.turn_index] if FakeSTT.turn_index < len(REP_LINES) else "(unscripted speech)"
        if rms > RMS_SPEECH:
            if self.speech_chunks == 0:
                print(f"[dryrun-stt] speech onset epoch={time.time():.3f} line={FakeSTT.turn_index}", flush=True)
            self.speech_chunks += 1
            self.silence = 0
            if self.speech_chunks % 3 == 0:
                words = line.split()
                await self.on_turn(" ".join(words[: max(1, int(self.speech_chunks * 0.1 * 2.8))]), False)
        elif self.speech_chunks:
            self.silence += 1
            if self.silence >= SILENCE_CHUNKS_TO_FINAL:
                self.speech_chunks = self.silence = 0
                FakeSTT.turn_index += 1
                print(f"[dryrun-stt] final epoch={time.time():.3f}: {line}", flush=True)
                await self.on_turn(line, True)


def fake_checker(sentence: str, clauses: list[dict]) -> dict:
    s = sentence.lower()
    if "discount" in s:
        return {"verdict": "contradiction", "clause_id": "3.1", "confidence": 0.9}
    if "24/7" in s or "twenty four seven" in s or "twenty-four seven" in s:
        return {"verdict": "contradiction", "clause_id": "6.1", "confidence": 0.9}
    return {"verdict": "consistent", "clause_id": None, "confidence": 0.9}


class FakeSpeaker:
    def __init__(self, *, on_audio, on_event, **_kw) -> None:
        self.on_audio, self.on_event = on_audio, on_event
        self.lock = asyncio.Lock()
        self.est_cost_usd = 0.0

    async def open(self) -> None: ...

    async def close(self) -> None: ...

    async def say_exactly(self, text: str) -> dict:
        async with self.lock:
            path = AGENT_DIR / agent_wav_name(text)
            if path.exists():
                with wave.open(str(path)) as w:
                    pcm = w.readframes(w.getnframes())
            else:  # 1.5 s tone so a missing render is audible, not silent
                pcm = array.array("h", (int(6000 * math.sin(2 * math.pi * 440 * i / 24000)) for i in range(36000))).tobytes()
            await self.on_event({"type": "agent_speaking", "state": "start", "text": text})
            step = 4800  # 100 ms at 24 kHz, 16-bit
            for i in range(0, len(pcm), step):
                await self.on_audio(pcm[i : i + step], 24000)
                await asyncio.sleep(0.05)
            await self.on_event({"type": "agent_speaking", "state": "end", "text": text})
            return {"literal_spoken": text, "similarity": 1.0}


def install_fakes() -> None:
    main.app.dependency_overrides[main.get_claim_checker] = lambda: fake_checker
    main.app.dependency_overrides[main.get_stt_factory] = lambda: (lambda **kw: FakeSTT(**kw))
    main.app.dependency_overrides[main.get_voice_factory] = lambda: (lambda **kw: FakeSpeaker(**kw))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8801)
    args = ap.parse_args()
    assert args.port != 8000, "port 8000 is reserved on this box"
    install_fakes()
    import uvicorn

    uvicorn.run(main.app, host="127.0.0.1", port=args.port, log_level="warning")
