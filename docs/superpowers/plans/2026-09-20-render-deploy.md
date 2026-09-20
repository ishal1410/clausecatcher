# ClauseCatcher Render Deploy Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to work through this task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put ClauseCatcher on a public Render URL and prove the whole live pipeline works there, so `[APP_URL]` in the lablab submission can be filled with a link a judge can actually use.

**Architecture:** `tools/deploy/render_deploy.py` drives the Render REST API from `render.yaml`: create a Docker web service, PUT env vars (secrets read from this process's environment, never written to disk or printed), deploy, poll until live, re-pin `CLAUSECATCHER_ALLOWED_ORIGINS` to the real service URL, redeploy env-only, then health-check. Verification does not stop at `/api/health` — a green health check on this app proves almost nothing, because the WebSocket and the Gemini leg can each be dead behind it.

**Tech Stack:** Render free tier (Docker runtime), FastAPI + WebSocket, AssemblyAI Streaming STT v3 + Voice Agent, Gemini claim check, React/Vite frontend built into the image.

## Global Constraints

- Deploy from `main` at `11f5dc0` or later; local and `origin/main` must match with a clean tree.
- `RENDER_API_KEY` is account-wide. It is read from a scratchpad file for one command, never committed, never printed, and the file is deleted immediately after. The user rotates the key in the Render dashboard once the deploy is done.
- `ASSEMBLYAI_API_KEY` and `GEMINI_API_KEY` are already exported in the session shell. They are passed through to Render, never echoed.
- `CLAUSECATCHER_GEMINI_MODEL` must end up **absent, not empty**, on the service. An empty value makes `claim_check.py` build an invalid model id and every Gemini call fails while the pill still reads green. `env_vars()` skips unset `sync: false` keys, so the scripted path is safe; the Blueprint UI path is not.
- `CLAUSECATCHER_ALLOWED_ORIGINS` must equal the service URL exactly, with no trailing slash, or every WebSocket upgrade returns 403 while `/api/health` stays green.
- Free tier sleeps after ~15 idle minutes. Every timing check below assumes a possible ~60 s cold start on the first hit.
- The demo is unauthenticated and bills the owner's keys. The user has accepted that risk (2026-09-20); do not add a gate as part of this deploy.

---

### Task 1: Get the API key into the process without putting it in the transcript

**Files:**
- Read: `<scratchpad>/render_key.txt` (created by the user, deleted in Task 5)

**Interfaces:**
- Produces: `RENDER_API_KEY` present in the environment of the deploy command in Task 2.

- [ ] **Step 1: Confirm the file exists and looks like a Render key, without printing it**

```bash
KEYFILE="C:/Users/vp141/AppData/Local/Temp/claude/C--Users-vp141/11e476dc-bd02-42d0-b958-634da8029d0e/scratchpad/render_key.txt"
test -f "$KEYFILE" && awk '{ printf "length=%d prefix_ok=%s\n", length($0), (substr($0,1,4)=="rnd_" ? "yes" : "NO") }' "$KEYFILE"
```

Expected: `length=<some number> prefix_ok=yes`. If `prefix_ok=NO`, stop and tell the user the file does not contain a Render API key.

- [ ] **Step 2: Confirm the repo is in the state we intend to deploy**

```bash
cd /c/Users/vp141/clausecatcher && git fetch -q origin && echo "local $(git rev-parse --short HEAD) remote $(git rev-parse --short origin/main) dirty $(git status --porcelain | wc -l)"
```

Expected: local and remote equal, `dirty 0`. If they differ, stop: Render builds from GitHub, so deploying a commit that is not pushed ships something other than what was tested.

- [ ] **Step 3: Confirm both upstream keys are present (lengths only, never values)**

```bash
for v in ASSEMBLYAI_API_KEY GEMINI_API_KEY; do eval "val=\$$v"; echo "$v: ${#val} chars"; done
```

Expected: both non-zero. `GOOGLE_API_KEY` is not needed.

---

### Task 2: Create the service and take it live

**Files:**
- Run: `tools/deploy/render_deploy.py`
- Read: `render.yaml`

**Interfaces:**
- Consumes: `RENDER_API_KEY` from Task 1.
- Produces: the live service URL (printed as `service URL: https://...`), used by every later task.

- [ ] **Step 1: Re-run the dry run against the current tree**

```bash
cd /c/Users/vp141/clausecatcher && ASSEMBLYAI_API_KEY=dummy GEMINI_API_KEY=dummy python tools/deploy/render_deploy.py --dry-run 2>&1 | tail -5
```

Expected: ends with `DRY RUN complete, nothing was sent.` and exit 0. This catches a broken `render.yaml` before any account is touched.

- [ ] **Step 2: Run the real deploy**

```bash
cd /c/Users/vp141/clausecatcher && KEYFILE="C:/Users/vp141/AppData/Local/Temp/claude/C--Users-vp141/11e476dc-bd02-42d0-b958-634da8029d0e/scratchpad/render_key.txt" && RENDER_API_KEY="$(tr -d '\r\n' < "$KEYFILE")" python tools/deploy/render_deploy.py 2>&1 | tail -40
```

Expected: `service URL: https://<name>.onrender.com` then `DEPLOYED: https://<name>.onrender.com`, exit 0. A free-tier Docker build takes roughly 5–12 minutes; the script polls every 15 s and this command may run that long.

**Failure modes and what each one means:**

| Symptom | Cause | Action |
|---|---|---|
| HTTP 401 | key wrong or revoked | Stop. Ask the user to re-copy the key. |
| HTTP 400 mentioning repo/owner | Render account has never been connected to GitHub | Stop. The user connects GitHub once in the Render dashboard, then re-run Step 2. This cannot be done over the API. |
| `deploy ... ended build_failed` | Docker build broke on Render | Read the Render log, fix, push, re-run. Do not retry blindly. |
| Stuck in `build_in_progress` past the timeout | slow free tier | Re-run Step 2; the script is idempotent — it finds the existing service and updates it. |

- [ ] **Step 3: Record the URL**

```bash
echo "<paste the printed URL>" > /c/Users/vp141/clausecatcher/docs/submission/_closing/app_url.txt && cat /c/Users/vp141/clausecatcher/docs/submission/_closing/app_url.txt
```

Expected: the URL echoes back. `_closing/` is gitignored, so this is a scratch note, not a committed artifact.

---

### Task 3: Prove the service actually works, not just that it answers

**Files:**
- Read: `docs/submission/CHECKLIST.md` ("60 seconds before judging" section, which this task executes for real)

**Interfaces:**
- Consumes: the URL from Task 2.

- [ ] **Step 1: Health, twice — the second call is the one that matters**

```bash
URL="$(cat /c/Users/vp141/clausecatcher/docs/submission/_closing/app_url.txt)"
time curl -s "$URL/api/health"; echo; time curl -s "$URL/api/health"
```

Expected: both print `{"status":"ok"}`. The first may take ~60 s (cold start); the second must return in well under a second. A slow second call means the instance is not warm and something is wrong.

- [ ] **Step 2: WebSocket upgrade must be 101, not 403**

```bash
URL="$(cat /c/Users/vp141/clausecatcher/docs/submission/_closing/app_url.txt)"
curl -s -o /dev/null -w "%{http_code}\n" -H "Connection: Upgrade" -H "Upgrade: websocket" -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" -H "Origin: $URL" "$URL/ws/session/probe"
```

Expected: `101`. If `403`, `CLAUSECATCHER_ALLOWED_ORIGINS` does not exactly equal `$URL` — fix it in the Render Environment tab (no trailing slash), wait for the redeploy, re-run. This is the failure that looks like a working app with a broken demo.

- [ ] **Step 3: Confirm the Gemini leg is actually ready on the deployed instance**

Drive the hosted app in a real browser and read the status frame, rather than trusting the env tab. Reuse the harness shape already proven locally in this session: open `$URL`, click **Try the live demo**, **Use the demo contract**, tick consent, **Start the call**, then read the verdict tile.

Expected: the tile reads **Listening** (checker ready, nothing said yet), not **Not checked**. `Not checked` here means the Gemini key or model is wrong on the service — check that `CLAUSECATCHER_GEMINI_MODEL` is absent rather than empty.

- [ ] **Step 4: Drive one real contradiction end to end**

In the same browser session, paste into *Simulate rep line*:

```
We can absolutely do a verbal twenty percent discount and add ten extra seats today, no paperwork needed.
```

Expected, within ~5 s: a red §3.1 alert card appears, the clause is read aloud, and the tile flips to **Off-contract**. This is the only check that proves AssemblyAI, Gemini and the voice leg are all alive on the deployed instance at once. Screenshot it to `docs/submission/_closing/live_alert.png`.

**If the alert never arrives but the tile stays Listening:** the claim check is failing silently upstream — read the Render logs for `claim check error for session`.

---

### Task 4: Fill the placeholders the deploy unblocks

**Files:**
- Modify: `docs/submission/LABLAB_SUBMISSION.md` (the `[APP_URL]` fenced block)
- Modify: `README.md:5` and the `Live app` line
- Modify: `docs/submission/CHECKLIST.md` item 12
- Modify: `docs/submission/COMPLIANCE.md` finding 1
- Modify: `docs/submission/ClauseCatcher.pptx` slide 11 (drop "A hosted, deployed instance" from NEXT), then re-export `ClauseCatcher.pdf`

**Interfaces:**
- Consumes: the verified URL from Task 3.

- [ ] **Step 1: Replace `[APP_URL]` and the README status line**

Use the URL exactly as Render prints it, no trailing slash. Grep first so nothing is missed:

```bash
cd /c/Users/vp141/clausecatcher && grep -rn "\[APP_URL\]\|no public deployment yet\|Live app: TODO" README.md docs/submission/*.md
```

Expected afterwards: that grep returns nothing.

- [ ] **Step 2: Drop the deployed-instance line from the deck**

Add to `EDITS` in `tools/fix_deck.py`, matching the established pattern (exact paragraph, annotated with its reason), then run the script and re-export the PDF with PowerPoint COM, exporting slide 11 to `docs/submission/_closing/f11_after.png`.

Expected: the script reports the paragraph changed. **Read the PNG** — a previous edit in this repo broke a text box mid-word and only a render caught it.

- [ ] **Step 3: Verify the test suites still pass and commit**

```bash
cd /c/Users/vp141/clausecatcher && env -u ASSEMBLYAI_API_KEY -u GEMINI_API_KEY -u GOOGLE_API_KEY python -m pytest server/tests -q | tail -2 && (cd frontend && npx vitest run 2>&1 | grep "Tests ")
```

Expected: `151 passed` and `42 passed`. Then commit the doc and deck changes with the live URL in the message.

---

### Task 5: Clean up the credential

**Files:**
- Delete: `<scratchpad>/render_key.txt`

- [ ] **Step 1: Delete the key file and confirm it is gone**

```bash
KEYFILE="C:/Users/vp141/AppData/Local/Temp/claude/C--Users-vp141/11e476dc-bd02-42d0-b958-634da8029d0e/scratchpad/render_key.txt"
rm -f "$KEYFILE" && test ! -f "$KEYFILE" && echo "key file deleted"
```

Expected: `key file deleted`.

- [ ] **Step 2: Confirm the key never entered the repo**

```bash
cd /c/Users/vp141/clausecatcher && git status --porcelain && grep -rn "rnd_" --exclude-dir=.git . | grep -v "rnd_xxx" | head
```

Expected: a clean tree and no `rnd_` match other than the `rnd_xxx` placeholder in `docs/DEPLOY.md`.

- [ ] **Step 3: Tell the user to rotate**

The key was on disk in a temp file and in one process environment. Rotating it in the Render dashboard costs nothing and closes that window.

---

## Rollback

Deploying is additive — nothing in the repo changes until Task 4 — so rollback is mostly "undo the service".

| What went wrong | Rollback |
|---|---|
| Build fails or the app misbehaves on Render | The repo is untouched. Fix forward, or suspend the service in the dashboard. Nothing to revert locally. |
| Wrong env var set on the service | Re-run Task 2 Step 2; both PUTs now merge with the live service rather than replacing it, so unset keys are preserved. |
| Service created under the wrong account/name | Delete the service in the Render dashboard, then re-run Task 2. The script has no delete path, by design. |
| Task 4 doc edits are wrong | `git checkout -- <file>`; they are committed as one commit, so `git revert` also works. |
| Deck edit breaks a slide | `docs/submission/_closing/ClauseCatcher.pptx.bak` holds the pre-edit deck; restore it and re-export. |

## What this plan deliberately does not do

- No demo key or auth gate. The user accepted the unauthenticated-cost risk on 2026-09-20.
- No provider-side spend cap. Same decision.
- No changes to the video. `demo.mp4` is final at 4:20.8; its end card shows the repo URL, not the app URL, and re-cutting it for one line is not worth the risk this close to the deadline.
