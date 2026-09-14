"""ClauseCatcher API skeleton (see docs/adr/0001-voice-architecture.md, docs/SCOPE_RESET_2026-09-14.md).

Thin skeleton for today: no real AssemblyAI/Gemini calls. The websocket takes
JSON transcript frames as a stand-in for STT, and runs an injectable
claim_checker (default: a stub) as a stand-in for spikes/claim_check.check_claim.
Both are named seams — see the two TODOs below for how they get wired up.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import Depends, FastAPI, HTTPException, UploadFile, WebSocket, WebSocketDisconnect, status
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server.session_store import SessionStore

logger = logging.getLogger("clausecatcher")

ROOT_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT_DIR / "web"
DEMO_CONTRACT_JSON = ROOT_DIR / "spikes" / "harness" / "fake_contract.json"

MAX_PDF_BYTES = int(os.environ.get("CLAUSECATCHER_MAX_PDF_BYTES", 5 * 1024 * 1024))

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


app = FastAPI(title="ClauseCatcher")
store = SessionStore()


# ---------------------------------------------------------------------------
# Claim-check seam
# TODO wire spikes/claim_check.check_claim here behind an env flag
# (e.g. CLAUSECATCHER_REAL_CLAIM_CHECK=1) once ready to call Gemini. Left
# unwired intentionally for this task.
# ---------------------------------------------------------------------------
def _stub_claim_checker(sentence: str, clauses: list[dict]) -> dict:
    return {
        "verdict": "unclear",
        "clause_id": None,
        "confidence": 0.0,
        "latency_ms": 0.0,
        "model": None,
        "error": None,
    }


def get_claim_checker() -> Callable[[str, list[dict]], dict]:
    return _stub_claim_checker


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
    return {
        "contract_clauses_referenced": sorted(session.referenced_sections),
        "contradictions": session.contradictions,
        "transcript_count": session.transcript_count,
        "started_at": session.started_at.isoformat(),
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
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
) -> None:
    await websocket.accept()
    session = store.get_session(session_id)
    if session is None:
        await websocket.send_json({"type": "error", "message": "unknown session"})
        await websocket.close(code=1008)
        return

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "invalid JSON"})
                continue

            msg_type = msg.get("type")

            if msg_type == "transcript":
                sentence = msg.get("text", "")
                session.transcript_count += 1
                try:
                    result = claim_checker(sentence, store.contract or [])
                except Exception:  # noqa: BLE001 - checker must never take the socket down
                    logger.exception("claim_checker raised for session %s", session_id)
                    continue
                if result.get("verdict") == "contradiction":
                    clause = store.get_clause(result.get("clause_id") or "")
                    if clause is not None:
                        session.referenced_sections.add(clause["section_number"])
                        session.contradictions.append(
                            {
                                "sentence": sentence,
                                "section_number": clause["section_number"],
                                "literal_text": clause["literal_text"],
                                "t": datetime.now(timezone.utc).isoformat(),
                            }
                        )
                        await websocket.send_json(
                            {
                                "type": "alert",
                                "section_number": clause["section_number"],
                                "title": clause["title"],
                                "literal_text": clause["literal_text"],
                                "sentence": sentence,
                            }
                        )
                    # clause_id not in the stored contract -> no alert, silently ignored.

            elif msg_type == "ask":
                section_number = msg.get("section_number", "")
                clause = store.get_clause(section_number)
                if clause is None:
                    await websocket.send_json({"type": "error", "message": "unknown section_number"})
                else:
                    session.referenced_sections.add(clause["section_number"])
                    await websocket.send_json({"type": "clause", **clause})

            else:
                await websocket.send_json({"type": "error", "message": f"unknown message type: {msg_type}"})
    except WebSocketDisconnect:
        pass


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc: Exception) -> JSONResponse:  # pragma: no cover - safety net
    logger.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": "internal error"})


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")
