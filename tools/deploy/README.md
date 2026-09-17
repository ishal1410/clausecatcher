# Render deploy automation

`render_deploy.py` creates or updates the `clausecatcher` web service with the
[Render REST API](https://api-docs.render.com/reference). It uses the settings in
`render.yaml`: Docker runtime, `plan: free`, `healthCheckPath`, Dockerfile
path/context, and env vars. The script:

1. `GET /owners` finds your workspace.
2. `GET /services?name=clausecatcher` checks whether the service exists. If not,
   `POST /services` creates it from the public GitHub repo, and that starts the
   first deploy. If it exists, it runs `PATCH` + `PUT /env-vars` +
   `POST /deploys`.
3. It polls `GET /services/{id}/deploys/{deployId}` until `live`, and fails on
   `build_failed`, `update_failed`, `canceled`, and similar states.
4. It sets `CLAUSECATCHER_ALLOWED_ORIGINS` to the service URL, then runs a
   restart-only redeploy (`deployMode: deploy_only`) and waits again.
5. It calls `GET <url>/api/health` and expects `{"status":"ok"}`, with retries
   for the free-tier cold start.

`ASSEMBLYAI_API_KEY` and `GEMINI_API_KEY` are read from **your local
environment at runtime**. They go straight into the API request and are never
written to disk or printed. `RENDER_API_KEY` is only used in the
`Authorization` header. `PUT /env-vars` replaces **all** env vars on the
service, so the script is the source of truth for them.

## The only manual step

1. Sign up at <https://dashboard.render.com> **with GitHub**. This links your
   GitHub account so Render can pull `ishal1410/clausecatcher`.
2. Create an API key: **Account Settings -> API Keys -> Create API Key**
   ([docs](https://render.com/docs/api)). Keep it in your shell only.

## Commands

Dry run (no network, prints every planned call with secrets redacted):

```powershell
python tools/deploy/render_deploy.py --dry-run
```

Real deploy:

```powershell
$env:RENDER_API_KEY = "<render key>"; $env:ASSEMBLYAI_API_KEY = "<key>"; $env:GEMINI_API_KEY = "<key>"
python tools/deploy/render_deploy.py
```

Options: `--owner-id` (only if your key sees several workspaces), `--region`
(default `oregon`, used on create only), `--branch` (default `main`),
`--allow-missing-keys` (deploy in simulate-only mode), `--timeout-s`.
`python tools/deploy/render_deploy.py --self-test` checks redaction and env
assembly offline. It needs PyYAML (`pip install pyyaml`).

## Free tier: what Render's docs actually say (checked 2026-09-17)

- **No card:** "No credit card is required." ([render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026](https://render.com/articles/platforms-with-a-real-free-tier-for-developers-in-2026))
  The free-tier doc itself doesn't say this directly. It does say that if you go
  over the limits "If you haven't added a payment method, Render instead suspends
  all of your Free services" ([render.com/docs/free](https://render.com/docs/free)).
  So you can run without a card, and going over the limits means suspension, not
  a charge.
- **750 free instance hours per workspace per month**, and the service is
  suspended until next month if you use them all ([render.com/docs/free](https://render.com/docs/free)).
- **Spins down after 15 minutes without inbound traffic.** Waking up "takes
  about one minute" ([render.com/docs/free](https://render.com/docs/free)).
  Wake it before judging (see `docs/DEPLOY.md`).
- Free services also get no persistent disk, a single instance, no SSH, and
  "Render might restart a Free web service at any time"
  ([render.com/docs/free](https://render.com/docs/free)). ClauseCatcher keeps
  sessions in memory, so a restart drops any live call.
- `plan: "free"` is a valid `serviceDetails.plan` value, `runtime: "docker"`
  replaces the deprecated `env`, and env var or service changes made through the
  API do **not** deploy by themselves
  ([create-service](https://api-docs.render.com/reference/create-service),
  [update-env-vars](https://api-docs.render.com/reference/update-env-vars-for-service)).

**Cost:** $0 on Render's free plan. The only spend is AssemblyAI and Gemini
usage by visitors, capped by `CLAUSECATCHER_BUDGET_USD=3` in `render.yaml`.
