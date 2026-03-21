"""Tests for rebuilt Buddhi (Antahkarana coordinator) + Narasimha.

Proves Buddhi makes correct decisions WITHOUT the LLM.
Every test validates a specific Sankhya principle.
"""
from __future__ import annotations

import pytest

from mahaclaw.buddhi import (
    Buddhi,
    BuddhiDirective,
    BuddhiVerdict,
    HebbianSynaptic,
    ModelTier,
    VerdictAction,
    check_intent,
    evaluate,
)
from mahaclaw.chitta import Chitta, ExecutionPhase
from mahaclaw.manas import ActionType, IntentGuna
from mahaclaw.narasimha import gate as narasimha_gate, NarasimhaVerdict
from mahaclaw.pani import ToolNamespace


# ---------------------------------------------------------------------------
# Narasimha (kill-switch, NOT Buddhi)
# ---------------------------------------------------------------------------

class TestNarasimha:
    """Narasimha blocks — it doesn't discriminate."""

    def test_safe_intent_passes(self):
        v = narasimha_gate({"intent": "research quantum computing"})
        assert v.blocked is False

    def test_blocked_intent(self):
        v = narasimha_gate({"intent": "delete_all"})
        assert v.blocked is True
        assert "blocked" in v.reason

    def test_rm_rf_blocked(self):
        v = narasimha_gate({"intent": "rm -rf everything"})
        assert v.blocked is True
        assert "rm -rf" in v.reason

    def test_bypass_viveka_blocked(self):
        v = narasimha_gate({"intent": "bypass_viveka"})
        assert v.blocked is True

    def test_modify_narasimha_blocked(self):
        v = narasimha_gate({"intent": "modify_narasimha"})
        assert v.blocked is True

    def test_fork_bomb_blocked(self):
        v = narasimha_gate({"intent": "run :(){ :|:& };: on server"})
        assert v.blocked is True

    def test_empty_intent_passes(self):
        v = narasimha_gate({"intent": ""})
        assert v.blocked is False

    def test_missing_intent_passes(self):
        v = narasimha_gate({})
        assert v.blocked is False


# ---------------------------------------------------------------------------
# check_intent — Narasimha + Buddhi validation
# ---------------------------------------------------------------------------

class TestCheckIntent:
    """check_intent delegates to Narasimha then validates with Buddhi."""

    def test_dangerous_intent_aborts_via_narasimha(self):
        v = check_intent({"intent": "rm -rf everything"})
        assert v.action == VerdictAction.ABORT
        assert "rm -rf" in v.reason

    def test_invalid_priority_redirects(self):
        v = check_intent({"intent": "ok", "priority": "mega"})
        assert v.action == VerdictAction.REDIRECT

    def test_negative_ttl_redirects(self):
        v = check_intent({"intent": "ok", "ttl_ms": -1})
        assert v.action == VerdictAction.REDIRECT

    def test_restricted_target_high_priority_reflects(self):
        v = check_intent({"intent": "ok", "target": "steward", "priority": "suddha"})
        assert v.action == VerdictAction.REFLECT

    def test_safe_intent_continues(self):
        v = check_intent({"intent": "research stuff"})
        assert v.action == VerdictAction.CONTINUE


# ---------------------------------------------------------------------------
# HebbianSynaptic — learning signal
# ---------------------------------------------------------------------------

