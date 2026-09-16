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

## One-time setup

1. Push this repo to GitHub (Render deploys from a GitHub repo).
2. Go to <https://dashboard.render.com> and sign up (GitHub login is
   fine — no card required for the free plan).
3. Click **New +** → **Blueprint**.
4. Connect your GitHub account if prompted, then pick the `clausecatcher`
   repo. Render detects `render.yaml` at the repo root and shows one
   service: `clausecatcher` (Docker, free plan).
5. Click **Apply**. Render starts the first build from `Dockerfile`
   (multi-stage: builds `frontend/dist`, then the Python/uvicorn image).
   First build takes a few minutes — watch the **Logs** tab.
6. Once the service is live, open its **Environment** tab and paste in the
   real secret values (these are the vars left blank by `render.yaml`
   because they're marked `sync: false` — nothing secret is ever in git):
   - `ASSEMBLYAI_API_KEY` — your AssemblyAI key.
   - `GEMINI_API_KEY` — your Gemini key.
   - `CLAUSECATCHER_GEMINI_MODEL` — optional; leave blank to use the
     server's default (`gemini-3.5-flash-lite`).
   - `CLAUSECATCHER_CLAIM_CHECK` is already set to `gemini` by
     `render.yaml`. (If you ever want to run the server with the claim
     checker stubbed out and no Gemini calls, delete that var or change
     its value to anything else.)
7. Click **Save Changes** — Render redeploys automatically with the new
   env vars.
8. Your hosted app URL is shown at the top of the service page, e.g.
   `https://clausecatcher.onrender.com`. Open it — you should see the
   ClauseCatcher landing page. Hit `https://<your-url>/api/health` and
   confirm `{"status":"ok"}`.

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

## Secrets

Never commit a real key. `.env` and `.env.*` (except `.env.example`) are
gitignored and also excluded from the Docker build context via
`.dockerignore`. The only place real key values live is the Render
dashboard's **Environment** tab for this service.
