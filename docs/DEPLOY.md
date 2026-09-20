# Deploying ClauseCatcher (free tier, no card)

## Host: Render (free Docker web service)

**Why Render over the alternatives:**

- **Hugging Face Spaces (Docker)** — ruled out. As of the current HF docs
  (`huggingface.co/docs/hub/spaces-overview`, fetched 2026-09-16): *"Gradio
  and Docker Spaces run on compute and require a paid plan to create: PRO
  for personal accounts, Team or Enterprise for organizations."* Only
  Static Spaces are free for everyone; the free-personal-account exception
  is 2 Gradio Spaces on ZeroGPU, which doesn't apply to a Docker/FastAPI
  app. This is a real change from the older "HF Spaces Docker is free"
  assumption — don't rely on memory here, the docs are current.
- **Fly.io** — ruled out. `fly.io/docs/about/pricing/` (fetched 2026-09-16):
  *"All organizations (except for Linked Organizations) require a credit
  card on file."* Violates the no-card constraint.
- **Koyeb** — inconclusive/unlikely. Current pricing page shows no general
  free web-service tier (only a 5-hour free Postgres trial and a paid Pro
  plan); not confidently free-and-card-free.
- **Render free web service** — confirmed workable. Render's own free-tier
  docs describe suspending (not blocking signup) if you exceed the free
  allowance with no payment method on file — i.e. you can sign up and
  deploy without ever adding a card, as long as you stay inside 750
  free instance-hours/month. Supports Docker runtime and WebSockets (the
  connection works normally while the service is awake). The only
  trade-off: it **sleeps after 15 minutes idle** and takes about a minute
  to wake on the next request — see "Wake it before judging" below.

## First deploy (you have no Render account yet)

Total: about 20 minutes, most of it waiting on the build. Nothing here
needs a credit card.

### 1. Make sure the repo is pushed

Render builds from GitHub, not from your laptop. Everything you want
deployed must be on the branch you point Render at (default `main`):

```bash
git status            # should be clean
git push origin main
```

### 2. Create the Render account (2 min)

1. Open <https://dashboard.render.com/register>.
2. Click **GitHub** and authorise Render. Use the GitHub account that owns
   `ishal1410/clausecatcher`.
3. Fill in the name/workspace prompts and accept the defaults. When it
   offers a paid plan or asks for a card, **skip it** — the free plan
   works without one.
4. You land on the dashboard. You do *not* need to create a service by
   hand; step 4 below does it.

### 3. Create an API key (1 min)

1. Open <https://dashboard.render.com/u/settings?add-api-key> (this is the
   Account Settings page with the API-key dialog already open — same as
   profile icon → **Account Settings** → **API Keys** → **Create API Key**).
2. Name it `clausecatcher-deploy`, click **Create API Key**.
3. **Copy the key now.** Render shows it exactly once; if you lose it,
   delete it and make another.

### 4. Run the one command

From the repo root, with the key you just copied and your two API keys:

```bash
RENDER_API_KEY=rnd_xxx \
ASSEMBLYAI_API_KEY=xxx \
GEMINI_API_KEY=xxx \
python tools/deploy/render_deploy.py
```

(PowerShell: `$env:RENDER_API_KEY="rnd_xxx"` etc. on separate lines, then
`python tools/deploy/render_deploy.py`.)

Rehearse it first with `python tools/deploy/render_deploy.py --dry-run` —
that prints every API call it would make, with secret values redacted, and
sends nothing.

The script needs PyYAML (`pip install pyyaml`). It reads `render.yaml`,
creates the service on the **free** plan with the Docker runtime, sets all
the env vars, waits for the build, then pins
`CLAUSECATCHER_ALLOWED_ORIGINS` to the real service URL, redeploys and
checks `/api/health`. Secret values are never printed or written anywhere.

### 5. What you should see, and how long it takes

```
local env: RENDER_API_KEY=set, ASSEMBLYAI_API_KEY=set, GEMINI_API_KEY=set
GET https://api.render.com/v1/owners?limit=100
GET https://api.render.com/v1/services?name=clausecatcher&...
service 'clausecatcher' not found in tea-xxxx: creating
POST https://api.render.com/v1/services
  deploy dep-xxxx: build_in_progress
  ...
  deploy dep-xxxx: live
service URL: https://clausecatcher.onrender.com
PUT https://api.render.com/v1/services/srv-xxxx/env-vars
POST https://api.render.com/v1/services/srv-xxxx/deploys
  deploy dep-yyyy: live
GET https://clausecatcher.onrender.com/api/health  ...
  health: ok
DEPLOYED: https://clausecatcher.onrender.com
```

