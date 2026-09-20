# demo.mp4 — what's in it, what was measured, how to upload

**File:** `docs/submission/demo.mp4` · 4:20.8 (260.8 s) · 1920×1080 · 30 fps · H.264 High / AAC-LC 48 kHz stereo · 25.6 MB
lablab limit is 5:00. The rubric scores a video under 3:00 in its *2 - Limited* band, so the shipped cut
is 4:20: the 2:54 product take, then three narrated closing cards before the end card.

Produced by `tools/demo_video/record.py --server live --i-mean-live` (Playwright take of the real app +
edge-tts narration + ffmpeg assembly), from the shot list in `DEMO_SCRIPT.md`.

## Everything on screen is a real run

The cockpit footage is one continuous live session against the real upstreams — `ASSEMBLYAI_API_KEY`
for Streaming STT and the Voice Agent, `CLAUSECATCHER_CLAIM_CHECK=gemini` for the contradiction check.
Nothing is simulated, staged, or re-timed:

- **Transcript** — real AssemblyAI Streaming STT of the rep audio played into the browser's mic.
  Its own formatting is visible in the footage (`$48,000`, `10%`, `24/7`), which is why the alert
  quotes read that way rather than matching the spoken words character for character.
- **Alerts** — real Gemini verdicts. Two contradictions, on §3.1 (pricing) and §6.1 (support SLA);
  §4.2 and §5.3 were checked and held.
- **Spoken correction** — real AssemblyAI Voice Agent audio, captured off the session WebSocket and
  laid back on the timeline at the moment it arrived. `READ VERBATIM 2/2` and the "Spoken verbatim"
  badges are the app's own post-speech check, not a caption.
- **Report** — the real end-of-call report, including the real cost meter.

## Beat map (final-video timecodes)

| Time | What |
|---|---|
| 0:00 | Title card — "Sales reps go off-script. Contracts don't." |
| 0:03 | Landing hero |
| 0:09 | "How it works" strip: Streaming STT → contradiction check → spoken correction |
| 0:21 | Setup screen |
| 0:24 | Demo contract loaded, 4 clauses quoted from the PDF |
| 0:38 | Consent checked, call starts |
| 0:42–1:00 | Live call, clean lines transcribed, nothing fires |
| 1:00 | Rep: "We can also do a 10% automatic discount for a client like this." |
| **1:09** | **Alert on §3.1 with the literal clause** |
| 1:09–1:23 | Voice Agent reads §3.1 aloud, verbatim |
| 1:23 | "Spoken verbatim" badge, READ VERBATIM 1/1 |
| 1:43 | Rep: "And support is available 24/7 on the Standard plan." |
| 1:50 | Second alert on §6.1, read aloud the same way |
| 2:09 | Manager opens the command bar; 2:13 asks for §4.2, agent speaks the clause |
| 2:32 | End call → report: 60% of lines on-contract, timeline, clauses checked, call facts |
| 2:44 | End card |

## The closing cards (added 2026-09-20)

The product take ends at 2:54. lablab's Presentation rubric puts a numeric floor at 3:00 - anything
shorter scores in its *2 - Limited* band - and its 4-5 bands ask for market analysis, competitive
positioning and future plans, none of which the take says. `tools/demo_video/append_closing.py`
splices three narrated cards in at **163.06 s** (`take_end`, the end-card boundary from
`docs/evidence/demo_take_timeline.json`), so they land before the end card, not after it. The live
footage is not re-cut or re-timed.

| Time | Card | What it claims |
|---|---|---|
| 2:43 | Market | $1.6B-$32B published 2026 conversation-intelligence estimates; 1.59M US reps; $0.6B-$1.1B at $30-60 a seat; 292k-rep beachhead |
| 3:19 | Why this is different | post-call scoring against a generic playbook vs. during-call against this contract; $0.08-$0.15 per call |
| 3:47 | What's next | browser-mic hardening then Zoom/Meet audio, CRM write-back, multi-contract accounts, paid pilot |
| 4:09 | End card | unchanged |

