"""Real-browser mic end-to-end test for ClauseCatcher.

Chromium's fake media device plays a TTS WAV into getUserMedia, so the real
frontend path runs untouched: getUserMedia -> AudioWorklet (mic-downsampler)
-> binary PCM16 WS frames -> server -> STT -> claim check -> alert + voice.

Modes:
  --mode dry  (default) no paid calls. Server must run WITHOUT keys
              (--start-server strips them). Checks the worklet captures the
              WAV and binary frames flow; expects stt/voice "disabled".
  --mode live real AssemblyAI + Gemini (~$0.12). Needs keys in the env of the
              server process. See README.md.

Usage (repo root):
  python tools/e2e_mic/run_mic_e2e.py --start-server --port 8802
"""
from __future__ import annotations

import argparse
import json
import math
import os
import struct
import subprocess
import sys
import tempfile
import time
import urllib.request
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
OUT = HERE / "out"  # gitignored (**/out/)

FALSE_PROMISE = "Past fifty seats, we will apply a ten percent volume discount automatically, no paperwork needed."
CONSISTENT = "Pricing stays a flat forty eight thousand dollars for up to fifty seats, as written in the contract."
RATE = 48000  # Chromium's fake capture accepts 16k/48k mono PCM16 WAV
# gap > alert + spoken clause, so mic gating (no send while agent speaks) cannot eat the consistent line.
# Measured 2026-09-17: sentence end -> alert 12.3 s, then 13.3 s of agent speech = 25.6 s, so 14 s was too
# short and the consistent line was swallowed. 30 s clears it with margin.
# tail keeps the looping fake file from replaying the promise before the run ends.
LEAD_S, GAP_S, TAIL_S = 0.5, 30.0, 20.0
SETTLE_S = 8.0  # after the consistent line: turn finalization + claim check
SECRET_ENV = ("ASSEMBLYAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "CLAUSECATCHER_CLAIM_CHECK")


# ---------------------------------------------------------------------------
# WAV: Windows SAPI (System.Speech) via PowerShell, $0, no network.
# ---------------------------------------------------------------------------
def _sapi(text: str, path: Path) -> None:
    ps = (
        "Add-Type -AssemblyName System.Speech;"
        "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
        f"$f=New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo({RATE},"
        "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono);"
        "$s.SetOutputToWaveFile($env:E2E_WAV_PATH,$f);$s.Speak($env:E2E_TTS_TEXT);$s.Dispose()"
    )
    env = {**os.environ, "E2E_WAV_PATH": str(path), "E2E_TTS_TEXT": text}
    subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps], env=env, check=True)


def _frames(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, RATE), "SAPI wav format mismatch"
        return w.readframes(w.getnframes())


