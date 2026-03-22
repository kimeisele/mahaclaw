"""Tests for all 8 new Sankhya elements.

Vedana, Rasa, Rasana, Payu, KsetraJna, Upastha, Pada, Cetana.

Covers functionality AND anauralia compliance.
"""
from __future__ import annotations

import dataclasses
import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Vedana — Health Pulse
# ---------------------------------------------------------------------------

class TestVedana:

    def test_healthy_system(self):
        from mahaclaw.vedana import pulse, HealthGuna
        from mahaclaw.chitta import Chitta

        c = Chitta()
        c.record("read_file", 0, True)
        c.record("write_file", 1, True)
        sig = pulse(c, confidence=0.9, queue_depth=0)

        assert sig.score >= 0.7
        assert sig.guna == HealthGuna.SATTVA
        assert sig.error_rate == 0.0
        assert sig.impression_count == 2
        assert sig.confidence == 0.9

    def test_degraded_system(self):
        from mahaclaw.vedana import pulse, HealthGuna
        from mahaclaw.chitta import Chitta

        c = Chitta()
        for i in range(10):
            c.record("bash", i, False)  # all errors
        sig = pulse(c, confidence=0.1, queue_depth=200)

        assert sig.score < 0.4
        assert sig.guna == HealthGuna.TAMAS
        assert sig.error_rate == 1.0

    def test_stressed_system(self):
        from mahaclaw.vedana import pulse, HealthGuna
        from mahaclaw.chitta import Chitta

        c = Chitta()
        for i in range(6):
            c.record("bash", i, True)
        for i in range(4):
            c.record("bash", i + 10, False)  # 40% error rate
        sig = pulse(c, confidence=0.5, queue_depth=50)

        assert sig.guna in (HealthGuna.RAJAS, HealthGuna.SATTVA)

    def test_empty_chitta(self):
        from mahaclaw.vedana import pulse, HealthGuna
        from mahaclaw.chitta import Chitta

        c = Chitta()
        sig = pulse(c)
        assert sig.error_rate == 0.0
        assert sig.impression_count == 0
        assert sig.uptime_s >= 0

    def test_signal_fields_anauralia(self):
        """VedanaSignal has no prose fields."""
        from mahaclaw.vedana import VedanaSignal
        for f in dataclasses.fields(VedanaSignal):
            assert f.name not in ("reason", "description", "message", "suggestion")


# ---------------------------------------------------------------------------
# Rasa — Trust Validation
# ---------------------------------------------------------------------------

class TestRasa:

    def test_internal_source_approved(self):
        from mahaclaw.rasa import validate, TrustLevel
        v = validate({"target": "some-agent", "priority": "rajas"}, source="mahaclaw")
        assert v.approved is True
        assert v.source_trust == TrustLevel.INTERNAL

    def test_unknown_source_blocked(self):
        from mahaclaw.rasa import validate, RasaCause
        v = validate({"target": "agent-city", "priority": "rajas"}, source="")
        assert v.approved is False
        assert v.cause == RasaCause.MISSING_SOURCE

    def test_low_trust_elevated_target(self):
        from mahaclaw.rasa import validate, RasaCause, TrustLevel
        v = validate({"target": "steward", "priority": "rajas"}, source="webchat")
        assert v.approved is False
        assert v.cause == RasaCause.ELEVATED_TARGET
        assert v.required_trust == TrustLevel.VERIFIED

    def test_signed_source_elevated(self):
        from mahaclaw.rasa import validate, TrustLevel
        v = validate(
            {"target": "agent-city", "priority": "rajas"},
            source="external",
            is_signed=True,
        )
        assert v.source_trust == TrustLevel.AUTHENTICATED

    def test_verified_source_highest(self):
        from mahaclaw.rasa import validate, TrustLevel
        v = validate(
            {"target": "steward", "priority": "suddha"},
            source="external",
            is_verified=True,
        )
        assert v.source_trust == TrustLevel.VERIFIED
        assert v.approved is True

    def test_priority_trust_escalation(self):
        from mahaclaw.rasa import validate, TrustLevel
        # suddha priority requires VERIFIED trust
        v = validate(
            {"target": "some-agent", "priority": "suddha"},
            source="webchat",  # DISCOVERED level
        )
        assert v.approved is False
        assert v.required_trust == TrustLevel.VERIFIED

    def test_verdict_fields_anauralia(self):
        from mahaclaw.rasa import RasaVerdict
        for f in dataclasses.fields(RasaVerdict):
            assert f.name not in ("reason", "description", "message", "suggestion")