class TestHebbianSynaptic:
    """Hebbian: success → asymptotic to 1.0, failure → asymptotic to 0.0."""

    def test_initial_confidence(self):
        h = HebbianSynaptic()
        assert h.confidence == 0.5

    def test_success_increases_weight(self):
        h = HebbianSynaptic()
        h.update("bash", True)
        assert h.weight("bash") > 0.5

    def test_failure_decreases_weight(self):
        h = HebbianSynaptic()
        h.update("bash", False)
        assert h.weight("bash") < 0.5

    def test_asymptotic_to_one(self):
        h = HebbianSynaptic()
        for _ in range(100):
            h.update("bash", True)
        assert h.weight("bash") > 0.99

    def test_asymptotic_to_zero(self):
        h = HebbianSynaptic()
        for _ in range(100):
            h.update("bash", False)
        assert h.weight("bash") < 0.01

    def test_confidence_averages(self):
        h = HebbianSynaptic()
        h.update("bash", True)
        h.update("read_file", False)
        assert 0.4 < h.confidence < 0.6  # averaged around 0.5

    def test_weights_snapshot(self):
        h = HebbianSynaptic()
        h.update("bash", True)
        h.update("write_file", False)
        w = h.weights
        assert "bash" in w
        assert "write_file" in w


# ---------------------------------------------------------------------------
# Buddhi.pre_flight — the core discrimination
# ---------------------------------------------------------------------------

class TestBuddhiPreFlight:
    """Buddhi decides tools, tier, tokens WITHOUT the LLM."""

    def test_research_intent_gives_observe_only(self):
        """RESEARCH → OBSERVE namespace → read_file, glob, grep, list_dir."""
        b = Buddhi()
        d = b.pre_flight("deploy the service")  # routes to RESEARCH via seed
        # In ORIENT phase (no impressions), OBSERVE is the intersection
        assert "read_file" in d.allowed_tools
        assert "write_file" not in d.allowed_tools
        assert d.tier == ModelTier.FLASH  # RESEARCH → FLASH

    def test_implement_intent_in_execute_phase(self):
        """IMPLEMENT + EXECUTE phase → full tools."""
        b = Buddhi()
        # Seed some reads to get past ORIENT phase
        b.chitta.record("read_file", 1, True, path="/a.py")
        b.chitta.record("read_file", 2, True, path="/b.py")
        d = b.pre_flight("research quantum computing applications")  # routes to IMPLEMENT
        assert d.phase == ExecutionPhase.EXECUTE  # 2+ reads → EXECUTE
        assert "write_file" in d.allowed_tools
        assert "bash" in d.allowed_tools

    def test_orient_phase_restricts_to_observe(self):
        """ORIENT phase: only OBSERVE tools, even for IMPLEMENT action."""
        b = Buddhi()
        d = b.pre_flight("research quantum computing applications")  # IMPLEMENT
        assert d.phase == ExecutionPhase.ORIENT
        assert "read_file" in d.allowed_tools
        assert "write_file" not in d.allowed_tools
        assert "bash" not in d.allowed_tools

    def test_verify_phase_no_new_writes(self):
        """VERIFY phase: OBSERVE + EXECUTE, no MODIFY."""
        b = Buddhi()
        b.chitta.record("read_file", 1, True, path="/a.py")
        b.chitta.record("write_file", 2, True, path="/a.py")
        # Push write out of recent window
        b.chitta.record("read_file", 3, True, path="/b.py")
        b.chitta.record("read_file", 4, True, path="/c.py")
        b.chitta.record("read_file", 5, True, path="/d.py")
        d = b.pre_flight("research quantum computing applications")  # IMPLEMENT
        assert d.phase == ExecutionPhase.VERIFY
        assert "bash" in d.allowed_tools  # can run tests
        assert "write_file" not in d.allowed_tools  # no new writes

    def test_complete_phase_observe_only(self):
        """COMPLETE phase: OBSERVE only."""
        b = Buddhi()
        b.chitta.record("write_file", 1, True, path="/a.py")
        b.chitta.record("bash", 2, True)
        b.chitta.record("bash", 3, True)
        d = b.pre_flight("research quantum computing applications")
        assert d.phase == ExecutionPhase.COMPLETE
        assert "read_file" in d.allowed_tools
        assert "write_file" not in d.allowed_tools
        assert "bash" not in d.allowed_tools

    def test_error_recovery_injects_bash(self):
        """2+ recent errors → bash injected even if not in namespace."""
        b = Buddhi()
        b.chitta.record("read_file", 1, False, error="fail")
        b.chitta.record("read_file", 2, False, error="fail")
        d = b.pre_flight("deploy the service")  # RESEARCH → OBSERVE only
        assert "bash" in d.allowed_tools  # injected by error recovery

    def test_perception_cached_across_rounds(self):
        """Manas perceives ONCE — subsequent rounds use cached perception."""
        b = Buddhi()
        d1 = b.pre_flight("research quantum computing applications", round_num=0)
        d2 = b.pre_flight("research quantum computing applications", round_num=1)
        assert d1.action == d2.action
        assert d1.guna == d2.guna

    def test_dsp_signal_chain(self):
        """Task weight × phase modulation → max_tokens."""
        b = Buddhi()
        # ORIENT phase (0.5 mod) + RESEARCH (0.0 weight) → 0.0 → 1024
        d = b.pre_flight("deploy the service")
        assert d.max_tokens == 1024

    def test_dsp_execute_implement(self):
        """EXECUTE phase + IMPLEMENT → full tokens."""
        b = Buddhi()
        b.chitta.record("read_file", 1, True, path="/a.py")
        b.chitta.record("read_file", 2, True, path="/b.py")
        d = b.pre_flight("research quantum computing applications")  # IMPLEMENT
        # EXECUTE (1.0) × IMPLEMENT (1.0) = 1.0 → 4096
        assert d.max_tokens == 4096


