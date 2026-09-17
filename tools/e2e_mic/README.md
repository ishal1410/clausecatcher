# Mic end-to-end test (real Chromium, fake microphone)

`run_mic_e2e.py` drives the real app in Chromium with a fake microphone that
plays a TTS WAV into `getUserMedia`. It runs the same path a user's mic does:
AudioWorklet (`mic-downsampler`) -> binary PCM16 WebSocket frames -> server ->
AssemblyAI STT -> Gemini claim check -> alert + AssemblyAI voice.

The WAV is generated each run with Windows SAPI (`System.Speech`, free,
offline) at 48 kHz mono PCM16, which Chromium's
`--use-file-for-fake-audio-capture` accepts:

| t (s)      | audio                                                                                   |
|------------|-----------------------------------------------------------------------------------------|
| 0.5 - 7.9  | "Past fifty seats, we will apply a ten percent volume discount automatically, no paperwork needed." (contradicts §3.1) |
| +30 s gap  | silence (longer than alert + spoken clause, so mic gating can't swallow the next line)   |
| ~37.9      | "Pricing stays a flat forty eight thousand dollars for up to fifty seats, as written in the contract." (consistent) |
| +20 s      | silence (Chromium loops the file; the run ends before it loops)                          |

Flow: landing -> **Try the live demo** -> **Use the demo contract** -> consent ->
**Start the call** -> listen -> **End call** -> report screen.

The harness listens to every WebSocket frame, so it can count what the browser
**sends** as well as what it receives.

Requirements: Windows (for SAPI), Python with `playwright` plus Chromium
(`python -m playwright install chromium`). The server must serve a built
`frontend/dist`, so run `npm run build` in `frontend/` after frontend changes.

## Dry run (no billing), the default

```powershell
python tools/e2e_mic/run_mic_e2e.py --start-server --port 8802
```

`--start-server` launches uvicorn with `ASSEMBLYAI_API_KEY`, `GEMINI_API_KEY`,
`GOOGLE_API_KEY` and `CLAUSECATCHER_CLAIM_CHECK` removed from its environment,
so STT and voice come up `disabled`. If the server reports anything other than
`disabled`, the dry run clicks End call right away and fails.

Checks: status message, 3200-byte binary frames (1600 int16 samples = 100 ms at
16 kHz), about 100 ms between frames, and that the captured audio really is the
WAV. The last check correlates the RMS envelope of the PCM that was sent with the
WAV's envelope (r >= 0.6). It then ends the call and checks for the report.

## Live run (real AssemblyAI + Gemini) — NOT run by the harness author

Put your keys in the shell environment (never in a file inside the repo), then:

```powershell
$env:ASSEMBLYAI_API_KEY = "<your key>"; $env:GEMINI_API_KEY = "<your key>"
python tools/e2e_mic/run_mic_e2e.py --mode live --start-server --port 8802
```

In live mode the spawned server keeps the keys and gets
`CLAUSECATCHER_CLAIM_CHECK=gemini`. Extra checks: transcript messages over the
WebSocket, the transcript pane showing at least 2 final lines (one with the
promise), an alert on **§3.1** (timed from sentence end to alert), no alert on the
consistent line, `agent_speaking` start/end, `agent_audio` frames, time from alert
to first agent audio, and the 3.1 contradiction in the report.

**Cost, about $0.08 and at most $0.12:** a session of about 55 s (measured
2026-09-17: `est_cost_usd` 0.0755). That is
AssemblyAI streaming STT at $0.45/h (~$0.006), the AssemblyAI Voice Agent at
$4.50/h while the session is open (~$0.069), and 3 Gemini flash-lite claim
checks (<$0.001). The rates come from `server/stt.py` and `server/voice.py`. The
server's own `CLAUSECATCHER_BUDGET_USD` and session cap still apply.

## Output

A PASS/FAIL/SKIP table goes to stdout, and the exit code is 1 on any FAIL.
Artifacts go to `tools/e2e_mic/out/` (gitignored by `**/out/`): the WAV,
`server.log`, `run-<mode>.json` (every received message, sent text frames,
console), and `report-<mode>.png`.
