"""ClauseCatcher API (see docs/adr/0001-voice-architecture.md, docs/SCOPE_RESET_2026-09-14.md).

Architecture: browser mic PCM16 16 kHz binary frames -> server -> a
StreamingTranscriber (server/stt.py) -> per finalized turn -> claim_check
(server/claim_check.py) -> on contradiction: send the literal contract clause
as alert JSON (never LLM text) AND speak it via AlertSpeaker (server/voice.py)
whose audio streams back to the browser. Monitor Q&A ("ask") looks the clause
up by section_number directly (no agent tool calling) and speaks the answer
the same way.

server/stt.py and server/voice.py are owned by other agents building
concurrently; both are imported lazily/defensively so this app still starts and serves everything
else before those files land, and so tests can inject fakes via the
stt_factory/voice_factory FastAPI dependencies without ever touching the
network.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, StrictBool
from starlette.exceptions import HTTPException as StarletteHTTPException

from server.clauses import ClauseExtractionError, extract_clauses_safe, load_demo_contract
from server.session_store import SessionState, SessionStore, Workspace
from server.claim_check import checker_state, get_claim_checker as _default_claim_checker_factory

logger = logging.getLogger("clausecatcher")

ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"
FRONTEND_DIST_DIR = ROOT_DIR / "frontend" / "dist"

MAX_PDF_BYTES = int(os.environ.get("CLAUSECATCHER_MAX_PDF_BYTES", 5 * 1024 * 1024))

# Per finalized turn behavior tuning (see WS protocol behavior spec).
ALERT_DEDUPE_S = 20.0
CHECK_ERROR_COOLDOWN_S = 20.0  # at most one check_error frame per session per window
CLAIM_CHECK_TIMEOUT_S = 15.0  # must exceed claim_check.TIMEOUT_MS (12 s; Gemini minimum is 10 s)
SPEAK_DRAIN_TIMEOUT_S = 5.0
MIN_CLAIM_CHECK_WORDS = 4  # skip claim-check on very short fragments
MAX_SENTENCE_CHARS = 400  # bounds Gemini prompt size per claim check
MAX_CONTRACT_CHARS = 200_000  # bounds per-workspace memory on a 512 MB box

COOKIE = "cc_ws"
COOKIE_MAX_AGE_S = 6 * 3600
CSP = (
    "default-src 'self'; connect-src 'self' ws: wss:; img-src 'self' data:; "
    "style-src 'self' 'unsafe-inline'; font-src 'self' data:; media-src 'self' blob:; "
    "worker-src 'self' blob:; frame-ancestors 'none'; base-uri 'none'; object-src 'none'; form-action 'self'"
)


def _env_num(name: str, default: float) -> float:
    """Read at call time so ops (and tests) can change limits without a redeploy of code."""
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


# server/stt.py and server/voice.py: same lazy-import pattern. See module
# docstring -- interfaces are fixed by contract even before the files exist.
try:
    from server.stt import StreamingTranscriber, keyterms_from_clauses
except ImportError:  # pragma: no cover - exercised only before stt.py exists
    StreamingTranscriber = None

    def keyterms_from_clauses(clauses: list[dict]) -> list[str]:  # noqa: ARG001
        return []


try:
    from server.voice import AlertSpeaker, build_alert_text, build_clause_answer_text
except ImportError:  # pragma: no cover - exercised only before voice.py exists
    AlertSpeaker = None

    def build_alert_text(clause: dict) -> str:  # noqa: ARG001
        return clause.get("literal_text", "")

    def build_clause_answer_text(clause: dict) -> str:  # noqa: ARG001
        return clause.get("literal_text", "")


app = FastAPI(title="ClauseCatcher", docs_url=None, redoc_url=None, openapi_url=None)
store = SessionStore()


def _is_https(scope: dict) -> bool:
    headers = dict(scope.get("headers") or [])
    return scope.get("scheme") in ("https", "wss") or headers.get(b"x-forwarded-proto") == b"https"


class SecurityHeadersMiddleware:
    """Pure ASGI (no BaseHTTPMiddleware) so it never buffers streamed bodies."""

    def __init__(self, app) -> None:  # noqa: ANN001
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        extra = [
            (b"content-security-policy", CSP.encode()),
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"no-referrer"),
            (b"permissions-policy", b"microphone=(self), camera=(), geolocation=()"),
        ]
        if _is_https(scope):
            extra.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))

        async def send_with_headers(message) -> None:  # noqa: ANN001
            if message["type"] == "http.response.start":
                message["headers"] = list(message.get("headers", [])) + extra
            await send(message)

        await self.app(scope, receive, send_with_headers)


class _BodyTooLarge(Exception):
    pass


class BodyLimitMiddleware:
    """Rejects bodies over MAX_PDF_BYTES + 64 KB before the route buffers them:
    by Content-Length up front, and by counting chunks for chunked uploads."""

    def __init__(self, app) -> None:  # noqa: ANN001
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        limit = MAX_PDF_BYTES + 64 * 1024
        too_large = JSONResponse(status_code=413, content={"detail": "file too large"})
        length = dict(scope["headers"]).get(b"content-length")
        if length is not None and (not length.isdigit() or int(length) > limit):
            return await too_large(scope, receive, send)

        received = 0
        exceeded = False
        started = False

        async def limited_receive():  # noqa: ANN202
            nonlocal received, exceeded
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    exceeded = True
                    raise _BodyTooLarge
            return message

        async def guarded_send(message) -> None:  # noqa: ANN001
            nonlocal started
            if exceeded:
                return  # drop whatever error response the app built; 413 below
            started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, guarded_send)
        except _BodyTooLarge:
            pass
        if exceeded and not started:
            await too_large(scope, receive, send)


app.add_middleware(BodyLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)  # outermost: 413s get headers too


def writable_workspace(request: Request, response: Response) -> Workspace:
    """The caller's workspace, created on first write; cookie (re)set every write."""
    workspace = store.get_workspace(request.cookies.get(COOKIE)) or store.new_workspace()
    response.set_cookie(
        COOKIE,
        workspace.workspace_id,
        max_age=COOKIE_MAX_AGE_S,
        httponly=True,
        samesite="strict",
        secure=_is_https(request.scope),
    )
    return workspace


