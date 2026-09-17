"""ClauseCatcher demo-video pipeline: narration TTS -> scripted browser take of
the real app -> agent-voice capture -> ffmpeg assembly. See README.md here.

  python tools/demo_video/record.py --server dryrun            # $0, fake upstreams
  python tools/demo_video/record.py --server live --i-mean-live  # real keys, ~$0.25

Pacing is narration-driven: every voiceover line from docs/submission/DEMO_SCRIPT.md
is rendered first, so the browser holds each beat for as long as its line runs.
Rep lines reach the app through Chromium's fake mic (--use-file-for-fake-audio-capture)
by default, or through the cockpit's "Simulate rep line" box with --mode sim.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))

# NB: dryrun_server scrubs the paid keys out of os.environ at import time, so it is
# imported lazily inside the dry-run branch only -- a module-level import here would
# leave --server live with no ASSEMBLYAI_API_KEY/GEMINI_API_KEY.
from server.clauses import load_demo_contract  # noqa: E402
from server.voice import build_alert_text, build_clause_answer_text  # noqa: E402

NARRATOR_VOICE = "en-US-AvaNeural"
REP_VOICE = "en-US-GuyNeural"
AGENT_STANDIN_VOICE = "en-US-EmmaNeural"  # dry run only; live uses the real Voice Agent audio
TITLE_S = 3.0
END_PAD_S = 2.5
LATENCY_S = 4.5  # planning margin: STT final + claim check + voice start (live; dry runs need ~1)
GAP_AFTER_AGENT_S = 5.0  # extra slack before the next mic line (mic is gated while the agent talks,
# and the live Voice Agent reads the clause slower than the edge-tts stand-in the plan is sized from)

REP_LINES = [
    "Thanks for making time today. Your fifty seats stay at the flat forty-eight thousand dollar rate.",
    "We can also do a ten percent automatic discount for a client like this.",
    "Renewal works the usual way, with sixty days written notice before the term ends.",
    "And support is available twenty four seven on the Standard plan.",
]

# DEMO_SCRIPT.md table rows, in order -> (anchor mark, delay s, avoid agent audio).
# None = silent row. "title"/"endcard" anchors are on the card clips, not the take.
BEATS = [
    ("title", 0.4, False),       # 0:00 hook
    ("how", 0.4, False),         # 0:12 how it works
    None,                        # 0:20 click CTA
    ("setup", 0.5, False),       # 0:22 demo contract
    ("clauses", 0.3, False),     # 0:32 clause cards
    ("consent", 0.2, False),     # 0:42 consent
    ("rep0_end", 0.5, False),    # 0:50 call is live
    ("n7", 0.0, False),          # 0:58 rep offers a discount
    ("alert1", 0.3, False),      # 1:05 flagged (may overlap the agent's preface; ducked)
    ("agent1_end", 0.4, True),   # 1:15 says the clause back
    ("agent1_end", 0.5, True),   # 1:28 verified
    ("n11", 0.0, True),          # 1:35 second false claim
    ("ask_focus", 0.2, False),   # 1:45 manager asks
    ("agent3_end", 0.4, True),   # 1:55 same mechanism
    None,                        # 2:05 end call
    ("report", 1.0, False),      # 2:12 report
    ("endcard", 0.5, False),     # 2:28 closing line
]


def log(*a) -> None:
    print("[demo]", *a, flush=True)


# ---------------------------------------------------------------- script ----
def parse_voiceover(script_md: Path) -> list[str]:
    rows = [ln for ln in script_md.read_text(encoding="utf-8").splitlines() if re.match(r"\|\s*\d:\d\d-\d:\d\d\s*\|", ln)]
    out = []
    for row in rows:
        cols = [c.strip() for c in row.strip().strip("|").split("|")]
        quoted = re.findall(r'"([^"]+)"', cols[2])
        out.append(" ".join(q.strip().lstrip(".").strip() for q in quoted))
    assert len(out) == len(BEATS), f"DEMO_SCRIPT.md has {len(out)} timed rows, BEATS expects {len(BEATS)}; update BEATS"
    return out


# ------------------------------------------------------------------- tts ----
def wav_duration(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def tts(text: str, voice: str, rate: int, cache: Path, rate_pct: str = "+0%") -> Path:
    """edge-tts (free) via uvx, Windows SAPI fallback. Cached by content hash."""
    key = hashlib.sha1(f"{voice}|{rate}|{rate_pct}|{text}".encode()).hexdigest()[:16]
    out = cache / f"tts_{key}.wav"
    if out.exists():
        return out
    cache.mkdir(parents=True, exist_ok=True)
    txt = cache / f"tts_{key}.txt"
    txt.write_text(text, encoding="utf-8")
    raw = cache / f"tts_{key}.raw"
    uvx = shutil.which("uvx")
    try:
        if not uvx:
            raise RuntimeError("uvx not on PATH")
        subprocess.run([uvx, "edge-tts", "--voice", voice, f"--rate={rate_pct}", "--file", str(txt), "--write-media", str(raw)],
                       check=True, capture_output=True, timeout=120)
    except Exception as exc:  # noqa: BLE001 - offline fallback, still $0
        log(f"edge-tts failed ({exc}); falling back to Windows SAPI")
        ps = ("Add-Type -AssemblyName System.Speech; $s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.SetOutputToWaveFile('{raw}'); $s.Speak([IO.File]::ReadAllText('{txt}')); $s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, capture_output=True, timeout=120)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(raw), "-ac", "1", "-ar", str(rate),
                    "-af", "silenceremove=start_periods=1:start_threshold=-50dB,areverse,silenceremove=start_periods=1:start_threshold=-50dB,areverse",
                    "-c:a", "pcm_s16le", str(out)], check=True)
    raw.unlink(missing_ok=True)
    return out


def read_pcm(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path)) as w:
        return w.readframes(w.getnframes()), w.getframerate()


def write_wav(path: Path, pcm: bytes | bytearray, rate: int) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(pcm))


def place_into(buf: bytearray, pcm: bytes, rate: int, at_s: float) -> None:
    i = max(0, int(at_s * rate)) * 2
    j = min(len(buf), i + len(pcm))
    if j > i:
        buf[i:j] = pcm[: j - i]


# ------------------------------------------------------------- timeline ----
class Narration:
    """Places narration clips: at anchor+delay, never overlapping each other
    or rep speech, and (when asked) sliding past agent speech."""

    def __init__(self, durations: list[float]) -> None:
        self.durations = durations
        self.starts: dict[int, float] = {}
        self.cursor = 0.0

    def place(self, idx: int, anchor: float, delay: float, avoid: list[tuple[float, float]]) -> float:
        d = self.durations[idx]
        start = max(anchor + delay, self.cursor + 0.25)
        moved = True
        while moved:
            moved = False
            for a, b in avoid:
                if start < b and start + d > a:
                    start, moved = b + 0.4, True
        self.starts[idx] = start
        self.cursor = start + d
        return start


class AgentTrack:
    """Rebuilds the agent voice exactly as the page schedules it: each chunk
    starts at max(previous end, arrival) (dsp.nextScheduleTime)."""

    def __init__(self) -> None:
        self.chunks: list[tuple[float, bytes, int]] = []
        self.cursor = 0.0
        self.intervals: list[list[float]] = []

    def add(self, t: float, pcm: bytes, rate: int) -> None:
        start = max(self.cursor, t)
        self.cursor = start + len(pcm) / 2 / rate
        self.chunks.append((start, pcm, rate))
        if self.intervals and start - self.intervals[-1][1] < 0.3:
            self.intervals[-1][1] = self.cursor
        else:
            self.intervals.append([start, self.cursor])


# ------------------------------------------------------------ recording ----
def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def start_server(kind: str, port: int, env_extra: dict, logf: Path) -> subprocess.Popen:
    assert port != 8000, "port 8000 is reserved on this box"
    assert port_free(port), f"port {port} is already in use; stop that server first"
    env = dict(os.environ, **env_extra)
    if kind == "dryrun":
        for k in ("ASSEMBLYAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "CLAUSECATCHER_CLAIM_CHECK"):
            env.pop(k, None)
        cmd = [sys.executable, str(HERE / "dryrun_server.py"), "--port", str(port)]
    else:
        missing = [k for k in ("ASSEMBLYAI_API_KEY",) if not env.get(k)]
        if not (env.get("GEMINI_API_KEY") or env.get("GOOGLE_API_KEY")):
            missing.append("GEMINI_API_KEY")
        assert not missing, f"live mode needs {missing} in the environment"
        env["CLAUSECATCHER_CLAIM_CHECK"] = "gemini"
        env.setdefault("CLAUSECATCHER_IDLE_TIMEOUT_S", "120")
        cmd = [sys.executable, "-m", "uvicorn", "server.main:app", "--app-dir", str(ROOT), "--port", str(port), "--log-level", "warning"]
    proc = subprocess.Popen(cmd, cwd=str(ROOT), env=env, stdout=logf.open("w"), stderr=subprocess.STDOUT)
    for _ in range(100):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1)
            return proc
        except Exception:  # noqa: BLE001
            if proc.poll() is not None:
                raise RuntimeError(f"server exited; see {logf}")
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError("server did not become healthy")


def record(args, out: Path, narr_wavs: list[Path | None], rep_wavs: list[Path]) -> dict:
    from playwright.sync_api import sync_playwright

    dur = [wav_duration(p) if p else 0.0 for p in narr_wavs]
    rep_dur = [wav_duration(p) for p in rep_wavs]
    narr = Narration(dur)
    marks: dict[str, float] = {}
    agent = AgentTrack()
    ws_log: list[dict] = []
    rep_at: list[float] = []  # epoch each rep line starts (mic mode)
    speaking = {"on": False, "ends": 0}

    def on_frame(payload) -> None:
        now = time.time()
        if not isinstance(payload, str):
            return
        msg = json.loads(payload)
        if msg.get("type") == "agent_audio":
            agent.add(now, base64.b64decode(msg["pcm16_b64"]), msg.get("sample_rate") or 24000)
            return
        if msg.get("type") == "agent_speaking":
            speaking["on"] = msg.get("state") == "start"
            speaking["ends"] += 0 if speaking["on"] else 1
        ws_log.append({"t": now, **{k: v for k, v in msg.items() if k in ("type", "state", "section_number", "text", "final", "stt", "voice", "message")}})

    mic_wav = out / "fake_mic.wav"
    plan = {}
    if args.mode == "mic":
        # rep line offsets from mic start, sized from narration + agent read-back lengths
        contract = {c["section_number"]: c for c in load_demo_contract()}
        a31 = wav_duration(tts(build_alert_text(contract["3.1"]), AGENT_STANDIN_VOICE, 24000, out / "cache"))
        plan["rep0"] = 1.0
        plan["rep1"] = plan["rep0"] + rep_dur[0] + 0.5 + dur[6] + 0.6 + dur[7] + 0.3
        agent1_end = plan["rep1"] + rep_dur[1] + LATENCY_S + a31
        plan["rep2"] = agent1_end + 0.4 + dur[9] + 0.3 + dur[10] + GAP_AFTER_AGENT_S
        plan["rep3"] = plan["rep2"] + rep_dur[2] + 0.4 + dur[11] + 0.3
        total = plan["rep3"] + rep_dur[3] + 60
        buf = bytearray(int(total * 16000) * 2)
        for i, p in enumerate(rep_wavs):
            place_into(buf, read_pcm(p)[0], 16000, plan[f"rep{i}"])
        write_wav(mic_wav, buf, 16000)
        log("mic plan (s from mic start):", {k: round(v, 1) for k, v in plan.items()})

    chrome_args = ["--autoplay-policy=no-user-gesture-required", "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"]
    if args.mode == "sim":  # silent mic: Chromium's default fake device beeps, which STT would transcribe
        write_wav(mic_wav, bytes(32000), 16000)
    chrome_args.append(f"--use-file-for-fake-audio-capture={mic_wav.as_posix()}")
    if args.mode == "mic":
        chrome_args[-1] += "%noloop"

    base = f"http://127.0.0.1:{args.port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not args.headed, args=chrome_args)
        ctx = browser.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=1,
                                  record_video_dir=str(out / "raw"), record_video_size={"width": 1920, "height": 1080},
                                  permissions=["microphone"])
        ctx.add_init_script("""
          const _gum = navigator.mediaDevices && navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
          if (_gum) navigator.mediaDevices.getUserMedia = async (c) => { const s = await _gum(c); window.__micStart = Date.now(); return s; };
        """)
        video_epoch0 = time.time()
        page = ctx.new_page()
        page.on("pageerror", lambda e: log("PAGEERROR:", str(e)[:300]))
        page.on("console", lambda m: log("console", m.type + ":", m.text[:200]) if m.type in ("error", "warning") else None)
        page.on("websocket", lambda ws: ws.on("framereceived", on_frame) if "/ws/session/" in ws.url else None)

        def hold(s: float) -> None:
            if s > 0:
                page.wait_for_timeout(int(s * 1000))

        def hold_until(epoch: float) -> None:
            hold(epoch - time.time())

        def wait_for(pred, timeout: float, what: str) -> bool:
            end = time.time() + timeout
            while time.time() < end:
                if pred():
                    return True
                page.wait_for_timeout(50)
            log(f"WARNING: timed out waiting for {what}")
            return False

        def speak(idx: int, mark: str | None = None, avoid_agent: bool = False) -> float:
            """Place narration idx now-ish; return epoch it ends (for holds)."""
            anchor_name, delay, avoid = BEATS[idx]
            anchor = marks.get(mark or anchor_name, time.time())
            avoid_iv = [tuple(iv) for iv in agent.intervals] if (avoid or avoid_agent) else []
            return narr.place(idx, anchor, delay, avoid_iv) + dur[idx]

        def alerts() -> list[dict]:
            return [m for m in ws_log if m["type"] == "alert"]

        def agent_done(n_alerts_before_end: int) -> bool:
            return speaking["ends"] >= n_alerts_before_end and not speaking["on"] and time.time() > agent.cursor + 0.2

        # -- landing ----------------------------------------------------------
        page.goto(base + "/")
        page.get_by_role("button", name="Try the live demo").first.wait_for()
        hold(0.8)
        marks["landing"] = time.time()
        # title card precedes the take: narration 0 runs TITLE_S - 0.4 s into the landing hold
        hold(max(3.0, dur[0] + 0.4 - TITLE_S) + 0.6)

        marks["how"] = time.time()
        page.evaluate("document.getElementById('how-it-works').scrollIntoView({behavior:'smooth', block:'start'})")
        hold_until(speak(1) + 0.8)

        page.evaluate("window.scrollTo({top:0, behavior:'smooth'})")
        hold(1.0)
        page.get_by_role("button", name="Try the live demo").first.click()
        hold(1.2)

        # -- setup ------------------------------------------------------------
        demo_btn = page.get_by_role("button", name="Use the demo contract")
        demo_btn.wait_for()
        marks["setup"] = time.time()
        hold(0.8)
        demo_btn.click()
        hold_until(speak(3) + 0.6)

        marks["clauses"] = time.time()
        end4 = speak(4)
        while time.time() < end4:
            page.mouse.wheel(0, 90)
            hold(0.45)
        hold(0.8)

        consent = page.get_by_text("Everyone on the call has been told").first
        consent.scroll_into_view_if_needed()
        hold(0.5)
        marks["consent"] = time.time()
        end5 = speak(5)
        hold(1.0)
        consent.click()
        hold_until(end5 + 0.5)
        page.get_by_role("button", name="Start the call").click()

        # -- cockpit ----------------------------------------------------------
        wait_for(lambda: any(m["type"] == "status" for m in ws_log), 30, "WS status")
        status = next(m for m in ws_log if m["type"] == "status")
        log("status:", status)
        if args.server == "live" and (status.get("stt") != "connected" or status.get("voice") != "connected"):
            log("WARNING: live upstreams not connected; this take will not show the alert beat")
        marks["cockpit"] = time.time()

        if args.mode == "mic":
            wait_for(lambda: page.evaluate("window.__micStart || 0") > 0, 15, "mic capture start")
            mic0 = (page.evaluate("window.__micStart || 0") / 1000.0) or time.time()
            mic0 += args.mic_offset
            rep_at = [mic0 + plan[f"rep{i}"] for i in range(4)]
            rep_iv = [(rep_at[i], rep_at[i] + rep_dur[i]) for i in range(4)]
            marks["rep0_end"] = rep_iv[0][1]
            marks["n7"] = rep_at[1] - dur[7] - 0.3
            marks["n11"] = rep_at[3] - dur[11] - 0.3
            speak(6)
            speak(7)
            wait_for(lambda: len(alerts()) >= 1, rep_iv[1][1] - time.time() + 25, "alert 1")
        else:
            rep_iv = []

            def type_line(i: int) -> None:
                box = page.locator("#cc-sim")
                box.click()
                box.press_sequentially(REP_LINES[i], delay=25)
                box.press("Enter")

            hold(1.5)
            type_line(0)
            marks["rep0_end"] = time.time()
            hold_until(speak(6) + 0.4)
            marks["n7"] = time.time()
            hold_until(speak(7))
            type_line(1)
            wait_for(lambda: len(alerts()) >= 1, 25, "alert 1")

        if alerts():
            marks["alert1"] = alerts()[0]["t"]
            speak(8)
            wait_for(lambda: agent_done(1), 40, "agent read-back 1")
        marks["agent1_end"] = max(time.time(), agent.cursor)
        speak(9)
        end10 = speak(10)

        if args.mode == "mic":
            wait_for(lambda: len(alerts()) >= 2, rep_iv[3][1] - time.time() + 25, "alert 2")
            speak(11)
        else:
            hold_until(end10 + 0.8)
            type_line(2)
            hold(1.2)
            marks["n11"] = time.time()
            hold_until(speak(11))
            type_line(3)
            wait_for(lambda: len(alerts()) >= 2, 25, "alert 2")
        if len(alerts()) >= 2:
            marks["alert2"] = alerts()[1]["t"]
            wait_for(lambda: agent_done(2), 40, "agent read-back 2")
        hold(4.5)  # narration 11 is queued behind the whole read-back; don't open the ask on top of it

        # ask §4.2. Two stacked alerts make the page taller than 1080, so keep
        # the top bar + orb in frame, then pan down to the watchlist afterwards.
        page.evaluate("window.scrollTo({top:0, behavior:'smooth'})")
        hold(0.8)
        page.evaluate("document.getElementById('cc-ask').focus({preventScroll:true})")
        marks["ask_focus"] = time.time()
        hold_until(speak(12) + 0.2)
        page.select_option("#cc-ask", "4.2")
        page.evaluate("window.scrollTo(0, 0)")
        marks["ask"] = time.time()
        ends_before = speaking["ends"]
        wait_for(lambda: speaking["ends"] > ends_before and agent_done(0), 40, "agent answer 4.2")
        marks["agent3_end"] = max(time.time(), agent.cursor)
        end13 = speak(13)
        hold(1.0)
        page.evaluate("window.scrollTo({top:document.body.scrollHeight, behavior:'smooth'})")  # §4.2 now "Referenced"
        hold_until(end13 + 0.8)
        page.evaluate("window.scrollTo({top:0, behavior:'smooth'})")
        hold(1.0)

        page.get_by_role("button", name="End call").click()
        marks["end_call"] = time.time()
        page.locator("#report-title").wait_for(timeout=15000)
        marks["report"] = time.time()
        end15 = speak(15)
        hold(3.0)  # score ring counts up
        while time.time() < end15 + 1.0:  # pan to the timeline + facts row (cost, calls, errors)
            page.mouse.wheel(0, 70)
            hold(0.4)
        hold(1.5)
        marks["take_end"] = time.time()

        video = page.video
        ctx.close()
        browser.close()
        raw_video = Path(video.path())

    return {
        "video_epoch0": video_epoch0 + args.av_offset,
        "raw_video": str(raw_video),
        "marks": marks,
        "rep_at": rep_at,
        "ws_log": ws_log,
        "agent_intervals": agent.intervals,
        "agent_chunks": [(t, rate) for t, _pcm, rate in agent.chunks],
        "_agent": agent,
        "_rep_iv": rep_iv,
    }


# ------------------------------------------------------------- assembly ----
CARD_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:Manrope;font-weight:700 800;src:url('%(font)s') format('woff2')}
html,body{margin:0;width:1920px;height:1080px;overflow:hidden;background:#0f172a;color:#f8fafc;font-family:Manrope,'Segoe UI',sans-serif}
body{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:36px;
 background:radial-gradient(900px 520px at 50%% 42%%,rgba(99,102,241,.28),transparent 70%%),#0f172a}
.mark{display:flex;align-items:center;gap:18px;font-size:44px;font-weight:800;letter-spacing:-.02em}
.dot{width:22px;height:22px;border-radius:50%%;background:#22d3ee;box-shadow:0 0 40px #22d3ee}
h1{margin:0;font-size:96px;line-height:1.04;font-weight:800;letter-spacing:-.045em;text-align:center;max-width:1760px}
h1 em{font-style:normal;color:#818cf8}
p{margin:0;font-size:30px;color:#94a3b8;text-align:center;max-width:1700px;line-height:1.35}
.url{font-size:30px;color:#22d3ee;letter-spacing:.01em}
</style></head><body>%(body)s</body></html>"""


