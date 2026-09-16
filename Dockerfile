# syntax=docker/dockerfile:1
#
# ClauseCatcher — multi-stage build for Render (free web service, Docker
# runtime). See docs/DEPLOY.md for the click-by-click host setup.
#
# Stage 1 builds the React/Vite frontend to static files (frontend/dist).
# Stage 2 is the actual runtime: FastAPI server + the built frontend + the
# no-build-step web/ fallback UI + the one demo-contract fixture the server
# reads at runtime (server/clauses.py: load_demo_contract()).

# ---------------------------------------------------------------------------
# Stage 1: build the frontend
# ---------------------------------------------------------------------------
FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend

# Copy lockfile first so `npm ci` is cached across builds that only touch src.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime
WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Server code.
COPY server/ ./server/

# No-build-step fallback UI (server/main.py mounts this only if
# frontend/dist is absent, but it costs nothing to keep it available).
COPY web/ ./web/

# Built frontend (copied from stage 1, not from the host — frontend/dist is
# in .dockerignore so a stale local build never leaks into the image).
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# server/clauses.py:load_demo_contract() resolves this path relative to the
# repo root at runtime (ROOT_DIR/spikes/harness/fake_contract.json) for the
# POST /api/contract/demo endpoint used by the hackathon demo flow. It must
# be present even though the rest of spikes/ (audio fixtures) is excluded.
COPY spikes/harness/fake_contract.json ./spikes/harness/fake_contract.json

# Secrets (ASSEMBLYAI_API_KEY, GEMINI_API_KEY, ...) are injected as host env
# vars at deploy time (Render dashboard) — never baked into the image.

RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Render assigns $PORT at runtime (defaults to 10000 for a Docker web
# service if unset). Default here matches Render; override PORT for other
# hosts (e.g. Hugging Face Docker Spaces use 7860).
ENV PORT=10000
EXPOSE 10000

CMD ["sh", "-c", "uvicorn server.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