def existing_workspace(request: Request) -> Workspace | None:
    return store.get_workspace(request.cookies.get(COOKIE))


# ---------------------------------------------------------------------------
# Claim-check seam: real Gemini call only when explicitly enabled with a key
# present (server/claim_check.get_claim_checker); otherwise a logged-once
# stub. Tests override this FastAPI dependency directly with fakes.
# ---------------------------------------------------------------------------
def get_claim_checker() -> Callable[[str, list[dict]], dict]:
    return _default_claim_checker_factory()


# ---------------------------------------------------------------------------
# STT / voice factory seams: constructing the real classes is deferred behind
# factories so tests can override construction with fakes (dependency_overrides)
# without ever importing/touching server.stt or server.voice's network code.
# ---------------------------------------------------------------------------
def get_stt_factory() -> Callable[..., Any]:
    def factory(*, api_key: str, on_turn: Callable, keyterms: list[str]) -> Any:
        if StreamingTranscriber is None:
            raise RuntimeError("server.stt not available yet")
        return StreamingTranscriber(api_key, on_turn=on_turn, keyterms=keyterms)

    return factory


def get_voice_factory() -> Callable[..., Any]:
    def factory(*, api_key: str, on_audio: Callable, on_event: Callable) -> Any:
        if AlertSpeaker is None:
            raise RuntimeError("server.voice not available yet")
        return AlertSpeaker(api_key, on_audio=on_audio, on_event=on_event)

    return factory


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class ConsentPayload(BaseModel):
    accepted: StrictBool


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/api/contract", status_code=status.HTTP_201_CREATED)
async def upload_contract(file: UploadFile, workspace: Workspace = Depends(writable_workspace)) -> dict:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="file must be application/pdf")
    pdf_bytes = await file.read(MAX_PDF_BYTES + 1)
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="file too large")
    try:
        clauses = await extract_clauses_safe(pdf_bytes)
    except ClauseExtractionError as exc:
        logger.warning("contract upload rejected: %s", exc)
        raise HTTPException(status_code=422, detail="unreadable PDF") from exc
    if sum(len(c.get("literal_text", "")) for c in clauses) > MAX_CONTRACT_CHARS:
        raise HTTPException(status_code=413, detail="contract too long")
    workspace.contract = clauses
    return {"clauses": clauses}