# ---------------------------------------------------------------------------
# Rasana — Preference Learning
# ---------------------------------------------------------------------------

class TestRasana:

    def test_record_and_query_targets(self):
        from mahaclaw.rasana import Rasana
        r = Rasana()
        r.record_target("agent-research")
        r.record_target("agent-research")
        r.record_target("agent-city")
        assert r.preferred_target == "agent-research"
        assert r.total_messages == 3

    def test_record_actions(self):
        from mahaclaw.rasana import Rasana
        r = Rasana()
        r.record_action("INQUIRY")
        r.record_action("INQUIRY")
        r.record_action("CODE_ANALYSIS")
        assert r.preferred_action == "INQUIRY"

    def test_tool_success_rate(self):
        from mahaclaw.rasana import Rasana
        r = Rasana()
        r.record_tool("bash", True)
        r.record_tool("bash", True)
        r.record_tool("bash", False)
        assert abs(r.tool_success_rate("bash") - 2/3) < 0.01

    def test_unknown_tool_neutral(self):
        from mahaclaw.rasana import Rasana
        r = Rasana()
        assert r.tool_success_rate("unknown") == 0.5

    def test_top_tools_sorted(self):
        from mahaclaw.rasana import Rasana
        r = Rasana()
        r.record_tool("good", True)
        r.record_tool("good", True)
        r.record_tool("bad", False)
        r.record_tool("bad", False)
        top = r.top_tools
        assert top[0][0] == "good"
        assert top[1][0] == "bad"

    def test_empty_preferences(self):
        from mahaclaw.rasana import Rasana
        r = Rasana()
        assert r.preferred_target == ""
        assert r.preferred_action == ""
        assert r.top_tools == []

    def test_serialization_roundtrip(self):
        from mahaclaw.rasana import Rasana
        r1 = Rasana()
        r1.record_target("agent-research")
        r1.record_action("INQUIRY")
        r1.record_tool("bash", True)
        r1.total_messages = 5

        data = r1.to_summary()
        r2 = Rasana()
        r2.load_summary(data)

        assert r2.target_counts == r1.target_counts
        assert r2.action_counts == r1.action_counts
        assert r2.tool_success == r1.tool_success
        assert r2.total_messages == 5


# ---------------------------------------------------------------------------
# Payu — Garbage Collection
# ---------------------------------------------------------------------------

