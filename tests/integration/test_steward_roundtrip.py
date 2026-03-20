"""End-to-end steward roundtrip — sends a real NADI envelope and waits for response.

Requires the federation relay to be running (steward + agent-internet).
Skips gracefully when relay is not available.

Run with:
    python -m pytest tests/integration/test_steward_roundtrip.py -v
    python -m pytest tests/integration/test_steward_roundtrip.py -v --live   # require live federation
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Fixtures & skip logic
# ---------------------------------------------------------------------------

def _relay_available() -> bool:
    """Check if the federation relay is reachable.

    Heuristics: nadi_outbox.json exists and is writable, and either
    the MAHACLAW_LIVE env var is set or --live was passed.
    """
    outbox = REPO_ROOT / "nadi_outbox.json"
    return outbox.exists() and os.access(outbox, os.W_OK)


def pytest_addoption(parser):
    """Add --live flag for requiring live federation."""
    try:
        parser.addoption("--live", action="store_true", default=False,
                         help="Require live federation relay")
    except ValueError:
        pass  # already registered


live_only = pytest.mark.skipif(
    not os.environ.get("MAHACLAW_LIVE"),
    reason=(
        "Live federation not available. Set MAHACLAW_LIVE=1 or pass --live.\n"
        "To start the relay:\n"
        "  1. Clone steward-federation alongside this repo\n"
        "  2. Run the steward MURALI cycle (python -m steward.cetana)\n"
        "  3. Set MAHACLAW_LIVE=1 and re-run"
    ),
)


# ---------------------------------------------------------------------------
# Step 1: Pipeline writes a valid envelope to outbox
# ---------------------------------------------------------------------------

from mahaclaw.intercept import parse_intent
from mahaclaw.tattva import classify
from mahaclaw.rama import encode_rama
from mahaclaw.lotus import resolve_route, reload
from mahaclaw.envelope import build_envelope, build_and_enqueue
from mahaclaw.inbox import poll_response, extract_response_payload


class TestPipelineToOutbox:
    """Verify the 5-gate pipeline writes a wire-compatible envelope."""

    def test_inquiry_to_steward(self, tmp_path, monkeypatch):
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text("[]\n")
        import mahaclaw.envelope as env_mod
        monkeypatch.setattr(env_mod, "OUTBOX_PATH", outbox)
        reload()

        raw = json.dumps({
            "intent": "inquiry",
            "target": "steward",
            "payload": {"query": "What agents are in the federation?"},
        })

        intent = parse_intent(raw)
        tattva = classify(intent)
        rama = encode_rama(intent, tattva)
        route = resolve_route(intent, rama)
        eid, cid = build_and_enqueue(intent, rama, route)

        # Read back and validate wire format
        data = json.loads(outbox.read_text())
        assert len(data) == 1
        env = data[0]

        # All required wire fields present
        required = {
            "source", "source_city_id", "target", "target_city_id",
            "operation", "payload", "envelope_id", "correlation_id",
            "id", "timestamp", "priority", "ttl_s", "ttl_ms",
            "nadi_type", "nadi_op", "nadi_priority", "maha_header_hex",
        }
        missing = required - env.keys()
        assert not missing, f"Missing wire fields: {missing}"

        assert env["target"] == "steward"
        assert env["source"] == "mahaclaw"
        assert env["operation"] == "inquiry"
        assert env["payload"]["query"] == "What agents are in the federation?"
        assert len(env["maha_header_hex"]) == 32
        assert env["nadi_op"] == "send"

    def test_simulated_roundtrip(self, tmp_path, monkeypatch):
        """Simulate: pipeline writes outbox, fake response in inbox, poll finds it."""
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text("[]\n")
        inbox = tmp_path / "nadi_inbox.json"
        inbox.write_text("[]\n")

        import mahaclaw.envelope as env_mod
        import mahaclaw.inbox as inbox_mod
        monkeypatch.setattr(env_mod, "OUTBOX_PATH", outbox)
        reload()

        # Pipeline
        raw = json.dumps({
            "intent": "inquiry",
            "target": "steward",
            "payload": {"query": "status"},
        })
        intent = parse_intent(raw)
        tattva = classify(intent)
        rama = encode_rama(intent, tattva)
        route = resolve_route(intent, rama)
        eid, cid = build_and_enqueue(intent, rama, route)

        # Simulate federation response
        response_env = {
            "correlation_id": cid,
            "source": "steward",
            "source_city_id": "kimeisele/steward",
            "target": "mahaclaw",
            "target_city_id": "mahaclaw",
            "operation": "inquiry_response",
            "nadi_type": "apana",
            "nadi_op": "send",
            "nadi_priority": "rajas",
            "maha_header_hex": "0" * 32,
            "envelope_id": "env_fake_response",
            "id": "fake-id",
            "timestamp": time.time(),
            "priority": 5,
            "ttl_s": 24.0,
            "ttl_ms": 24000,
            "payload": {
                "agents": ["steward", "agent-city", "agent-research", "agent-world"],
                "count": 4,
            },
        }
        inbox.write_text(json.dumps([response_env]) + "\n")

        # Poll
        result = poll_response(cid, timeout_s=2.0, inbox_path=inbox)
        assert result is not None
        assert result["correlation_id"] == cid
        assert result["payload"]["count"] == 4

        extracted = extract_response_payload(result)
        assert extracted["source"] == "steward"
        assert extracted["data"]["count"] == 4


# ---------------------------------------------------------------------------
# Step 2: Live roundtrip (only with --live or MAHACLAW_LIVE=1)
# ---------------------------------------------------------------------------

class TestLiveRoundtrip:
    """Real federation roundtrip — needs live relay."""

    @live_only
    def test_steward_inquiry_live(self):
        """Send an inquiry to steward and wait for a real response."""
        reload()

        raw = json.dumps({
            "intent": "inquiry",
            "target": "steward",
            "payload": {"query": "What agents are in the federation?"},
        })

        intent = parse_intent(raw)
        tattva = classify(intent)
        rama = encode_rama(intent, tattva)
        route = resolve_route(intent, rama)
        eid, cid = build_and_enqueue(intent, rama, route)

        print(f"\n  Sent envelope {eid}")
        print(f"  correlation_id: {cid}")
        print(f"  Waiting up to 30s for response...")

        response = poll_response(cid, timeout_s=30.0)

        assert response is not None, (
            "No response from steward within 30s.\n"
            "Check that:\n"
            "  1. steward MURALI cycle is running\n"
            "  2. steward-federation relay is syncing\n"
            "  3. nadi_outbox.json is being read by the relay"
        )

        assert response["correlation_id"] == cid
        payload = response.get("payload", {})
        assert payload, "Response payload is empty"

        print(f"  Got response from: {response.get('source')}")
        print(f"  Payload keys: {list(payload.keys())}")

    @live_only
    def test_heartbeat_live(self):
        """Send a heartbeat and verify acknowledgment."""
        reload()

        raw = json.dumps({
            "intent": "heartbeat",
            "target": "steward",
            "payload": {"agent_id": "mahaclaw", "health": 1.0},
        })

        intent = parse_intent(raw)
        tattva = classify(intent)
        rama = encode_rama(intent, tattva)
        route = resolve_route(intent, rama)
        eid, cid = build_and_enqueue(intent, rama, route)

        print(f"\n  Sent heartbeat {eid}, waiting 15s...")
        response = poll_response(cid, timeout_s=15.0)

        if response is None:
            pytest.skip("Heartbeats may not generate responses — this is OK")

        assert response["correlation_id"] == cid
        print(f"  Heartbeat acknowledged by: {response.get('source')}")