@app.post("/api/contract/demo", status_code=status.HTTP_201_CREATED)
async def demo_contract(workspace: Workspace = Depends(writable_workspace)) -> dict:
    workspace.contract = load_demo_contract()
    return {"clauses": workspace.contract}


@app.get("/api/contract")
async def get_contract(workspace: Workspace | None = Depends(existing_workspace)) -> dict:
    if workspace is None or workspace.contract is None:
        raise HTTPException(status_code=404, detail="no contract loaded")
    return {"clauses": workspace.contract}


@app.post("/api/consent")
async def set_consent(payload: ConsentPayload, workspace: Workspace = Depends(writable_workspace)) -> dict:
    workspace.consent = payload.accepted
    return {"consent": workspace.consent}


@app.post("/api/session/start", status_code=status.HTTP_201_CREATED)
async def start_session(workspace: Workspace | None = Depends(existing_workspace)) -> dict:
    if workspace is None or workspace.contract is None or not workspace.consent:
        raise HTTPException(status_code=409, detail="contract and consent are required before starting a session")
    session = store.start_session(workspace)
    return {"session_id": session.session_id}


def _report(session: SessionState, claim_check_state: str | None = None) -> dict:
    # claim_check_state tells "0 contradictions because every line was checked
    # and was clean" apart from "0 contradictions because nothing was checked".
    # Sockets pass the state their own checker had; REST reads it live.
    state = claim_check_state or checker_state()
    if session.claim_check_errors:
        state = "error"
    return {
        "claim_check_state": state,
        "contract_clauses_referenced": sorted(session.referenced_sections),
        "contradictions": session.contradictions,
        "transcript_count": session.transcript_count,
        "started_at": session.started_at.isoformat(),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "est_cost_usd": session.est_cost_usd,
        "claim_check_calls": session.claim_check_calls,
        "claim_check_errors": session.claim_check_errors,
    }


def owned_session(session_id: str, request: Request) -> SessionState:
    """404 (not 403) for someone else's session: don't confirm it exists."""
    session = store.get_session(session_id, request.cookies.get(COOKIE))
    if session is None:
        raise HTTPException(status_code=404, detail="unknown session")
    return session


@app.post("/api/session/{session_id}/end")
async def end_session(session: SessionState = Depends(owned_session)) -> dict:
    store.end_session(session)
    return _report(session)


@app.get("/api/session/{session_id}/report")
async def get_report(session: SessionState = Depends(owned_session)) -> dict:
    return _report(session)