Timing: the Docker build installs npm deps, runs a Vite build, then
installs the Python deps. A full `--no-cache` build of this exact
Dockerfile took **46 s** on the dev laptop (measured 2026-09-17, 373 MB
image). Render's free builder is a shared, much slower machine and has to
pull every base layer, so **budget 5–15 minutes for the first deploy** and
don't panic at minute three. The second deploy in the run
is `deployMode: deploy_only` — it reuses the image it just built and
finishes in under a minute. The script's own timeout is 25 minutes per
deploy (`--timeout-s`). If it looks stuck, open the service's **Logs** tab
in the dashboard; the script is only polling the same status.

If the run dies partway (laptop sleeps, network drops), just run the same
command again — it finds the existing service and updates it instead of
creating a second one.

### 6. Confirm it actually works (do not skip)

1. `curl https://<your-url>/api/health` → `{"status":"ok"}`.
2. Open `https://<your-url>/` — the landing page should render.
3. Click **Try the live demo** → **Use the demo contract** → tick the
   consent box → **Start the call**.
4. In the right-hand rail, type into **Simulate rep line**:
   *"We can absolutely do a verbal twenty percent discount and add ten
   extra seats today, no paperwork needed."* and press the send button.
5. Within a few seconds you must get a red §3.1 contradiction card **and**
   hear the clause read aloud. If the top bar sits on "Connecting…" and
   nothing ever happens, the WebSocket handshake is being rejected — see
   the trap below.

> **The one trap: `CLAUSECATCHER_ALLOWED_ORIGINS`.** The server compares
> the browser's `Origin` header against this value exactly. A trailing
> slash, `http://` instead of `https://`, or a stale URL all make every
> WebSocket handshake return 403, and the cockpit then shows a 5-second
> error toast and afterwards just says "Connecting…" forever — which looks
> like a broken app, not a config error. It must be exactly
> `https://clausecatcher.onrender.com`, no trailing slash. The deploy
> script sets this for you; only hand-editing breaks it. To check without
> a browser:
>
> ```bash
> curl -s -o /dev/null -w "%{http_code}\n" \
>   -H "Connection: Upgrade" -H "Upgrade: websocket" \
>   -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
>   -H "Origin: https://clausecatcher.onrender.com" \
>   https://clausecatcher.onrender.com/ws/session/probe
> ```
>
> `101` = origin accepted (good). `403` = the origin value is wrong.

### Alternative: deploy from the dashboard instead of the script

If you would rather click than run a command, the Blueprint path does the
same thing:

1. **New +** → **Blueprint** → pick the `clausecatcher` repo → **Apply**.
   Render reads `render.yaml` and creates one free Docker web service.
2. When the build finishes, open the service's **Environment** tab and
   fill in the vars `render.yaml` deliberately leaves blank
   (`sync: false`, so no secret is ever in git): `ASSEMBLYAI_API_KEY`,
   `GEMINI_API_KEY`, `CLAUSECATCHER_ALLOWED_ORIGINS` (the service URL from
   the top of the page, no trailing slash), and optionally
   `CLAUSECATCHER_GEMINI_MODEL` (blank = the server default).
3. **Save Changes** — Render redeploys with them. Then do step 6 above.

## If Render signup fails — fallback hosts

Checked against the vendors' own docs on 2026-09-17.

1. **Northflank Sandbox** — <https://northflank.com/pricing>. Free tier
   with *"Always-on-compute – no sleeping :)"*, 2 free services, deploys a
   Dockerfile straight from GitHub. **Better than Render for judging**
   because there is no 15-minute sleep. Caveat: the pricing FAQ only says
   *"when you enter a card we only verify the card"*, so it is not
   confirmed card-free — find that out in the first two minutes of signup,
   not on deadline day. Set the same env vars from `render.yaml` by hand,
   and set `PORT` to whatever Northflank expects (the image reads `$PORT`
   and defaults to 10000).
