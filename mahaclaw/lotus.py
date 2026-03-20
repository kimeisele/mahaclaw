"""Gate 4: RESULT — O(1) Lotus route resolver + buddy_bubble.

Resolves a RAMA signal to a concrete target_city_id using the federation
peer registry.  Maintains an in-memory routing table that can be
exported as a "buddy_bubble" JSON snapshot for observability.
"""
from __future__ import annotations

import json
from pathlib import Path

from .rama import RAMASignal

REPO_ROOT = Path(__file__).resolve().parents[1]
SEEDS_PATH = REPO_ROOT / "data" / "federation" / "authority-descriptor-seeds.json"
PEERS_PATH = REPO_ROOT / ".federation" / "peers.json"

# Pre-built route table: target_name → city_id (repo slug)
# Loaded once, O(1) dict lookup thereafter.
_route_table: dict[str, str] | None = None


def _build_route_table() -> dict[str, str]:
    """Build the routing table from seeds and/or peer registry."""
    table: dict[str, str] = {}

    # Source 1: authority descriptor seeds (always available)
    if SEEDS_PATH.exists():
        seeds = json.loads(SEEDS_PATH.read_text())
        for url in seeds.get("descriptor_urls", []):
            # Extract repo name from raw.githubusercontent URL
            parts = url.split("/")
            if len(parts) >= 5 and "githubusercontent" in parts[2]:
                repo_name = parts[4]
                full_name = f"{parts[3]}/{parts[4]}"
                table[repo_name] = full_name

    # Source 2: discovered peers (if available, overrides seeds)
    if PEERS_PATH.exists():
        registry = json.loads(PEERS_PATH.read_text())
        for peer in registry.get("peers", []):
            full_name = peer.get("full_name", "")
            if "/" in full_name:
                repo_name = full_name.split("/", 1)[1]
                table[repo_name] = full_name

    return table


def _get_table() -> dict[str, str]:
    global _route_table
    if _route_table is None:
        _route_table = _build_route_table()
    return _route_table


def resolve_route(intent: dict, rama: RAMASignal) -> dict:
    """Resolve the target for a RAMA signal.  O(1) dict lookup.

    Returns a dict with routing metadata for the envelope builder.
    Raises ValueError if the target is unroutable.
    """
    table = _get_table()
    target_name = intent["target"]

    # Direct match
    city_id = table.get(target_name)
    if city_id is None:
        # Try with common prefixes stripped
        for suffix in (target_name, target_name.replace("agent-", ""), target_name.replace("steward-", "")):
            for key, val in table.items():
                if suffix in key:
                    city_id = val
                    break
            if city_id:
                break

    if city_id is None:
        raise ValueError(f"unroutable target: {target_name} (known: {sorted(table.keys())})")

    return {
        "target_city_id": city_id,
        "target_name": target_name,
        "nadi_type": rama.to_dict()["element"],
        "zone": rama.zone,
        "resolved_via": "lotus_o1",
    }


def buddy_bubble() -> dict:
    """Export the current routing state as a JSON-serializable snapshot."""
    table = _get_table()
    return {
        "kind": "buddy_bubble",
        "route_count": len(table),
        "routes": {k: v for k, v in sorted(table.items())},
        "seeds_path": str(SEEDS_PATH),
        "peers_path": str(PEERS_PATH),
        "peers_available": PEERS_PATH.exists(),
    }


def reload() -> None:
    """Force-reload the routing table (e.g. after peer discovery)."""
    global _route_table
    _route_table = None
