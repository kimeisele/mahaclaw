"""Pada — Dynamic Routing / Peer Discovery.

Karmendriya #3 — Action Organ: locomotion
Category: KARMENDRIYA (Action Organ)

Pada extends Lotus's static route table with dynamic peer discovery.
Watches inbox for peer announcements, extracts routing info from
heartbeat responses, and triggers Lotus reload when routes change.

Mirrors agent-internet's RegistryRouter + agent-city's CityRouter.

ANAURALIA: All outputs are counts and booleans. No prose.

Pure stdlib. No pip deps.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path

from mahaclaw.lotus import PEERS_PATH, reload as lotus_reload


@dataclass(frozen=True, slots=True)
class DiscoveryResult:
    """Result of a peer discovery scan.

    ANAURALIA: Only counts and booleans.
    """
    peers_found: int = 0
    peers_added: int = 0
    routes_refreshed: bool = False


def _read_peers() -> dict:
    """Read the current peers registry."""
    if not PEERS_PATH.exists():
        return {"peers": [], "updated_at": 0}
    try:
        return json.loads(PEERS_PATH.read_text())
    except (json.JSONDecodeError, OSError):
        return {"peers": [], "updated_at": 0}


def _write_peers(registry: dict) -> None:
    """Write the peers registry."""
    PEERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    PEERS_PATH.write_text(json.dumps(registry, indent=2) + "\n")


def extract_peer_from_envelope(envelope: dict) -> dict | None:
    """Extract peer info from a federation envelope.

    Heartbeat responses and announce operations contain peer metadata.
    Returns a peer dict suitable for the peers registry, or None.
    """
    source = envelope.get("source_city_id", "")
    if not source or "/" not in source:
        # Need org/repo format
        source = envelope.get("source", "")
        if not source:
            return None
        # If bare name, skip — can't route without full_name
        if "/" not in source:
            return None

    operation = envelope.get("operation", "")
    payload = envelope.get("payload", {})

    return {
        "full_name": source,
        "operation": operation,
        "last_seen": envelope.get("timestamp", time.time()),
        "nadi_type": envelope.get("nadi_type", "vyana"),
        "capabilities": payload.get("capabilities", []),
    }


def discover_from_inbox(inbox_path: Path | None = None) -> DiscoveryResult:
    """Scan inbox for peer announcements and update the peers registry.

    Non-destructive: reads inbox without consuming messages.
    Only adds peers, never removes them.
    """
    from mahaclaw.inbox import INBOX_PATH, _read_inbox

    path = inbox_path or INBOX_PATH
    messages = _read_inbox(path)

    if not messages:
        return DiscoveryResult()

    # Extract peers from all inbox messages
    new_peers: dict[str, dict] = {}
    for msg in messages:
        peer = extract_peer_from_envelope(msg)
        if peer is not None:
            full_name = peer["full_name"]
            # Keep most recent entry per peer
            existing = new_peers.get(full_name)
            if existing is None or peer["last_seen"] > existing.get("last_seen", 0):
                new_peers[full_name] = peer

    if not new_peers:
        return DiscoveryResult()

    # Merge with existing registry
    registry = _read_peers()
    existing_names = {p["full_name"] for p in registry["peers"]}
    added = 0

    for full_name, peer in new_peers.items():
        if full_name not in existing_names:
            registry["peers"].append(peer)
            added += 1
        else:
            # Update last_seen for known peers
            for p in registry["peers"]:
                if p["full_name"] == full_name:
                    p["last_seen"] = peer["last_seen"]
                    if peer.get("capabilities"):
                        p["capabilities"] = peer["capabilities"]
                    break

    registry["updated_at"] = time.time()

    if added > 0:
        _write_peers(registry)
        lotus_reload()

    return DiscoveryResult(
        peers_found=len(new_peers),
        peers_added=added,
        routes_refreshed=added > 0,
    )


def refresh_routes() -> DiscoveryResult:
    """Force a route table refresh from current peers file.

    Use after manually updating .federation/peers.json.
    """
    registry = _read_peers()
    peer_count = len(registry.get("peers", []))
    lotus_reload()
    return DiscoveryResult(
        peers_found=peer_count,
        peers_added=0,
        routes_refreshed=True,
    )
