"""Pani + Chitta compatibility tests — verified against steward patterns.

Pani (tool dispatch):
  - ToolResult schema matches vibe_core/tools/tool_protocol.py
  - ToolNamespace matches steward/buddhi.py
  - Action → Namespace resolution matches steward/buddhi.py
  - Gate check blocks tools outside allowed namespaces

Chitta (impression storage):
  - Impression schema matches steward/antahkarana/chitta.py
  - ExecutionPhase derivation matches steward/antahkarana/chitta.py
  - Cross-turn awareness (prior_reads, end_turn, was_file_read)
  - to_summary / load_summary round-trip
  - Gandha pattern detection matches steward/antahkarana/gandha.py
"""
from __future__ import annotations

import pytest

from mahaclaw.pani import (
    ToolResult,
    ToolUse,
    ToolNamespace,
    resolve_namespaces,
    resolve_action_tools,
    check_tool_gates,
    dispatch,
    params_hash,
    register_tool,
    unregister_tool,
    _ACTION_NAMESPACES,
    _NAMESPACE_TOOLS,
)
from mahaclaw.manas import ActionType
from mahaclaw.chitta import (
    Chitta,
    Impression,
    ExecutionPhase,
    Detection,
    VerdictAction,
    detect_patterns,
    MAX_IDENTICAL_CALLS,
    MAX_CONSECUTIVE_ERRORS,
    MAX_SAME_TOOL_STREAK,
    ERROR_RATIO_THRESHOLD,
)


# =============================================================================
# PANI — Tool Dispatch
# =============================================================================


class TestToolResult:
    """ToolResult schema must match steward's vibe_core/tools/tool_protocol.py."""

    def test_success_result(self):
        r = ToolResult(success=True, output="hello")
        assert r.success is True
        assert r.output == "hello"
        assert r.error is None
        assert r.metadata is None

    def test_error_result(self):
        r = ToolResult(success=False, error="not found")
        assert r.success is False
        assert r.error == "not found"
        assert r.output is None

    def test_metadata(self):
        r = ToolResult(success=True, output="ok", metadata={"duration_ms": 42.0})
        assert r.metadata["duration_ms"] == 42.0


class TestToolUse:
    """ToolUse schema must match steward/types.py."""

    def test_fields(self):
        tu = ToolUse(id="call_1", name="read_file", parameters={"path": "/tmp/x"})
        assert tu.id == "call_1"
        assert tu.name == "read_file"
        assert tu.parameters["path"] == "/tmp/x"


class TestToolNamespace:
    """ToolNamespace values must match steward/buddhi.py."""

    def test_values(self):
        assert ToolNamespace.OBSERVE == "observe"
        assert ToolNamespace.MODIFY == "modify"
        assert ToolNamespace.EXECUTE == "execute"
        assert ToolNamespace.DELEGATE == "delegate"

    def test_all_four(self):
        assert len(ToolNamespace) == 4


class TestNamespaceResolution:
    """Action → Namespace → Tool resolution must match steward/buddhi.py."""

    def test_research_is_observe_only(self):
        tools = resolve_action_tools(ActionType.RESEARCH)
        # OBSERVE tools only
        assert "read_file" in tools
        assert "write_file" not in tools
        assert "bash" not in tools

    def test_implement_has_all_three(self):
        tools = resolve_action_tools(ActionType.IMPLEMENT)
        assert "read_file" in tools
        assert "write_file" in tools
        assert "bash" in tools

    def test_debug_has_all_three(self):
        tools = resolve_action_tools(ActionType.DEBUG)
        assert "read_file" in tools
        assert "write_file" in tools
        assert "bash" in tools

    def test_review_is_observe_only(self):
        tools = resolve_action_tools(ActionType.REVIEW)
        assert "read_file" in tools
        assert "write_file" not in tools

    def test_test_has_observe_execute(self):
        tools = resolve_action_tools(ActionType.TEST)
        assert "read_file" in tools
        assert "bash" in tools
        assert "write_file" not in tools

    def test_all_actions_have_namespaces(self):
        """Every ActionType must have a namespace mapping."""
        for action in ActionType:
            assert action in _ACTION_NAMESPACES, f"Missing namespace for {action}"

    def test_resolve_empty(self):
        assert resolve_namespaces(frozenset()) == frozenset()