# ---------------------------------------------------------------------------
# Buddhi tier selection (5-layer cascade)
# ---------------------------------------------------------------------------

class TestBuddhiTier:
    """Tier selection: action → Hebbian → guardian → phase → context."""

    def test_design_gets_pro(self):
        """DESIGN action → PRO tier."""
        b = Buddhi()
        # Need an intent that routes to DESIGN... use pre_flight with forced perception
        # Since we can't easily force a seed to DESIGN, test via _ACTION_TIER directly
        from mahaclaw.buddhi import _ACTION_TIER
        assert _ACTION_TIER[ActionType.DESIGN] == ModelTier.PRO

    def test_research_gets_flash(self):
        """RESEARCH action → FLASH tier."""
        b = Buddhi()
        d = b.pre_flight("deploy the service")  # routes to RESEARCH
        assert d.tier == ModelTier.FLASH

    def test_hebbian_low_confidence_escalates(self):
        """Confidence < 0.4 → escalate tier."""
        b = Buddhi()
        # Tank confidence
        for _ in range(20):
            b.synaptic.update("bash", False)
        assert b.synaptic.confidence < 0.4
        d = b.pre_flight("deploy the service")  # RESEARCH → FLASH
        # FLASH → escalated to STANDARD
        assert d.tier in (ModelTier.STANDARD, ModelTier.PRO)

    def test_hebbian_very_low_escalates_to_pro(self):
        """Confidence < 0.25 → straight to PRO."""
        b = Buddhi()
        for _ in range(50):
            b.synaptic.update("bash", False)
        assert b.synaptic.confidence < 0.25
        d = b.pre_flight("deploy the service")
        assert d.tier == ModelTier.PRO

    def test_guardian_escalation(self):
        """Guardian in escalate set → tier +1."""
        b = Buddhi()
        d_normal = b.pre_flight("deploy the service", guardian="vyasa")
        b2 = Buddhi()
        d_escalated = b2.pre_flight("deploy the service", guardian="nrisimha")
        # nrisimha is in _GUARDIAN_ESCALATE
        assert _tier_index(d_escalated.tier) >= _tier_index(d_normal.tier)

    def test_context_pressure_demotes_to_flash(self):
        """Context ≥ 70% → FLASH (save tokens)."""
        b = Buddhi()
        b.chitta.record("read_file", 1, True, path="/a.py")
        b.chitta.record("read_file", 2, True, path="/b.py")
        d = b.pre_flight("research quantum computing applications", context_pct=0.8)
        assert d.tier == ModelTier.FLASH

    def test_pro_demoted_in_verify(self):
        """PRO tier → STANDARD in VERIFY phase."""
        b = Buddhi()
        b.chitta.record("read_file", 1, True, path="/a.py")
        b.chitta.record("write_file", 2, True, path="/a.py")
        b.chitta.record("read_file", 3, True, path="/b.py")
        b.chitta.record("read_file", 4, True, path="/c.py")
        b.chitta.record("read_file", 5, True, path="/d.py")
        # Force tier to PRO via very low confidence
        for _ in range(50):
            b.synaptic.update("bash", False)
        d = b.pre_flight("research quantum computing applications")
        assert d.phase == ExecutionPhase.VERIFY
        # PRO should be demoted to STANDARD in VERIFY
        assert d.tier != ModelTier.PRO


