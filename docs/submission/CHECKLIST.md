# ClauseCatcher: lablab.ai submission checklist

Deadline: **Wed Sep 30 2026, 11:00 AM EDT** (15:00 UTC). Aim to submit by Sep 29 so there's time to fix upload problems.

Sources (read 2026-09-17):
- Event page ("What to submit", judging criteria, rules): https://lablab.ai/ai-hackathons/assemblyai-voice-agent-hackathon
- Field limits and formats: https://lablab.ai/delivering-your-hackathon-solution

Worth knowing from the event page: "5 winners · $1,000 cash + $1,000 in API credits each". No prize is ranked above the others, so the target is a top-5 finish. Judging criteria: Application of Technology, Presentation, Business Value, Originality. Rules: "Submissions must be original and MIT-compliant."

Form text for every field: `docs/submission/LABLAB_SUBMISSION.md`.

## Requirements

| # | Requirement (official wording) | Status | What you do |
|---|---|---|---|
| 1 | Enroll on lablab.ai and join the lablab.ai Discord ("Please register for both in order to participate") | needs user login | On the event page, click **Enroll** at the bottom. Join https://discord.gg/lablabai. |
| 2 | Team of 1-6 people | needs user login | A solo team is fine. After enrolling, create the team from the event dashboard. Only a logged-in account can see the exact button name. |
| 3 | Project title | done | Paste `ClauseCatcher`. |
| 4 | Short description, "up to 255 characters" | done (235 chars) | Paste it from LABLAB_SUBMISSION.md. |
| 5 | Long description, "at least 100 words" | done (~760 words) | Paste the whole code block. If the editor supports headings, turn the CAPS headings into headings. |
| 6 | Technology & category tags | needs user login | Pick from the tag picker, in the priority order in LABLAB_SUBMISSION.md. Only use tags the picker actually offers. |
| 7 | Cover image: "PNG or JPG", "Recommended 16:9" | done | Upload `docs/submission/cover.png` (1920x1080 PNG). |
| 8 | Video presentation: "A maximum 5-minute video in MP4 format" | recorded, upload pending | `docs/submission/demo.mp4` is shipped (2:54, 1920x1080, 22.4 MB; see `DEMO_NOTES.md`). Two things left: pad it to 3:30-4:30 first (lablab's rubric scores anything under 3:00 in its lower band, see `COMPLIANCE.md` finding 9 and the padding plan in `DEMO_NOTES.md`), then upload to Vimeo (privacy "Anyone") and replace `[VIMEO_URL]` with the plain vimeo.com/<id> link. |
| 9 | Slide presentation, "PDF format" | done (upload pending) | Upload `docs/submission/ClauseCatcher.pdf` (10 pages). Both it and `SLIDES.md` say 136 tests, which matches the suite. The "81 tests" this row used to warn about appears nowhere in the repo. |
| 10 | Public GitHub repository | done | https://github.com/ishal1410/clausecatcher is public (HTTP 200) and everything is pushed: `git rev-parse HEAD origin/main` matched at `a629536` on 2026-09-17, with a clean working tree. Open the repo logged out once and confirm the README images render. |
| 11 | Demo application platform | done (text) | Type or pick `Render`. If the picker only offers Streamlit, Replit or Vercel, choose "Other" if it exists. |
| 12 | Application URL ("a link that allows interaction with your prototype") | pending | Deploy using `docs/DEPLOY.md`: Render dashboard, then **New +**, then **Web Service**, connect the GitHub repo, and use Docker from `render.yaml`. Set `ASSEMBLYAI_API_KEY` and `GEMINI_API_KEY` in Render's Environment tab. Open the URL and drive a real alert. Then replace `[APP_URL]`. |
| 13 | "MIT-compliant" submission | **done** | MIT `LICENSE` added at repo root; README License section updated. |
| 14 | Browser-mic live path verified end to end | done | Verified 2026-09-17 by `tools/e2e_mic/run_mic_e2e.py`: a real browser, getUserMedia, an AudioWorklet and 16 kHz PCM16 frames through the full pipeline, 17 of 17 live-path checks. The capture device was Chromium's fake audio device playing a WAV, not a physical microphone, and the README and LABLAB_SUBMISSION say so. Physical mic hardware is still untested. Log: `docs/evidence/e2e_mic_run-live.json`. |
| 15 | Submit | needs user login | On the event dashboard, open your team's project submission form. Paste the fields, upload the cover, video and PDF, and submit. Afterwards, open the public project page and check that every field shows up. |

## Final order of work (with time estimates)

Done already: MIT LICENSE (#13), everything pushed (#10), the video recorded (#8),
the deck and cover rebuilt with the corrected numbers (#7, #9), the browser-mic path
verified (#14). What is left:

1. Deploy to Render and smoke-test a live alert (#12): 45 min
2. Pad the video to 3:30-4:30 and upload it to Vimeo (#8): 1-2 h — the plan is in `DEMO_NOTES.md`
3. Skim the slide PDF once before uploading (#9): 5 min
4. Fill in the form and submit (#3-7, #11, #15): 20 min
5. Wake the Render app right before judging: 1 min

## 60 seconds before judging

Run this every time, in this order, starting ~5 minutes before any judging
slot or live demo. Set `URL` once. Risks covered: `docs/submission/RISKS.md`
R-01, R-03, R-04, R-09, R-10.

```bash
URL=<your Render URL>    # no trailing slash; nothing is deployed yet
```

**1. Wake it and prove it's awake (~40 s of the 60).**

```bash
time curl -s $URL/api/health          # first hit: may take ~60 s (cold start)
time curl -s $URL/api/health          # second hit: must be fast
```

Both must print `{"status":"ok"}`. The second call must come back in well
under a second — that is the proof it is actually warm, not the first one.
Then open `$URL` in a browser so the static frontend and fonts are warm too,
and **leave that tab open**; reload it every ~10 minutes until judging starts,
or Render sleeps it again after 15 idle minutes.

**2. Prove the WebSocket is not 403 (~5 s).** Green health with a rejected
socket is the failure that looks like a broken app.

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  -H "Connection: Upgrade" -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Origin: $URL" $URL/ws/session/probe
```

Must print `101`. If it prints `403`, `CLAUSECATCHER_ALLOWED_ORIGINS` in the
Render Environment tab does not exactly equal `$URL` — fix it (no trailing
slash), save, wait for the redeploy, re-run.

**3. Confirm the budget and kill-switch values (~10 s).** Render dashboard →
service → **Environment**. Read, do not edit:

| Variable | Must be | Why |
|---|---|---|
| `CLAUSECATCHER_PAID_DISABLED` | `0` | `1` means no alerts fire at all. |
| `CLAUSECATCHER_BUDGET_USD` | `3` | `0` would refuse every AssemblyAI socket. |
| `CLAUSECATCHER_MAX_LIVE_WS` | `2` | `0`/`1` can lock a judge out with "demo busy". |
| `CLAUSECATCHER_MAX_CHECKS` | `40` | Per-session claim-check cap. |
| `CLAUSECATCHER_MAX_GEMINI_CALLS` | `300` | Process-wide Gemini cap. |
| `CLAUSECATCHER_ALLOWED_ORIGINS` | exactly `$URL` | See step 2. |

While you're there, glance at the AssemblyAI and Gemini dashboards. If usage
jumped overnight, set `CLAUSECATCHER_PAID_DISABLED=1` and rotate the key —
but know that turns the alerts off, so only do it if the alternative is a
dead key mid-demo.

**4. Confirm the video link plays (~5 s).** Open the exact Vimeo URL you put
in the submission form in a **private / logged-out** window. It must start
playing without a login or password prompt — privacy must be "Anyone", not
"Only me" or "People with the password". A link that only works while you're
logged in is the most common silent submission failure.

**If you have 60 more seconds**, drive one real alert: **Try the live demo** →
**Use the demo contract** → tick consent → **Start the call** → paste into
*Simulate rep line*: "We can absolutely do a verbal twenty percent discount
and add ten extra seats today, no paperwork needed." A red §3.1 card must
appear and the clause must be read aloud. That is the only check that proves
AssemblyAI, Gemini and the voice leg are all alive at once.
