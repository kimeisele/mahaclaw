"""Gate 1: PARSE — Validate and extract OpenClaw intents."""
from __future__ import annotations

import json

REQUIRED_FIELDS = {"intent", "target"}
MAX_PAYLOAD_BYTES = 65536


def parse_intent(raw: str) -> dict:
    """Parse and validate a raw JSON string into an OpenClaw intent.

    Returns a normalized dict with at least: intent, target, payload.
    Raises ValueError on malformed input.
    """
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise ValueError(f"payload exceeds {MAX_PAYLOAD_BYTES} bytes")

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError("intent must be a JSON object")

    missing = REQUIRED_FIELDS - data.keys()
    if missing:
        raise ValueError(f"missing required fields: {sorted(missing)}")

    intent = str(data["intent"]).strip().lower()
    target = str(data["target"]).strip().lower()

    if not intent:
        raise ValueError("intent must be non-empty")
    if not target:
        raise ValueError("target must be non-empty")

    return {
        "intent": intent,
        "target": target,
        "payload": data.get("payload") or {},
        "priority": str(data.get("priority", "rajas")).strip().lower(),
        "ttl_ms": int(data.get("ttl_ms", 24_000)),
    }
