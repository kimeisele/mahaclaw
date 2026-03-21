"""KsetraJna — Meta-Observer / State Digest.

Additional Element — Beyond Canonical 25
Category: META (Observer)

KsetraJna exports a frozen, peer-readable state digest (BubbleSnapshot).
Expands lotus.py buddy_bubble() with session, health, pipeline, and
identity state. Federation peers can read this to understand our state.

Mirrors steward/antahkarana/ksetrajna.py → KsetraJna → BubbleSnapshot.

ANAURALIA: All outputs are counts, booleans, enums, and hashes. No prose.

Pure stdlib. No pip deps.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass

from mahaclaw.chitta import Chitta, ExecutionPhase
from mahaclaw.lotus import buddy_bubble


@dataclass(frozen=True, slots=True)
class BubbleSnapshot:
    """Frozen state digest — peer-readable.

    ANAURALIA: All fields are numeric, boolean, or enum. No prose.
    """
    # Routing
    route_count: int
    peers_available: bool

    # Chitta (memory)
    impression_count: int
    phase: ExecutionPhase
    error_count: int
    success_count: int

    # Health
    health_score: float       # 0.0–1.0 (from Vedana if available)
    uptime_s: float

    # Identity
    fingerprint: str          # 16-char hex identifier
    signing_method: str       # "hmac-sha256" or "ecdsa" — identifier

    # Pipeline
    outbox_depth: int
    inbox_depth: int

    # Digest
    snapshot_hash: str        # SHA-256 of all above fields → integrity


_start_time = time.monotonic()


def _count_json_file(path_str: str) -> int:
    """Count entries in a JSON array file. Returns 0 on any error."""
    import json
    from pathlib import Path
    p = Path(path_str)
    if not p.exists():
        return 0
    try:
        data = json.loads(p.read_text())
        return len(data) if isinstance(data, list) else 0
    except Exception:
        return 0


def observe(
    chitta: Chitta | None = None,
    health_score: float = 0.5,
) -> BubbleSnapshot:
    """Take a full state snapshot. Pure computation, minimal I/O.

    Args:
        chitta: Current Chitta state (if available).
        health_score: Current Vedana health score (0.0–1.0).
    """
    from mahaclaw.envelope import OUTBOX_PATH
    from mahaclaw.inbox import INBOX_PATH

    # Routing state from buddy_bubble
    bubble = buddy_bubble()
    route_count = bubble["route_count"]
    peers_available = bubble["peers_available"]

    # Chitta state
    if chitta is not None:
        impressions = chitta.impressions
        impression_count = len(impressions)
        phase = chitta.phase
        error_count = sum(1 for i in impressions if not i.success)
        success_count = impression_count - error_count
    else:
        impression_count = 0
        phase = ExecutionPhase.ORIENT
        error_count = 0
        success_count = 0

    # Identity
    try:
        from mahaclaw.ahamkara import get_identity
        identity = get_identity()
        fingerprint = identity.fingerprint
        signing_method = identity.signing_method
    except Exception:
        fingerprint = ""
        signing_method = "none"

    # Queue depths
    outbox_depth = _count_json_file(str(OUTBOX_PATH))
    inbox_depth = _count_json_file(str(INBOX_PATH))

    uptime_s = time.monotonic() - _start_time

    # Compute digest hash of all fields
    digest_input = (
        f"{route_count}:{peers_available}:"
        f"{impression_count}:{phase.value}:{error_count}:{success_count}:"
        f"{health_score:.4f}:{uptime_s:.2f}:"
        f"{fingerprint}:{signing_method}:"
        f"{outbox_depth}:{inbox_depth}"
    )
    snapshot_hash = hashlib.sha256(digest_input.encode()).hexdigest()[:32]

    return BubbleSnapshot(
        route_count=route_count,
        peers_available=peers_available,
        impression_count=impression_count,
        phase=phase,
        error_count=error_count,
        success_count=success_count,
        health_score=max(0.0, min(1.0, health_score)),
        uptime_s=uptime_s,
        fingerprint=fingerprint,
        signing_method=signing_method,
        outbox_depth=outbox_depth,
        inbox_depth=inbox_depth,
        snapshot_hash=snapshot_hash,
    )


def to_dict(snapshot: BubbleSnapshot) -> dict:
    """Serialize a BubbleSnapshot to a JSON-serializable dict."""
    return {
        "kind": "bubble_snapshot",
        "route_count": snapshot.route_count,
        "peers_available": snapshot.peers_available,
        "impression_count": snapshot.impression_count,
        "phase": snapshot.phase.value,
        "error_count": snapshot.error_count,
        "success_count": snapshot.success_count,
        "health_score": snapshot.health_score,
        "uptime_s": round(snapshot.uptime_s, 2),
        "fingerprint": snapshot.fingerprint,
        "signing_method": snapshot.signing_method,
        "outbox_depth": snapshot.outbox_depth,
        "inbox_depth": snapshot.inbox_depth,
        "snapshot_hash": snapshot.snapshot_hash,
    }