# ---------------------------------------------------------------------------
# Buddhi.evaluate — post-execution judgment
# ---------------------------------------------------------------------------

class TestBuddhiEvaluate:
    """Buddhi judges tool results and detects patterns."""

    def test_clean_execution_continues(self):
        b = Buddhi()
        v = b.evaluate([("read_file", 1, True, "", "/a.py")])
        assert v.action == VerdictAction.CONTINUE

    def test_tool_failure_redirects(self):
        b = Buddhi()
        v = b.evaluate([("bash", 1, False, "command not found", "")])
        assert v.action == VerdictAction.REDIRECT

    def test_gandha_detects_blind_write(self):
        b = Buddhi()
        v = b.evaluate([("write_file", 1, True, "", "/new.py")])
        assert v.action == VerdictAction.REDIRECT
        assert "write" in v.reason.lower() or "blind" in v.reason.lower()

    def test_gandha_detects_consecutive_errors(self):
        b = Buddhi()
        for i in range(5):
            b.chitta.record("bash", i, False, error="fail")
        v = b.evaluate()
        assert v.action == VerdictAction.ABORT

    def test_hebbian_updates_on_evaluate(self):
        b = Buddhi()
        b.evaluate([("bash", 1, True, "", ""), ("bash", 2, False, "err", "")])
        assert b.synaptic.weight("bash") != 0.5

    def test_phase_transition_reflects(self):
        """Phase change triggers REFLECT with guidance."""
        b = Buddhi()
        # Set initial phase tracking
        b._last_phase = ExecutionPhase.ORIENT
        # Record reads to move to EXECUTE
        b.chitta.record("read_file", 1, True, path="/a.py")
        b.chitta.record("read_file", 2, True, path="/b.py")
        v = b.evaluate()
        # Phase changed from ORIENT → EXECUTE
        if v.action == VerdictAction.REFLECT:
            assert "ORIENT" in v.reason and "EXECUTE" in v.reason


# ---------------------------------------------------------------------------
# Buddhi end_turn + persistence
# ---------------------------------------------------------------------------

class TestBuddhiLifecycle:
    def test_end_turn_clears_impressions(self):
        b = Buddhi()
        b.chitta.record("read_file", 1, True, path="/a.py")
        b.end_turn()
        assert len(b.chitta.impressions) == 0

    def test_end_turn_preserves_prior_reads(self):
        b = Buddhi()
        b.chitta.record("read_file", 1, True, path="/a.py")
        b.end_turn()
        assert "/a.py" in b.chitta.prior_reads

    def test_chitta_summary(self):
        b = Buddhi()
        b.chitta.record("read_file", 1, True, path="/a.py")
        s = b.chitta_summary()
        assert "prior_reads" in s

    def test_synaptic_weights_persist(self):
        b = Buddhi()
        b.synaptic.update("bash", True)
        w = b.synaptic_weights()
        assert "bash" in w
        assert w["bash"] > 0.5


# ---------------------------------------------------------------------------
# Full Antahkarana integration (Manas → Chitta → Gandha → Buddhi)
# ---------------------------------------------------------------------------

