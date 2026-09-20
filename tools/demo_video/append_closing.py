"""append_closing.py - add the narrated closing cards to a finished demo.mp4.

Why this exists: lablab's Presentation rubric scores a video under 3:00 as a
2 out of 5, and its 4-5 bands want market analysis, competitive positioning
and future plans. The shipped take is 2:54 of product footage and says none
of those things. Rather than re-record the live call (~$0.15 and a new set of
measurements to re-verify), this splices three narrated cards in front of the
existing end card.

Everything here is free: cards are Playwright screenshots of the same
CARD_HTML the take uses, narration is edge-tts through record.py's cached
`tts`, and the splice is one ffmpeg pass.

    python tools/demo_video/append_closing.py \
        --in docs/submission/demo.mp4 --out docs/submission/demo.mp4

The split point is the end-card boundary from the take's own timeline
(`take_end` in docs/evidence/demo_take_timeline.json), so the cards land
before "The correction the rep actually hears" rather than after it.

Numbers on the market card are sourced, not invented:
  - conversation-intelligence market range: published 2026 estimates differ by
    an order of magnitude depending on how the category is drawn, so the card
    shows the range instead of picking the flattering end.
  - 1.59M US wholesale + manufacturing sales reps: BLS OOH, 2025 employment
    (1.3M except-technical + 292k technical/scientific).
  - The per-seat price is labelled a hypothesis, because it is one.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE))

from record import CARD_HTML, NARRATOR_VOICE, log, tts, wav_duration  # noqa: E402

LEAD_S = 0.6   # silence before each card's narration starts
TAIL_S = 0.9   # silence after it, before the cut to the next card

# (name, body html, narration). Narration is what gets spoken; the card only
# carries the numbers the ear cannot hold.
CARDS = [
    (
        "market",
        '<div class="mark"><span class="dot"></span>Market</div>'
        "<h1>Sized <em>bottom-up.</em></h1>"
        '<div class="stats">'
        '<div class="stat"><b>$1.6B&ndash;$32B</b><span>published 2026 estimates for conversation-intelligence '
        "software &mdash; the spread is how the category is drawn</span></div>"
        '<div class="stat"><b>1.59M</b><span>US wholesale &amp; manufacturing sales reps (BLS, 2025)</span></div>'
        '<div class="stat"><b>$0.6B&ndash;$1.1B</b><span>those reps at a $30&ndash;60 per-seat hypothesis</span></div>'
        "</div>"
        '<p class="url">Beachhead: the 292,000 technical &amp; scientific reps, who sell the hardest contracts</p>',
        "So who buys this. Published estimates for the conversation intelligence market run from one and a half to "
        "thirty two billion dollars, depending on how you draw the category, so we sized ours from the bottom up. "
        "The Bureau of Labor Statistics counts one point five nine million wholesale and manufacturing sales reps "
        "in the United States. At thirty to sixty dollars a seat, that is a six hundred million to one point one "
        "billion dollar serviceable market. We start with the two hundred ninety two thousand technical and "
        "scientific reps, who sell the hardest contracts.",
    ),
    (
        "different",
        '<div class="mark"><span class="dot"></span>Why this is different</div>'
        "<h1>During the call. Against <em>this</em> contract.</h1>"
        '<div class="stats">'
        '<div class="stat"><b>After</b><span>call-intelligence platforms score the recording, against a generic '
        "playbook, once the promise is already made</span></div>"
        '<div class="stat"><b>During</b><span>ClauseCatcher checks the rep against the customer\'s signed contract '
        "and reads the clause back while the call is live</span></div>"
        "</div>"
        '<p>$0.08&ndash;$0.15 of API cost per call, by the app\'s own meter, against a per-seat subscription.</p>',
        "What makes this different. Most call intelligence platforms score the recording after the call ends, "
        "against a generic sales playbook. ClauseCatcher works during the call, against this customer's signed "
        "contract, and puts the correction in the rep's ear while the sentence is still hanging in the air. The "
        "economics work because the check is cheap: eight to fifteen cents of API cost per call, by the app's own "
        "meter, against a per seat subscription.",
    ),
    (
        "next",
        '<div class="mark"><span class="dot"></span>What\'s next</div>'
        "<h1>From demo to <em>a real sales floor.</em></h1>"
        '<div class="stats">'
        '<div class="stat"><b>Audio</b><span>hardened browser-mic path, then Zoom and Google Meet call audio</span></div>'
        '<div class="stat"><b>System of record</b><span>CRM write-back, so every caught contradiction lands on the '
        "opportunity</span></div>"
        '<div class="stat"><b>Pilot</b><span>multi-contract accounts and a paid per-seat pilot with one sales '
        "team</span></div>"
        "</div>"
        '<p class="url">Open source, MIT licensed, today</p>',
        "What's next. A hardened browser microphone path, then Zoom and Google Meet call audio. C R M write-back, so "
        "every caught contradiction lands on the opportunity record instead of in a log. Multi contract accounts, "
        "and a paid per seat pilot with one real sales team. The code is open source and M I T licensed today.",
    ),
]

# Extra styling for the stat rows; CARD_HTML only knows .mark/h1/p/.url.
EXTRA_CSS = """<style>
.stats{display:flex;gap:28px;max-width:1720px;margin-top:6px}
.stat{flex:1;background:rgba(148,163,184,.10);border:1px solid rgba(148,163,184,.22);border-radius:20px;
 padding:30px 32px;display:flex;flex-direction:column;gap:12px;text-align:left}
