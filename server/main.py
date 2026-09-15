"""ClauseCatcher API (see docs/adr/0001-voice-architecture.md, docs/SCOPE_RESET_2026-09-14.md).

Architecture: browser mic PCM16 16 kHz binary frames -> server -> a
StreamingTranscriber (server/stt.py) -> per finalized turn -> claim_check
(server/claim_check.py) -> on contradiction: send the literal contract clause
as alert JSON (never LLM text) AND speak it via AlertSpeaker (server/voice.py)
whose audio streams back to the browser. Monitor Q&A ("ask") looks the clause
up by section_number directly (no agent tool calling) and speaks the answer
the same way.

server/stt.py and server/voice.py are owned by other agents building
concurrently; both are imported lazily/defensively (same pattern already used
below for server/clauses.py) so this app still starts and serves everything
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

from fastapi import Depends, FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server.session_store import SessionStore
from server.claim_check import get_call_stats
from server.claim_check import get_claim_checker as _default_claim_checker_factory

logger = logging.getLogger("clausecatcher")

ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"
DEMO_CONTRACT_JSON = ROOT_DIR / "spikes" / "harness" / "fake_contract.json"

MAX_PDF_BYTES = int(os.environ.get("CLAUSECATCHER_MAX_PDF_BYTES", 5 * 1024 * 1024))

# Per finalized turn behavior tuning (see WS protocol behavior spec).
ALERT_DEDUPE_S = 20.0
CLAIM_CHECK_TIMEOUT_S = 10.0
SPEAK_DRAIN_TIMEOUT_S = 5.0
MIN_CLAIM_CHECK_WORDS = 4  # skip claim-check on very short fragments

# clauses.py is owned by a different agent building concurrently; import it
# lazily/defensively so this app still starts and serves everything else
# before that file lands.
try:
    from server.clauses import ClauseExtractionError, extract_clauses, load_demo_contract
except ImportError:  # pragma: no cover - exercised only before clauses.py exists
    extract_clauses = None
    load_demo_contract = None

    class ClauseExtractionError(Exception):
        pass


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


app = FastAPI(title="ClauseCatcher")
store = SessionStore()


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
    accepted: bool


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/api/contract", status_code=status.HTTP_201_CREATED)
async def upload_contract(file: UploadFile) -> dict:
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=422, detail="file must be application/pdf")
    pdf_bytes = await file.read()
    if len(pdf_bytes) > MAX_PDF_BYTES:
        raise HTTPException(status_code=422, detail="file too large")
    if extract_clauses is None:
        raise HTTPException(status_code=503, detail="clause extraction not available yet")
    try:
        clauses = extract_clauses(pdf_bytes)
    except ClauseExtractionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    store.set_contract(clauses)
    return {"clauses": clauses}


@app.post("/api/contract/demo", status_code=status.HTTP_201_CREATED)
async def demo_contract() -> dict:
    if load_demo_contract is not None:
        clauses = load_demo_contract()
    else:
        # ponytail: fallback until clauses.py exists, same fixture either way.
        clauses = json.loads(DEMO_CONTRACT_JSON.read_text())["clauses"]
    store.set_contract(clauses)
    return {"clauses": clauses}


@app.get("/api/contract")
async def get_contract() -> dict:
    if store.contract is None:
        raise HTTPException(status_code=404, detail="no contract loaded")
    return {"clauses": store.contract}


@app.post("/api/consent")
async def set_consent(payload: ConsentPayload) -> dict:
    store.set_consent(payload.accepted)
    return {"consent": store.consent}


@app.post("/api/session/start", status_code=status.HTTP_201_CREATED)
async def start_session() -> dict:
    if store.contract is None or not store.consent:
        raise HTTPException(status_code=409, detail="contract and consent are required before starting a session")
    session = store.start_session()
    return {"session_id": session.session_id}


def _report(session_id: str) -> dict:
    session = store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="unknown session")
    stats = get_call_stats()
    return {
        "contract_clauses_referenced": sorted(session.referenced_sections),
        "contradictions": session.contradictions,
        "transcript_count": session.transcript_count,
        "started_at": session.started_at.isoformat(),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        # ponytail: SessionState (session_store.py) is out of scope for this
        # task, so runtime-only fields (cost) are set as plain instance
        # attributes on the dataclass instance rather than editing its schema.
        "est_cost_usd": getattr(session, "est_cost_usd", 0.0),
        "claim_check_calls": stats["calls"],
        "claim_check_errors": stats["errors"],
    }


@app.post("/api/session/{session_id}/end")
async def end_session(session_id: str) -> dict:
    if store.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="unknown session")
    store.end_session(session_id)
    return _report(session_id)


@app.get("/api/session/{session_id}/report")
async def get_report(session_id: str) -> dict:
    return _report(session_id)


@app.websocket("/ws/session/{session_id}")
async def session_ws(
    websocket: WebSocket,
    session_id: str,
    claim_checker: Callable[[str, list[dict]], dict] = Depends(get_claim_checker),
    stt_factory: Callable[..., Any] = Depends(get_stt_factory),
    voice_factory: Callable[..., Any] = Depends(get_voice_factory),
) -> None:
    await websocket.accept()
    session = store.get_session(session_id)
    if session is None:
        await websocket.send_json({"type": "error", "message": "unknown session"})
        await websocket.close(code=1008)
        return

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
        if len(sentence.split()) < MIN_CLAIM_CHECK_WORDS:
            return
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(None, claim_checker, sentence, store.contract or []),
                timeout=CLAIM_CHECK_TIMEOUT_S,
            )
        except Exception:  # noqa: BLE001 - checker must never take the socket down
            logger.exception("claim_checker failed for session %s", session_id)
            return
        if result.get("verdict") != "contradiction":
            return
        clause = store.get_clause(result.get("clause_id") or "")
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
        clause = store.get_clause(section_number)
        if clause is None:
            await send({"type": "error", "message": "unknown section_number"})
            return
        session.referenced_sections.add(clause["section_number"])
        await send({"type": "clause", **clause})
        if speaker is not None:
            speak_tasks.append(asyncio.create_task(_speak_answer(clause)))

    async def on_turn(text: str, end_of_turn: bool) -> None:
        if end_of_turn:
            await handle_turn(text)

    # -- set up STT + voice (concurrently) -------------------------------
    stt_status = "disabled"
    voice_status = "disabled"
    api_key = os.environ.get("ASSEMBLYAI_API_KEY")

    async def _setup_stt() -> None:
        nonlocal stt, stt_status
        try:
            stt = stt_factory(api_key=api_key, on_turn=on_turn, keyterms=keyterms_from_clauses(store.contract or []))
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

    if api_key:
        await asyncio.gather(_setup_stt(), _setup_voice())

    await send({"type": "status", "stt": stt_status, "voice": voice_status})

    cleaned = False

    async def finish() -> dict:
        nonlocal cleaned
        if cleaned:
            return _report(session_id)
        cleaned = True
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
        session.est_cost_usd = getattr(session, "est_cost_usd", 0.0) + cost
        store.end_session(session_id)
        return _report(session_id)

    try:
        while True:
            raw = await websocket.receive()
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

            msg_type = msg.get("type")
            if msg_type == "transcript":
                await handle_turn(msg.get("text", ""))
            elif msg_type == "ask":
                await handle_ask(msg.get("section_number", ""))
            elif msg_type == "stop":
                report = await finish()
                await send({"type": "session_ended", "report": report})
                break
            else:
                await send({"type": "error", "message": f"unknown message type: {msg_type}"})
    except WebSocketDisconnect:
        pass
    finally:
        if not cleaned:
            await finish()


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception) -> JSONResponse:  # pragma: no cover - safety net
    logger.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": "internal error"})


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
