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
        assert "jala/research" in result.stdout
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
        assert result["element"] == "jala"

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
        assert result["element"] == "jala"

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
    def test_detect_intent_types(self):
        assert _detect_intent("build something") == "code_analysis"
        assert _detect_intent("what's the governance policy?") == "governance_proposal"
        assert _detect_intent("find agents nearby") == "discover_peers"
        assert _detect_intent("are you alive?") == "heartbeat"
        assert _detect_intent("tell me about quantum physics") == "inquiry"

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
        assert "jala/research" in replies[0]

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