class TestRegisterUnregister:
    def test_register_and_unregister(self):
        register_tool(ToolNamespace.OBSERVE, "custom_search")
        assert "custom_search" in _NAMESPACE_TOOLS[ToolNamespace.OBSERVE]
        unregister_tool(ToolNamespace.OBSERVE, "custom_search")
        assert "custom_search" not in _NAMESPACE_TOOLS[ToolNamespace.OBSERVE]


class TestGateCheck:
    """Pre-execution gating must match steward/loop/tool_dispatch.py."""

    def test_allowed_tool_passes(self):
        tu = ToolUse(id="1", name="read_file", parameters={"path": "x"})
        allowed = frozenset({"read_file", "list_dir", "grep", "glob"})
        assert check_tool_gates(tu, allowed) is None

    def test_disallowed_tool_blocked(self):
        tu = ToolUse(id="1", name="bash", parameters={"command": "ls"})
        allowed = frozenset({"read_file"})
        error = check_tool_gates(tu, allowed)
        assert error is not None
        assert "not in allowed" in error

    def test_write_without_prior_read_passes_gate(self):
        """Gate doesn't hard-block writes — Gandha detects the pattern."""
        tu = ToolUse(id="1", name="write_file", parameters={"path": "new.txt", "content": "x"})
        allowed = frozenset({"read_file", "write_file", "bash"})
        assert check_tool_gates(tu, allowed) is None


class TestParamsHash:
    def test_deterministic(self):
        p = {"path": "/tmp/x", "content": "hello"}
        assert params_hash(p) == params_hash(p)

    def test_different_params(self):
        assert params_hash({"a": 1}) != params_hash({"b": 2})


class TestDispatch:
    """Full dispatch pipeline through sandbox."""

    def test_dispatch_read_file(self, tmp_path):
        from mahaclaw.tools.sandbox import ToolSandbox
        sandbox = ToolSandbox(workspace=tmp_path)
        (tmp_path / "test.txt").write_text("hello world")

        # Use an intent that routes to IMPLEMENT (has OBSERVE namespace)
        tu = ToolUse(id="1", name="read_file", parameters={"path": "test.txt"})
        result = dispatch("fix the login bug", tu, sandbox)
        assert result.success is True
        assert result.output == "hello world"

    def test_dispatch_bash(self, tmp_path):
        from mahaclaw.tools.sandbox import ToolSandbox
        sandbox = ToolSandbox(workspace=tmp_path)

        # "fix the login bug in auth.py" routes to DEBUG → OBSERVE+MODIFY+EXECUTE
        tu = ToolUse(id="1", name="bash", parameters={"command": "echo hi"})
        result = dispatch("fix the login bug in auth.py", tu, sandbox)
        assert result.success is True
        assert "hi" in result.output

    def test_dispatch_blocked_by_namespace(self, tmp_path):
        from mahaclaw.tools.sandbox import ToolSandbox
        sandbox = ToolSandbox(workspace=tmp_path)

        # "deploy the service" routes to RESEARCH (moksha) → OBSERVE only
        tu = ToolUse(id="1", name="bash", parameters={"command": "echo hi"})
        result = dispatch("deploy the service", tu, sandbox)
        # Research action should not allow bash (EXECUTE namespace)
        assert result.success is False
        assert "not in allowed" in result.error


# =============================================================================
# CHITTA — Impression Storage
# =============================================================================


class TestImpression:
    """Impression schema must match steward/antahkarana/chitta.py."""

    def test_fields(self):
        imp = Impression(name="read_file", params_hash=12345, success=True, path="/tmp/x")
        assert imp.name == "read_file"
        assert imp.params_hash == 12345
        assert imp.success is True
        assert imp.error == ""
        assert imp.path == "/tmp/x"

    def test_error_impression(self):
        imp = Impression(name="bash", params_hash=0, success=False, error="timeout")
        assert not imp.success
        assert imp.error == "timeout"