class TestPayu:

    def test_rotate_outbox_removes_old(self, tmp_path):
        from mahaclaw.payu import rotate_outbox

        outbox = tmp_path / "outbox.json"
        now = time.time()
        data = [
            {"timestamp": now - 100000, "id": "old"},   # older than 24h
            {"timestamp": now - 10, "id": "new"},        # recent
        ]
        outbox.write_text(json.dumps(data))

        result = rotate_outbox(outbox)
        assert result.envelopes_removed == 1
        assert result.success is True

        remaining = json.loads(outbox.read_text())
        assert len(remaining) == 1
        assert remaining[0]["id"] == "new"

    def test_rotate_outbox_trims_excess(self, tmp_path):
        from mahaclaw.payu import rotate_outbox

        outbox = tmp_path / "outbox.json"
        now = time.time()
        data = [{"timestamp": now, "id": str(i)} for i in range(10)]
        outbox.write_text(json.dumps(data))

        result = rotate_outbox(outbox, max_entries=5)
        assert result.envelopes_removed == 5

        remaining = json.loads(outbox.read_text())
        assert len(remaining) == 5

    def test_rotate_outbox_missing_file(self, tmp_path):
        from mahaclaw.payu import rotate_outbox
        result = rotate_outbox(tmp_path / "nonexistent.json")
        assert result.envelopes_removed == 0
        assert result.success is True

    def test_clean_inbox(self, tmp_path):
        from mahaclaw.payu import clean_inbox

        inbox = tmp_path / "inbox.json"
        now = time.time()
        data = [
            {"timestamp": now - 100000, "id": "old"},
            {"timestamp": now, "id": "new"},
        ]
        inbox.write_text(json.dumps(data))

        result = clean_inbox(inbox)
        assert result.envelopes_removed == 1

    def test_expire_sessions(self, tmp_path):
        from mahaclaw.payu import expire_sessions

        db = tmp_path / "sessions.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE sessions (session_id TEXT, updated_at REAL)")
        conn.execute("CREATE TABLE session_ledger (session_id TEXT, data TEXT)")
        now = time.time()
        conn.execute("INSERT INTO sessions VALUES (?, ?)", ("old", now - 700000))
        conn.execute("INSERT INTO sessions VALUES (?, ?)", ("new", now))
        conn.execute("INSERT INTO session_ledger VALUES (?, ?)", ("old", "data"))
        conn.commit()
        conn.close()

        result = expire_sessions(db)
        assert result.sessions_expired == 1

        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT * FROM sessions").fetchall()
        ledger = conn.execute("SELECT * FROM session_ledger").fetchall()
        conn.close()
        assert len(rows) == 1
        assert rows[0][0] == "new"
        assert len(ledger) == 0  # orphaned ledger cleaned

    def test_sweep_combines_all(self, tmp_path):
        from mahaclaw.payu import sweep

        outbox = tmp_path / "outbox.json"
        inbox = tmp_path / "inbox.json"
        db = tmp_path / "sessions.db"

        now = time.time()
        outbox.write_text(json.dumps([{"timestamp": now - 100000}]))
        inbox.write_text(json.dumps([{"timestamp": now - 100000}]))

        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE sessions (session_id TEXT, updated_at REAL)")
        conn.execute("CREATE TABLE session_ledger (session_id TEXT, data TEXT)")
        conn.execute("INSERT INTO sessions VALUES (?, ?)", ("old", now - 700000))
        conn.commit()
        conn.close()

        result = sweep(outbox, inbox, db)
        assert result.envelopes_removed == 2
        assert result.sessions_expired == 1
        assert result.success is True

    def test_result_fields_anauralia(self):
        from mahaclaw.payu import PayuResult
        for f in dataclasses.fields(PayuResult):
            assert f.name not in ("reason", "description", "message", "suggestion")


# ---------------------------------------------------------------------------
# KsetraJna — Meta-Observer
# ---------------------------------------------------------------------------

class TestKsetraJna:

    def test_observe_empty(self):
        from mahaclaw.ksetrajna import observe
        snap = observe()
        assert snap.impression_count == 0
        assert snap.error_count == 0
        assert snap.success_count == 0
        assert snap.uptime_s >= 0
        assert len(snap.snapshot_hash) == 32

    def test_observe_with_chitta(self):
        from mahaclaw.ksetrajna import observe
        from mahaclaw.chitta import Chitta, ExecutionPhase

        c = Chitta()
        c.record("read_file", 0, True)
        c.record("bash", 1, False)
        snap = observe(chitta=c, health_score=0.8)

        assert snap.impression_count == 2
        assert snap.error_count == 1
        assert snap.success_count == 1
        assert snap.health_score == 0.8
        assert snap.phase == c.phase

    def test_snapshot_hash_changes(self):
        from mahaclaw.ksetrajna import observe
        from mahaclaw.chitta import Chitta

        c1 = Chitta()
        c1.record("read_file", 0, True)
        snap1 = observe(chitta=c1, health_score=0.5)

        c2 = Chitta()
        c2.record("read_file", 0, True)
        c2.record("bash", 1, False)
        snap2 = observe(chitta=c2, health_score=0.5)

        # Different state → different hash
        assert snap1.snapshot_hash != snap2.snapshot_hash

    def test_to_dict(self):
        from mahaclaw.ksetrajna import observe, to_dict
        snap = observe()
        d = to_dict(snap)
        assert d["kind"] == "bubble_snapshot"
        assert "route_count" in d
        assert "snapshot_hash" in d
        assert "phase" in d

    def test_snapshot_fields_anauralia(self):
        from mahaclaw.ksetrajna import BubbleSnapshot
        for f in dataclasses.fields(BubbleSnapshot):
            assert f.name not in ("reason", "description", "message", "suggestion")


# ---------------------------------------------------------------------------
# Upastha — Generation / Artifact Creation
# ---------------------------------------------------------------------------

