"""End-to-end tests for the Maha Claw bridge pipeline."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Gate 1: PARSE
# ---------------------------------------------------------------------------

from mahaclaw.intercept import parse_intent


class TestParseGate:
    def test_valid_intent(self):
        raw = json.dumps({"intent": "inquiry", "target": "agent-research", "payload": {"q": "test"}})
        result = parse_intent(raw)
        assert result["intent"] == "inquiry"
        assert result["target"] == "agent-research"
        assert result["payload"] == {"q": "test"}
        assert result["priority"] == "rajas"
        assert result["ttl_ms"] == 24_000
        assert result["openclaw"] == {}

    def test_openclaw_metadata_preserved(self):
        raw = json.dumps({
            "intent": "inquiry", "target": "agent-research",
            "openclaw_session": "agent:default:telegram:dm:12345",
            "openclaw_skill": "federation-bridge",
            "openclaw_channel": "telegram",
        })
        result = parse_intent(raw)
        assert result["openclaw"]["session"] == "agent:default:telegram:dm:12345"
        assert result["openclaw"]["skill"] == "federation-bridge"
        assert result["openclaw"]["channel"] == "telegram"

    def test_missing_field(self):
        with pytest.raises(ValueError, match="missing required"):
            parse_intent('{"intent": "test"}')

    def test_invalid_json(self):
        with pytest.raises(ValueError, match="invalid JSON"):
            parse_intent("not json")

    def test_empty_intent(self):
        with pytest.raises(ValueError, match="non-empty"):
            parse_intent('{"intent": "", "target": "x"}')

    def test_custom_priority(self):
        raw = json.dumps({"intent": "x", "target": "y", "priority": "sattva", "ttl_ms": 5000})
        result = parse_intent(raw)
        assert result["priority"] == "sattva"
        assert result["ttl_ms"] == 5000


# ---------------------------------------------------------------------------
# Gate 2: VALIDATE (Tattva)
# ---------------------------------------------------------------------------

from mahaclaw.tattva import classify, ELEMENTS


class TestTattvaGate:
    def test_heartbeat_is_vayu(self):
        intent = {"intent": "heartbeat", "target": "agent-city"}
        result = classify(intent)
        assert result.dominant == "vayu"
        assert result.zone == "general"

    def test_inquiry_is_jala(self):
        intent = {"intent": "inquiry", "target": "agent-research"}
        result = classify(intent)
        assert result.dominant == "jala"
        assert result.zone == "research"

    def test_code_is_prithvi(self):
        intent = {"intent": "code_analysis", "target": "steward"}
        result = classify(intent)
        assert result.dominant == "prithvi"
        assert result.zone == "engineering"

    def test_governance_is_agni(self):
        intent = {"intent": "governance_proposal", "target": "agent-world"}
        result = classify(intent)
        assert result.dominant == "agni"
        assert result.zone == "governance"

    def test_discover_is_akasha(self):
        intent = {"intent": "discover_peers", "target": "agent-internet"}
        result = classify(intent)
        assert result.dominant == "akasha"
        assert result.zone == "discovery"

    def test_unknown_defaults_vayu(self):
        intent = {"intent": "something_random", "target": "x"}
        result = classify(intent)
        assert result.dominant == "vayu"

    def test_affinity_has_5_dims(self):
        intent = {"intent": "heartbeat", "target": "x"}
        result = classify(intent)
        assert len(result.affinity) == 5

    def test_to_dict(self):
        intent = {"intent": "heartbeat", "target": "x"}
        d = classify(intent).to_dict()
        assert set(d["affinity"].keys()) == set(ELEMENTS)


# ---------------------------------------------------------------------------
# Gate 3: EXECUTE (RAMA)
# ---------------------------------------------------------------------------

from mahaclaw.rama import encode_rama, GUARDIANS, QUARTERS


class TestRamaGate:
    def _make(self, intent_str="inquiry"):
        intent = {"intent": intent_str, "target": "agent-research", "priority": "rajas"}
        tattva = classify(intent)
        return encode_rama(intent, tattva)

    def test_7_layers(self):
        r = self._make()
        d = r.to_dict()
        assert set(d.keys()) == {"element", "zone", "operation", "affinity", "guardian", "quarter", "guna", "position"}

    def test_inquiry_maps_to_prahlada(self):
        r = self._make("inquiry")
        assert r.guardian == "prahlada"
        assert r.quarter == "karma"
        assert r.position == 9

    def test_heartbeat_maps_to_vyasa(self):
        r = self._make("heartbeat")
        assert r.guardian == "vyasa"
        assert r.quarter == "genesis"

    def test_parampara_vector(self):
        r = self._make("inquiry")
        assert r.parampara_vector == (9 + 1) * 37 == 370
        assert r.parampara_vector % 37 == 0  # connected

    def test_unknown_defaults_prahlada(self):
        r = self._make("something_unknown")
        assert r.position == 9  # default


# ---------------------------------------------------------------------------
# Gate 4: RESULT (Lotus)
# ---------------------------------------------------------------------------

from mahaclaw.lotus import resolve_route, buddy_bubble, reload


class TestLotusGate:
    def test_resolve_known_target(self):
        reload()
        intent = {"intent": "inquiry", "target": "agent-research"}
        rama = self._make_rama(intent)
        route = resolve_route(intent, rama)
        assert route["target_city_id"] == "kimeisele/agent-research"
        assert route["resolved_via"] == "lotus_o1"

    def test_resolve_unknown_raises(self):
        reload()
        intent = {"intent": "x", "target": "nonexistent-node-xyz"}
        rama = self._make_rama(intent)
        with pytest.raises(ValueError, match="unroutable"):
            resolve_route(intent, rama)

    def test_buddy_bubble_snapshot(self):
        reload()
        bubble = buddy_bubble()
        assert bubble["kind"] == "buddy_bubble"
        assert bubble["route_count"] > 0
        assert "agent-internet" in bubble["routes"]

    def _make_rama(self, intent):
        tattva = classify(intent)
        return encode_rama(intent, tattva)


# ---------------------------------------------------------------------------
# Gate 5: SYNC (Envelope)
# ---------------------------------------------------------------------------

from mahaclaw.envelope import build_envelope, build_maha_header_hex, OUTBOX_PATH


class TestEnvelopeGate:
    def test_openclaw_metadata_in_envelope(self):
        intent = {
            "intent": "inquiry", "target": "agent-research", "payload": {},
            "priority": "rajas", "ttl_ms": 24000,
            "openclaw": {"session": "agent:default:telegram:dm:999", "skill": "fed-bridge"},
        }
        tattva = classify(intent)
        rama = encode_rama(intent, tattva)
        route = {"target_city_id": "kimeisele/agent-research", "target_name": "agent-research"}
        env = build_envelope(intent, rama, route)
        assert env["payload"]["_openclaw"]["session"] == "agent:default:telegram:dm:999"
        assert env["payload"]["_openclaw"]["skill"] == "fed-bridge"

    def test_no_openclaw_when_empty(self):
        intent = {"intent": "inquiry", "target": "agent-research", "payload": {}, "priority": "rajas", "ttl_ms": 24000, "openclaw": {}}
        tattva = classify(intent)
        rama = encode_rama(intent, tattva)
        route = {"target_city_id": "kimeisele/agent-research", "target_name": "agent-research"}
        env = build_envelope(intent, rama, route)
        assert "_openclaw" not in env["payload"]

    def test_build_envelope_format(self):
        intent = {"intent": "inquiry", "target": "agent-research", "payload": {"q": "test"}, "priority": "rajas", "ttl_ms": 24000}
        tattva = classify(intent)
        rama = encode_rama(intent, tattva)
        route = {"target_city_id": "kimeisele/agent-research", "target_name": "agent-research"}

        env = build_envelope(intent, rama, route)

        # Check all required fields exist
        assert env["source_city_id"] == "mahaclaw"
        assert env["target_city_id"] == "kimeisele/agent-research"
        assert env["operation"] == "inquiry"
        assert env["nadi_op"] == "send"
        assert env["nadi_priority"] == "rajas"
        assert env["envelope_id"].startswith("env_")
        assert len(env["maha_header_hex"]) == 32
        assert env["ttl_ms"] == 24000
        assert env["ttl_s"] == 24.0
        # RAMA metadata preserved in payload
        assert "_rama" in env["payload"]
        assert env["payload"]["_rama"]["guardian"] == "prahlada"

    def test_maha_header_deterministic(self):
        h1 = build_maha_header_hex("a", "b", "c", "vyana", "rajas", 24000)
        h2 = build_maha_header_hex("a", "b", "c", "vyana", "rajas", 24000)
        assert h1 == h2
        assert len(h1) == 32

    def test_maha_header_changes_with_input(self):
        h1 = build_maha_header_hex("a", "b", "c", "vyana", "rajas", 24000)
        h2 = build_maha_header_hex("a", "b", "c", "prana", "rajas", 24000)
        assert h1 != h2


# ---------------------------------------------------------------------------
# Full pipeline (no daemon, direct function calls)
# ---------------------------------------------------------------------------

from mahaclaw.envelope import build_and_enqueue


class TestFullPipeline:
    def test_end_to_end(self, tmp_path, monkeypatch):
        """Run the full 5-gate pipeline without the socket daemon."""
        # Use a temp outbox
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text("[]\n")
        import mahaclaw.envelope as env_mod
        monkeypatch.setattr(env_mod, "OUTBOX_PATH", outbox)
        reload()

        raw = json.dumps({
            "intent": "inquiry",
            "target": "agent-research",
            "payload": {"question": "What is dark matter?"},
        })

        # Gate 1
        intent = parse_intent(raw)
        # Gate 2
        tattva = classify(intent)
        assert tattva.dominant == "jala"
        # Gate 3
        rama = encode_rama(intent, tattva)
        assert rama.guardian == "prahlada"
        # Gate 4
        route = resolve_route(intent, rama)
        assert "agent-research" in route["target_city_id"]
        # Gate 5
        eid, cid = build_and_enqueue(intent, rama, route)
        assert eid.startswith("env_")
        assert len(cid) > 0

        # Verify outbox
        data = json.loads(outbox.read_text())
        assert len(data) == 1
        assert data[0]["source_city_id"] == "mahaclaw"
        assert data[0]["payload"]["question"] == "What is dark matter?"
        assert data[0]["payload"]["_rama"]["element"] == "jala"


# ---------------------------------------------------------------------------
# Daemon socket test
# ---------------------------------------------------------------------------

class TestDaemon:
    @pytest.mark.asyncio
    async def test_daemon_accepts_and_relays(self, tmp_path, monkeypatch):
        """Start the daemon, send an intent via Unix socket, verify response."""
        sock_path = tmp_path / "test.sock"
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text("[]\n")

        import mahaclaw.envelope as env_mod
        import mahaclaw.daemon as daemon_mod
        monkeypatch.setattr(env_mod, "OUTBOX_PATH", outbox)
        monkeypatch.setattr(daemon_mod, "PID_FILE", tmp_path / "test.pid")
        reload()

        # Start server
        server = await asyncio.start_unix_server(
            daemon_mod.handle_client, path=str(sock_path),
        )

        try:
            # Connect and send
            reader, writer = await asyncio.open_unix_connection(str(sock_path))
            msg = json.dumps({"intent": "heartbeat", "target": "agent-city"})
            writer.write(msg.encode())
            writer.write_eof()

            resp_raw = await asyncio.wait_for(reader.read(65536), timeout=5.0)
            resp = json.loads(resp_raw)

            assert resp["ok"] is True
            assert resp["envelope_id"].startswith("env_")

            # Verify outbox got the envelope
            data = json.loads(outbox.read_text())
            assert len(data) == 1
            assert data[0]["operation"] == "heartbeat"
        finally:
            server.close()
            await server.wait_closed()


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

import subprocess
import sys


class TestCLI:
    def test_cli_pipe(self, tmp_path, monkeypatch):
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text("[]\n")

        env_code = f"""
