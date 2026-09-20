# ClauseCatcher — submission risk register

Scope: everything between now and the lablab.ai judging of this submission —
the app, the hosted URL, the video, the docs, and how the four judging
criteria get read. Written 2026-09-17.

Deadline: **Wed 2026-09-30, 11:00 AM EDT**. Five equal winners, no ranked
first place, so the goal is a top-5 finish: nothing here is about being
spectacular, it is about not being the submission that fails in front of a
judge.

**How to read the "mitigated in code" column:** it means a mechanism exists
in this repo and was exercised. Everything in **You must do** is manual and
nobody else will do it.

Verification behind the code claims: the Render image was built from the
repo `Dockerfile` and run locally under `--memory 512m` with only the env
vars `render.yaml` sets, then driven through the real UI with Playwright
(landing → demo contract → consent → live session → simulated rep line →
§3.1 alert + spoken clause → report). Evidence is quoted per risk below.

---

## Severity-ranked

### R-01 — Free instance is asleep when a judge clicks the link · CRITICAL · demo

Render free web services spin down *"after 15 minutes without receiving any
inbound traffic"* and take *"about one minute"* to spin back up
(<https://render.com/docs/free>). Judges arrive on their own schedule, often
days after you submit. A judge who clicks and sees a blank/loading page for
60 seconds scores Presentation on that, and may never see the app at all.

- **Mitigated in code:** nothing can fix this from inside the app — the
  container is not running. `healthCheckPath: /api/health` in `render.yaml`
  makes the wake-up deterministic once traffic arrives, and a warm container
  answers `/api/health` in well under a second (measured: healthy 7 s after
  `docker run`, 54 MB of the 512 MB limit at idle).
- **You must do:** the video is the real mitigation — a judge who cannot
  reach the app must still be able to see it work. Beyond that: run
  `docs/submission/CHECKLIST.md` § "60 seconds before judging" in the hour
  before any live session, and keep a tab on `/api/health` reloading every
  ~10 minutes during it. If you learn the judging window, wake it 5 minutes
  ahead.
- **Fallback:** if the free instance is suspended (750 instance-hours/month
  exhausted), redeploy to Northflank Sandbox — free tier, *"Always-on-compute
  – no sleeping"* (<https://northflank.com/pricing>) — see `docs/DEPLOY.md`.

### R-02 — No hosted URL at all on submission day · RESOLVED 2026-09-20 · infra

**RESOLVED 2026-09-20: live at https://clausecatcher.onrender.com**, deployed with
`tools/deploy/render_deploy.py` and verified by driving one real contradiction
through the hosted app (4.7 s). The original text follows, for the record.

As of this writing the Render account does not exist and nothing is
deployed. lablab's form asks for *"a link that allows interaction with your
prototype"*; an empty Application URL field costs you on every criterion at
once.

- **Mitigated in code:** the whole deploy path is built and rehearsed.
  `Dockerfile` builds clean (46 s `--no-cache`, 373 MB), the image runs under
  Render's 512 MB limit and passes its own `HEALTHCHECK`, and
  `tools/deploy/render_deploy.py` creates the service, sets env vars, waits
  for live, pins the origin and health-checks in one command. Its payloads
  were re-verified against the current Render API reference on 2026-09-17
  (`POST /v1/services` with `plan`/`region`/`runtime`/`envSpecificDetails`
  inside `serviceDetails`, `runtime` not the deprecated `env`, `plan: free`
  still a valid enum value, `PUT /v1/services/{id}/env-vars` replaces all
  vars and does not deploy, `POST /v1/services/{id}/deploys` with
  `deployMode: deploy_only`). `--dry-run` and `--self-test` both pass.
- **You must do:** deploy **now**, not on the 29th. Budget 20 minutes.
  A free-tier first build is 5–15 minutes and you want the failure, if there
  is one, to happen with days of slack, not hours.
- **Fallback:** `docs/DEPLOY.md` § "If Render signup fails" — Northflank
  Sandbox, or a TryCloudflare quick tunnel over the local container for a
  scheduled live demo.

### R-03 — `CLAUSECATCHER_ALLOWED_ORIGINS` set wrong → app looks broken · HIGH · infra

The WebSocket origin check compares the browser `Origin` header against the
env var exactly. Measured in the container: allowed origin → `101`, wrong
origin → `403`, missing origin → `403`. A single trailing slash is enough.
The visible symptom is the dangerous part — a 5-second error toast, then a
cockpit that says "Connecting…" forever while still echoing your typed line
into the transcript and incrementing "LINES CHECKED". It looks like a broken
product, not a misconfiguration.

- **Mitigated in code:** `render_deploy.py` pins the var to the real service
  URL automatically after the first deploy and redeploys, so the hand-typed
  version never happens on the scripted path. `server/main.py` rejects before
  `accept()`, so a bad origin costs no socket and no paid upstream.
- **You must do:** after deploying, run the WebSocket probe in
  `docs/DEPLOY.md` § "The one trap" and confirm `101`, **and** drive one real
  simulated line through the hosted UI. A green `/api/health` proves nothing
  about the socket.

### R-04 — A visitor burns the AssemblyAI credits before judging · HIGH · api

The app is public and the URL is on a public submission page. Every live call
opens a paid AssemblyAI streaming-STT socket and a paid voice socket. A
handful of curious visitors, or one person leaving a tab open, can exhaust
the free credit that the judge's own session needs.

- **Mitigated in code, and exercised:**
  `CLAUSECATCHER_MAX_LIVE_WS=2` (extra callers get "demo busy, try again
  shortly", close code 1013), `CLAUSECATCHER_SESSION_CAP_S=420` hard cap per
  call, `CLAUSECATCHER_IDLE_TIMEOUT_S=60` ends an abandoned tab,
  `CLAUSECATCHER_BUDGET_USD=3` stops opening AssemblyAI sockets once
  estimated spend passes it, `CLAUSECATCHER_MAX_CHECKS=40` per session. All
  are read at call time, so changing them in the Render dashboard takes
  effect without a code change. Verified end to end: with
  `CLAUSECATCHER_PAID_DISABLED=1` the session opens with
  `{"stt":"disabled","voice":"disabled"}`, sends *"live audio is paused for
  this demo; simulate lines instead"*, and the report comes back with
  `est_cost_usd: 0.0` — the app stays usable, it just stops spending.
- **You must do:** check the AssemblyAI dashboard the morning of the 30th and
  once more before any live judging. If usage is climbing, set
  `CLAUSECATCHER_PAID_DISABLED=1` in the Render Environment tab, save, and
  rotate the key. Know that the kill switch also disables the alerts, so only
  flip it if the alternative is a dead key during judging.

### R-05 — Single scripted run is the only evidence the thing works · HIGH · demo

Everything demonstrable today comes from one happy-path flow with one demo
contract and one rehearsed rep line. Judges scoring *Application of
Technology* discount a demo that only ever does the one thing it was filmed
doing, and a judge who improvises a different sentence and gets nothing back
reads it as fake.

- **Mitigated in code:** the claim check is a real Gemini call against the
  loaded clauses, not a scripted match — it returned §3.1 for a sentence
  ("*We can absolutely do a verbal twenty percent discount and add ten extra
  seats today, no paperwork needed*") that appears nowhere in the repo.
  151 server tests pass. Since 2026-09-20 a runtime Gemini failure also degrades
  honestly in the cockpit itself: the verdict tile reads "Not checked" rather than
  "On-contract" whenever the checker is not ready or a check has failed. The demo contract has four clauses (§3.1 pricing,
  §4.2 renewal, §5.3 retention, §6.1 SLA), so there are four independent
  things to contradict, plus "Ask a clause aloud" which reads any section
  verbatim on demand.
- **You must do:** before recording, run one contradiction against a *second*
  clause (e.g. "we can cancel mid-term whenever you want" → §4.2) and one
  sentence that is genuinely consistent, so you know the app does not just
  alert on everything. Put a second clause in the video if it fits in five
  minutes. Upload your own PDF once so you have seen the upload path work on
  the hosted instance.

### R-06 — Judge's browser blocks the microphone · HIGH · demo

The live path needs `getUserMedia` plus an AudioWorklet. That requires a
secure context (fine on `https://…onrender.com`) and an explicit permission
grant. A judge on a locked-down work laptop, in a browser with mic access
denied by policy, or on iOS Safari in a background tab, may never get audio
in. The mic path itself is verified end to end: an automated run on 2026-09-17
drove a real browser through getUserMedia, an AudioWorklet and 16 kHz PCM16
frames and passed 17 of 17 live-path checks (`docs/evidence/e2e_mic_run-live.json`).
The capture device in that run was Chromium's fake audio device playing a WAV,
so **physical microphone hardware remains untested** — which is exactly the
failure mode this risk is about.

- **Mitigated in code:** the **Simulate rep line** box is a first-class,
  labelled control in the cockpit rail, not a hidden debug hook — it sends
  the same `{"type":"transcript"}` message the real STT turn produces, so it
  exercises the identical claim-check → alert → spoken-clause path. This is
  exactly how the container was verified. If the mic fails, `useSession`
  catches it and toasts *"Microphone unavailable: … Use 'Simulate rep line'
  instead."*, and `Permissions-Policy: microphone=(self)` is set so the app
  is allowed to ask.
- **You must do:** say in the submission text and on the page that the
  simulate box exists and does the same thing — a judge who can't use a mic
  should not have to guess. Finish the real-mic verification before the 30th
  and add the measured line to the README and LABLAB_SUBMISSION.md; several
  submission texts currently promise that verification.

### R-07 — Gemini free-tier quota / rate limit during judging · MEDIUM · api

Every finalized sentence over 3 words is one Gemini call. Free-tier keys are
rate-limited per minute and per day. Hitting the limit means no alerts —
the single most important thing the demo does.

- **Mitigated in code:** `server/claim_check.py` never raises; a 429 or any
  other failure returns `verdict: "unclear"` with an error and is logged
  (*"claim_check: rate-limited or model unavailable … verdict stays
  unclear"*), the socket survives, the error counter goes into the end-of-call
  report. `CLAUSECATCHER_MAX_GEMINI_CALLS=300` bounds process-wide usage,
  `CLAUSECATCHER_MAX_CHECKS=40` bounds one session, sentences are truncated
  to 400 chars, and there is a 12 s call timeout under a 15 s outer timeout.
  The model is `gemini-*-flash-lite` — the cheapest tier.
- **You must do:** the failure is silent by design (no alert looks identical
  to "nothing contradicted"), so if alerts stop firing mid-demo, check the
  Render logs rather than improvising. Keep a second Gemini key ready to
  paste into the Environment tab.

### R-08 — AssemblyAI Voice Agent / streaming API degraded on the day · MEDIUM · api

Two AssemblyAI services are on the critical path (streaming STT in, voice out).
Either can be slow or down; it is the hackathon's sponsor API and everyone's
demo is hitting it that week.

- **Mitigated in code:** both are set up concurrently and defensively —
  `_setup_stt` / `_setup_voice` each catch everything, mark themselves
  `"error"`, and the session continues. A dead voice service still produces
  the on-screen alert card with the literal clause text (the alert JSON is
  sent before and independently of the speech). A dead STT service still
  leaves the simulate seam working. The status frame tells the UI exactly
  which legs are up, and the top bar renders it. Speech failures are caught
  per-utterance and drained with a 5 s timeout on call end.
- **You must do:** if the voice leg is down during a live demo, say so and
  keep going — the alert card is the substance, the spoken clause is the
  flourish. Do not restart the app mid-judging.

### R-09 — Demo link rot: submitted URL stops working · MEDIUM · demo

Judging can run days after submission. The URL can break from: free
instance-hours exhausted, a bad later push auto-deploying (`autoDeploy: yes`),
Render suspending the service, or an env var edited and never saved.

- **Mitigated in code:** `autoDeploy` only redeploys what is on `main`, and
  the health check means a broken build does not replace a working instance
  silently.
- **You must do:** freeze `main` after you deploy the version you filmed —
  no more pushes before judging unless something is actually broken. Re-check
  the URL every couple of days between the 30th and the results. If you must
  push, re-run the checklist afterwards.

### R-10 — Video is the weakest artifact · MEDIUM · demo

The video is still unrecorded (`CHECKLIST.md` item 8) and is the only artifact
every judge definitely watches. lablab allows a maximum of five minutes. It
carries the whole *Presentation* criterion and, if the app is asleep, the
whole submission.

- **Mitigated in code:** nothing — this is pure execution.
  `docs/submission/DEMO_SCRIPT.md` exists; the UI is recorded-ready (the
  cockpit screenshot from the container run is clean at 1440×900).
- **You must do:** record against the **hosted** URL, not localhost, so the
  video doubles as proof the deployed thing works. Show the literal clause
  quoting — that is the originality argument. Upload to Vimeo with privacy
  "Anyone", use the plain `vimeo.com/<id>` link, and *open it in a logged-out
  private window* before pasting it into the form.

### R-11 — Judges can't tell what is original · MEDIUM · demo

*Originality* is a quarter of the score. "Voice agent that listens to a call"
is the most common shape in this hackathon. The actual differentiator —
alerts are the **literal contract text**, never LLM prose, with a verbatim
similarity check on what was spoken — is invisible unless you say it.

- **Mitigated in code:** the design enforces it (`build_alert_text` speaks the
  clause; `say_exactly` records `literal_spoken` / `similarity`; the cockpit
  shows a "READ VERBATIM" counter and the report shows the exact clause text
  next to what the rep said).
- **You must do:** put the claim in the first 30 seconds of the video and in
  the short description. Show the report screen — the side-by-side of "REP
  SAID" vs "CONTRACT §3.1 SAYS" is the strongest single frame you have.

### R-12 — Public unauthenticated API surface · LOW · infra

`POST /api/contract/demo` and `POST /api/contract` accept cross-origin
requests (measured: `201` from `Origin: https://evil.example.com`) — the
origin allow-list only guards the WebSocket. An attacker could mint
workspaces or push PDFs at the parser.

- **Mitigated in code:** no CORS middleware is installed, so a browser cannot
  read the response cross-site; the `cc_ws` cookie is `HttpOnly` +
  `SameSite=strict` + `Secure` over HTTPS, so a cross-site request carries no
  workspace. `SessionStore` is capped at 1000 workspaces / 500 sessions with
  oldest-dropped eviction, so a flood cannot grow memory without bound. PDF
  uploads are capped at 5 MB by a body-limit middleware *before* buffering and
  parsed in a separate memory-capped worker with a 10 s timeout and a 50-page
  limit. Security headers verified on the live container: CSP with
  `frame-ancestors 'none'`, `X-Content-Type-Options`, `X-Frame-Options: DENY`,
  `Referrer-Policy`, `Permissions-Policy`, HSTS when behind HTTPS, no `Server`
  header, no OpenAPI/docs endpoints.
- **You must do:** nothing before the deadline. Do not widen this to "make
  testing easier".

### R-13 — Repo doesn't match the submission · LOW · demo

Judges open the GitHub link. Everything is pushed as of `a629536`: local and
`origin/main` matched on 2026-09-17 with a clean working tree. The remaining
exposure is cosmetic — the README screenshots only render for a logged-out
visitor if the image paths resolve on the remote.

- **Mitigated in code:** MIT `LICENSE` is in place (lablab requires
  MIT-compliant submissions); `.gitignore` and `.dockerignore` keep `.env` out
  of both git and the image.
- **You must do:** open the repo in a logged-out browser and confirm the
  README renders with images.

---

## Summary

| Severity | Count | IDs |
|---|---|---|
| Critical | 1 | R-01 (R-02 resolved 2026-09-20) |
| High | 4 | R-03, R-04, R-05, R-06 |
| Medium | 5 | R-07, R-08, R-09, R-10, R-11 |
| Low | 2 | R-12, R-13 |

**Overall: amber.** The application itself is in good shape — it was driven
end to end inside the Render-shaped container and did the thing it claims to
do, with real paid APIs, under 512 MB. Every remaining critical and high risk
is operational: deploy it, verify the socket, record the video, and wake it
before judging. None of them need more code.

**Do these in this order:**

1. Deploy to Render and verify the WebSocket probe returns `101` (~30 min).
2. Pad the recorded video to 3:30–4:30 and upload it to Vimeo (1–2 h). The take
   is shipped at 4:20.8, above the rubric's 3:00 floor; see `DEMO_NOTES.md`.
3. Check the repo in a logged-out browser (~15 min).
4. Fill in and submit the lablab form (~20 min).

The mic path and the push are done (R-06, R-13).
6. Freeze `main`. Wake the app before judging (`CHECKLIST.md`, 60 s).