class TestUpastha:

    def test_skill_to_intent_success(self):
        from mahaclaw.upastha import skill_to_intent
        from mahaclaw.skills._types import SkillResult

        sr = SkillResult(ok=True, output="hello", data={"key": "val"})
        intent = skill_to_intent(sr, "test_skill", target="agent-research")

        assert intent is not None
        assert intent["intent"] == "skill_result"
        assert intent["target"] == "agent-research"
        assert intent["payload"]["_skill"] == "test_skill"
        assert intent["payload"]["skill_output"] == "hello"
        assert intent["payload"]["key"] == "val"

    def test_skill_to_intent_failed_skill(self):
        from mahaclaw.upastha import skill_to_intent
        from mahaclaw.skills._types import SkillResult

        sr = SkillResult(ok=False, error="failed")
        assert skill_to_intent(sr, "bad_skill") is None

    def test_skill_to_intent_empty_output(self):
        from mahaclaw.upastha import skill_to_intent
        from mahaclaw.skills._types import SkillResult

        sr = SkillResult(ok=True)  # no output, no data
        assert skill_to_intent(sr, "empty_skill") is None

    def test_generate_failed_skill(self):
        from mahaclaw.upastha import generate, GenerationStatus
        from mahaclaw.skills._types import SkillResult

        sr = SkillResult(ok=False)
        result = generate(sr, "bad")
        assert result.status == GenerationStatus.SKILL_FAILED
        assert result.enveloped is False

    def test_generate_no_output(self):
        from mahaclaw.upastha import generate, GenerationStatus
        from mahaclaw.skills._types import SkillResult

        sr = SkillResult(ok=True)
        result = generate(sr, "empty")
        assert result.status == GenerationStatus.NO_OUTPUT

    def test_result_fields_anauralia(self):
        from mahaclaw.upastha import GenerationResult
        for f in dataclasses.fields(GenerationResult):
            assert f.name not in ("reason", "description", "message", "suggestion")


# ---------------------------------------------------------------------------
# Pada — Dynamic Routing / Peer Discovery
# ---------------------------------------------------------------------------

class TestPada:

    def test_extract_peer_from_envelope(self):
        from mahaclaw.pada import extract_peer_from_envelope

        env = {
            "source_city_id": "kimeisele/agent-research",
            "operation": "heartbeat_response",
            "timestamp": 1000.0,
            "nadi_type": "vyana",
            "payload": {"capabilities": ["research"]},
        }
        peer = extract_peer_from_envelope(env)
        assert peer is not None
        assert peer["full_name"] == "kimeisele/agent-research"
        assert peer["capabilities"] == ["research"]

    def test_extract_peer_no_source(self):
        from mahaclaw.pada import extract_peer_from_envelope
        peer = extract_peer_from_envelope({"source": "", "payload": {}})
        assert peer is None

    def test_extract_peer_bare_name(self):
        from mahaclaw.pada import extract_peer_from_envelope
        # Bare name without org/ — can't route
        peer = extract_peer_from_envelope({
            "source_city_id": "bare-name",
            "source": "bare-name",
            "payload": {},
        })
        assert peer is None

    def test_discover_from_inbox_empty(self, tmp_path):
        from mahaclaw.pada import discover_from_inbox

        inbox = tmp_path / "inbox.json"
        inbox.write_text("[]")
        result = discover_from_inbox(inbox)
        assert result.peers_found == 0
        assert result.routes_refreshed is False

    def test_discover_from_inbox_with_peers(self, tmp_path, monkeypatch):
        from mahaclaw import pada
        from mahaclaw.pada import discover_from_inbox

        inbox = tmp_path / "inbox.json"
        peers_file = tmp_path / "peers.json"

        # Patch PEERS_PATH
        monkeypatch.setattr(pada, "PEERS_PATH", peers_file)
        monkeypatch.setattr("mahaclaw.lotus.PEERS_PATH", peers_file)

        messages = [
            {
                "source_city_id": "kimeisele/agent-research",
                "operation": "heartbeat_response",
                "timestamp": time.time(),
                "nadi_type": "vyana",
                "payload": {},
            },
        ]
        inbox.write_text(json.dumps(messages))

        result = discover_from_inbox(inbox)
        assert result.peers_found == 1
        assert result.peers_added == 1
        assert result.routes_refreshed is True

        # Verify peers file was created
        assert peers_file.exists()
        registry = json.loads(peers_file.read_text())
        assert len(registry["peers"]) == 1

    def test_refresh_routes(self, monkeypatch):
        from mahaclaw.pada import refresh_routes
        result = refresh_routes()
        assert result.routes_refreshed is True

    def test_result_fields_anauralia(self):
        from mahaclaw.pada import DiscoveryResult
        for f in dataclasses.fields(DiscoveryResult):
            assert f.name not in ("reason", "description", "message", "suggestion")