import mahaclaw.envelope as m; m.OUTBOX_PATH = __import__('pathlib').Path('{outbox}')
from mahaclaw.cli import main; raise SystemExit(main())
"""
        result = subprocess.run(
            [sys.executable, "-c", env_code],
            input='{"intent":"heartbeat","target":"agent-city"}',
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        resp = json.loads(result.stdout)
        assert resp["ok"] is True
        assert resp["envelope_id"].startswith("env_")
        assert "correlation_id" in resp
        assert resp["element"] == "vayu"
        assert resp["guardian"] == "vyasa"

    def test_cli_empty_input(self):
        result = subprocess.run(
            [sys.executable, "-c", "from mahaclaw.cli import main; raise SystemExit(main())"],
            input="", capture_output=True, text=True,
        )
        assert result.returncode == 1
        resp = json.loads(result.stdout)
        assert resp["ok"] is False


# ---------------------------------------------------------------------------
# Inbox / Return Loop
# ---------------------------------------------------------------------------

from mahaclaw.inbox import poll_response, extract_response_payload, _read_inbox


class TestInbox:
    def test_poll_finds_matching_response(self, tmp_path):
        inbox = tmp_path / "nadi_inbox.json"
        corr_id = "test-corr-001"
        inbox.write_text(json.dumps([
            {"correlation_id": corr_id, "source": "agent-research",
             "payload": {"answer": "42"}, "operation": "inquiry_response",
             "nadi_type": "apana", "source_city_id": "kimeisele/agent-research"},
        ]) + "\n")

        result = poll_response(corr_id, timeout_s=0.5, inbox_path=inbox)
        assert result is not None
        assert result["correlation_id"] == corr_id
        assert result["payload"]["answer"] == "42"

        # Consumed — inbox should be empty
        remaining = _read_inbox(inbox)
        assert len(remaining) == 0

    def test_poll_timeout_returns_none(self, tmp_path):
        inbox = tmp_path / "nadi_inbox.json"
        inbox.write_text("[]\n")
        result = poll_response("nonexistent", timeout_s=0.3, inbox_path=inbox)
        assert result is None

    def test_poll_leaves_other_messages(self, tmp_path):
        inbox = tmp_path / "nadi_inbox.json"
        inbox.write_text(json.dumps([
            {"correlation_id": "other-1", "payload": {}},
            {"correlation_id": "target-2", "payload": {"x": 1}},
            {"correlation_id": "other-3", "payload": {}},
        ]) + "\n")

        result = poll_response("target-2", timeout_s=0.5, inbox_path=inbox)
        assert result is not None
        remaining = _read_inbox(inbox)
        assert len(remaining) == 2
        assert remaining[0]["correlation_id"] == "other-1"
        assert remaining[1]["correlation_id"] == "other-3"

    def test_poll_no_inbox_file(self, tmp_path):
        inbox = tmp_path / "does_not_exist.json"
        result = poll_response("x", timeout_s=0.3, inbox_path=inbox)
        assert result is None

    def test_extract_response_payload(self):
        env = {
            "source": "agent-research",
            "source_city_id": "kimeisele/agent-research",
            "operation": "inquiry_response",
            "nadi_type": "apana",
            "payload": {"answer": "42", "_rama": {"element": "jala"}, "_source_intent": "inquiry"},
        }
        extracted = extract_response_payload(env)
        assert extracted["source"] == "agent-research"
        assert extracted["data"] == {"answer": "42"}
        # Internal keys filtered
        assert "_rama" not in extracted["data"]
        assert "_source_intent" not in extracted["data"]

    def test_cli_wait_with_response(self, tmp_path):
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text("[]\n")
        inbox = tmp_path / "nadi_inbox.json"

        # We need to write a response *after* the CLI writes the outbox.
        # Strategy: pre-populate inbox with the correlation_id we'll get.
        # Since correlation_id is random, we use a helper script that:
        # 1. Runs the pipeline
        # 2. Reads the outbox to get correlation_id
        # 3. Writes a fake response to inbox
        # 4. Polls
        env_code = f"""
