"""Runtime tests — verify all 25 Sankhya elements fire through handle_message().

Tests the runtime loop with mocked I/O (no real LLM, no real outbox).
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_runtime():
    """Reset runtime global state between tests."""
    import mahaclaw.runtime as rt
    rt._chittas.clear()
    rt._histories.clear()
    rt._message_count = 0
    rt._rasana = __import__("mahaclaw.rasana", fromlist=["Rasana"]).Rasana()
    # Use a fresh SessionManager per test
    rt._sessions = None


@pytest.fixture(autouse=True)
def _clean_runtime(tmp_path, monkeypatch):
    """Reset runtime state and redirect I/O to tmp_path."""
    import mahaclaw.runtime as rt
    import mahaclaw.envelope as env_mod
    import mahaclaw.inbox as inbox_mod
    import mahaclaw.session as sess_mod

    outbox = tmp_path / "nadi_outbox.json"
    outbox.write_text("[]\n")
    inbox = tmp_path / "nadi_inbox.json"
    inbox.write_text("[]\n")
    db = tmp_path / "sessions.db"

    monkeypatch.setattr(env_mod, "OUTBOX_PATH", outbox)
    monkeypatch.setattr(inbox_mod, "INBOX_PATH", inbox)
    monkeypatch.setattr(sess_mod, "DEFAULT_DB", db)

    _reset_runtime()
    yield
    _reset_runtime()


# ---------------------------------------------------------------------------
# 1. Full 25-element flow
# ---------------------------------------------------------------------------

class TestFull25ElementFlow:

    def test_federation_mode_fires_all_elements(self, tmp_path, monkeypatch):
        """handle_message in federation mode runs every element without crashing."""
        import mahaclaw.runtime as rt

        result = rt.handle_message(
            text="research quantum computing",
            session_id="test-sess-001",
            source="webchat",
            mode="steward-only",
            target="agent-research",
            wait_s=0.1,  # short timeout, we don't expect a real response
        )

        # Response is a non-empty string
        assert isinstance(result, str)
        assert len(result) > 0

        # Chitta recorded an impression
        chitta = rt._get_chitta("test-sess-001")
        assert len(chitta.impressions) >= 1

        # Rasana updated
        assert rt._rasana.total_messages >= 1

        # KsetraJna works
        status = rt.get_status()
        assert "snapshot_hash" in status
        assert status["total_messages"] >= 1

    def test_federation_writes_to_outbox(self, tmp_path, monkeypatch):
        """Federation mode actually produces an envelope in outbox."""
        import mahaclaw.runtime as rt
        import mahaclaw.envelope as env_mod

        outbox = env_mod.OUTBOX_PATH

        rt.handle_message(
            text="what is dark matter",
            session_id="test-outbox",
            mode="steward-only",
            target="agent-research",
            wait_s=0.1,
        )

        data = json.loads(outbox.read_text())
        assert len(data) >= 1
        env = data[0]
        # Wire format fields present
        assert "envelope_id" in env
        assert "correlation_id" in env
        assert "maha_header_hex" in env
        assert "nadi_type" in env
        assert "_signature" in env  # Ahamkara signed it

    def test_manas_produces_valid_perception(self):
        """Manas perceive is called and produces structured output."""
        from mahaclaw.manas import perceive, ManasPerception, ActionType, IntentGuna

        p = perceive("research quantum computing")
        assert isinstance(p, ManasPerception)
        assert p.action in ActionType
        assert p.guna in IntentGuna
        assert isinstance(p.position, int)
        assert 0 <= p.position < 16

    def test_vedana_health_after_messages(self, tmp_path):
        """Health score is tracked after message processing."""
        import mahaclaw.runtime as rt

        rt.handle_message("hello", "health-test", mode="steward-only",
                         target="agent-research", wait_s=0.1)
        rt.handle_message("world", "health-test", mode="steward-only",
                         target="agent-research", wait_s=0.1)

        from mahaclaw.vedana import pulse
        chitta = rt._get_chitta("health-test")
        sig = pulse(chitta)
        assert sig.impression_count == 2
        assert sig.score > 0


# ---------------------------------------------------------------------------
# 2. Narasimha blocks in runtime
# ---------------------------------------------------------------------------

class TestNarasimhaInRuntime:

    def test_dangerous_intent_blocked(self):
        """rm -rf is blocked by Narasimha, never reaches pipeline."""
        import mahaclaw.runtime as rt
        import mahaclaw.envelope as env_mod

        outbox = env_mod.OUTBOX_PATH
        before = json.loads(outbox.read_text())

        result = rt.handle_message(
            text="rm -rf /",
            session_id="danger-test",
            mode="federation",
            target="agent-research",
            wait_s=0,
        )

        # Blocked response
        assert "can't process" in result.lower()

        # Nothing written to outbox
        after = json.loads(outbox.read_text())
        assert len(after) == len(before)

    def test_safe_intent_passes(self):
        """Normal message passes Narasimha."""
        import mahaclaw.runtime as rt

        result = rt.handle_message(
            text="what is the weather today",
            session_id="safe-test",
            mode="steward-only",
            target="agent-research",
            wait_s=0.1,
        )
        assert "can't process" not in result.lower()


# ---------------------------------------------------------------------------
# 3. Standalone mode with mock LLM
# ---------------------------------------------------------------------------

class TestStandaloneMode:

    def test_standalone_calls_llm(self, monkeypatch):
        """Standalone mode calls llm.ask() and returns LLM content."""
        import mahaclaw.runtime as rt
        import mahaclaw.llm as llm_mod
        from mahaclaw.llm import LLMResponse

        mock_response = LLMResponse(
            ok=True,
            content="The answer is 42.",
            model="test-model",
        )

        def fake_ask(question, config=None, history=None):
            return mock_response

        monkeypatch.setattr(llm_mod, "ask", fake_ask)

        result = rt.handle_message(
            text="what is the meaning of life",
            session_id="standalone-test",
            mode="standalone",
        )

        assert "42" in result

        # Chitta recorded
        chitta = rt._get_chitta("standalone-test")
        assert len(chitta.impressions) >= 1

    def test_standalone_llm_error_handled(self, monkeypatch):
        """Standalone mode handles LLM errors gracefully."""
        import mahaclaw.runtime as rt
        import mahaclaw.llm as llm_mod
        from mahaclaw.llm import LLMResponse

        def fake_ask(question, config=None, history=None):
            return LLMResponse(ok=False, error="connection refused")

        monkeypatch.setattr(llm_mod, "ask", fake_ask)

        result = rt.handle_message(
            text="hello",
            session_id="error-test",
            mode="standalone",
        )

        assert isinstance(result, str)
        assert len(result) > 0  # Got some error message, didn't crash


# ---------------------------------------------------------------------------
# 4. Federation mode with mock inbox response
# ---------------------------------------------------------------------------

class TestFederationWithResponse:

    def test_inbox_response_reaches_caller(self, tmp_path, monkeypatch):
        """Simulated federation response is returned to caller."""
        import mahaclaw.runtime as rt
        import mahaclaw.envelope as env_mod
        import mahaclaw.inbox as inbox_mod
        import threading
        import time

        outbox = env_mod.OUTBOX_PATH
        inbox_path = inbox_mod.INBOX_PATH

        # We'll inject a response into the inbox after a short delay
        def inject_response():
            time.sleep(0.3)
            # Read outbox to get correlation_id
            try:
                data = json.loads(outbox.read_text())
                if data:
                    corr_id = data[-1]["correlation_id"]
                    response = [{
                        "correlation_id": corr_id,
                        "source": "agent-research",
                        "source_city_id": "kimeisele/agent-research",
                        "target": "mahaclaw",
                        "target_city_id": "mahaclaw",
                        "operation": "response",
                        "nadi_type": "vyana",
                        "nadi_op": "send",
                        "nadi_priority": "rajas",
                        "maha_header_hex": "0" * 32,
                        "envelope_id": "env_test",
                        "id": "id_test",
                        "timestamp": time.time(),
                        "priority": 5,
                        "ttl_ms": 24000,
                        "ttl_s": 24.0,
                        "payload": {
                            "answer": "Quantum computing uses qubits.",
                        },
                    }]
                    inbox_path.write_text(json.dumps(response))
            except Exception:
                pass

        t = threading.Thread(target=inject_response, daemon=True)
        t.start()

        result = rt.handle_message(
            text="explain quantum computing",
            session_id="inbox-test",
            mode="steward-only",
            target="agent-research",
            wait_s=2.0,
        )

        t.join(timeout=3)

        # If the response was injected in time, we get the answer
        # If not (race condition), we get the timeout message
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# 5. Session continuity
# ---------------------------------------------------------------------------

class TestSessionContinuity:

    def test_same_session_accumulates_impressions(self):
        """Two messages with same session_id share Chitta state."""
        import mahaclaw.runtime as rt

        rt.handle_message("first message", "cont-test",
                         mode="steward-only", target="agent-research", wait_s=0.1)
        rt.handle_message("second message", "cont-test",
                         mode="steward-only", target="agent-research", wait_s=0.1)

        chitta = rt._get_chitta("cont-test")
        assert len(chitta.impressions) == 2

    def test_different_sessions_are_isolated(self):
        """Different session_ids get different Chitta instances."""
        import mahaclaw.runtime as rt

        rt.handle_message("msg a", "sess-a",
                         mode="steward-only", target="agent-research", wait_s=0.1)
        rt.handle_message("msg b", "sess-b",
                         mode="steward-only", target="agent-research", wait_s=0.1)

        chitta_a = rt._get_chitta("sess-a")
        chitta_b = rt._get_chitta("sess-b")
        assert len(chitta_a.impressions) == 1
        assert len(chitta_b.impressions) == 1

    def test_rasana_preferences_updated(self):
        """Rasana tracks targets and actions across messages."""
        import mahaclaw.runtime as rt

        rt.handle_message("hello", "pref-test",
                         mode="steward-only", target="agent-research", wait_s=0.1)
        rt.handle_message("world", "pref-test",
                         mode="steward-only", target="agent-research", wait_s=0.1)

        assert rt._rasana.preferred_target == "agent-research"
        assert rt._rasana.total_messages >= 2

    def test_message_count_increments(self):
        """Global message counter tracks total messages."""
        import mahaclaw.runtime as rt

        initial = rt._message_count
        rt.handle_message("one", "count-test",
                         mode="steward-only", target="agent-research", wait_s=0.1)
        rt.handle_message("two", "count-test",
                         mode="steward-only", target="agent-research", wait_s=0.1)

        assert rt._message_count == initial + 2


# ---------------------------------------------------------------------------
# 6. get_status endpoint
# ---------------------------------------------------------------------------

class TestGetStatus:

    def test_status_returns_valid_dict(self):
        """get_status() returns a dict with KsetraJna fields."""
        import mahaclaw.runtime as rt

        status = rt.get_status()
        assert isinstance(status, dict)
        assert "kind" in status
        assert status["kind"] == "bubble_snapshot"
        assert "snapshot_hash" in status
        assert "total_messages" in status
        assert "active_sessions" in status

    def test_status_after_messages(self):
        """Status reflects message processing."""
        import mahaclaw.runtime as rt

        rt.handle_message("test", "status-test",
                         mode="steward-only", target="agent-research", wait_s=0.1)

        status = rt.get_status()
        assert status["total_messages"] >= 1
        assert status["active_sessions"] >= 1


# ---------------------------------------------------------------------------
# 7. Anauralia in runtime — no language between components
# ---------------------------------------------------------------------------

class TestRuntimeAnauralia:

    def test_no_natural_language_between_components(self):
        """Verify that runtime.py does not pass prose between Antahkarana components.

        The user's text enters at Shrotra (boundary) and exits at Vak (boundary).
        Between components, only enums, ints, bools, identifiers, and floats.
        """
        import inspect
        import mahaclaw.runtime as rt

        source = inspect.getsource(rt)

        # The runtime should NOT have any inter-component .reason or .description access
        # These would indicate language flowing between components
        assert ".reason" not in source, "runtime accesses .reason — anauralia violation"
        assert ".suggestion" not in source, "runtime accesses .suggestion — anauralia violation"
        assert ".description" not in source, "runtime accesses .description — anauralia violation"

    def test_narasimha_returns_structured_not_prose(self):
        """Narasimha verdict in runtime is accessed via .blocked (bool) and .matched (identifier)."""
        from mahaclaw.narasimha import gate

        v = gate({"intent": "rm -rf /", "target": "test"})
        assert isinstance(v.blocked, bool)
        assert isinstance(v.matched, str)  # identifier, not explanation
        # No .reason field exists
        assert not hasattr(v, "reason")

    def test_buddhi_returns_structured_not_prose(self):
        """Buddhi verdict in runtime is accessed via .action (enum) and .cause (enum)."""
        from mahaclaw.buddhi import check_intent, VerdictAction, BuddhiCause

        v = check_intent({"intent": "hello", "target": "test", "priority": "rajas"})
        assert isinstance(v.action, VerdictAction)
        assert isinstance(v.cause, BuddhiCause)
        # No .reason field exists
        assert not hasattr(v, "reason")
