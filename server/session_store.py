"""In-memory state for the single demo session (per SCOPE_RESET: no DB, no auth).

One process, one contract, one consent flag, and a handful of session runtime
states keyed by session_id. Plain dict/list mutations are atomic in CPython
and every route here runs on the one event loop with no `await` between a
read and its matching write, so no lock is needed.
# ponytail: no lock — single-process demo, add asyncio.Lock if that changes.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class SessionState:
    session_id: str
    started_at: datetime
    ended_at: datetime | None = None
    transcript_count: int = 0
    contradictions: list[dict] = field(default_factory=list)
    referenced_sections: set[str] = field(default_factory=set)


class SessionStore:
    def __init__(self) -> None:
        self.contract: list[dict] | None = None
        self.consent: bool = False
        self.sessions: dict[str, SessionState] = {}

    # -- contract / consent (global, single demo) --------------------------
    def set_contract(self, clauses: list[dict]) -> None:
        self.contract = clauses

    def set_consent(self, accepted: bool) -> None:
        self.consent = accepted

    def get_clause(self, section_number: str) -> dict | None:
        if not self.contract:
            return None
        for clause in self.contract:
            if clause.get("section_number") == section_number:
                return clause
        return None

    # -- sessions ------------------------------------------------------------
    def start_session(self) -> SessionState:
        session = SessionState(session_id=uuid.uuid4().hex, started_at=datetime.now(timezone.utc))
        self.sessions[session.session_id] = session
        return session

    def get_session(self, session_id: str) -> SessionState | None:
        return self.sessions.get(session_id)

    def end_session(self, session_id: str) -> SessionState | None:
        session = self.sessions.get(session_id)
        if session is not None and session.ended_at is None:
            session.ended_at = datetime.now(timezone.utc)
        return session


def demo() -> None:
    """ponytail self-check."""
    store = SessionStore()
    assert store.get_clause("3.1") is None
    store.set_contract([{"section_number": "3.1", "title": "Pricing", "literal_text": "Flat $48,000."}])
    assert store.get_clause("3.1")["title"] == "Pricing"
    assert store.get_clause("9.9") is None

    store.set_consent(True)
    assert store.consent is True

    s = store.start_session()
    assert store.get_session(s.session_id) is s
    assert s.ended_at is None
    ended = store.end_session(s.session_id)
    assert ended.ended_at is not None
    assert store.get_session("nope") is None
    print("session_store.py demo: OK")


if __name__ == "__main__":
    demo()
