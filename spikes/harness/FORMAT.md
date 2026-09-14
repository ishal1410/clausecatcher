# Audio format for test fixtures

Verified 2026-09-13 via WebFetch against AssemblyAI docs.

## AssemblyAI Streaming v3
Source: https://www.assemblyai.com/docs/streaming
Source: https://www.assemblyai.com/docs/streaming/api-spec/streaming-websocket

- Encoding: `pcm_s16le` (default) — raw PCM, 16-bit signed little-endian. Mono 16-bit PCM is the stated default.
- Sample rate: default `16000` Hz; server accepts any integer 8000-96000 for PCM encodings; `sample_rate` query param must match the audio you send.
- Channels: mono (per "mono 16-bit PCM by default").
- Chunk size: doc's Python example streams in 4096-byte chunks (`iter_content(chunk_size=4096)`); no hard requirement stated, just a convention.

## AssemblyAI Voice Agent API
Source: https://www.assemblyai.com/docs/voice-agents/voice-agent-api
Source: https://www.assemblyai.com/docs/voice-agents/voice-agent-api/api-spec/create-agent

- Encoding: `audio/pcm` (default); alternatives `audio/pcmu`, `audio/pcma`.
- Sample rate: defaults to `24000` Hz if the audio config is omitted ("Defaults to PCM at 24 kHz if omitted").
- Channels: **UNVERIFIED** — not stated in either fetched page.
- Bit depth: **UNVERIFIED** — not stated beyond "PCM"; assumed 16-bit signed like Streaming v3, not confirmed.
- Chunk size: **UNVERIFIED** — not documented on the fetched pages.

## Decision for this harness
All generated WAVs use **16-bit signed PCM, mono, 16000 Hz** — this matches the Streaming v3 default exactly (verified). For the Voice Agent API spike, this is a mono/16-bit PCM stream at 16kHz instead of the 24kHz default; if the voice_agent spike needs the literal 24kHz default, resample with stdlib-only tooling (SAPI can render straight to 24kHz mono 16-bit via `SpeechAudioFormatInfo` — no resampling library needed) or pass `sample_rate=16000` explicitly if the API's create-agent config allows overriding rate (unverified — check `api-spec/create-agent` schema before assuming).
