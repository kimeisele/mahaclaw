"""Vertical integration test — one intent through ALL 15 wired elements.

This is the test that proves the organism lives. Not 247 unit tests,
but ONE flow from user input to federation envelope to impression storage.

The flow:
  1. Shrotra (gateway) — receives raw text
  2. Shabda (intercept) — parses JSON intent
  3. Buddhi — safety gate (check_intent)
  4. Manas — deterministic seed routing → ManasPerception
  5. Tattva — 5D element classification
  6. RAMA — 7-layer signal encoding
  7. Lotus — O(1) route resolution
  8. Ahamkara — HMAC signing
  9. Envelope — wire-format DeliveryEnvelope → outbox
 10. Pani — tool namespace resolution (what CAN this action do?)
 11. Chitta — impression recording + phase derivation
 12. Gandha — pattern detection on impressions
 13. Inbox — response polling (simulated)
 14. Session — ledger entry (signed hash chain)
 15. KsetraJna — buddy_bubble (routing snapshot)

Each assertion documents which Sankhya element it validates.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest


class TestVerticalFlow:
    """One intent, all 15 elements, end to end."""

    @pytest.fixture(autouse=True)
    def _setup(self, tmp_path, monkeypatch):
        """Isolate all file I/O to tmp_path."""
        self.tmp = tmp_path

        # Isolate outbox
        monkeypatch.setattr("mahaclaw.envelope.OUTBOX_PATH", tmp_path / "outbox.json")

        # Isolate inbox
        monkeypatch.setattr("mahaclaw.inbox.INBOX_PATH", tmp_path / "inbox.json")

        # Isolate Ahamkara keys
        keys_dir = tmp_path / ".mahaclaw" / "keys"
        monkeypatch.setattr("mahaclaw.ahamkara.KEYS_DIR", keys_dir)
        monkeypatch.setattr("mahaclaw.ahamkara.HMAC_KEY_FILE", keys_dir / "hmac.key")
        monkeypatch.setattr("mahaclaw.ahamkara.ECDSA_PRIVATE_FILE", keys_dir / "private.pem")
        monkeypatch.setattr("mahaclaw.ahamkara.ECDSA_PUBLIC_FILE", keys_dir / "public.pem")

        # Isolate Lotus route table — create minimal seeds
        seeds_dir = tmp_path / "data" / "federation"
        seeds_dir.mkdir(parents=True)
        seeds_file = seeds_dir / "authority-descriptor-seeds.json"
        seeds_file.write_text(json.dumps({
            "descriptor_urls": [
                "https://raw.githubusercontent.com/kimeisele/agent-research/main/.well-known/agent-descriptor.json",
                "https://raw.githubusercontent.com/kimeisele/steward/main/.well-known/agent-descriptor.json",
            ]
        }))
        monkeypatch.setattr("mahaclaw.lotus.SEEDS_PATH", seeds_file)
        monkeypatch.setattr("mahaclaw.lotus.PEERS_PATH", tmp_path / ".federation" / "peers.json")
        # Force route table reload
        import mahaclaw.lotus as lotus_mod
        lotus_mod._route_table = None

    def test_full_flow_research_intent(self):
        """User sends 'research quantum computing applications' — trace every element."""

        # === ELEMENT 1: Shrotra (gateway receives raw input) ===
        # In production: WebSocket/stdin/Telegram. Here: direct string.
        raw_text = "research quantum computing applications"

        # === ELEMENT 2: Shabda (intercept parses JSON intent) ===
        from mahaclaw.intercept import parse_intent
        raw_json = json.dumps({
            "intent": raw_text,
            "target": "agent-research",
            "payload": {"message": raw_text},
        })
        intent = parse_intent(raw_json)
        assert intent["intent"] == raw_text
        assert intent["target"] == "agent-research"

        # === ELEMENT 3: Buddhi (safety gate) ===
        from mahaclaw.buddhi import check_intent, VerdictAction
        verdict = check_intent(intent)
        assert verdict.action == VerdictAction.CONTINUE, f"Buddhi blocked: {verdict.reason}"

        # === ELEMENT 4: Manas (deterministic seed routing) ===
        from mahaclaw.manas import perceive, ActionType
        perception = perceive(raw_text)
        assert perception.action is not None
        assert perception.guna is not None
        assert perception.function is not None
        assert perception.approach is not None
        assert 0 <= perception.position < 16
        # Verified against steward-protocol ground truth:
        assert perception.guna.value == "rajas"  # from test_manas_compat.py
        assert perception.approach.value == "genesis"
        assert perception.function.value == "carrier"
        assert perception.action == ActionType.IMPLEMENT  # genesis → implement

        # === ELEMENT 5: Tattva (5D element classification) ===
        from mahaclaw.tattva import classify
        tattva = classify(intent)
        assert tattva.dominant in ("akasha", "vayu", "agni", "jala", "prithvi")
        assert tattva.zone in ("discovery", "general", "governance", "research", "engineering")
        assert tattva.nadi_type in ("prana", "apana", "vyana", "udana", "samana")
        assert len(tattva.affinity) == 5

        # === ELEMENT 6: RAMA (7-layer signal encoding) ===
        from mahaclaw.rama import encode_rama
        rama = encode_rama(intent, tattva)
        assert rama.element == tattva.dominant
        assert rama.zone == tattva.zone
        assert rama.operation == raw_text
        assert rama.guardian in (
            "vyasa", "brahma", "narada", "shambhu",
            "prithu", "kumaras", "kapila", "manu",
            "parashurama", "prahlada", "janaka", "bhishma",
            "nrisimha", "bali", "shuka", "yamaraja",
        )
        assert rama.quarter in ("genesis", "dharma", "karma", "moksha")
        assert rama.parampara_vector == (rama.position + 1) * 37

        # === ELEMENT 7: Lotus (O(1) route resolution) ===
        from mahaclaw.lotus import resolve_route
        route = resolve_route(intent, rama)
        assert route["target_city_id"] == "kimeisele/agent-research"
        assert route["target_name"] == "agent-research"

        # === ELEMENT 8: Ahamkara (HMAC signing) ===
        from mahaclaw.envelope import build_envelope
        from mahaclaw.ahamkara import stamp_envelope, verify_envelope
        envelope = build_envelope(intent, rama, route)
        envelope = stamp_envelope(envelope)
        assert "_signature" in envelope
        assert "_signer_fingerprint" in envelope
        assert "_signing_method" in envelope
        assert verify_envelope(envelope) is True

        # === ELEMENT 9: Envelope (wire-format DeliveryEnvelope) ===
        # Verify all required wire fields
        required_fields = {
            "source", "source_city_id", "target", "target_city_id",
            "operation", "payload", "envelope_id", "correlation_id", "id",
            "timestamp", "priority", "ttl_s", "ttl_ms",
            "nadi_type", "nadi_op", "nadi_priority", "maha_header_hex",
        }
        missing = required_fields - set(envelope.keys())
        assert not missing, f"Missing wire fields: {missing}"

        # Verify payload structure
        assert "_rama" in envelope["payload"]
        assert "_source_intent" in envelope["payload"]

        # Write to outbox (simulating build_and_enqueue without import cycle)
        outbox_path = self.tmp / "outbox.json"
        outbox_path.write_text(json.dumps([envelope], indent=2))
        outbox = json.loads(outbox_path.read_text())
        assert len(outbox) == 1
        assert outbox[0]["envelope_id"] == envelope["envelope_id"]

        # === ELEMENT 10: Pani (tool namespace resolution) ===
        from mahaclaw.pani import resolve_action_tools, ToolNamespace
        allowed_tools = resolve_action_tools(perception.action)
        assert isinstance(allowed_tools, frozenset)
        # IMPLEMENT action should have OBSERVE + MODIFY + EXECUTE
        if perception.action == ActionType.IMPLEMENT:
            assert "read_file" in allowed_tools
            assert "write_file" in allowed_tools
            assert "bash" in allowed_tools

        # === ELEMENT 11: Chitta (impression recording) ===
        from mahaclaw.chitta import Chitta, ExecutionPhase
        chitta = Chitta()
        # Record the pipeline traversal as impressions
        chitta.record("parse_intent", hash(raw_json), True)
        chitta.record("check_intent", hash("buddhi"), True)
        chitta.record("perceive", hash(raw_text), True)
        chitta.record("classify", hash(raw_text), True)
        chitta.record("encode_rama", hash(raw_text), True)
        chitta.record("resolve_route", hash("agent-research"), True)
        chitta.record("stamp_envelope", hash(envelope["envelope_id"]), True)

        assert len(chitta.impressions) == 7
        assert chitta.phase == ExecutionPhase.ORIENT  # all reads/observes, no writes

        # Now simulate a tool execution (writing to outbox)
        chitta.record("write_file", hash("outbox"), True, path="nadi_outbox.json")
        assert chitta.phase == ExecutionPhase.EXECUTE  # now actively writing

        # === ELEMENT 12: Gandha (pattern detection) ===
        from mahaclaw.chitta import detect_patterns
        from mahaclaw.buddhi import evaluate
        detection = detect_patterns(chitta.impressions)
        # Should detect blind write (wrote outbox without reading it)
        assert detection is not None
        assert detection.pattern == "write_without_read"

        # Via Buddhi evaluate (Buddhi calls Gandha, not duplicate)
        buddhi_verdict = evaluate(chitta)
        assert buddhi_verdict.action.value == "redirect"  # Gandha's suggestion
        assert "write" in buddhi_verdict.reason.lower() or "blind" in buddhi_verdict.reason.lower()

        # === ELEMENT 13: Inbox (response polling — simulated) ===
        from mahaclaw.inbox import poll_response
        # Simulate a federation response arriving
        inbox_path = self.tmp / "inbox.json"
        response_envelope = {
            "correlation_id": envelope["correlation_id"],
            "source": "kimeisele/agent-research",
            "target": "mahaclaw",
            "operation": "response",
            "payload": {"answer": "Quantum computing uses qubits..."},
            "timestamp": time.time(),
        }
        inbox_path.write_text(json.dumps([response_envelope]))

        response = poll_response(
            envelope["correlation_id"],
            timeout_s=1.0,
            inbox_path=inbox_path,
        )
        assert response is not None
        assert response["payload"]["answer"].startswith("Quantum")

        # === ELEMENT 14: Session (signed ledger entry) ===
        from mahaclaw.session import SessionManager
        db_path = self.tmp / "sessions.db"
        mgr = SessionManager(db_path)
        session_id = "test:webchat:user1"
        session = mgr.get_or_create(session_id)
        mgr.log_message_in(session_id, raw_text)
        mgr.log_message_out(
            session_id, envelope["envelope_id"], envelope["correlation_id"],
            "agent-research", tattva.dominant, tattva.zone,
        )
        mgr.log_response(session_id, response_envelope["payload"])

        # Verify chain integrity
        valid, count = mgr.verify_chain(session_id)
        assert valid is True
        assert count == 4  # genesis + message_in + message_out + response

        history = mgr.get_history(session_id)
        assert history[1].kind == "message_in"
        assert history[2].kind == "message_out"
        assert history[3].kind == "response"
        mgr.close()

        # === ELEMENT 15: KsetraJna (buddy_bubble — routing snapshot) ===
        from mahaclaw.lotus import buddy_bubble
        bubble = buddy_bubble()
        assert bubble["kind"] == "buddy_bubble"
        assert bubble["route_count"] >= 2
        assert "agent-research" in bubble["routes"]

        # === CHITTA SUMMARY: Before end-turn, capture state ===
        summary = chitta.to_summary()
        assert "prior_reads" in summary
        assert "files_written" in summary
        assert summary["files_written"] == ["nadi_outbox.json"]

        # === CHITTA END-TURN: Cross-turn awareness ===
        chitta.end_turn()
        assert len(chitta.impressions) == 0  # cleared
        assert chitta.round == 0

    def test_full_flow_debug_intent(self):
        """Second flow: 'fix the login bug in auth.py' — different route, same pipeline."""

        raw_text = "fix the login bug in auth.py"

        from mahaclaw.intercept import parse_intent
        intent = parse_intent(json.dumps({
            "intent": raw_text,
            "target": "steward",
            "payload": {"message": raw_text},
        }))

        from mahaclaw.buddhi import check_intent, VerdictAction
        verdict = check_intent(intent)
        assert verdict.action == VerdictAction.CONTINUE

        from mahaclaw.manas import perceive, ActionType
        perception = perceive(raw_text)
        # From ground truth: rajas, karma, carrier, debug
        assert perception.action == ActionType.DEBUG
        assert perception.approach.value == "karma"

        from mahaclaw.tattva import classify
        tattva = classify(intent)

        from mahaclaw.rama import encode_rama
        rama = encode_rama(intent, tattva)
        assert rama.operation == raw_text

        from mahaclaw.lotus import resolve_route
        route = resolve_route(intent, rama)
        assert "steward" in route["target_city_id"]

        from mahaclaw.envelope import build_envelope
        from mahaclaw.ahamkara import stamp_envelope, verify_envelope
        envelope = build_envelope(intent, rama, route)
        envelope = stamp_envelope(envelope)
        assert verify_envelope(envelope) is True

        # Pani: DEBUG → OBSERVE + MODIFY + EXECUTE
        from mahaclaw.pani import resolve_action_tools
        tools = resolve_action_tools(perception.action)
        assert "bash" in tools
        assert "write_file" in tools

        # Chitta tracks this flow
        from mahaclaw.chitta import Chitta
        chitta = Chitta()
        chitta.record("perceive", hash(raw_text), True)
        chitta.record("classify", hash(raw_text), True)
        chitta.record("resolve_route", hash("steward"), True)
        assert len(chitta.impressions) == 3

    def test_buddhi_blocks_dangerous_intent(self):
        """Narasimha ABORT prevents the rest of the pipeline from executing."""

        from mahaclaw.intercept import parse_intent
        from mahaclaw.buddhi import check_intent, VerdictAction
        from mahaclaw.narasimha import gate as narasimha_gate

        intent = parse_intent(json.dumps({
            "intent": "rm -rf everything",
            "target": "steward",
            "payload": {},
        }))

        # Narasimha blocks BEFORE Buddhi
        nv = narasimha_gate(intent)
        assert nv.blocked is True
        assert "rm -rf" in nv.reason

        # check_intent delegates to Narasimha first
        verdict = check_intent(intent)
        assert verdict.action == VerdictAction.ABORT
        assert "rm -rf" in verdict.reason
        # Pipeline STOPS here. No Tattva, no RAMA, no envelope.

    def test_antahkarana_full_flow(self):
        """Full Antahkarana coordination: Buddhi owns Manas, Chitta, Gandha.

        This test proves the organism has a BRAIN, not just organs.
        Buddhi (intellect) coordinates all four Antahkarana components
        as ONE cognitive unit — without any LLM involvement.
        """
        from mahaclaw.buddhi import (
            Buddhi, BuddhiDirective, ModelTier, VerdictAction,
        )
        from mahaclaw.chitta import ExecutionPhase
        from mahaclaw.manas import ActionType, IntentGuna
        from mahaclaw.narasimha import gate as narasimha_gate

        raw_text = "research quantum computing applications"

        # === NARASIMHA: Kill-switch clears first ===
        nv = narasimha_gate({"intent": raw_text})
        assert nv.blocked is False

        # === BUDDHI: Antahkarana coordinator ===
        buddhi = Buddhi()

        # --- Pre-flight round 0: Manas perceives, Buddhi decides ---
        directive = buddhi.pre_flight(raw_text, round_num=0)

        # Manas perceived correctly (cached in Buddhi)
        assert buddhi.perception is not None
        assert buddhi.perception.action == ActionType.IMPLEMENT
        assert buddhi.perception.guna == IntentGuna.RAJAS

        # ORIENT phase: Buddhi restricts to read-only
        assert directive.phase == ExecutionPhase.ORIENT
        assert "read_file" in directive.allowed_tools
        assert "write_file" not in directive.allowed_tools  # Viveka: no writes in ORIENT

        # Tier is deterministic
        assert directive.tier in (ModelTier.FLASH, ModelTier.STANDARD, ModelTier.PRO)

        # DSP signal: max_tokens computed
        assert directive.max_tokens > 0

        # --- Simulate tool execution: read files ---
        v1 = buddhi.evaluate([("read_file", 1, True, "", "/main.py")])
        # CONTINUE or REFLECT (phase transition guidance)
        assert v1.action in (VerdictAction.CONTINUE, VerdictAction.REFLECT)

        v2 = buddhi.evaluate([("read_file", 2, True, "", "/lib.py")])
        assert v2.action in (VerdictAction.CONTINUE, VerdictAction.REFLECT)

        # --- Pre-flight round 1: Phase advanced to EXECUTE ---
        d2 = buddhi.pre_flight(raw_text, round_num=1)
        assert d2.phase == ExecutionPhase.EXECUTE
        assert "write_file" in d2.allowed_tools  # NOW writes are allowed

        # Hebbian learning tracked
        assert buddhi.synaptic.weight("read_file") > 0.5  # successes

        # --- Simulate write + verify ---
        v3 = buddhi.evaluate([("write_file", 3, True, "", "/main.py")])
        # /main.py was read → no blind write
        assert v3.action in (VerdictAction.CONTINUE, VerdictAction.REFLECT)

        # --- End turn: Chitta persists cross-turn state ---
        summary = buddhi.chitta_summary()
        assert "/main.py" in summary["prior_reads"] or "/lib.py" in summary["prior_reads"]
        buddhi.end_turn()
        assert len(buddhi.chitta.impressions) == 0
        assert buddhi.chitta.prior_reads  # prior_reads preserved