.stat b{font-size:56px;font-weight:800;letter-spacing:-.03em;color:#f8fafc}
.stat span{font-size:25px;line-height:1.35;color:#94a3b8}
</style>"""


def render(out: Path) -> list[Path]:
    from playwright.sync_api import sync_playwright

    font = (ROOT / "frontend/node_modules/@fontsource/manrope/files/manrope-latin-800-normal.woff2").as_uri()
    pngs = []
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1920, "height": 1080})
        for name, body, _ in CARDS:
            html = out / f"close_{name}.html"
            html.write_text(CARD_HTML % {"font": font, "body": EXTRA_CSS + body}, encoding="utf-8")
            pg.goto(html.as_uri())
            pg.wait_for_timeout(350)
            png = out / f"close_{name}.png"
            pg.screenshot(path=str(png))
            pngs.append(png)
        b.close()
    return pngs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="src", default=str(ROOT / "docs/submission/demo.mp4"))
    ap.add_argument("--out", dest="dst", default=str(ROOT / "docs/submission/demo.mp4"))
    ap.add_argument("--timeline", default=str(ROOT / "docs/evidence/demo_take_timeline.json"))
    ap.add_argument("--split", type=float, default=None, help="override the end-card boundary, seconds")
    ap.add_argument("--work", default=str(ROOT / "docs/submission/_closing"))
    args = ap.parse_args()

    src, work = Path(args.src), Path(args.work)
    split = args.split
    if split is None:
        split = json.loads(Path(args.timeline).read_text(encoding="utf-8"))["take_end"]
    src_dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                    "-of", "csv=p=0", str(src)], check=True, capture_output=True,
                                   text=True).stdout.strip())
    assert 0 < split < src_dur, f"split {split} outside 0..{src_dur}"

    pngs = render(work)
    wavs = [tts(n, NARRATOR_VOICE, 24000, work / "cache") for _, _, n in CARDS]
    durs = [wav_duration(w) + LEAD_S + TAIL_S for w in wavs]
    added = sum(durs)
    total = src_dur + added
    log(f"split at {split:.2f}s | cards {' + '.join(f'{d:.1f}' for d in durs)} = {added:.1f}s "
        f"| {src_dur:.1f}s -> {total:.1f}s ({int(total // 60)}:{total % 60:04.1f})")

    inputs = ["-i", str(src)]
    for png, d in zip(pngs, durs):
        inputs += ["-loop", "1", "-framerate", "30", "-t", f"{d:.3f}", "-i", str(png)]
    for w in wavs:
        inputs += ["-i", str(w)]

    fl = [
        f"[0:v]trim=0:{split:.3f},setpts=PTS-STARTPTS,fps=30,format=yuv420p[va]",
        f"[0:a]atrim=0:{split:.3f},asetpts=PTS-STARTPTS,aresample=48000[aa]",
        f"[0:v]trim=start={split:.3f},setpts=PTS-STARTPTS,fps=30,format=yuv420p[vb]",
        f"[0:a]atrim=start={split:.3f},asetpts=PTS-STARTPTS,aresample=48000[ab]",
    ]
    for i, d in enumerate(durs):
        # fade in on the cut so the card does not slam in after live footage
        fl.append(f"[{1 + i}:v]fps=30,format=yuv420p,fade=t=in:st=0:d=0.35[cv{i}]")
        # loudnorm each narration to the same target the original mix used, so
        # the cards do not jump in level against the footage
        fl.append(f"[{1 + len(durs) + i}:a]aresample=48000,adelay={int(LEAD_S * 1000)}:all=1,"
                  f"apad,atrim=0:{d:.3f},asetpts=PTS-STARTPTS,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[ca{i}]")
    chain = "[va][aa]" + "".join(f"[cv{i}][ca{i}]" for i in range(len(durs))) + "[vb][ab]"
    fl.append(f"{chain}concat=n={len(durs) + 2}:v=1:a=1[v][a]")

    tmp = work / "demo_with_closing.mp4"
    cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(fl),
           "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
           "-maxrate", "10M", "-bufsize", "20M", "-pix_fmt", "yuv420p", "-r", "30",
           "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", str(tmp)]
    (work / "ffmpeg_cmd.json").write_text(json.dumps(cmd, indent=1), encoding="utf-8")
    subprocess.run(cmd, check=True)

    out_dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                    "-of", "csv=p=0", str(tmp)], check=True, capture_output=True,
                                   text=True).stdout.strip())
    assert abs(out_dur - total) < 1.5, f"expected ~{total:.1f}s, got {out_dur:.1f}s"
    assert 210 <= out_dur <= 270, f"{out_dur:.1f}s is outside the 3:30-4:30 rubric window"
    Path(args.dst).write_bytes(tmp.read_bytes())
    log(f"wrote {args.dst} - {out_dur:.1f}s ({int(out_dur // 60)}:{out_dur % 60:04.1f})")


if __name__ == "__main__":
    main()