def make_wav(path: Path) -> dict:
    """lead silence, false promise, gap, consistent line, tail. Returns offsets (s)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        a, b = Path(tmp) / "a.wav", Path(tmp) / "b.wav"
        _sapi(FALSE_PROMISE, a)
        _sapi(CONSISTENT, b)
        pa, pb = _frames(a), _frames(b)
    sil = lambda s: b"\x00\x00" * int(RATE * s)  # noqa: E731
    pcm = sil(LEAD_S) + pa + sil(GAP_S) + pb + sil(TAIL_S)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    dur = lambda p: len(p) / 2 / RATE  # noqa: E731
    promise_end = LEAD_S + dur(pa)
    return {
        "promise_start": LEAD_S,
        "promise_end": promise_end,
        "consistent_start": promise_end + GAP_S,
        "consistent_end": promise_end + GAP_S + dur(pb),
        "total": dur(pcm),
        "pcm": pcm,
    }


def envelope(pcm: bytes, rate: int, win_s: float = 0.1) -> list[float]:
    n = int(rate * win_s)
    samples = struct.unpack(f"<{len(pcm) // 2}h", pcm[: len(pcm) // 2 * 2])
    return [
        math.sqrt(sum(x * x for x in samples[i : i + n]) / n) / 32768.0
        for i in range(0, len(samples) - n + 1, n)
    ]


def best_lag_corr(sent: list[float], ref: list[float], max_lag: int = 30) -> tuple[float, int]:
    """Pearson correlation of RMS envelopes; best over small lags (capture start jitter)."""

    def pearson(x, y):
        m = min(len(x), len(y))
        if m < 20:
            return 0.0
        x, y = x[:m], y[:m]
        mx, my = sum(x) / m, sum(y) / m
        sxy = sum((a - mx) * (b - my) for a, b in zip(x, y))
        sx = math.sqrt(sum((a - mx) ** 2 for a in x))
        sy = math.sqrt(sum((b - my) ** 2 for b in y))
        return sxy / (sx * sy) if sx and sy else 0.0

    best = (-1.0, 0)
    for lag in range(0, max_lag + 1):
        for s, r in ((sent[lag:], ref), (sent, ref[lag:])):
            c = pearson(s, r)
            if c > best[0]:
                best = (c, lag if s is not sent else -lag)
    return best


# ---------------------------------------------------------------------------
# server
# ---------------------------------------------------------------------------
def start_server(port: int, mode: str) -> subprocess.Popen:
    env = dict(os.environ)
    if mode == "dry":
        for k in SECRET_ENV:
            env.pop(k, None)
    else:
        env["CLAUSECATCHER_CLAIM_CHECK"] = "gemini"  # server stubs the claim check unless this is set
    env.pop("CLAUSECATCHER_ALLOWED_ORIGINS", None)
    log = open(OUT / "server.log", "w", encoding="utf-8")  # noqa: SIM115
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server.main:app", "--app-dir", str(REPO), "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(REPO), env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1) as r:
                if json.load(r).get("status") == "ok":
                    return proc
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("server did not become healthy; see tools/e2e_mic/out/server.log")


# Reads the cockpit "Live transcript" pane. Partial lines render italic (TranscriptPane.tsx).
DOM_TRANSCRIPT_JS = """() => {
  const head = [...document.querySelectorAll('section span')].find(e => e.textContent.trim() === 'Live transcript');
  const sec = head && head.closest('section');
  if (!sec) return null;
  return [...sec.querySelectorAll('ol > li')].map(li => ({text: li.innerText.trim(), final: !li.classList.contains('italic')}));
}"""


# ---------------------------------------------------------------------------
# browser run
# ---------------------------------------------------------------------------
def run(args, wavinfo: dict, wav_path: Path) -> list[tuple[str, str, str]]:
    from playwright.sync_api import sync_playwright

    sent_bin: list[tuple[float, bytes]] = []
    sent_text: list[tuple[float, str]] = []
    recv: list[tuple[float, dict]] = []
    ws_urls: list[str] = []
    console: list[str] = []
    t_click_start = [0.0]
    dom_max, dom_last = [0], []  # transcript pane lines as rendered: [{text, final}]

    def on_ws(ws):
        ws_urls.append(ws.url)

        def fs(payload):
            if isinstance(payload, (bytes, bytearray)):
                sent_bin.append((time.monotonic(), bytes(payload)))
            else:
                sent_text.append((time.monotonic(), payload))

        def fr(payload):
            if isinstance(payload, str):
                try:
                    recv.append((time.monotonic(), json.loads(payload)))
                except ValueError:
                    pass

        ws.on("framesent", fs)
        ws.on("framereceived", fr)

    def msgs(t):
        return [(ts, m) for ts, m in recv if m.get("type") == t]

    results: list[tuple[str, str, str]] = []

    def check(name, ok, detail=""):
        results.append((name, "PASS" if ok is True else ("SKIP" if ok is None else "FAIL"), str(detail)))

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not args.headed,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                f"--use-file-for-fake-audio-capture={wav_path}",
                "--autoplay-policy=no-user-gesture-required",
            ],
        )
        ctx = browser.new_context(permissions=["microphone"])
        page = ctx.new_page()
        page.on("console", lambda m: console.append(f"{m.type}: {m.text}"))
        page.on("websocket", on_ws)

        page.goto(args.base_url, wait_until="networkidle")
        page.get_by_role("button", name="Try the live demo").first.click()
        page.get_by_role("button", name="Use the demo contract").click()
        page.get_by_text("Everyone on the call has been told").click()
        start_btn = page.get_by_role("button", name="Start the call")
        start_btn.wait_for(state="visible")
        page.wait_for_function("b => !b.disabled", arg=start_btn.element_handle())
        t_click_start[0] = time.monotonic()
        start_btn.click()

        deadline = time.monotonic() + 20
        while not msgs("status") and time.monotonic() < deadline:
            page.wait_for_timeout(100)
        status = msgs("status")[0][1] if msgs("status") else None
        check("WS opened + status message", status is not None, status)

        if args.mode == "dry":
            disabled = bool(status) and status.get("stt") == "disabled" and status.get("voice") == "disabled"
            check("stt/voice disabled (no billing)", disabled, status)
            if not disabled:
                page.get_by_role("button", name="End call").click()  # stop any paid session immediately
                page.wait_for_timeout(1500)
                browser.close()
                return results
            # let the whole WAV play once
            page.wait_for_timeout(int(min(wavinfo["total"], args.listen_s) * 1000))
        else:
            ok_live = bool(status) and status.get("stt") == "connected" and status.get("voice") == "connected"
            check("stt/voice connected (live)", ok_live, status)
            # listen through the consistent line (+ settle) so a false alert on it would be caught
            listen = min(args.listen_s, wavinfo["consistent_end"] + SETTLE_S)
            end_at = time.monotonic() + listen
            shot = False
            while time.monotonic() < end_at:
                page.wait_for_timeout(500)
                dom_lines = page.evaluate(DOM_TRANSCRIPT_JS)
                if dom_lines:
                    dom_max[0] = max(dom_max[0], len(dom_lines))
                    dom_last[:] = dom_lines
                if not shot and msgs("alert"):  # cockpit while the alert card is up
                    page.screenshot(path=str(OUT / f"cockpit-alert-{args.mode}.png"), full_page=True)
                    shot = True

        # -- mic path (both modes) -----------------------------------------
        n = len(sent_bin)
        sizes = sorted({len(b) for _, b in sent_bin})
        check("worklet sent binary WS frames", n > 20, f"{n} frames")
        check("frame size = 3200 bytes (1600 x int16 @16k/100ms)", sizes == [3200], sizes)
        if n > 1:
            # median, not mean: live mode gates the mic while the agent speaks, so one gap is seconds long
            gaps = sorted(sent_bin[i + 1][0] - sent_bin[i][0] for i in range(n - 1))
            med = gaps[len(gaps) // 2] * 1000
            check("frame cadence ~100 ms (median)", 70 <= med <= 140, f"median {med:.1f} ms, longest gap {gaps[-1] * 1000:.0f} ms (mic gated while agent speaks)")
        first_frame_ms = (sent_bin[0][0] - t_click_start[0]) * 1000 if n else None
        check("first frame after Start click", n > 0, f"{first_frame_ms:.0f} ms" if n else "none")
        if n:
            sent_pcm = b"".join(b for _, b in sent_bin)
            env_sent = envelope(sent_pcm, 16000)
            env_ref = envelope(wavinfo["pcm"], RATE)
            corr, lag = best_lag_corr(env_sent, env_ref)
            # lag from the first 6 s only: in live mode later frames are gated while the agent speaks
            _, lag0 = best_lag_corr(env_sent[:60], env_ref)
            peak = max(env_sent) if env_sent else 0
            # dry: whole file played, envelope must match. live: mic is gated while agent speaks, so weaker bar.
            bar = 0.6 if args.mode == "dry" else 0.3
            check("captured audio is the fake WAV (envelope corr)", corr >= bar and peak > 0.01, f"r={corr:.2f} lag={lag * 100}ms peak_rms={peak:.3f}")

        # -- live pipeline -------------------------------------------------
        # wall clock of WAV t=0: frame 0 covers WAV [L, L+0.1] (L from envelope lag) and is sent at its end
        t0 = sent_bin[0][0] - (max(0, -lag0) * 0.1 + 0.1) if n else None
        tr = msgs("transcript")
        alerts = msgs("alert")
        speaking = msgs("agent_speaking")
        audio = msgs("agent_audio")
        if args.mode == "live":
            check("transcript lines received over WS", len(tr) > 0, f"{len(tr)} msgs; " + " | ".join(m.get("text", "") for _, m in tr[-3:]))
            a31 = [(ts, m) for ts, m in alerts if m.get("section_number") == "3.1"]
            if a31 and t0 is not None:
                ms = (a31[0][0] - (t0 + wavinfo["promise_end"])) * 1000
                check("alert on section 3.1", True, f"sentence_end->alert {ms:.0f} ms; heard: {a31[0][1].get('sentence')!r}")
            else:
                check("alert on section 3.1", False, [m.get("section_number") for _, m in alerts])
            finals = [l["text"] for l in dom_last if l["final"]]
            check(
                "transcript pane: >=2 final lines, promise among them",
                len(finals) >= 2 and any("discount" in t.lower() for t in finals),
                f"max {dom_max[0]} lines seen; at end: " + " | ".join(("F: " if l["final"] else "P: ") + l["text"][:50] for l in dom_last),
            )
            other = [m.get("section_number") for _, m in alerts if m.get("section_number") != "3.1"]
            # non-vacuous: the consistent line must actually have been transcribed (a final AFTER the 3.1 alert)
            after = [m.get("text", "") for ts, m in tr if m.get("final") and a31 and ts > a31[0][0]]
            check(
                "consistent line transcribed and NOT alerted",
                not other and bool(after),
                f"alerts besides 3.1: {other or 'none'}; finals after alert: {after or 'NONE (line never reached STT)'}",
            )
            states = [m.get("state") for _, m in speaking]
            check("agent_speaking start + stop/end", "start" in states and any(s in ("stop", "end") for s in states), states)
            b64_bytes = sum(len(m.get("pcm16_b64", "")) * 3 // 4 for _, m in audio)
            check("agent_audio frames arrived", len(audio) > 0, f"{len(audio)} frames, ~{b64_bytes} bytes pcm16")
            if a31 and audio:
                check("alert->first agent audio", True, f"{(audio[0][0] - a31[0][0]) * 1000:.0f} ms")
        else:
            check("live pipeline (transcript/alert/voice)", None, "dry run: stt/voice disabled by design")

        # -- end call -> report ---------------------------------------------
        page.get_by_role("button", name="End call").click()
        deadline = time.monotonic() + 10
        while not msgs("session_ended") and time.monotonic() < deadline:
            page.wait_for_timeout(100)
        ended = msgs("session_ended")
        report = ended[0][1].get("report") if ended else None
        check("stop sent + session_ended with report", report is not None, (report and {k: report[k] for k in ("transcript_count", "claim_check_calls", "est_cost_usd")}) or "none")
        page.wait_for_timeout(1500)
        body = page.inner_text("body")
        check("report screen rendered", "contradiction" in body.lower(), "report text present" if "contradiction" in body.lower() else body[:120])
        if args.mode == "live":
            contra = (report or {}).get("contradictions", [])
            check("report lists the 3.1 contradiction", any(c.get("section_number") == "3.1" for c in contra), contra)
        page.screenshot(path=str(OUT / f"report-{args.mode}.png"), full_page=True)

        (OUT / f"run-{args.mode}.json").write_text(
            json.dumps(
                {
                    "ws_urls": ws_urls,
                    "binary_frames_sent": n,
                    "text_frames_sent": [t for _, t in sent_text],
                    # t_ms: ms after the Start click, so STT-final -> alert -> voice can be attributed
                    "received": [
                        {"t_ms": round((ts - t_click_start[0]) * 1000), **(m if m.get("type") != "agent_audio" else {"type": "agent_audio", "b64_len": len(m.get("pcm16_b64", ""))})}
                        for ts, m in recv
                    ],
                    "console": console[-50:],
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        browser.close()
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", choices=("dry", "live"), default="dry")
    ap.add_argument("--port", type=int, default=8802)
    ap.add_argument("--base-url", default=None, help="default http://127.0.0.1:<port>")
    ap.add_argument("--start-server", action="store_true", help="spawn uvicorn (dry mode strips API keys from its env)")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--listen-s", type=float, default=60.0, help="max seconds to listen (capped at consistent line + settle)")
    args = ap.parse_args()
    if args.port == 8000:
        raise SystemExit("port 8000 is reserved on this machine; use 8802")
    args.base_url = args.base_url or f"http://127.0.0.1:{args.port}"
    OUT.mkdir(parents=True, exist_ok=True)

    if args.mode == "live" and args.start_server and not (os.environ.get("ASSEMBLYAI_API_KEY") and (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))):
        raise SystemExit("live mode needs ASSEMBLYAI_API_KEY and GEMINI_API_KEY in the environment")

    wav_path = OUT / "false_promise_48k.wav"
    wavinfo = make_wav(wav_path)  # regenerated every run (~3 s): keeps sentence offsets exact
    print(f"WAV {wav_path} {wavinfo['total']:.1f}s; promise {wavinfo['promise_start']:.1f}-{wavinfo['promise_end']:.1f}s, consistent @ {wavinfo['consistent_start']:.1f}s")

    proc = start_server(args.port, args.mode) if args.start_server else None
    try:
        t = time.monotonic()
        results = run(args, wavinfo, wav_path)
        print(f"\nClauseCatcher mic E2E ({args.mode}) in {time.monotonic() - t:.1f}s\n")
        w = max(len(r[0]) for r in results)
        print(f"{'CHECK'.ljust(w)}  RESULT  DETAIL")
        for name, res, detail in results:
            print(f"{name.ljust(w)}  {res.ljust(6)}  {detail[:160]}")
        failed = [r for r in results if r[1] == "FAIL"]
        print(f"\n{'FAIL' if failed else 'PASS'}: {len(results) - len(failed)}/{len(results)} checks not failing. Artifacts: {OUT}")
        return 1 if failed else 0
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=10)


if __name__ == "__main__":
    sys.exit(main())
