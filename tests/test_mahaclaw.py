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
    def test_seed_deterministic(self):
        """Same intent always produces same classification (seed-based)."""
        intent = {"intent": "heartbeat", "target": "agent-city"}
        r1 = classify(intent)
        r2 = classify(intent)
        assert r1.dominant == r2.dominant
        assert r1.zone == r2.zone
        assert r1.affinity == r2.affinity

    def test_different_intents_may_differ(self):
        """Different intent strings produce (possibly) different seeds."""
        r1 = classify({"intent": "heartbeat", "target": "x"})
        r2 = classify({"intent": "code_analysis", "target": "x"})
        # They CAN be equal by hash collision, but test the pipeline runs
        assert r1.dominant in ELEMENTS
        assert r2.dominant in ELEMENTS

    def test_heartbeat_seed_routing(self):
        """heartbeat hashes to position 10 → karma → DEBUG → engineering."""
        result = classify({"intent": "heartbeat", "target": "agent-city"})
        assert result.dominant == "prithvi"
        assert result.zone == "engineering"

    def test_inquiry_seed_routing(self):
        """inquiry hashes to position 5 → dharma → REVIEW → governance."""
        result = classify({"intent": "inquiry", "target": "agent-research"})
        assert result.dominant == "agni"
        assert result.zone == "governance"

    def test_code_analysis_seed_routing(self):
        """code_analysis hashes to position 11 → karma → DEBUG → engineering."""
        result = classify({"intent": "code_analysis", "target": "steward"})
        assert result.dominant == "prithvi"
        assert result.zone == "engineering"

    def test_valid_elements(self):
        """All results use valid elements and zones."""
        for intent_str in ("heartbeat", "inquiry", "test", "governance", "random_xyz"):
            r = classify({"intent": intent_str, "target": "x"})
            assert r.dominant in ELEMENTS
            assert r.zone in ("discovery", "general", "governance", "research", "engineering")

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

    def test_inquiry_seed_position(self):
        """inquiry hashes to position 5 → kumaras (dharma quarter)."""
        r = self._make("inquiry")
        assert r.position == 5
        assert r.guardian == GUARDIANS[5]  # kumaras
        assert r.quarter == "dharma"

    def test_heartbeat_seed_position(self):
        """heartbeat hashes to position 10 → janaka (karma quarter)."""
        r = self._make("heartbeat")
        assert r.position == 10
        assert r.guardian == GUARDIANS[10]  # janaka
        assert r.quarter == "karma"

    def test_parampara_vector(self):
        r = self._make("inquiry")
        assert r.parampara_vector == (r.position + 1) * 37
        assert r.parampara_vector % 37 == 0  # connected

    def test_position_deterministic(self):
        """Same intent always produces same position (seed-based)."""
        r1 = self._make("something_unknown")
        r2 = self._make("something_unknown")
        assert r1.position == r2.position
        assert 0 <= r1.position < 16


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
        # RAMA metadata preserved in payload (seed-based position)
        assert "_rama" in env["payload"]
        assert env["payload"]["_rama"]["guardian"] in GUARDIANS

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
        # Gate 2 (seed-based: inquiry → pos 5 → dharma → REVIEW → governance)
        tattva = classify(intent)
        assert tattva.dominant in ELEMENTS
        # Gate 3
        rama = encode_rama(intent, tattva)
        assert rama.guardian in GUARDIANS
        assert 0 <= rama.position < 16
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
        assert data[0]["payload"]["_rama"]["element"] in ELEMENTS


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
        assert resp["element"] in ELEMENTS
        assert resp["guardian"] in GUARDIANS

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


# ---------------------------------------------------------------------------
# Standalone Chat
# ---------------------------------------------------------------------------


