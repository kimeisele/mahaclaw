"""Session Manager — signed SQLite ledger for gateway sessions.

Every session action is logged as an append-only, hash-chained entry.
No plain Markdown memory.  Each row contains:
  - session_id: unique session key (agent:channel:user format)
  - seq: monotonic sequence number within the session
  - ts: timestamp
  - kind: message_in | message_out | pipeline | error | system
  - data: JSON payload
  - prev_hash: SHA-256 of the previous row (chain integrity)
  - row_hash: SHA-256 of this row (tamper detection)

Pure stdlib: sqlite3, hashlib, json, time.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = REPO_ROOT / "mahaclaw_sessions.db"

_SCHEMA = """\
CREATE TABLE IF NOT EXISTS session_ledger (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT    NOT NULL,
    seq         INTEGER NOT NULL,
    ts          REAL    NOT NULL,
    kind        TEXT    NOT NULL,
    data        TEXT    NOT NULL,
    prev_hash   TEXT    NOT NULL,
    row_hash    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_session_id ON session_ledger(session_id);
CREATE INDEX IF NOT EXISTS idx_session_seq ON session_ledger(session_id, seq);

CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    created_at   REAL NOT NULL,
    updated_at   REAL NOT NULL,
    target       TEXT NOT NULL DEFAULT 'agent-research',
    message_count INTEGER NOT NULL DEFAULT 0,
    metadata     TEXT NOT NULL DEFAULT '{}'
);
"""


def _compute_hash(session_id: str, seq: int, ts: float, kind: str, data: str, prev_hash: str) -> str:
    """Compute the hash for a ledger row."""
    raw = f"{session_id}:{seq}:{ts}:{kind}:{data}:{prev_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass
class LedgerEntry:
    session_id: str
    seq: int
    ts: float
    kind: str
    data: dict
    prev_hash: str
    row_hash: str


@dataclass
class Session:
    session_id: str
    created_at: float
    updated_at: float
    target: str
    message_count: int
    metadata: dict = field(default_factory=dict)


class SessionManager:
    """Manages sessions with a signed, append-only SQLite ledger."""

    def __init__(self, db_path: Path | str | None = None):
        self._db_path = str(db_path or DEFAULT_DB)
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    # --- Session CRUD ---

    def get_or_create(self, session_id: str, target: str = "agent-research") -> Session:
        """Get existing session or create a new one."""
        row = self._conn.execute(
            "SELECT session_id, created_at, updated_at, target, message_count, metadata "
            "FROM sessions WHERE session_id = ?", (session_id,),
        ).fetchone()

        if row:
            return Session(
                session_id=row[0], created_at=row[1], updated_at=row[2],
                target=row[3], message_count=row[4], metadata=json.loads(row[5]),
            )

        now = time.time()
        self._conn.execute(
            "INSERT INTO sessions (session_id, created_at, updated_at, target) VALUES (?, ?, ?, ?)",
            (session_id, now, now, target),
        )
        self._conn.commit()

        # Write genesis ledger entry
        self._append(session_id, "system", {"event": "session_created", "target": target})

        return Session(session_id=session_id, created_at=now, updated_at=now,
                       target=target, message_count=0)

    def list_sessions(self, limit: int = 50) -> list[Session]:
        """List recent sessions."""
        rows = self._conn.execute(
            "SELECT session_id, created_at, updated_at, target, message_count, metadata "
            "FROM sessions ORDER BY updated_at DESC LIMIT ?", (limit,),
        ).fetchall()
        return [
            Session(r[0], r[1], r[2], r[3], r[4], json.loads(r[5]))
            for r in rows
        ]

    # --- Ledger (append-only, hash-chained) ---

    def _get_last_hash(self, session_id: str) -> str:
        """Get the hash of the last entry for a session.  Returns '0' for genesis."""
        row = self._conn.execute(
            "SELECT row_hash FROM session_ledger WHERE session_id = ? ORDER BY seq DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return row[0] if row else "0"

    def _get_next_seq(self, session_id: str) -> int:
        row = self._conn.execute(
            "SELECT MAX(seq) FROM session_ledger WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return (row[0] or 0) + 1

    def _append(self, session_id: str, kind: str, data: dict) -> LedgerEntry:
        """Append a hash-chained entry to the ledger."""
        seq = self._get_next_seq(session_id)
        ts = time.time()
        prev_hash = self._get_last_hash(session_id)
        data_str = json.dumps(data, sort_keys=True)
        row_hash = _compute_hash(session_id, seq, ts, kind, data_str, prev_hash)

        self._conn.execute(
            "INSERT INTO session_ledger (session_id, seq, ts, kind, data, prev_hash, row_hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, seq, ts, kind, data_str, prev_hash, row_hash),
        )
        self._conn.execute(
            "UPDATE sessions SET updated_at = ?, message_count = message_count + 1 WHERE session_id = ?",
            (ts, session_id),
        )
        self._conn.commit()

        return LedgerEntry(session_id, seq, ts, kind, data, prev_hash, row_hash)

    def log_message_in(self, session_id: str, message: str, metadata: dict | None = None) -> LedgerEntry:
        """Log an incoming user message."""
        return self._append(session_id, "message_in", {
            "message": message,
            **(metadata or {}),
        })

    def log_message_out(self, session_id: str, envelope_id: str, correlation_id: str,
                         target: str, element: str, zone: str) -> LedgerEntry:
        """Log an outgoing federation envelope."""
        return self._append(session_id, "message_out", {
            "envelope_id": envelope_id,
            "correlation_id": correlation_id,
            "target": target,
            "element": element,
            "zone": zone,
        })

    def log_pipeline(self, session_id: str, stage: str, data: dict) -> LedgerEntry:
        """Log a pipeline stage result."""
        return self._append(session_id, "pipeline", {"stage": stage, **data})

    def log_response(self, session_id: str, response: dict) -> LedgerEntry:
        """Log a federation response."""
        return self._append(session_id, "response", response)

    def log_error(self, session_id: str, error: str) -> LedgerEntry:
        """Log an error."""
        return self._append(session_id, "error", {"error": error})

    # --- History retrieval ---

    def get_history(self, session_id: str, limit: int = 50) -> list[LedgerEntry]:
        """Get recent ledger entries for a session."""
        rows = self._conn.execute(
            "SELECT session_id, seq, ts, kind, data, prev_hash, row_hash "
            "FROM session_ledger WHERE session_id = ? ORDER BY seq DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [
            LedgerEntry(r[0], r[1], r[2], r[3], json.loads(r[4]), r[5], r[6])
            for r in reversed(rows)
        ]

    def verify_chain(self, session_id: str) -> tuple[bool, int]:
        """Verify the hash chain integrity for a session.

        Returns (is_valid, entries_checked).
        """
        rows = self._conn.execute(
            "SELECT session_id, seq, ts, kind, data, prev_hash, row_hash "
            "FROM session_ledger WHERE session_id = ? ORDER BY seq ASC",
            (session_id,),
        ).fetchall()

        if not rows:
            return True, 0

        prev = "0"
        for r in rows:
            expected = _compute_hash(r[0], r[1], r[2], r[3], r[4], r[5])
            if expected != r[6]:
                return False, r[1]
            if r[5] != prev:
                return False, r[1]
            prev = r[6]

        return True, len(rows)