Where the market numbers come from, so they can be defended or dropped:

- **$1.6B-$32B.** Published 2026 estimates for "conversation intelligence software" really do span an
  order of magnitude, because each firm draws the category differently. The card shows the spread
  rather than quoting the flattering end; the narration says why.
- **1.59M US wholesale and manufacturing sales reps.** BLS Occupational Outlook Handbook, 2025
  employment: 1.3M except-technical-and-scientific + 292k technical and scientific.
  https://www.bls.gov/ooh/sales/wholesale-and-manufacturing-sales-representatives.htm
- **$0.6B-$1.1B.** 1.59M x $30-60 x 12. The per-seat price is a hypothesis, labelled as one on the
  card and in the narration. It has not been tested with a buyer.

Audio is level-matched, not just appended: each narration is loudnorm'd to the same I=-16 target the
original mix used. Measured on the shipped file, mean volume is -19.3 to -20.0 dBFS across the three
cards against -21.4 dBFS for the footage, with identical -4.5 dBFS peaks.

## Measured in the take that shipped

| Measurement | Value |
|---|---|
| Rep's sentence ends → alert card on screen (§3.1) | **5.6 s** |
| Rep's sentence ends → alert card on screen (§6.1) | **4.0 s** |
| STT final turn → alert (§3.1 / §6.1) | 5.35 s / 3.68 s |
| Voice Agent read-back length (§3.1) | 13.5 s, continuous |
| Verbatim status | 2/2 alerts read verbatim; §4.2 answer also spoken |
| Claim checks / errors | 5 / 0 |
| Transcript lines | 5 |
| Est. API cost, whole call (app's own meter) | **$0.1535** |
| Call duration in the take | 1:52 |

The first live take measured 6.2 s / 4.3 s and $0.1466 — same shape, so the honest headline is
"about 4–6 seconds" and "about 15 cents a call".

Two script/copy claims were corrected to match these measurements rather than the other way round:

- `DEMO_SCRIPT.md` said "Two seconds later, ClauseCatcher flags it" → now "Seconds later, it flags
  the line and cites the section."
- The landing page's "Measured on our demo calls" row said `~2 s` and `~$0.12` → now `~5 s` and
  `~$0.15` (`frontend/src/components/landing/Landing.tsx`). The old numbers would have been visible
  on screen 50 seconds before the video's own footage contradicted them.

The ~5 s gaps of silence before each alert are the real claim-check latency. They were left in;
cutting them would have misrepresented the system's speed.

## Upload to Vimeo

1. vimeo.com → **New video → Upload** → `docs/submission/demo.mp4`.
2. Title: `ClauseCatcher — live contract contradiction catching (AssemblyAI)`.
3. **Privacy → Who can watch this? → "Anyone"** (not "Only people with the private link", not
   "Hide from Vimeo" — lablab judges must reach it without a login).
4. Leave "Anyone can embed" on; no password.
5. Wait for transcoding to finish, then open the video page and copy the **clean** URL —
   `vimeo.com/<id>` only. Strip any `?share=copy`, `/settings`, hash, or review-link suffix.
6. Paste that URL into the lablab submission's video field and confirm it plays in a logged-out
   private window before submitting.

Do not upload to YouTube.

## Rebuilding this video

```bash
cd frontend && npm run build          # the take records the built dist, not the dev server
python tools/demo_video/record.py --server dryrun --port 8803 --out <dir>   # $0 rehearsal
python tools/demo_video/record.py --server live --i-mean-live --port 8803 --out <dir>  # ~$0.15
```

Two things worth knowing before a re-run:

- `record.py` imports `dryrun_server` lazily on purpose: that module scrubs the paid keys out of
  `os.environ` at import time, so a module-level import silently breaks `--server live`.
- Playwright's recorder starts ~1.6 s after the context is created, so raw takes come out with the
  video leading the narration by that much. This cut corrects it; use `--av-offset 1.65` on the next
  take to get it right in one pass, and re-measure (it is a timing property of the box, not a constant).