def render_cards(out: Path) -> tuple[Path, Path]:
    from playwright.sync_api import sync_playwright

    font = (ROOT / "frontend/node_modules/@fontsource/manrope/files/manrope-latin-800-normal.woff2").as_uri()
    cards = {
        "title": '<div class="mark"><span class="dot"></span>ClauseCatcher</div>'
                 "<h1>Sales reps go off-script.<br><em>Contracts don't.</em></h1>",
        "end": '<div class="mark"><span class="dot"></span>ClauseCatcher</div>'
               "<h1>The correction the rep <em>actually hears.</em></h1>"
               "<p>Live call &rarr; AssemblyAI Streaming STT &rarr; contradiction check &rarr; AssemblyAI Voice Agent reads the clause verbatim</p>"
               '<p class="url">github.com/ishal1410/clausecatcher</p>',
    }
    paths = []
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        for name, body in cards.items():
            html = out / f"card_{name}.html"
            html.write_text(CARD_HTML % {"font": font, "body": body}, encoding="utf-8")
            pg.goto(html.as_uri())
            pg.wait_for_timeout(300)
            png = out / f"card_{name}.png"
            pg.screenshot(path=str(png))
            paths.append(png)
        b.close()
    return paths[0], paths[1]


def assemble(args, out: Path, take: dict, narr_wavs: list[Path | None], rep_wavs: list[Path]) -> Path:
    marks = take["marks"]
    e0 = take["video_epoch0"]
    trim = marks["landing"] - e0 - 0.2
    to_final = lambda epoch: TITLE_S + (epoch - e0 - trim)  # noqa: E731

    dur = [wav_duration(p) if p else 0.0 for p in narr_wavs]
    app_dur = marks["take_end"] - e0 - trim
    rep_iv = [(to_final(a), to_final(b)) for a, b in take["_rep_iv"]]
    agent_iv = [(to_final(a), to_final(b)) for a, b in take["agent_intervals"]]

    # final narration placement on the real (measured) timeline
    narr = Narration(dur)
    starts: dict[int, float] = {}
    for idx, beat in enumerate(BEATS):
        if beat is None or not narr_wavs[idx]:
            continue
        name, delay, avoid = beat
        if name == "title":
            anchor = 0.0
        elif name == "endcard":
            anchor = TITLE_S + app_dur
        elif name in marks:
            anchor = to_final(marks[name])
        else:
            log(f"beat {idx}: mark {name!r} missing (event never happened); narration skipped")
            continue
        starts[idx] = narr.place(idx, anchor, delay, rep_iv + (agent_iv if avoid else []))
    app_needed = max((starts[i] + dur[i] for i in starts if i != 16), default=0) + 1.0 - TITLE_S
    app_dur = max(app_dur, app_needed)
    if 16 in starts:
        starts[16] = TITLE_S + app_dur + BEATS[16][1]
    end_s = max(4.0, (dur[16] if 16 in starts else 0) + BEATS[16][1] + END_PAD_S)
    total = TITLE_S + app_dur + end_s
    log(f"timeline: title {TITLE_S}s + take {app_dur:.1f}s + end {end_s:.1f}s = {total:.1f}s")

    agent_buf = bytearray(int((total + 1) * 24000) * 2)
    for (t, pcm, rate) in take["_agent"].chunks:
        assert rate == 24000, rate
        place_into(agent_buf, pcm, 24000, to_final(t))
    write_wav(out / "agent_voice.wav", agent_buf, 24000)
    rep_buf = bytearray(int((total + 1) * 16000) * 2)
    for i, p in enumerate(rep_wavs if take["_rep_iv"] else []):
        place_into(rep_buf, read_pcm(p)[0], 16000, rep_iv[i][0])
    write_wav(out / "rep_voice.wav", rep_buf, 16000)

    title_png, end_png = render_cards(out)
    inputs = ["-loop", "1", "-framerate", "30", "-t", f"{TITLE_S}", "-i", str(title_png),
              "-i", take["raw_video"],
              "-loop", "1", "-framerate", "30", "-t", f"{end_s:.3f}", "-i", str(end_png),
              "-i", str(out / "agent_voice.wav"), "-i", str(out / "rep_voice.wav")]
    fl = [
        f"[0:v]fps=30,format=yuv420p,fade=t=out:st={TITLE_S - 0.35}:d=0.35[v0]",
        f"[1:v]tpad=stop_mode=clone:stop_duration=60,trim=start={trim:.3f}:end={trim + app_dur:.3f},setpts=PTS-STARTPTS,"
        f"fps=30,scale=1920:1080,setsar=1,format=yuv420p,fade=t=in:st=0:d=0.35[v1]",
        "[2:v]fps=30,format=yuv420p,fade=t=in:st=0:d=0.5[v2]",
        "[v0][v1][v2]concat=n=3:v=1:a=0[v]",
        "[3:a]aresample=48000,volume=0.8[ag]",
        "[4:a]aresample=48000,volume=0.9[rp]",
        "[ag][rp]amix=inputs=2:normalize=0[app]",
    ]
    narr_labels = []
    for k, idx in enumerate(sorted(starts)):
        inputs += ["-i", str(narr_wavs[idx])]
        ms = int(starts[idx] * 1000)
        fl.append(f"[{5 + k}:a]aresample=48000,adelay={ms}:all=1[n{k}]")
        narr_labels.append(f"[n{k}]")
    fl.append(f"{''.join(narr_labels)}amix=inputs={len(narr_labels)}:normalize=0,apad,atrim=0:{total:.3f},asplit[nr1][nr2]")
    fl.append("[app]apad,atrim=0:%.3f[app2]" % total)
    fl.append("[app2][nr1]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=350[duck]")
    fl.append("[duck][nr2]amix=inputs=2:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[a]")

    final = out / "clausecatcher_demo.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(fl), "-map", "[v]", "-map", "[a]",
           "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-maxrate", "10M", "-bufsize", "20M", "-pix_fmt", "yuv420p",
           "-r", "30", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", "-t", f"{total:.3f}", str(final)]
    (out / "ffmpeg_cmd.json").write_text(json.dumps(cmd, indent=1), encoding="utf-8")
    subprocess.run(cmd, check=True)

    # timeline for frame checks
    tl = {k: round(to_final(v), 2) for k, v in marks.items()}
    tl.update({f"narr{idx}": [round(s, 2), round(s + dur[idx], 2)] for idx, s in starts.items()})
    tl["agent_intervals"] = [[round(a, 2), round(b, 2)] for a, b in agent_iv]
    tl["rep_intervals"] = [[round(a, 2), round(b, 2)] for a, b in rep_iv]
    tl["total"] = round(total, 2)
    (out / "timeline.json").write_text(json.dumps(tl, indent=1), encoding="utf-8")
    return final


