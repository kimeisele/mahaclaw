"""Gate 5: SYNC — Build DeliveryEnvelope and append to nadi_outbox.json.

Produces envelopes wire-compatible with the steward-federation/agent-internet
relay pump.  The original OpenClaw intent is preserved verbatim inside
payload["_rama"] so no semantic information is lost.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

from .rama import RAMASignal

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTBOX_PATH = REPO_ROOT / "nadi_outbox.json"
SOURCE_CITY_ID = "mahaclaw"


def build_maha_header_hex(
    source: str,
    target: str,
    operation: str,
    nadi_type: str,
    priority: str,
    ttl_ms: int,
) -> str:
    """Compute the MahaHeader hex matching steward_protocol_compat."""
    raw = f"{source}:{target}:{operation}:{nadi_type}:{priority}:{ttl_ms}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _read_outbox() -> list:
    if not OUTBOX_PATH.exists():
        return []
    text = OUTBOX_PATH.read_text().strip()
    if not text:
        return []
    data = json.loads(text)
    return data if isinstance(data, list) else []


def _write_outbox(messages: list) -> None:
    OUTBOX_PATH.write_text(json.dumps(messages, indent=2, sort_keys=True) + "\n")


def build_envelope(intent: dict, rama: RAMASignal, route: dict) -> dict:
    """Build a DeliveryEnvelope dict matching the canonical wire format."""
    target_city_id = route["target_city_id"]
    nadi_type = rama.to_dict().get("element", "vyana")
    # Map element to NADI type (Five Pranas)
    element_to_nadi = {
        "akasha": "udana",
        "vayu": "vyana",
        "agni": "prana",
        "jala": "udana",
        "prithvi": "prana",
    }
    nadi = element_to_nadi.get(nadi_type, "vyana")
    ttl_ms = intent.get("ttl_ms", 24_000)

    envelope_id = f"env_{uuid.uuid4().hex[:16]}"
    correlation_id = str(uuid.uuid4())
    now = time.time()

    return {
        "correlation_id": correlation_id,
        "envelope_id": envelope_id,
        "id": str(uuid.uuid4()),
        "maha_header_hex": build_maha_header_hex(
            SOURCE_CITY_ID, target_city_id, rama.operation,
            nadi, rama.guna, ttl_ms,
        ),
        "nadi_op": "send",
        "nadi_priority": rama.guna,
        "nadi_type": nadi,
        "operation": rama.operation,
        "payload": {
            **intent.get("payload", {}),
            "_rama": rama.to_dict(),
            "_source_intent": intent["intent"],
            **({"_openclaw": intent["openclaw"]} if intent.get("openclaw") else {}),
        },
        "priority": {"tamas": 1, "rajas": 5, "sattva": 8, "suddha": 10}.get(rama.guna, 5),
        "source": SOURCE_CITY_ID,
        "source_city_id": SOURCE_CITY_ID,
        "target": route.get("target_name", target_city_id),
        "target_city_id": target_city_id,
        "timestamp": now,
        "ttl_ms": ttl_ms,
        "ttl_s": ttl_ms / 1000.0,
    }


def build_and_enqueue(intent: dict, rama: RAMASignal, route: dict) -> str:
    """Build envelope and append to outbox.  Returns the envelope_id."""
    envelope = build_envelope(intent, rama, route)
    outbox = _read_outbox()
    outbox.append(envelope)
    _write_outbox(outbox)
    return envelope["envelope_id"]
