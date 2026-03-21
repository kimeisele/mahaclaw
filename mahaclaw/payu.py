"""Payu — Elimination / Garbage Collection.

Karmendriya #5 — Action Organ: elimination
Category: KARMENDRIYA (Action Organ)

Payu eliminates stale data: rotates outbox, expires sessions,
removes old envelopes. Mirrors steward's context compaction +
ShivaLifecycleManager (destroys stale intents).

ANAURALIA: All operations return counts and booleans. No prose.

Pure stdlib. No pip deps.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PayuResult:
    """Result of a cleanup operation.

    ANAURALIA: Only counts and booleans.
    """
    envelopes_removed: int = 0
    envelopes_archived: int = 0
    sessions_expired: int = 0
    bytes_freed: int = 0
    success: bool = True


# Defaults
DEFAULT_MAX_OUTBOX = 1000       # max envelopes in outbox
DEFAULT_MAX_AGE_S = 86400       # 24 hours
DEFAULT_SESSION_TTL_S = 604800  # 7 days


def rotate_outbox(
    outbox_path: Path,
    max_entries: int = DEFAULT_MAX_OUTBOX,
    max_age_s: float = DEFAULT_MAX_AGE_S,
) -> PayuResult:
    """Rotate outbox — remove old/excess envelopes.

    Keeps recent envelopes, archives or discards old ones.
    Returns count of removed envelopes.
    """
    if not outbox_path.exists():
        return PayuResult()

    try:
        data = json.loads(outbox_path.read_text())
    except (json.JSONDecodeError, OSError):
        return PayuResult(success=False)

    if not isinstance(data, list):
        return PayuResult()

    original_count = len(data)
    now = time.time()

    # Filter: keep envelopes within age limit
    kept = []
    removed = 0
    for envelope in data:
        ts = envelope.get("timestamp", 0)
        if isinstance(ts, (int, float)) and (now - ts) > max_age_s:
            removed += 1
        else:
            kept.append(envelope)

    # Trim to max entries (keep newest)
    if len(kept) > max_entries:
        excess = len(kept) - max_entries
        kept = kept[excess:]
        removed += excess

    if removed > 0:
        new_data = json.dumps(kept, indent=2)
        old_size = outbox_path.stat().st_size
        outbox_path.write_text(new_data)
        new_size = outbox_path.stat().st_size
        return PayuResult(
            envelopes_removed=removed,
            bytes_freed=max(0, old_size - new_size),
        )

    return PayuResult()


def expire_sessions(
    db_path: Path,
    ttl_s: float = DEFAULT_SESSION_TTL_S,
) -> PayuResult:
    """Expire old sessions from the session database.

    Removes sessions not updated within ttl_s seconds.
    """
    import sqlite3

    if not db_path.exists():
        return PayuResult()

    try:
        conn = sqlite3.connect(str(db_path))
        cutoff = time.time() - ttl_s
        cursor = conn.execute(
            "DELETE FROM sessions WHERE updated_at < ?", (cutoff,)
        )
        expired = cursor.rowcount
        if expired > 0:
            # Also clean up orphaned ledger entries
            conn.execute(
                "DELETE FROM session_ledger WHERE session_id NOT IN "
                "(SELECT session_id FROM sessions)"
            )
        conn.commit()
        conn.close()
        return PayuResult(sessions_expired=expired)
    except Exception:
        return PayuResult(success=False)


def clean_inbox(
    inbox_path: Path,
    max_age_s: float = DEFAULT_MAX_AGE_S,
) -> PayuResult:
    """Remove old responses from inbox."""
    if not inbox_path.exists():
        return PayuResult()

    try:
        data = json.loads(inbox_path.read_text())
    except (json.JSONDecodeError, OSError):
        return PayuResult(success=False)

    if not isinstance(data, list):
        return PayuResult()

    now = time.time()
    kept = []
    removed = 0
    for entry in data:
        ts = entry.get("timestamp", 0)
        if isinstance(ts, (int, float)) and (now - ts) > max_age_s:
            removed += 1
        else:
            kept.append(entry)

    if removed > 0:
        inbox_path.write_text(json.dumps(kept, indent=2))

    return PayuResult(envelopes_removed=removed)


def sweep(
    outbox_path: Path,
    inbox_path: Path,
    db_path: Path,
    max_outbox: int = DEFAULT_MAX_OUTBOX,
    max_age_s: float = DEFAULT_MAX_AGE_S,
    session_ttl_s: float = DEFAULT_SESSION_TTL_S,
) -> PayuResult:
    """Full cleanup sweep — outbox + inbox + sessions."""
    r1 = rotate_outbox(outbox_path, max_outbox, max_age_s)
    r2 = clean_inbox(inbox_path, max_age_s)
    r3 = expire_sessions(db_path, session_ttl_s)
    return PayuResult(
        envelopes_removed=r1.envelopes_removed + r2.envelopes_removed,
        envelopes_archived=r1.envelopes_archived,
        sessions_expired=r3.sessions_expired,
        bytes_freed=r1.bytes_freed,
        success=r1.success and r2.success and r3.success,
    )