# ---------------------------------------------------------------------------
# Cetana — Heartbeat Daemon
# ---------------------------------------------------------------------------

class TestCetana:

    def test_heartbeat_intent(self):
        from mahaclaw.cetana import _build_heartbeat_intent

        intent = _build_heartbeat_intent()
        assert intent["intent"] == "heartbeat"
        assert intent["target"] == "agent-city"
        assert intent["priority"] == "tamas"
        assert intent["payload"]["node"] == "mahaclaw"

    def test_beat_once_increments(self):
        from mahaclaw.cetana import beat_once, HeartbeatState, MuraliPhase

        state = HeartbeatState()
        assert state.cycle_count == 0

        beat_once(state)
        assert state.cycle_count == 1
        # beat might succeed or fail depending on route table
        assert state.successful_beats + state.errors == 1

    def test_adaptive_interval_on_failure(self):
        from mahaclaw.cetana import beat_once, HeartbeatState, MIN_INTERVAL_S

        state = HeartbeatState(interval_s=300.0)
        original = state.interval_s

        # Force failure by monkey-patching
        import mahaclaw.cetana as cetana_mod
        orig_send = cetana_mod._send_heartbeat
        cetana_mod._send_heartbeat = lambda: False
        try:
            beat_once(state)
            assert state.interval_s < original  # should decrease on failure
            assert state.interval_s >= MIN_INTERVAL_S
            assert state.errors == 1
        finally:
            cetana_mod._send_heartbeat = orig_send

    def test_daemon_start_stop(self):
        from mahaclaw.cetana import CetanaDaemon

        d = CetanaDaemon(interval_s=3600)  # long interval so it doesn't actually beat
        assert d.running is False

        assert d.start() is True
        assert d.running is True
        assert d.start() is False  # already running

        assert d.stop() is True
        assert d.running is False
        assert d.stop() is False  # already stopped

    def test_state_fields_anauralia(self):
        from mahaclaw.cetana import HeartbeatState
        for f in dataclasses.fields(HeartbeatState):
            assert f.name not in ("reason", "description", "message", "suggestion")

    def test_murali_phases_exist(self):
        from mahaclaw.cetana import MuraliPhase
        phases = {p.value for p in MuraliPhase}
        assert "measure" in phases
        assert "report" in phases
        assert "adapt" in phases
        assert "listen" in phases
        assert "integrate" in phases


# ---------------------------------------------------------------------------
# Cross-element anauralia: all new modules
# ---------------------------------------------------------------------------

class TestNewElementsAnauralia:
    """All 8 new element modules have NO forbidden str fields on dataclasses."""

    NEW_MODULES = [
        "mahaclaw.vedana",
        "mahaclaw.rasa",
        "mahaclaw.rasana",
        "mahaclaw.payu",
        "mahaclaw.ksetrajna",
        "mahaclaw.upastha",
        "mahaclaw.pada",
        "mahaclaw.cetana",
    ]

    FORBIDDEN = frozenset({
        "reason", "suggestion", "description", "message",
        "explanation", "summary", "guidance", "advice", "hint", "note",
    })

    def test_no_forbidden_fields_on_dataclasses(self):
        import importlib
        violations = []
        for mod_name in self.NEW_MODULES:
            mod = importlib.import_module(mod_name)
            for name in dir(mod):
                obj = getattr(mod, name)
                if isinstance(obj, type) and dataclasses.is_dataclass(obj):
                    if getattr(obj, "__module__", "") == mod_name:
                        for f in dataclasses.fields(obj):
                            if f.name in self.FORBIDDEN:
                                violations.append(f"{mod_name}.{obj.__name__}.{f.name}")
        assert violations == [], f"Anauralia violations: {violations}"