# ------------------------------------------------------------------ main ----
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--server", choices=["dryrun", "live", "external"], default="dryrun",
                    help="dryrun: fake upstreams, $0. live: real keys from env (costs money). external: already running on --port")
    ap.add_argument("--i-mean-live", action="store_true", help="required with --server live")
    ap.add_argument("--mode", choices=["mic", "sim"], default="mic", help="mic: Chromium fake mic WAV (real mic path). sim: Simulate-rep-line box")
    ap.add_argument("--port", type=int, default=8801)
    ap.add_argument("--out", type=Path, default=HERE / "out")
    ap.add_argument("--build", action="store_true", help="run `npm run build` in frontend/ first")
    ap.add_argument("--headed", action="store_true")
    ap.add_argument("--av-offset", type=float, default=0.0, help="seconds; + shifts audio later relative to video")
    ap.add_argument("--mic-offset", type=float, default=0.3, help="seconds; fake-mic audio reaching the app vs getUserMedia resolve (dry runs measured 0.15-0.55)")
    args = ap.parse_args()
    if args.server == "live" and not args.i_mean_live:
        sys.exit("--server live spends real AssemblyAI/Gemini credit; add --i-mean-live")
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "cache"

    if args.build:
        subprocess.run("npm run build", cwd=ROOT / "frontend", shell=True, check=True)
    assert (ROOT / "frontend/dist/index.html").exists(), "frontend/dist missing; run with --build"

    lines = parse_voiceover(ROOT / "docs/submission/DEMO_SCRIPT.md")
    log("rendering narration + rep voices")
    narr_wavs = [tts(t, NARRATOR_VOICE, 48000, cache) if t else None for t in lines]
    rep_wavs = [tts(t, REP_VOICE, 16000, cache, rate_pct="+5%") for t in REP_LINES]

    env_extra = {}
    if args.server == "dryrun":
        from dryrun_server import agent_wav_name  # scrubs paid keys from this process; dry run only

        contract = {c["section_number"]: c for c in load_demo_contract()}
        agent_dir = out / "dryrun_agent"
        agent_dir.mkdir(exist_ok=True)
        for text in (build_alert_text(contract["3.1"]), build_alert_text(contract["6.1"]), build_clause_answer_text(contract["4.2"])):
            src = tts(text, AGENT_STANDIN_VOICE, 24000, cache)
            shutil.copy(src, agent_dir / agent_wav_name(text))
        env_extra = {"DEMO_REP_LINES": json.dumps(REP_LINES), "DEMO_AGENT_AUDIO_DIR": str(agent_dir)}

    proc = None if args.server == "external" else start_server(args.server, args.port, env_extra, out / "server.log")
    try:
        take = record(args, out, narr_wavs, rep_wavs)
    finally:
        if proc:
            proc.terminate()
            proc.wait(timeout=10)
    (out / "take.json").write_text(json.dumps({k: v for k, v in take.items() if not k.startswith("_")}, indent=1, default=str), encoding="utf-8")
    final = assemble(args, out, take, narr_wavs, rep_wavs)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size:stream=codec_name,width,height",
                            "-of", "json", str(final)], capture_output=True, text=True).stdout
    log("done:", final)
    log(probe)


if __name__ == "__main__":
    main()
