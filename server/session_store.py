"""In-memory state, isolated per browser (no DB, no accounts).

A Workspace is keyed by an unguessable httponly cookie (cc_ws) and holds that
browser's contract + consent. A SessionState snapshots its workspace's
contract at start, so a later upload never changes a live call. Both maps are
capped (oldest dropped) so a flood can't grow memory without bound.
Every mutation runs on the one event loop with no `await` between a read and
its matching write, so no lock is needed.
# ponytail: no lock, single-process demo; add asyncio.Lock if that changes.
"""
from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Workspace:
    workspace_id: str
    contract: list[dict] | None = None
    consent: bool = False


@dataclass
class SessionState:
    session_id: str
    workspace_id: str
    contract: list[dict]
    started_at: datetime
    ended_at: datetime | None = None
    ws_attached: bool = False
    transcript_count: int = 0
    contradictions: list[dict] = field(default_factory=list)
    referenced_sections: set[str] = field(default_factory=set)
    est_cost_usd: float = 0.0
    claim_check_calls: int = 0
    claim_check_errors: int = 0

    def get_clause(self, section_number: str) -> dict | None:
        return next((c for c in self.contract if c.get("section_number") == section_number), None)


class SessionStore:
    def __init__(self, max_workspaces: int = 1000, max_sessions: int = 500) -> None:
        self.max_workspaces = max_workspaces
        self.max_sessions = max_sessions
        self.workspaces: dict[str, Workspace] = {}  # insertion order == LRU order
        self.sessions: dict[str, SessionState] = {}
        self.live_ws = 0  # sockets currently attached, process-wide
        self.spent_usd = 0.0  # est. paid-upstream spend, process-wide

    # -- workspaces -------------------------------------------------------------
    def new_workspace(self) -> Workspace:
        ws = Workspace(workspace_id=secrets.token_urlsafe(32))
        # Evict BEFORE inserting. Inserting first meant the brand-new, still
        # empty workspace was itself the first "empty" match below, so the
        # loop picked it, hit the self-eviction guard, broke, and nothing was
        # ever evicted once every older workspace held a contract - which is
        # every real request. The cap silently stopped existing.
        while len(self.workspaces) >= self.max_workspaces:
            # Evict empty workspaces first, oldest one, and only then fall back
            # to the oldest workspace overall. Straight LRU let anyone flush a
            # real user's uploaded contract: POST /api/contract/demo needs no
            # body, no cookie and no auth, so ~1000 of them in a loop pushed
            # every loaded contract out and the app answered "no contract
            # loaded" to the person who had just uploaded one. Same shape as
            # the session eviction below.
            victim = next((w for w in self.workspaces.values() if not w.contract), None) or next(iter(self.workspaces.values()))
            del self.workspaces[victim.workspace_id]
        self.workspaces[ws.workspace_id] = ws
        return ws

    def get_workspace(self, workspace_id: str | None) -> Workspace | None:
        ws = self.workspaces.pop(workspace_id, None) if workspace_id else None
        if ws is not None:
            self.workspaces[workspace_id] = ws  # touch: move to newest
        return ws

    # -- sessions ---------------------------------------------------------------
    def start_session(self, workspace: Workspace) -> SessionState:
        session = SessionState(
            session_id=uuid.uuid4().hex,
            workspace_id=workspace.workspace_id,
            contract=list(workspace.contract or []),
            started_at=datetime.now(timezone.utc),
        )
        self.sessions[session.session_id] = session
        while len(self.sessions) > self.max_sessions:
            # oldest ended first, else oldest never-attached; never a live call
            victim = next((s for s in self.sessions.values() if s.ended_at is not None), None) or next(
                (s for s in self.sessions.values() if not s.ws_attached), None
            )
            if victim is None:
                break
            del self.sessions[victim.session_id]
        return session

    def get_session(self, session_id: str, workspace_id: str | None) -> SessionState | None:
        session = self.sessions.get(session_id)
        if session is None or not workspace_id or not workspace_id.isascii():
            return None
        if not secrets.compare_digest(session.workspace_id, workspace_id):
            return None
        return session

    def end_session(self, session: SessionState) -> None:
        if session.ended_at is None:
            session.ended_at = datetime.now(timezone.utc)


def demo() -> None:
    """ponytail self-check."""
    store = SessionStore(max_workspaces=2)
    ws = store.new_workspace()
    ws.contract = [{"section_number": "3.1", "title": "Pricing", "literal_text": "Flat $48,000."}]
    ws.consent = True
    s = store.start_session(ws)
    ws.contract = []  # later upload must not touch the snapshot
    assert s.get_clause("3.1")["title"] == "Pricing"
    assert store.get_session(s.session_id, ws.workspace_id) is s
    assert store.get_session(s.session_id, "someone-else") is None
    store.end_session(s)
    assert s.ended_at is not None
    store.new_workspace(), store.new_workspace()
    assert store.get_workspace(ws.workspace_id) is None  # evicted (its contract was emptied above)

    # A flood of empty workspaces must not evict one that holds a contract:
    # POST /api/contract/demo needs no body, cookie or auth, so under straight
    # LRU anyone could loop it and flush every real upload.
    flood = SessionStore(max_workspaces=2)
    keeper = flood.new_workspace()
    keeper.contract = [{"section_number": "3.1", "title": "Pricing", "literal_text": "Flat $48,000."}]
    for _ in range(10):
        flood.new_workspace()
    assert flood.get_workspace(keeper.workspace_id) is keeper, "a contract-bearing workspace was evicted"

    # ...and the cap must still hold when EVERY workspace has a contract, which
    # is what real traffic looks like. Preferring empty victims must not turn
    # into never evicting at all: that is unbounded memory on an open endpoint.
    capped = SessionStore(max_workspaces=10)
    for _ in range(500):
        capped.new_workspace().contract = [{"section_number": "3.1", "literal_text": "x" * 100}]
    assert len(capped.workspaces) <= 10, f"cap defeated: holding {len(capped.workspaces)}"
    print("session_store.py demo: OK")


if __name__ == "__main__":
    demo()