2. **TryCloudflare quick tunnel** — the zero-signup emergency exit.
   <https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/>:
   no account, no domain, no payment. Run the container locally and expose
   it:

   ```bash
   docker build -t clausecatcher .
   docker run -d --name cc -p 8000:10000 \
     -e ASSEMBLYAI_API_KEY=... -e GEMINI_API_KEY=... \
     -e CLAUSECATCHER_CLAIM_CHECK=gemini clausecatcher
   cloudflared tunnel --url http://localhost:8000
   ```

   It prints a random `https://<words>.trycloudflare.com` URL. Then set
   `CLAUSECATCHER_ALLOWED_ORIGINS` to that exact URL and restart the
   container, or the WebSocket will 403. Cloudflare's own caveats:
   *"Quick Tunnels are intended for testing and development only"*, no SLA,
   and a hard limit of 200 concurrent requests. The URL dies when you stop
   `cloudflared`, so this is a fallback for a scheduled live demo, not a
   link you submit and walk away from.

Already ruled out, don't re-litigate: Hugging Face Docker Spaces (paid
plan required), Fly.io (card required on every org), Koyeb (no free
web-service tier on its pricing page as of 2026-09-17 — only a 5-hour free
Postgres trial).

## Every time before judging (or any live demo)

Render free services sleep after 15 minutes with no inbound traffic and
take about a minute to wake back up on the next request — a judge's first
click would otherwise sit on a slow/blank page.

**Wake it before judging:**

1. A few minutes before your demo/judging slot, open
   `https://<your-url>/api/health` in a browser tab (or `curl` it) and
   confirm you get `{"status":"ok"}` back quickly, not after a long hang.
2. If it hung for ~30-60s the first time, that was the cold start — hit it
   a second time to confirm it now responds fast.
3. Leave that tab open, or reload it every ~10 minutes if there's a gap
   before judging starts, so the service never goes back to sleep.
4. Load the actual app URL (not just `/api/health`) once too, so the
   static frontend is warm as well.

## Updating the deployed app

Push to the branch Render is watching (default: your repo's default
branch) — Render rebuilds and redeploys automatically. To redeploy the
current commit without a code change (e.g. after only touching an env
var), use **Manual Deploy** → **Deploy latest commit** on the service page.

## Spend and abuse limits

The app is public, so paid API use is capped by env vars. `render.yaml`
sets these defaults; change them in the **Environment** tab.

| Variable | Default | What it does |
|---|---|---|
| `CLAUSECATCHER_MAX_LIVE_WS` | `2` | Max concurrent live call WebSockets; extra callers get "demo busy, try again shortly". |
| `CLAUSECATCHER_BUDGET_USD` | `3` | Cap on **AssemblyAI** spend (STT + voice) for the running process. It does not count Gemini — Gemini is bounded by call count instead, below. |
| `CLAUSECATCHER_PAID_DISABLED` | `0` | **Kill switch.** Set to `1` to stop all paid API use — AssemblyAI STT/voice *and* Gemini claim-checks (`server/main.py` and `server/claim_check.get_claim_checker`). Takes effect on the next session after the redeploy; the app stays up and still shows the contract, it just stops flagging. The client is told: the `status` frame carries `claim_check: "disabled"` and each unchecked line gets a `check_error`, so the UI can never show a clean call that was never checked. |
| `CLAUSECATCHER_SESSION_CAP_S` | `420` | Max length of one live call, in seconds. |
| `CLAUSECATCHER_IDLE_TIMEOUT_S` | `60` | End a live call after this many seconds with no client messages. Not set by `render.yaml`; the server default is 60. |
| `CLAUSECATCHER_MAX_CHECKS` | `40` | Max claim checks per session. |
| `CLAUSECATCHER_MAX_GEMINI_CALLS` | `300` | Max Gemini calls for the running process. Once reached, `status.claim_check` becomes `"error"` and further lines go unchecked. |
| `CLAUSECATCHER_ALLOWED_ORIGINS` | *(unset)* | Allowed browser origin(s); set to your `https://<service>.onrender.com` URL. |

If you see unexpected usage on the AssemblyAI or Gemini dashboards, set
`CLAUSECATCHER_PAID_DISABLED=1`, save, and rotate the keys.

Uploaded PDFs are parsed in a separate, memory-capped worker process with
a 10 s timeout and a 50-page limit, so a hostile PDF can't hang or OOM the
512 MB instance.

## Secrets

Never commit a real key. `.env` and `.env.*` (except `.env.example`) are
gitignored and also excluded from the Docker build context via
`.dockerignore`. The only place real key values live is the Render
dashboard's **Environment** tab for this service.