class TestExecutionPhase:
    """ExecutionPhase values must match steward/antahkarana/chitta.py."""

    def test_values(self):
        assert ExecutionPhase.ORIENT == "ORIENT"
        assert ExecutionPhase.EXECUTE == "EXECUTE"
        assert ExecutionPhase.VERIFY == "VERIFY"
        assert ExecutionPhase.COMPLETE == "COMPLETE"

    def test_all_four(self):
        assert len(ExecutionPhase) == 4


class TestChittaPhase:
    """Phase derivation must match steward/antahkarana/chitta.py."""

    def test_empty_is_orient(self):
        c = Chitta()
        assert c.phase == ExecutionPhase.ORIENT

    def test_reads_progress_to_execute(self):
        c = Chitta()
        c.record("read_file", 1, True, path="/a.py")
        c.record("read_file", 2, True, path="/b.py")
        assert c.phase == ExecutionPhase.EXECUTE

    def test_writes_progress_to_verify(self):
        c = Chitta()
        c.record("read_file", 1, True, path="/a.py")
        c.record("write_file", 2, True, path="/a.py")
        # Need write out of recent window (last 3) for VERIFY
        c.record("read_file", 3, True, path="/b.py")
        c.record("read_file", 4, True, path="/c.py")
        c.record("read_file", 5, True, path="/d.py")
        assert c.phase == ExecutionPhase.VERIFY

    def test_bash_after_write_is_complete(self):
        c = Chitta()
        c.record("write_file", 1, True, path="/a.py")
        c.record("read_file", 2, True, path="/a.py")
        c.record("bash", 3, True)
        assert c.phase == ExecutionPhase.COMPLETE

    def test_errors_regress_to_orient(self):
        c = Chitta()
        c.record("write_file", 1, True, path="/a.py")
        c.record("bash", 2, False, error="fail1")
        c.record("bash", 3, False, error="fail2")
        assert c.phase == ExecutionPhase.ORIENT

    def test_active_writing_is_execute(self):
        c = Chitta()
        c.record("read_file", 1, True, path="/a.py")
        c.record("write_file", 2, True, path="/a.py")
        c.record("write_file", 3, True, path="/b.py")
        assert c.phase == ExecutionPhase.EXECUTE


class TestChittaCrossTurn:
    """Cross-turn awareness must match steward/antahkarana/chitta.py."""

    def test_end_turn_preserves_reads(self):
        c = Chitta()
        c.record("read_file", 1, True, path="/a.py")
        c.record("write_file", 2, True, path="/a.py")
        c.end_turn()
        assert "/a.py" in c.prior_reads
        assert len(c.impressions) == 0  # cleared

    def test_was_file_read_cross_turn(self):
        c = Chitta()
        c.record("read_file", 1, True, path="/a.py")
        c.end_turn()
        assert c.was_file_read("/a.py") is True
        assert c.was_file_read("/b.py") is False

    def test_was_file_read_current_turn(self):
        c = Chitta()
        c.record("read_file", 1, True, path="/x.py")
        assert c.was_file_read("/x.py") is True

    def test_round_not_reset_on_end_turn(self):
        c = Chitta()
        c.advance_round()
        c.advance_round()
        c.end_turn()
        assert c.round == 2

    def test_clear_resets_everything(self):
        c = Chitta()
        c.record("read_file", 1, True, path="/a.py")
        c.advance_round()
        c.end_turn()
        c.clear()
        assert c.round == 0
        assert len(c.prior_reads) == 0
        assert len(c.impressions) == 0


class TestChittaSummary:
    """to_summary / load_summary must match steward/antahkarana/chitta.py."""

    def test_round_trip(self):
        c1 = Chitta()
        c1.record("read_file", 1, True, path="/a.py")
        c1.record("read_file", 2, True, path="/b.py")
        summary = c1.to_summary()

        c2 = Chitta()
        c2.load_summary(summary)
        assert c2.was_file_read("/a.py") is True
        assert c2.was_file_read("/b.py") is True

    def test_summary_fields(self):
        c = Chitta()
        c.record("read_file", 1, True, path="/a.py")
        c.record("write_file", 2, True, path="/b.py")
        s = c.to_summary()
        assert "prior_reads" in s
        assert "files_written" in s
        assert "last_phase" in s
        assert "/b.py" in s["files_written"]