@app.websocket("/ws/session/{session_id}")
async def session_ws(
    websocket: WebSocket,
    session_id: str,
    claim_checker: Callable[[str, list[dict]], dict] = Depends(get_claim_checker),
    stt_factory: Callable[..., Any] = Depends(get_stt_factory),
    voice_factory: Callable[..., Any] = Depends(get_voice_factory),
) -> None:
    allowed = [o.strip() for o in os.environ.get("CLAUSECATCHER_ALLOWED_ORIGINS", "").split(",") if o.strip()]
    if allowed and websocket.headers.get("origin") not in allowed:
        await websocket.close(code=1008)  # before accept -> HTTP 403, no socket
        return
    await websocket.accept()
    session = store.get_session(session_id, websocket.cookies.get(COOKIE))
    if session is None or session.ended_at is not None or session.ws_attached:
        await websocket.send_json({"type": "error", "message": "unknown session"})
        await websocket.close(code=1008)
        return
    if store.live_ws >= _env_num("CLAUSECATCHER_MAX_LIVE_WS", 2):
        await websocket.send_json({"type": "error", "message": "demo busy, try again shortly"})
        await websocket.close(code=1013)
        return
    # No await between the checks above and these two lines: atomic on the loop.
    session.ws_attached = True  # one socket per session, ever
    store.live_ws += 1

    send_lock = asyncio.Lock()

    async def send(payload: dict) -> None:
        async with send_lock:
            try:
                await websocket.send_json(payload)
            except Exception:  # noqa: BLE001 - socket may already be closing
                pass

    async def on_audio(pcm16: bytes, rate: int) -> None:
        await send(
            {
                "type": "agent_audio",
                "pcm16_b64": base64.b64encode(pcm16).decode("ascii"),
                "sample_rate": rate,
            }
        )

    async def on_event(event: dict) -> None:
        await send(event)

    last_alert_at: dict[str, float] = {}
    speak_tasks: list[asyncio.Task] = []
    stt: Any = None
    speaker: Any = None
    max_checks = _env_num("CLAUSECATCHER_MAX_CHECKS", 40)
    # computed once, before anything can fail: finish() closes over it
    claim_check_status = checker_state(claim_checker)
    last_check_error_at = float("-inf")

    async def send_check_error(message: str) -> None:
        """Tell the client a line was NOT checked. Rate-limited so a dead
        Gemini leg can't spam one frame per finalized turn."""
        nonlocal last_check_error_at
        now = time.monotonic()
        if now - last_check_error_at < CHECK_ERROR_COOLDOWN_S:
            return
        last_check_error_at = now
        await send({"type": "check_error", "message": message})

    async def _speak_alert(record: dict, clause: dict) -> None:
        try:
            result = await speaker.say_exactly(build_alert_text(clause))
        except Exception:  # noqa: BLE001 - a speaker failure must never crash the socket
            logger.exception("speaker.say_exactly (alert) failed for session %s", session_id)
            return
        record["literal_spoken"] = result.get("literal_spoken")
        record["similarity"] = result.get("similarity")

    async def _speak_answer(clause: dict) -> None:
        try:
            await speaker.say_exactly(build_clause_answer_text(clause))
        except Exception:  # noqa: BLE001
            logger.exception("speaker.say_exactly (answer) failed for session %s", session_id)

    async def handle_turn(sentence: str) -> None:
        # record transcript regardless of claim-check outcome
        session.transcript_count += 1
        sentence = sentence[:MAX_SENTENCE_CHARS]
        if len(sentence.split()) < MIN_CLAIM_CHECK_WORDS:
            return
        if session.claim_check_calls >= max_checks:
            await send_check_error("Claim-check limit reached for this call - later lines were not verified.")
            return
        session.claim_check_calls += 1
        if claim_check_status != "ready":
            await send_check_error("Claim check is off - lines are not being verified against the contract.")
        loop = asyncio.get_running_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, claim_checker, sentence, session.contract),
                timeout=CLAIM_CHECK_TIMEOUT_S,
            )
        except Exception:  # noqa: BLE001 - checker must never take the socket down
            session.claim_check_errors += 1
            logger.exception("claim_checker failed for session %s", session_id)
            # generic text: upstream error strings never reach the browser
            await send_check_error("Claim check is unavailable right now - this line was not verified.")
            return
        if result.get("error"):
            session.claim_check_errors += 1
            logger.warning("claim check error for session %s: %s", session_id, result["error"])
            await send_check_error("Claim check is unavailable right now - this line was not verified.")
            return  # a failed check never produces an alert
        if result.get("verdict") != "contradiction":
            return
        clause = session.get_clause(result.get("clause_id") or "")
        if clause is None:
            return
        section = clause["section_number"]
        now = time.monotonic()
        if now - last_alert_at.get(section, -ALERT_DEDUPE_S) < ALERT_DEDUPE_S:
            return
        last_alert_at[section] = now
        session.referenced_sections.add(section)
        record = {
            "sentence": sentence,
            "section_number": section,
            "literal_text": clause["literal_text"],
            "t": datetime.now(timezone.utc).isoformat(),
        }
        session.contradictions.append(record)
        await send(
            {
                "type": "alert",
                "section_number": section,
                "title": clause["title"],
                "literal_text": clause["literal_text"],
                "sentence": sentence,
                "t": record["t"],
            }
        )
        if speaker is not None:
            speak_tasks.append(asyncio.create_task(_speak_alert(record, clause)))

    async def handle_ask(section_number: str) -> None:
        clause = session.get_clause(section_number)
        if clause is None:
            await send({"type": "error", "message": "unknown section_number"})
            return
        session.referenced_sections.add(clause["section_number"])
        await send({"type": "clause", **clause})
        # ask spam: at most one spoken answer in flight (the text reply above still goes out)
        if speaker is not None and all(t.done() for t in speak_tasks):
            speak_tasks.append(asyncio.create_task(_speak_answer(clause)))

    turn_queue: asyncio.Queue[str] = asyncio.Queue()

    async def _turn_worker() -> None:
        """Run claim checks off the STT reader loop.

        `on_turn` is awaited from inside stt.py's `_reader_loop`, so awaiting a
        multi-second Gemini call there stopped us reading the AssemblyAI socket
        for the length of the check: later turns queued upstream, the session
        cap stopped being enforced on time, and every subsequent alert paid the
        backlog. Checks still run one at a time, so alerts keep their order.
        """
        while True:
            sentence = await turn_queue.get()
            try:
                await handle_turn(sentence)
            except Exception:  # noqa: BLE001 - one bad line must not kill the call
                logger.exception("handle_turn failed for session %s", session_id)
            finally:
                turn_queue.task_done()

    turn_task = asyncio.create_task(_turn_worker())

    async def on_turn(text: str, end_of_turn: bool) -> None:
        # live mic path: show partials + finals in the transcript pane (the
        # simulate seam renders its own line client-side, so it never comes here)
        await send({"type": "transcript", "text": text, "final": end_of_turn})
        if end_of_turn:
            turn_queue.put_nowait(text)

    cleaned = False

    async def finish() -> dict:
        nonlocal cleaned
        if cleaned:
            return _report(session, claim_check_status)
        cleaned = True
        session.ws_attached = False  # let the client reconnect to a call that is still open
        # stop checking the moment the call ends: any line still queued is
        # dropped rather than held open behind a slow check, and an in-flight
        # check is cancelled. The report counts what actually ran.
        turn_task.cancel()
        try:
            await turn_task
        except asyncio.CancelledError:
            pass
        if speak_tasks:
            _, pending = await asyncio.wait(speak_tasks, timeout=SPEAK_DRAIN_TIMEOUT_S)
            for t in pending:
                t.cancel()
        cost = 0.0
        if stt is not None:
            try:
                await stt.stop()
            except Exception:  # noqa: BLE001
                logger.exception("stt.stop failed for session %s", session_id)
            cost += getattr(stt, "est_cost_usd", 0.0) or 0.0
        if speaker is not None:
            try:
                await speaker.close()
            except Exception:  # noqa: BLE001
                logger.exception("speaker.close failed for session %s", session_id)
            cost += getattr(speaker, "est_cost_usd", 0.0) or 0.0
        session.est_cost_usd += cost
        store.spent_usd += cost
        store.end_session(session)
        return _report(session, claim_check_status)

    try:
        # -- set up STT + voice (concurrently) -------------------------------
        stt_status = "disabled"
        voice_status = "disabled"
        api_key = os.environ.get("ASSEMBLYAI_API_KEY")
        paid_ok = (
            os.environ.get("CLAUSECATCHER_PAID_DISABLED") != "1"
            and store.spent_usd < _env_num("CLAUSECATCHER_BUDGET_USD", 3.0)
        )
        if api_key and not paid_ok:
            logger.warning("paid upstreams refused (kill switch or budget); spent=%.4f", store.spent_usd)
            await send({"type": "error", "message": "live audio is paused for this demo; simulate lines instead"})

        async def _setup_stt() -> None:
            nonlocal stt, stt_status
            try:
                stt = stt_factory(api_key=api_key, on_turn=on_turn, keyterms=keyterms_from_clauses(session.contract))
                await stt.start()
                stt_status = "connected"
            except Exception:  # noqa: BLE001
                logger.exception("StreamingTranscriber setup failed for session %s", session_id)
                stt = None
                stt_status = "error"

        async def _setup_voice() -> None:
            nonlocal speaker, voice_status
            try:
                speaker = voice_factory(api_key=api_key, on_audio=on_audio, on_event=on_event)
                await speaker.open()
                voice_status = "connected"
            except Exception:  # noqa: BLE001
                logger.exception("AlertSpeaker setup failed for session %s", session_id)
                speaker = None
                voice_status = "error"

        if api_key and paid_ok:
            await asyncio.gather(_setup_stt(), _setup_voice())

        await send({"type": "status", "stt": stt_status, "voice": voice_status, "claim_check": claim_check_status})

        deadline = time.monotonic() + _env_num("CLAUSECATCHER_SESSION_CAP_S", 420)
        idle_s = _env_num("CLAUSECATCHER_IDLE_TIMEOUT_S", 60)
        while True:
            remaining = deadline - time.monotonic()
            try:
                if remaining <= 0:
                    raise asyncio.TimeoutError
                raw = await asyncio.wait_for(websocket.receive(), timeout=min(idle_s, remaining))
            except asyncio.TimeoutError:
                reason = "time_limit" if time.monotonic() >= deadline else "idle"
                report = await finish()
                await send({"type": "session_ended", "reason": reason, "report": report})
                try:
                    await websocket.close(code=1000)
                except Exception:  # noqa: BLE001
                    pass
                break
            if raw["type"] == "websocket.disconnect":
                break
            if raw.get("bytes") is not None:
                if stt is not None:
                    try:
                        await stt.send_audio(raw["bytes"])
                    except Exception:  # noqa: BLE001
                        logger.exception("stt.send_audio failed for session %s", session_id)
                continue
            text = raw.get("text")
            if text is None:
                continue
            try:
                msg = json.loads(text)
            except json.JSONDecodeError:
                await send({"type": "error", "message": "invalid JSON"})
                continue
            if not isinstance(msg, dict):
                await send({"type": "error", "message": "invalid message"})
                continue

            msg_type = msg.get("type")
            if msg_type == "transcript":
                await handle_turn(str(msg.get("text", "")))
            elif msg_type == "ask":
                await handle_ask(str(msg.get("section_number", "")))
            elif msg_type == "stop":
                report = await finish()
                await send({"type": "session_ended", "reason": "stopped", "report": report})
                break
            else:
                await send({"type": "error", "message": "unknown message type"})
    except WebSocketDisconnect:
        pass
    finally:
        try:
            if not cleaned:
                await finish()
        finally:
            store.live_ws -= 1


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception) -> JSONResponse:  # pragma: no cover - safety net
    logger.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": "internal error"})


class SPAStaticFiles(StaticFiles):
    """StaticFiles that falls back to index.html for any unmatched path that
    isn't under /api or /ws, so a client-side router (none yet, but the next
    round may add one) gets index.html instead of a 404. Real /api and /ws
    routes are registered as explicit routes above and are matched before
    this mount ever sees the request; a genuinely unknown /api/... path
    still 404s instead of silently returning HTML.
    """

    async def get_response(self, path: str, scope):  # noqa: ANN001 - Starlette's own signature
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404 and not path.startswith("api") and not path.startswith("ws"):
                return await super().get_response("index.html", scope)
            raise


# Serve the built frontend (frontend/dist) when present; otherwise fall back
# to the no-build-step web/ UI. Both are mounted at "/" with SPA fallback so
# either one keeps working standalone.
if FRONTEND_DIST_DIR.exists():
    app.mount("/", SPAStaticFiles(directory=str(FRONTEND_DIST_DIR), html=True), name="frontend")
elif WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