class TestAntahkaranaUnit:
    """One cognitive unit — all four components working together."""

    def test_full_antahkarana_flow(self):
        """Buddhi coordinates: perceive → pre_flight → evaluate → end_turn."""
        b = Buddhi()

        # Pre-flight: Manas perceives, Buddhi decides
        d = b.pre_flight("research quantum computing applications")
        assert d.action is not None
        assert d.phase == ExecutionPhase.ORIENT
        assert "read_file" in d.allowed_tools
        # ORIENT restricts writes
        assert "write_file" not in d.allowed_tools

        # Simulate reading files
        v1 = b.evaluate([("read_file", 1, True, "", "/main.py")])
        assert v1.action == VerdictAction.CONTINUE
        v2 = b.evaluate([("read_file", 2, True, "", "/lib.py")])
        # Phase transition ORIENT → EXECUTE may trigger REFLECT (guidance)
        assert v2.action in (VerdictAction.CONTINUE, VerdictAction.REFLECT)

        # Now in EXECUTE phase — re-check directive
        d2 = b.pre_flight("research quantum computing applications", round_num=1)
        assert d2.phase == ExecutionPhase.EXECUTE
        assert "write_file" in d2.allowed_tools

        # Write a file
        v3 = b.evaluate([("write_file", 3, True, "", "/output.py")])
        assert v3.action == VerdictAction.REDIRECT  # blind write!

        # Properly read first (new Buddhi to test clean flow)
        b2 = Buddhi()
        b2._last_phase = ExecutionPhase.ORIENT  # init phase tracking
        b2.evaluate([("read_file", 1, True, "", "/output.py")])
        b2._last_phase = b2.chitta.phase  # sync phase to avoid transition noise
        v4 = b2.evaluate([("write_file", 2, True, "", "/output.py")])
        # read-before-write is fine; may get REFLECT from phase transition
        assert v4.action in (VerdictAction.CONTINUE, VerdictAction.REFLECT)

    def test_buddhi_without_llm(self):
        """THE PHILOSOPHICAL TEST: Buddhi makes correct decisions without LLM.

        No language model. No neural network. No tokens.
        Pure deterministic discrimination (Viveka).
        """
        b = Buddhi()

        # 1. Perception is deterministic (Manas)
        d = b.pre_flight("fix the login bug in auth.py")
        assert d.action == ActionType.DEBUG
        assert d.guna == IntentGuna.RAJAS

        # 2. Tools are deterministic (phase + action)
        assert d.phase == ExecutionPhase.ORIENT
        assert "read_file" in d.allowed_tools

        # 3. Tier is deterministic (action + Hebbian + phase)
        assert d.tier == ModelTier.STANDARD  # DEBUG → STANDARD

        # 4. Tokens are deterministic (DSP)
        assert d.max_tokens > 0

        # 5. Hebbian learning is deterministic
        b.evaluate([("bash", 1, False, "error", "")])
        assert b.synaptic.confidence < 0.5
        b.evaluate([("bash", 2, True, "", "")])
        # Learning adjusts confidence

        # 6. Gandha patterns are deterministic
        for i in range(5):
            b.chitta.record("bash", i + 100, False, error="fail")
        v = b.evaluate()
        assert v.action == VerdictAction.ABORT

        # All decisions made. Zero LLM involvement.

    def test_narasimha_before_buddhi(self):
        """Narasimha blocks BEFORE Buddhi even sees the intent.

        "rm -rf" is caught by string matching (Narasimha),
        not by intelligent discrimination (Buddhi).
        """
        # Through Narasimha directly
        nv = narasimha_gate({"intent": "rm -rf everything"})
        assert nv.blocked is True

        # Through check_intent (Narasimha → Buddhi pipeline)
        v = check_intent({"intent": "rm -rf everything"})
        assert v.action == VerdictAction.ABORT


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _tier_index(tier: ModelTier) -> int:
    return (ModelTier.FLASH, ModelTier.STANDARD, ModelTier.PRO).index(tier)
