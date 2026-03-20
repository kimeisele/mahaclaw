"""Return loop — poll nadi_inbox.json for federation responses.

The federation relay pump drops responses into nadi_inbox.json.  This module
polls that file for envelopes matching a given correlation_id, with a short
timeout.  Pure stdlib, no threads, simple sleep loop.

Accepts both legacy envelopes (no MahaHeader) and current format.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INBOX_PATH = REPO_ROOT / "nadi_inbox.json"

# After consuming a response we rewrite the inbox without it.
# This prevents the same response from being read twice.

DEFAULT_TIMEOUT_S = 5.0
POLL_INTERVAL_S = 0.25


def _read_inbox(path: Path | None = None) -> list[dict]:
    p = path or INBOX_PATH
    if not p.exists():
        return []
    text = p.read_text().strip()
    if not text:
        return []
    try:
        data = json.loads(text)
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []


def _write_inbox(messages: list[dict], path: Path | None = None) -> None:
    p = path or INBOX_PATH
    p.write_text(json.dumps(messages, indent=2, sort_keys=True) + "\n")


def poll_response(
    correlation_id: str,
    timeout_s: float = DEFAULT_TIMEOUT_S,
    inbox_path: Path | None = None,
) -> dict | None:
    """Poll the inbox for a response matching correlation_id.

    Returns the response envelope dict (normalized to current format), or
    None on timeout.  Consumes the matched envelope from the inbox file.

    Accepts both legacy and current envelope formats — matches on
    correlation_id regardless of whether MahaHeader fields are present.
    """
    from .envelope import normalize_envelope, is_legacy_envelope

    deadline = time.monotonic() + timeout_s
    p = inbox_path or INBOX_PATH

    while time.monotonic() < deadline:
        messages = _read_inbox(p)
        for i, msg in enumerate(messages):
            if msg.get("correlation_id") == correlation_id:
                # Log warning for legacy envelopes
                if is_legacy_envelope(msg):
                    source = msg.get("source", "unknown")
                    print(f"  inbox: legacy envelope (no MahaHeader) from {source}",
                          file=sys.stderr)

                # Consume: remove from inbox
                messages.pop(i)
                _write_inbox(messages, p)
                return normalize_envelope(msg)

        time.sleep(POLL_INTERVAL_S)

    return None


def extract_response_payload(envelope: dict) -> dict:
    """Extract the useful payload from a federation response envelope.

    Works with both legacy and current format envelopes.
    """
    payload = envelope.get("payload", {})
    return {
        "source": envelope.get("source", ""),
        "source_city_id": envelope.get("source_city_id", ""),
        "operation": envelope.get("operation", ""),
        "nadi_type": envelope.get("nadi_type", "vyana"),
        "data": {k: v for k, v in payload.items() if not k.startswith("_")},
    }