import json, pathlib
import mahaclaw.envelope as m
import mahaclaw.inbox as ib
m.OUTBOX_PATH = pathlib.Path('{outbox}')
ib.INBOX_PATH = pathlib.Path('{inbox}')

from mahaclaw.intercept import parse_intent
from mahaclaw.tattva import classify
from mahaclaw.rama import encode_rama
from mahaclaw.lotus import resolve_route

intent = parse_intent('{{"intent":"inquiry","target":"agent-research"}}')
tattva = classify(intent)
rama = encode_rama(intent, tattva)
route = resolve_route(intent, rama)
eid, cid = m.build_and_enqueue(intent, rama, route)

# Simulate federation response arriving
inbox_data = [{{"correlation_id": cid, "source": "agent-research",
    "source_city_id": "kimeisele/agent-research", "operation": "inquiry_response",
    "nadi_type": "apana", "payload": {{"answer": "dark matter is cool"}}}}]
pathlib.Path('{inbox}').write_text(json.dumps(inbox_data))

resp = ib.poll_response(cid, timeout_s=1.0)
assert resp is not None
assert resp["payload"]["answer"] == "dark matter is cool"
print(json.dumps({{"ok": True, "cid": cid}}))
"""
        result = subprocess.run(
            [sys.executable, "-c", env_code],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        resp = json.loads(result.stdout)
        assert resp["ok"] is True