class TestChittaStats:
    def test_stats(self):
        c = Chitta()
        c.record("read_file", 1, True, path="/a.py")
        c.record("bash", 2, False, error="fail")
        s = c.stats
        assert s["total_calls"] == 2
        assert s["errors"] == 1
        assert s["error_ratio"] == 0.5
        assert s["tool_distribution"]["read_file"] == 1


class TestChittaFilesReadWritten:
    def test_files_read(self):
        c = Chitta()
        c.record("read_file", 1, True, path="/a.py")
        c.record("read_file", 2, True, path="/a.py")  # duplicate
        c.record("read_file", 3, True, path="/b.py")
        assert c.files_read == ["/a.py", "/b.py"]

    def test_files_written(self):
        c = Chitta()
        c.record("write_file", 1, True, path="/x.py")
        c.record("write_file", 2, True, path="/x.py")  # duplicate
        assert c.files_written == ["/x.py"]


# =============================================================================
# GANDHA — Pattern Detection
# =============================================================================


class TestGandhaConsecutiveErrors:
    def test_no_detection_below_threshold(self):
        # Use different params_hash to avoid triggering identical_calls
        imps = [Impression("bash", i, False, error="err") for i in range(MAX_CONSECUTIVE_ERRORS - 1)]
        assert detect_patterns(imps) is None

    def test_detection_at_threshold(self):
        imps = [Impression("bash", i, False, error="err") for i in range(MAX_CONSECUTIVE_ERRORS)]
        d = detect_patterns(imps)
        assert d is not None
        assert d.severity == VerdictAction.ABORT
        assert d.pattern == "consecutive_errors"


class TestGandhaIdenticalCalls:
    def test_identical_calls_detected(self):
        imps = [Impression("bash", 42, True) for _ in range(MAX_IDENTICAL_CALLS)]
        d = detect_patterns(imps)
        assert d is not None
        assert d.pattern == "identical_calls"

    def test_recovery_not_detected(self):
        """Last success after earlier failures = recovery, not stuck."""
        imps = [
            Impression("bash", 42, False, error="fail"),
            Impression("bash", 42, False, error="fail"),
            Impression("bash", 42, True),
        ]
        d = detect_patterns(imps)
        assert d is None

    def test_different_params_not_detected(self):
        imps = [Impression("bash", i, True) for i in range(MAX_IDENTICAL_CALLS)]
        d = detect_patterns(imps)
        assert d is None


class TestGandhaToolStreak:
    def test_streak_detected(self):
        imps = [Impression("bash", i, True) for i in range(MAX_SAME_TOOL_STREAK)]
        d = detect_patterns(imps)
        assert d is not None
        assert d.pattern == "tool_streak"

    def test_read_file_streak_exempt(self):
        """read_file streaks are legitimate (codebase exploration)."""
        imps = [Impression("read_file", i, True, path=f"/{i}.py") for i in range(MAX_SAME_TOOL_STREAK)]
        d = detect_patterns(imps)
        assert d is None


class TestGandhaErrorRatio:
    def test_high_error_ratio_detected(self):
        # Interleaved errors to avoid consecutive_errors and identical_calls
        # 6 calls, 5 errors = 83% > 70%
        imps = [
            Impression("bash", 0, False, error="err"),
            Impression("read_file", 1, True, path="/a"),
            Impression("bash", 2, False, error="err"),
            Impression("write_file", 3, False, error="err"),
            Impression("bash", 4, False, error="err"),
            Impression("write_file", 5, False, error="err"),
        ]
        d = detect_patterns(imps)
        assert d is not None
        assert d.pattern == "error_ratio"


class TestGandhaBlindWrite:
    def test_blind_write_detected(self):
        imps = [Impression("write_file", 1, True, path="/new.py")]
        d = detect_patterns(imps)
        assert d is not None
        assert d.pattern == "write_without_read"

    def test_read_then_write_ok(self):
        imps = [
            Impression("read_file", 1, True, path="/a.py"),
            Impression("write_file", 2, True, path="/a.py"),
        ]
        d = detect_patterns(imps)
        assert d is None

    def test_prior_read_counts(self):
        imps = [Impression("write_file", 1, True, path="/a.py")]
        d = detect_patterns(imps, prior_reads=frozenset({"/a.py"}))
        assert d is None