class TestChat:
    def test_chat_status_and_quit(self, tmp_path):
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text("[]\n")

        env_code = f"""
import sys; sys.argv = ['chat', '--target', 'agent-research', '--nowait']
import mahaclaw.envelope as m; m.OUTBOX_PATH = __import__('pathlib').Path('{outbox}')
from mahaclaw.chat import main; raise SystemExit(main())
"""
        result = subprocess.run(
            [sys.executable, "-c", env_code],
            input="/status\nWhat is dark matter?\n/quit\n",
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, result.stderr
        assert "target: agent-research" in result.stdout
        # Seed-based routing — check that some element/zone was reported
        assert "/" in result.stdout  # element/zone format
        assert "bye" in result.stdout

    def test_chat_send_writes_outbox(self, tmp_path):
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text("[]\n")

        env_code = f"""
import sys; sys.argv = ['chat', '--target', 'agent-research', '--nowait']
import mahaclaw.envelope as m; m.OUTBOX_PATH = __import__('pathlib').Path('{outbox}')
from mahaclaw.chat import main; raise SystemExit(main())
"""
        subprocess.run(
            [sys.executable, "-c", env_code],
            input="hello federation\n/quit\n",
            capture_output=True, text=True, timeout=10,
        )
        data = json.loads(outbox.read_text())
        assert len(data) == 1
        assert data[0]["payload"]["message"] == "hello federation"
        assert data[0]["target_city_id"] == "kimeisele/agent-research"


# ---------------------------------------------------------------------------
# Session Manager (signed ledger)
# ---------------------------------------------------------------------------

from mahaclaw.session import SessionManager


class TestSessionManager:
    def test_create_session(self, tmp_path):
        mgr = SessionManager(tmp_path / "test.db")
        s = mgr.get_or_create("test:telegram:user1")
        assert s.session_id == "test:telegram:user1"
        assert s.message_count == 0
        mgr.close()

    def test_get_existing_session(self, tmp_path):
        mgr = SessionManager(tmp_path / "test.db")
        s1 = mgr.get_or_create("test:sess:1", target="agent-city")
        s2 = mgr.get_or_create("test:sess:1")
        assert s2.target == "agent-city"
        mgr.close()

    def test_ledger_chain_integrity(self, tmp_path):
        mgr = SessionManager(tmp_path / "test.db")
        sid = "test:chain:1"
        mgr.get_or_create(sid)
        mgr.log_message_in(sid, "hello")
        mgr.log_message_out(sid, "env_abc", "corr_123", "agent-research", "jala", "research")
        mgr.log_message_in(sid, "second message")

        valid, count = mgr.verify_chain(sid)
        assert valid is True
        assert count == 4  # genesis + 3 entries
        mgr.close()

    def test_ledger_tamper_detection(self, tmp_path):
        mgr = SessionManager(tmp_path / "test.db")
        sid = "test:tamper:1"
        mgr.get_or_create(sid)
        mgr.log_message_in(sid, "original")

        # Tamper with a row
        mgr._conn.execute(
            "UPDATE session_ledger SET data = '{\"message\":\"tampered\"}' WHERE session_id = ? AND seq = 2",
            (sid,),
        )
        mgr._conn.commit()

        valid, at_seq = mgr.verify_chain(sid)
        assert valid is False
        mgr.close()

    def test_history_retrieval(self, tmp_path):
        mgr = SessionManager(tmp_path / "test.db")
        sid = "test:hist:1"
        mgr.get_or_create(sid)
        mgr.log_message_in(sid, "msg1")
        mgr.log_message_in(sid, "msg2")

        history = mgr.get_history(sid)
        assert len(history) == 3  # genesis + 2 messages
        assert history[1].kind == "message_in"
        assert json.loads(json.dumps(history[1].data))["message"] == "msg1"
        mgr.close()

    def test_list_sessions(self, tmp_path):
        mgr = SessionManager(tmp_path / "test.db")
        mgr.get_or_create("sess:a")
        mgr.get_or_create("sess:b")
        sessions = mgr.list_sessions()
        assert len(sessions) == 2
        mgr.close()


# ---------------------------------------------------------------------------
# Skill Engine
# ---------------------------------------------------------------------------

from mahaclaw.skills.engine import SkillEngine
from mahaclaw.skills._types import SkillContext, SkillResult, SkillMetadata
from mahaclaw.skills.compat import parse_skill_md


class TestSkillEngine:
    def test_register_and_run(self):
        engine = SkillEngine()

        def echo_skill(ctx: SkillContext) -> SkillResult:
            return SkillResult(ok=True, output=f"echo: {ctx.message}")

        engine.register("echo", echo_skill)
        assert engine.skill_count == 1

        result = engine.run("echo", SkillContext(message="hello", session_id="s1", target="t1"))
        assert result.ok is True
        assert result.output == "echo: hello"

    def test_run_unknown_skill(self):
        engine = SkillEngine()
        result = engine.run("nonexistent", SkillContext(message="x", session_id="s1", target="t1"))
        assert result.ok is False
        assert "not found" in result.error or "no runner" in result.error

    def test_match_slash_command(self):
        engine = SkillEngine()
        engine.register("test", lambda ctx: SkillResult(ok=True))
        assert engine.match_skill("/test hello") == "test"
        assert engine.match_skill("regular message") is None

    def test_discover_python_skills(self, tmp_path):
        skill_dir = tmp_path / "skills"
        skill_dir.mkdir()
        (skill_dir / "greet.py").write_text(
            'METADATA = {"name": "greet", "description": "A greeting skill"}\n'
            'def run(ctx):\n'
            '    from mahaclaw.skills.engine import SkillResult\n'
            '    return SkillResult(ok=True, output=f"Hello {ctx.message}")\n'
        )

        engine = SkillEngine()
        count = engine.discover_python(skill_dir)
        assert count == 1
        assert engine.get_skill("greet") is not None

    def test_parse_our_skill_md(self):
        skill_path = Path(__file__).resolve().parents[1] / "openclaw_skill" / "SKILL.md"
        meta = parse_skill_md(skill_path)
        assert meta is not None
        assert meta.name == "federation-bridge"
        assert meta.user_invocable is True
        assert "python3" in meta.requires_bins
        assert meta.kind == "skillmd"


# ---------------------------------------------------------------------------
# Tool Sandbox
# ---------------------------------------------------------------------------

from mahaclaw.tools.sandbox import ToolSandbox


class TestToolSandbox:
    def test_run_allowed_command(self, tmp_path):
        sandbox = ToolSandbox(workspace=tmp_path)
        result = sandbox.run("echo hello world")
        assert result.ok is True
        assert "hello world" in result.stdout

    def test_block_dangerous_command(self, tmp_path):
        sandbox = ToolSandbox(workspace=tmp_path)
        result = sandbox.run("rm -rf /")
        assert result.ok is False
        assert "blocked" in result.error

    def test_block_unlisted_command(self, tmp_path):
        sandbox = ToolSandbox(workspace=tmp_path)
        result = sandbox.run("wget http://evil.com")
        assert result.ok is False
        assert "allowlist" in result.error

    def test_block_shell_metacharacters(self, tmp_path):
        sandbox = ToolSandbox(workspace=tmp_path)
        result = sandbox.run("echo hello; rm -rf /")
        assert result.ok is False
        assert "blocked character" in result.error

    def test_path_escape_prevention(self, tmp_path):
        sandbox = ToolSandbox(workspace=tmp_path)
        ok, reason = sandbox.validate_path("../../etc/passwd")
        assert ok is False
        assert "escapes" in reason

    def test_read_file_in_scope(self, tmp_path):
        sandbox = ToolSandbox(workspace=tmp_path)
        (tmp_path / "test.txt").write_text("hello")
        ok, content = sandbox.read_file("test.txt")
        assert ok is True
        assert content == "hello"

    def test_write_file_in_scope(self, tmp_path):
        sandbox = ToolSandbox(workspace=tmp_path)
        ok, msg = sandbox.write_file("output.txt", "test content")
        assert ok is True
        assert (tmp_path / "output.txt").read_text() == "test content"

    def test_list_dir(self, tmp_path):
        sandbox = ToolSandbox(workspace=tmp_path)
        (tmp_path / "a.txt").write_text("a")
        (tmp_path / "b.txt").write_text("b")
        ok, entries = sandbox.list_dir()
        assert ok is True
        assert "a.txt" in entries
        assert "b.txt" in entries

    def test_command_timeout(self, tmp_path):
        # Write a script that sleeps, avoid shell metacharacters
        script = tmp_path / "sleeper.py"
        script.write_text("import time\ntime.sleep(10)\n")
        sandbox = ToolSandbox(workspace=tmp_path, timeout_s=1)
        result = sandbox.run(f"python3 {script}")
        assert result.ok is False
        assert "timeout" in result.error


# ---------------------------------------------------------------------------
# Gateway WebSocket (basic connectivity)
# ---------------------------------------------------------------------------

from mahaclaw.gateway import _ws_accept_key, _ws_frame, _ws_read_frame, _process_message


class TestGateway:
    def test_ws_accept_key(self):
        key = _ws_accept_key(b"dGhlIHNhbXBsZSBub25jZQ==")
        assert key == "7ZaunlI/AuSFdL5rz2ebhN0QS2U="
        # Deterministic: same input → same output
        assert _ws_accept_key(b"dGhlIHNhbXBsZSBub25jZQ==") == key

    def test_ws_frame_roundtrip(self):
        payload = b'{"ok":true}'
        frame = _ws_frame(payload)
        assert frame[0] == 0x81  # FIN + TEXT
        assert payload in frame

    @pytest.mark.asyncio
    async def test_process_message_intent(self, tmp_path, monkeypatch):
        import mahaclaw.envelope as env_mod
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text("[]\n")
        monkeypatch.setattr(env_mod, "OUTBOX_PATH", outbox)

        from mahaclaw.lotus import reload
        reload()

        result = await _process_message('{"intent":"inquiry","target":"agent-research","wait":0}')
        assert result["ok"] is True
        assert result["element"] in ELEMENTS

    @pytest.mark.asyncio
    async def test_process_message_chat(self, tmp_path, monkeypatch):
        import mahaclaw.envelope as env_mod
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text("[]\n")
        monkeypatch.setattr(env_mod, "OUTBOX_PATH", outbox)

        from mahaclaw.lotus import reload
        reload()

        result = await _process_message('{"message":"What is dark matter?","target":"agent-research","wait":0}')
        assert result["ok"] is True
        assert result["element"] in ELEMENTS

    @pytest.mark.asyncio
    async def test_gateway_http_health(self, tmp_path, monkeypatch):
        """Connect with plain HTTP (no WS upgrade) — should get health response."""
        import mahaclaw.envelope as env_mod
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text("[]\n")
        monkeypatch.setattr(env_mod, "OUTBOX_PATH", outbox)

        from mahaclaw.gateway import handle_ws_client

        server = await asyncio.start_server(handle_ws_client, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]

        try:
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            resp = await asyncio.wait_for(reader.read(4096), timeout=5.0)
            assert b"200 OK" in resp
            assert b"mahaclaw-gateway" in resp
            writer.close()
            await writer.wait_closed()
        finally:
            server.close()
            await server.wait_closed()


# ---------------------------------------------------------------------------
# LLM Client
# ---------------------------------------------------------------------------

from mahaclaw.llm import (
    LLMConfig, LLMResponse, chat, ask, is_available, config_from_env,
    _curl_post, DEFAULT_BASE_URL, DEFAULT_MODEL,
)


class TestLLMClient:
    def test_config_defaults(self):
        config = LLMConfig()
        assert config.base_url == DEFAULT_BASE_URL
        assert config.model == DEFAULT_MODEL
        assert config.temperature == 0.7
        assert config.max_tokens == 1024

    def test_config_from_env(self, monkeypatch):
        monkeypatch.setenv("MAHACLAW_LLM_URL", "http://test:1234/v1")
        monkeypatch.setenv("MAHACLAW_LLM_MODEL", "test-model")
        monkeypatch.setenv("MAHACLAW_LLM_KEY", "sk-test")
        config = config_from_env()
        assert config.base_url == "http://test:1234/v1"
        assert config.model == "test-model"
        assert config.api_key == "sk-test"

    def test_llm_response_dataclass(self):
        resp = LLMResponse(ok=True, content="hello", model="test", duration_ms=42.0)
        assert resp.ok is True
        assert resp.content == "hello"

    def test_chat_unreachable_endpoint(self):
        """Chat with an unreachable endpoint returns error gracefully."""
        config = LLMConfig(base_url="http://127.0.0.1:1/v1", timeout_s=2)
        resp = chat([{"role": "user", "content": "test"}], config)
        assert resp.ok is False
        assert resp.error  # Should have an error message

    def test_ask_builds_messages(self, monkeypatch):
        """Verify ask() builds the right message structure."""
        captured = {}

        def mock_chat(messages, config):
            captured["messages"] = messages
            return LLMResponse(ok=True, content="mocked", model="test")

        import mahaclaw.llm as llm_mod
        monkeypatch.setattr(llm_mod, "chat", mock_chat)

        config = LLMConfig(system_prompt="You are a test bot.")
        history = [{"role": "user", "content": "prev"}, {"role": "assistant", "content": "prev-resp"}]
        resp = ask("hello", config=config, history=history)

        assert resp.ok is True
        msgs = captured["messages"]
        assert msgs[0]["role"] == "system"
        assert msgs[0]["content"] == "You are a test bot."
        assert msgs[1]["role"] == "user"
        assert msgs[1]["content"] == "prev"
        assert msgs[2]["role"] == "assistant"
        assert msgs[3]["role"] == "user"
        assert msgs[3]["content"] == "hello"

    def test_is_available_unreachable(self):
        config = LLMConfig(base_url="http://127.0.0.1:1/v1", timeout_s=2)
        avail, info = is_available(config)
        assert avail is False


# ---------------------------------------------------------------------------
# Channel Types
# ---------------------------------------------------------------------------

from mahaclaw.channels import IncomingMessage


class TestChannelTypes:
    def test_incoming_message_session_id(self):
        msg = IncomingMessage(
            channel="telegram", user_id="123", username="alice",
            text="hello", chat_id="456",
        )
        assert msg.session_id == "mahaclaw:telegram:456:123"

    def test_incoming_message_defaults(self):
        msg = IncomingMessage(
            channel="discord", user_id="u1", username="bob",
            text="test", chat_id="c1",
        )
        assert msg.reply_to == ""
        assert msg.raw == {}


# ---------------------------------------------------------------------------
# Telegram Adapter (unit tests — no network)
# ---------------------------------------------------------------------------

from mahaclaw.channels.telegram import _normalize_update, TelegramConfig


class TestTelegramAdapter:
    def test_normalize_text_message(self):
        update = {
            "update_id": 1,
            "message": {
                "message_id": 42,
                "from": {"id": 123, "username": "alice", "first_name": "Alice"},
                "chat": {"id": -456, "type": "group"},
                "text": "hello federation",
            },
        }
        msg = _normalize_update(update)
        assert msg is not None
        assert msg.channel == "telegram"
        assert msg.user_id == "123"
        assert msg.username == "alice"
        assert msg.text == "hello federation"
        assert msg.chat_id == "-456"

    def test_normalize_no_text(self):
        update = {"update_id": 2, "message": {"message_id": 43, "from": {"id": 1}, "chat": {"id": 1}, "photo": []}}
        msg = _normalize_update(update)
        assert msg is None

    def test_normalize_no_message(self):
        update = {"update_id": 3}
        msg = _normalize_update(update)
        assert msg is None

    def test_normalize_edited_message(self):
        update = {
            "update_id": 4,
            "edited_message": {
                "message_id": 44,
                "from": {"id": 789, "first_name": "Bob"},
                "chat": {"id": 100},
                "text": "edited text",
            },
        }
        msg = _normalize_update(update)
        assert msg is not None
        assert msg.text == "edited text"
        assert msg.username == "Bob"

    def test_config_allowed_users(self):
        cfg = TelegramConfig(token="test", allowed_users=frozenset({"123", "456"}))
        assert "123" in cfg.allowed_users
        assert "789" not in cfg.allowed_users


# ---------------------------------------------------------------------------
# Channel Bridge
# ---------------------------------------------------------------------------

from mahaclaw.channels.bridge import ChannelBridge, BridgeConfig, _detect_intent


class TestChannelBridge:
    def test_detect_intent_passthrough(self):
        """_detect_intent now returns raw text (Manas routes by seed)."""
        assert _detect_intent("build something") == "build something"
        assert _detect_intent("tell me about quantum physics") == "tell me about quantum physics"

    def test_bridge_command_help(self, tmp_path):
        replies = []
        bridge = ChannelBridge(BridgeConfig(session_db=str(tmp_path / "test.db")))
        bridge.register_sender("test", lambda cid, text, rt: replies.append(text))

        msg = IncomingMessage(channel="test", user_id="u1", username="a", text="/help", chat_id="c1")
        bridge.handle_message(msg)
        assert len(replies) == 1
        assert "/status" in replies[0]
        bridge.close()

    def test_bridge_command_status(self, tmp_path):
        replies = []
        bridge = ChannelBridge(BridgeConfig(session_db=str(tmp_path / "test.db")))
        bridge.register_sender("test", lambda cid, text, rt: replies.append(text))

        msg = IncomingMessage(channel="test", user_id="u1", username="a", text="/status", chat_id="c1")
        bridge.handle_message(msg)
        assert len(replies) == 1
        assert "federation" in replies[0].lower() or "Mode" in replies[0]
        bridge.close()

    def test_bridge_command_mode_toggle(self, tmp_path):
        replies = []
        bridge = ChannelBridge(BridgeConfig(session_db=str(tmp_path / "test.db")))
        bridge.register_sender("test", lambda cid, text, rt: replies.append(text))

        msg = IncomingMessage(channel="test", user_id="u1", username="a", text="/mode", chat_id="c1")
        bridge.handle_message(msg)
        assert "standalone" in replies[0].lower()

        bridge.handle_message(msg)
        assert "federation" in replies[1].lower()
        bridge.close()

    def test_bridge_federation_send(self, tmp_path, monkeypatch):
        """Test that federation mode runs the pipeline and writes to outbox."""
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text("[]\n")
        import mahaclaw.envelope as env_mod
        monkeypatch.setattr(env_mod, "OUTBOX_PATH", outbox)
        from mahaclaw.lotus import reload
        reload()

        replies = []
        bridge = ChannelBridge(BridgeConfig(
            session_db=str(tmp_path / "test.db"),
            response_wait_s=0,  # fire-and-forget for test
        ))
        bridge.register_sender("test", lambda cid, text, rt: replies.append(text))

        msg = IncomingMessage(
            channel="test", user_id="u1", username="alice",
            text="What is dark matter?", chat_id="c1",
        )
        bridge.handle_message(msg)

        assert len(replies) == 1
        # Seed-based routing — check element/zone format present
        assert "/" in replies[0]  # "[element/zone] Sent to ..."

        # Verify outbox got an envelope
        data = json.loads(outbox.read_text())
        assert len(data) == 1
        assert data[0]["payload"]["message"] == "What is dark matter?"
        bridge.close()


# ---------------------------------------------------------------------------
# Chat standalone mode (args parsing)
# ---------------------------------------------------------------------------


class TestChatStandalone:
    def test_chat_standalone_quit(self, tmp_path):
        """Test that --standalone mode starts and handles /quit."""
        env_code = f"""
import sys; sys.argv = ['chat', '--standalone']
import mahaclaw.llm as llm_mod
# Mock is_available to avoid network call
llm_mod.is_available = lambda config=None: (False, "test mock")
from mahaclaw.chat import main; raise SystemExit(main())
"""
        result = subprocess.run(
            [sys.executable, "-c", env_code],
            input="/status\n/quit\n",
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, result.stderr
        assert "standalone" in result.stdout.lower()
        assert "bye" in result.stdout

    def test_chat_mode_switch(self, tmp_path):
        """Test switching from federation to standalone and back."""
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text("[]\n")

        env_code = f"""
import sys; sys.argv = ['chat', '--target', 'agent-research', '--nowait']
import mahaclaw.envelope as m; m.OUTBOX_PATH = __import__('pathlib').Path('{outbox}')
import mahaclaw.llm as llm_mod
llm_mod.is_available = lambda config=None: (False, "test mock")
from mahaclaw.chat import main; raise SystemExit(main())
"""
        result = subprocess.run(
            [sys.executable, "-c", env_code],
            input="/standalone\n/status\n/federation\n/status\n/quit\n",
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0, result.stderr
        assert "standalone" in result.stdout.lower()
        assert "federation" in result.stdout.lower()
        assert "bye" in result.stdout


# ---------------------------------------------------------------------------
# Legacy Envelope Compatibility
# ---------------------------------------------------------------------------

from mahaclaw.envelope import normalize_envelope, is_legacy_envelope


class TestLegacyEnvelopeCompat:
    def test_legacy_envelope_detected(self):
        legacy = {
            "source": "steward",
            "target": "mahaclaw",
            "operation": "heartbeat",
            "payload": {"health": 0.95},
            "timestamp": 1774014592.66,
            "priority": 1,
            "correlation_id": "corr-123",
            "ttl_s": 900.0,
            "id": "974960abc",
        }
        assert is_legacy_envelope(legacy) is True

    def test_current_envelope_not_legacy(self):
        current = {
            "maha_header_hex": "a" * 32,
            "nadi_type": "vyana",
            "nadi_op": "send",
            "nadi_priority": "rajas",
            "source": "steward",
            "target": "mahaclaw",
        }
        assert is_legacy_envelope(current) is False

    def test_normalize_legacy_adds_maha_fields(self):
        legacy = {
            "source": "steward",
            "target": "mahaclaw",
            "operation": "heartbeat",
            "payload": {"health": 0.95},
            "timestamp": 1774014592.66,
            "priority": 1,
            "correlation_id": "corr-123",
            "ttl_s": 900.0,
            "id": "974960abc",
        }
        normalized = normalize_envelope(legacy)

        # MahaHeader fields filled with defaults
        assert normalized["nadi_type"] == "vyana"
        assert normalized["nadi_op"] == "send"
        assert normalized["nadi_priority"] == "rajas"
        assert len(normalized["maha_header_hex"]) == 32
        # TTL computed from ttl_s
        assert normalized["ttl_ms"] == 900000
        # Original fields preserved
        assert normalized["source"] == "steward"
        assert normalized["correlation_id"] == "corr-123"
        assert normalized["payload"]["health"] == 0.95

    def test_normalize_current_is_idempotent(self):
        current = {
            "source": "steward",
            "target": "mahaclaw",
            "operation": "inquiry_response",
            "payload": {"answer": "42"},
            "timestamp": 1774014592.66,
            "priority": 5,
            "correlation_id": "corr-456",
            "ttl_s": 24.0,
            "ttl_ms": 24000,
            "nadi_type": "apana",
            "nadi_op": "send",
            "nadi_priority": "sattva",
            "maha_header_hex": "b" * 32,
            "envelope_id": "env_abc",
            "id": "id_abc",
        }
        normalized = normalize_envelope(current)
        # All existing values preserved
        assert normalized["nadi_type"] == "apana"
        assert normalized["nadi_priority"] == "sattva"
        assert normalized["maha_header_hex"] == "b" * 32

    def test_normalize_fills_missing_ids(self):
        minimal = {
            "correlation_id": "c1",
            "source": "x",
            "target": "y",
            "operation": "op",
            "payload": {},
        }
        normalized = normalize_envelope(minimal)
        assert normalized["source_city_id"] == "x"
        assert normalized["target_city_id"] == "y"
        assert normalized["ttl_ms"] == 24000
        assert normalized["ttl_s"] == 24.0

    def test_poll_accepts_legacy_response(self, tmp_path):
        """Poll finds and normalizes a legacy envelope matching correlation_id."""
        inbox = tmp_path / "nadi_inbox.json"
        legacy_response = {
            "correlation_id": "legacy-corr-001",
            "source": "steward",
            "target": "mahaclaw",
            "operation": "inquiry_response",
            "payload": {"answer": "federation has 4 agents"},
            "timestamp": 1774014592.66,
            "priority": 1,
            "ttl_s": 900.0,
            "id": "legacy-id-001",
        }
        inbox.write_text(json.dumps([legacy_response]) + "\n")

        result = poll_response("legacy-corr-001", timeout_s=0.5, inbox_path=inbox)
        assert result is not None
        assert result["correlation_id"] == "legacy-corr-001"
        # Should be normalized — has MahaHeader fields
        assert result["nadi_type"] == "vyana"
        assert len(result["maha_header_hex"]) == 32
        assert result["payload"]["answer"] == "federation has 4 agents"


# ---------------------------------------------------------------------------
# Steward-Only Bridge Mode
# ---------------------------------------------------------------------------


class TestStewardOnlyBridge:
    def test_steward_only_routes_through_pipeline(self, tmp_path, monkeypatch):
        """In steward-only mode, all messages go through federation pipeline."""
        outbox = tmp_path / "nadi_outbox.json"
        outbox.write_text("[]\n")
        import mahaclaw.envelope as env_mod
        monkeypatch.setattr(env_mod, "OUTBOX_PATH", outbox)
        reload()

        replies = []
        bridge = ChannelBridge(BridgeConfig(
            session_db=str(tmp_path / "test.db"),
            steward_only=True,
            response_wait_s=0,
        ))
        bridge.register_sender("test", lambda cid, text, rt: replies.append(text))

        msg = IncomingMessage(
            channel="test", user_id="u1", username="alice",
            text="hello steward", chat_id="c1",
        )
        bridge.handle_message(msg)

        # Should route through pipeline (not standalone)
        assert len(replies) == 1
        assert "steward" in replies[0].lower()

        data = json.loads(outbox.read_text())
        assert len(data) == 1
        assert data[0]["payload"]["message"] == "hello steward"
        bridge.close()

    def test_steward_only_mode_lock(self, tmp_path):
        """In steward-only mode, /mode command is locked."""
        replies = []
        bridge = ChannelBridge(BridgeConfig(
            session_db=str(tmp_path / "test.db"),
            steward_only=True,
        ))
        bridge.register_sender("test", lambda cid, text, rt: replies.append(text))

        msg = IncomingMessage(
            channel="test", user_id="u1", username="a",
            text="/mode", chat_id="c1",
        )
        bridge.handle_message(msg)
        assert "locked" in replies[0].lower()
        bridge.close()

    def test_detect_intent_passthrough(self):
        """_detect_intent returns raw text (Manas routes by seed, not keywords)."""
        assert _detect_intent("research quantum computing") == "research quantum computing"
        assert _detect_intent("investigate this bug") == "investigate this bug"


# ---------------------------------------------------------------------------
# Buddhi (Safety Gate)
# ---------------------------------------------------------------------------

from mahaclaw.buddhi import (
    VerdictAction, BuddhiVerdict, Impression, Chitta,
    check_intent, detect_patterns,
)


class TestBuddhiGate:
    def test_safe_intent_continues(self):
        intent = {"intent": "inquiry", "target": "agent-research", "priority": "rajas", "ttl_ms": 24000}
        v = check_intent(intent)
        assert v.action == VerdictAction.CONTINUE

    def test_blocked_intent_aborts(self):
        intent = {"intent": "delete_all", "target": "x", "priority": "rajas", "ttl_ms": 24000}
        v = check_intent(intent)
        assert v.action == VerdictAction.ABORT

    def test_dangerous_substring_aborts(self):
        intent = {"intent": "rm -rf everything", "target": "x", "priority": "rajas", "ttl_ms": 24000}
        v = check_intent(intent)
        assert v.action == VerdictAction.ABORT

    def test_invalid_priority_redirects(self):
        intent = {"intent": "inquiry", "target": "x", "priority": "mega", "ttl_ms": 24000}
        v = check_intent(intent)
        assert v.action == VerdictAction.REDIRECT

    def test_negative_ttl_redirects(self):
        intent = {"intent": "inquiry", "target": "x", "priority": "rajas", "ttl_ms": -1}
        v = check_intent(intent)
        assert v.action == VerdictAction.REDIRECT

    def test_restricted_target_high_priority_reflects(self):
        intent = {"intent": "inquiry", "target": "steward", "priority": "suddha", "ttl_ms": 24000}
        v = check_intent(intent)
        assert v.action == VerdictAction.REFLECT

    def test_narasimha_bypass_blocked(self):
        intent = {"intent": "bypass_viveka", "target": "x", "priority": "rajas", "ttl_ms": 24000}
        v = check_intent(intent)
        assert v.action == VerdictAction.ABORT


class TestGandhaDetection:
    def test_no_patterns_on_empty(self):
        assert detect_patterns([]) is None

    def test_consecutive_errors_aborts(self):
        imps = [Impression(name="bash", success=False, error="fail") for _ in range(5)]
        v = detect_patterns(imps)
        assert v is not None
        assert v.action == VerdictAction.ABORT

    def test_identical_calls_reflects(self):
        imps = [Impression(name="bash", params_hash=42, success=False) for _ in range(3)]
        v = detect_patterns(imps)
        assert v is not None
        assert v.action in (VerdictAction.REFLECT, VerdictAction.ABORT)

    def test_blind_write_redirects(self):
        imps = [Impression(name="edit_file", path="/foo.py", success=True)]
        v = detect_patterns(imps, prior_reads=frozenset())
        assert v is not None
        assert v.action == VerdictAction.REDIRECT

    def test_write_after_read_ok(self):
        imps = [Impression(name="edit_file", path="/foo.py", success=True)]
        v = detect_patterns(imps, prior_reads=frozenset({"/foo.py"}))
        assert v is None

    def test_high_error_ratio_reflects(self):
        imps = [Impression(name=f"t{i}", success=(i == 0)) for i in range(5)]
        v = detect_patterns(imps)
        assert v is not None
        assert v.action == VerdictAction.REFLECT


class TestChitta:
    def test_record_and_evaluate(self):
        c = Chitta()
        c.record(Impression(name="read_file", path="/x.py", success=True))
        assert "/x.py" in c.prior_reads
        v = c.evaluate()
        assert v.action == VerdictAction.CONTINUE

    def test_clear_preserves_prior_reads(self):
        c = Chitta()
        c.record(Impression(name="read_file", path="/x.py", success=True))
        c.clear()
        assert "/x.py" in c.prior_reads
        assert len(c.impressions) == 0


# ---------------------------------------------------------------------------
# Ahamkara (Identity / Signing)
# ---------------------------------------------------------------------------

from mahaclaw.ahamkara import (
    hmac_sign, hmac_verify, hmac_fingerprint,
    sign_envelope, verify_envelope, stamp_envelope,
    get_identity, _canonical_content, KEYS_DIR,
)
import shutil


class TestAhamkara:
    @pytest.fixture(autouse=True)
    def _clean_keys(self, tmp_path, monkeypatch):
        """Use temp directory for keys so tests don't pollute real keys."""
        keys_dir = tmp_path / ".mahaclaw" / "keys"
        monkeypatch.setattr("mahaclaw.ahamkara.KEYS_DIR", keys_dir)
        monkeypatch.setattr("mahaclaw.ahamkara.HMAC_KEY_FILE", keys_dir / "hmac.key")
        monkeypatch.setattr("mahaclaw.ahamkara.ECDSA_PRIVATE_FILE", keys_dir / "private.pem")
        monkeypatch.setattr("mahaclaw.ahamkara.ECDSA_PUBLIC_FILE", keys_dir / "public.pem")

    def test_hmac_sign_and_verify(self):
        sig = hmac_sign("hello")
        assert hmac_verify("hello", sig)
        assert not hmac_verify("tampered", sig)

    def test_hmac_fingerprint_stable(self):
        fp1 = hmac_fingerprint()
        fp2 = hmac_fingerprint()
        assert fp1 == fp2
        assert len(fp1) == 16

    def test_stamp_envelope_adds_fields(self):
        env = {
            "source": "mahaclaw", "target": "steward",
            "operation": "inquiry", "nadi_type": "vyana",
            "priority": 5, "ttl_ms": 24000,
            "envelope_id": "env_abc", "correlation_id": "corr_123",
        }
        stamped = stamp_envelope(env)
        assert "_signature" in stamped
        assert "_signer_fingerprint" in stamped
        assert "_signing_method" in stamped
        assert len(stamped["_signer_fingerprint"]) == 16

    def test_verify_stamped_envelope(self):
        env = {
            "source": "mahaclaw", "target": "steward",
            "operation": "inquiry", "nadi_type": "vyana",
            "priority": 5, "ttl_ms": 24000,
            "envelope_id": "env_abc", "correlation_id": "corr_123",
        }
        stamped = stamp_envelope(env)
        assert verify_envelope(stamped)

    def test_tampered_envelope_fails(self):
        env = {
            "source": "mahaclaw", "target": "steward",
            "operation": "inquiry", "nadi_type": "vyana",
            "priority": 5, "ttl_ms": 24000,
            "envelope_id": "env_abc", "correlation_id": "corr_123",
        }
        stamped = stamp_envelope(env)
        stamped["target"] = "evil-agent"
        assert not verify_envelope(stamped)

    def test_identity_method(self):
        ident = get_identity()
        assert ident.signing_method in ("ecdsa", "hmac-sha256")
        assert len(ident.fingerprint) == 16

    def test_canonical_content_deterministic(self):
        env = {"source": "a", "target": "b", "operation": "c",
               "nadi_type": "d", "priority": 1, "ttl_ms": 2,
               "envelope_id": "e", "correlation_id": "f", "extra": "ignored"}
        c1 = _canonical_content(env)
        c2 = _canonical_content(env)
        assert c1 == c2
        assert "extra" not in c1


from mahaclaw.manas import perceive


class TestManaSeedPipeline:
    """Test the pure seed-based Manas routing (zero keywords)."""

    def test_seed_deterministic(self):
        """Same text always produces same seed."""
        from mahaclaw.manas import _compute_seed
        s1 = _compute_seed("hello world")
        s2 = _compute_seed("hello world")
        assert s1 == s2

    def test_seed_case_insensitive(self):
        """Seeds are case-insensitive (text.lower())."""
        from mahaclaw.manas import _compute_seed
        assert _compute_seed("Hello") == _compute_seed("hello")

    def test_position_in_range(self):
        """Position is always 0-15."""
        from mahaclaw.manas import _compute_seed, _seed_to_position
        for text in ("a", "abc", "inquiry", "heartbeat", "xyzzy", "test_long_string_here"):
            seed = _compute_seed(text)
            pos = _seed_to_position(seed)
            assert 0 <= pos < 16, f"{text} → pos {pos}"

    def test_perceive_returns_all_fields(self):
        """ManasPerception has all required fields."""
        p = perceive("test intent")
        assert hasattr(p, "action")
        assert hasattr(p, "guna")
        assert hasattr(p, "function")
        assert hasattr(p, "approach")
        assert hasattr(p, "position")
        assert 0 <= p.position < 16

    def test_perceive_deterministic(self):
        """Same intent → same perception."""
        p1 = perceive("hello federation")
        p2 = perceive("hello federation")
        assert p1 == p2

    def test_guna_from_position(self):
        """Guna is derived from position via opcode sets."""
        from mahaclaw.manas import _position_to_guna, IntentGuna
        from mahaclaw.manas import SATTVA_POSITIONS, TAMAS_POSITIONS, RAJAS_POSITIONS
        for pos in range(16):
            g = _position_to_guna(pos)
            if pos in SATTVA_POSITIONS:
                assert g == IntentGuna.SATTVA
            elif pos in TAMAS_POSITIONS:
                assert g == IntentGuna.TAMAS
            else:
                assert g == IntentGuna.RAJAS

    def test_function_from_position(self):
        """Function is derived from HARE/KRISHNA/RAMA position sets."""
        from mahaclaw.manas import _position_to_function, Function
        from mahaclaw.manas import HARE_POSITIONS, KRISHNA_POSITIONS, RAMA_POSITIONS
        for pos in range(16):
            f = _position_to_function(pos)
            if pos in HARE_POSITIONS:
                assert f == Function.CARRIER
            elif pos in KRISHNA_POSITIONS:
                assert f == Function.SOURCE
            elif pos in RAMA_POSITIONS:
                assert f == Function.DELIVERER

    def test_approach_from_position(self):
        """Approach = quarter from position // 4."""
        from mahaclaw.manas import _position_to_approach, Approach
        assert _position_to_approach(0) == Approach.GENESIS
        assert _position_to_approach(3) == Approach.GENESIS
        assert _position_to_approach(4) == Approach.DHARMA
        assert _position_to_approach(7) == Approach.DHARMA
        assert _position_to_approach(8) == Approach.KARMA
        assert _position_to_approach(11) == Approach.KARMA
        assert _position_to_approach(12) == Approach.MOKSHA
        assert _position_to_approach(15) == Approach.MOKSHA

    def test_action_from_approach_chain(self):
        """ActionType derives from approach affinity (primary)."""
        from mahaclaw.manas import _APPROACH_TO_ACTION, Approach, ActionType
        assert _APPROACH_TO_ACTION[Approach.GENESIS] == ActionType.IMPLEMENT
        assert _APPROACH_TO_ACTION[Approach.DHARMA] == ActionType.REVIEW
        assert _APPROACH_TO_ACTION[Approach.KARMA] == ActionType.DEBUG
        assert _APPROACH_TO_ACTION[Approach.MOKSHA] == ActionType.RESEARCH

    def test_synth_transform_deterministic(self):
        """MahaModularSynth transform is deterministic."""
        from mahaclaw.manas import _synth_transform
        assert _synth_transform(42) == _synth_transform(42)
        assert _synth_transform(0) != _synth_transform(1)  # different inputs differ

    def test_phonetic_vibration(self):
        """Phonetic vibration is deterministic and position-weighted."""
        from mahaclaw.manas import _phonetic_vibration
        v1 = _phonetic_vibration("abc")
        v2 = _phonetic_vibration("abc")
        assert v1 == v2
        # "ab" and "ba" should differ (position-weighted)
        assert _phonetic_vibration("ab") != _phonetic_vibration("ba")

    def test_no_keywords_in_manas(self):
        """Verify _KEYWORD_ACTIONS does not exist in manas module."""
        import mahaclaw.manas as m
        assert not hasattr(m, "_KEYWORD_ACTIONS")

    def test_mahamantra_constants(self):
        """Verify Mahamantra constants match steward-protocol."""
        from mahaclaw.manas import WORDS, MAHA_QUANTUM, PARAMPARA, QUARTERS
        assert WORDS == 16
        assert MAHA_QUANTUM == 137
        assert PARAMPARA == 37
        assert QUARTERS == 4


class TestAhamkaraInPipeline:
    """Test that Ahamkara is wired into the envelope pipeline."""

    @pytest.fixture(autouse=True)
    def _clean(self, tmp_path, monkeypatch):
        keys_dir = tmp_path / ".mahaclaw" / "keys"
        monkeypatch.setattr("mahaclaw.ahamkara.KEYS_DIR", keys_dir)
        monkeypatch.setattr("mahaclaw.ahamkara.HMAC_KEY_FILE", keys_dir / "hmac.key")
        monkeypatch.setattr("mahaclaw.ahamkara.ECDSA_PRIVATE_FILE", keys_dir / "private.pem")
        monkeypatch.setattr("mahaclaw.ahamkara.ECDSA_PUBLIC_FILE", keys_dir / "public.pem")
        outbox = tmp_path / "nadi_outbox.json"
        monkeypatch.setattr("mahaclaw.envelope.OUTBOX_PATH", outbox)

    def test_build_and_enqueue_stamps(self):
        from mahaclaw.intercept import parse_intent
        from mahaclaw.tattva import classify
        from mahaclaw.rama import encode_rama
        from mahaclaw.lotus import resolve_route
        from mahaclaw.envelope import build_and_enqueue, OUTBOX_PATH

        raw = json.dumps({"intent": "inquiry", "target": "agent-research", "payload": {"q": "test"}})
        intent = parse_intent(raw)
        tattva = classify(intent)
        rama = encode_rama(intent, tattva)
        route = resolve_route(intent, rama)
        eid, cid = build_and_enqueue(intent, rama, route)

        outbox = json.loads(OUTBOX_PATH.read_text())
        assert len(outbox) >= 1
        last = outbox[-1]
        assert "_signature" in last
        assert "_signer_fingerprint" in last
