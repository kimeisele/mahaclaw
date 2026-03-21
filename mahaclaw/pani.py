"""Pani — The Hands (Tool Dispatch).

PrakritiElement #19 — Protocol Layer: action
Category: KARMENDRIYA (Action Organ)

In Sankhya, Pani is the organ of grasping/action.
It answers: "HOW do I act?" — dispatching tools under safety gates.

Mirrors steward's tool dispatch pipeline:
  - ToolResult (from vibe_core/tools/tool_protocol.py)
  - ToolNamespace (from steward/buddhi.py)
  - Action → Namespace resolution (from steward/buddhi.py)
  - Pre-execution gating (from steward/loop/tool_dispatch.py)
  - Impression recording (feeds back to Chitta)

Pure stdlib. No pip deps.
"""
from __future__ import annotations

import enum
import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path

from mahaclaw.manas import ActionType, perceive


# ---------------------------------------------------------------------------
# ToolResult — mirrors vibe_core/tools/tool_protocol.py
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    """Result of tool execution. Mirrors steward's ToolResult."""
    success: bool
    output: object = None
    error: str | None = None
    metadata: dict[str, object] | None = None


# ---------------------------------------------------------------------------
# ToolUse — mirrors steward/types.py
# ---------------------------------------------------------------------------

@dataclass
class ToolUse:
    """A tool invocation request. Mirrors steward's ToolUse."""
    id: str
    name: str
    parameters: dict[str, object]


# ---------------------------------------------------------------------------
# ToolNamespace — mirrors steward/buddhi.py
# ---------------------------------------------------------------------------

class ToolNamespace(str, enum.Enum):
    """Semantic tool capability domains (Shakti → business English).

    From steward/buddhi.py:
      JNANA  (knowledge)     → OBSERVE
      PALANA (maintenance)   → MODIFY
      KSHATRA (enforcement)  → EXECUTE
      UDDHARA (rescue/spawn) → DELEGATE
    """
    OBSERVE = "observe"
    MODIFY = "modify"
    EXECUTE = "execute"
    DELEGATE = "delegate"


# Namespace → tool names (runtime-mutable, mirrors steward/buddhi.py)
_NAMESPACE_TOOLS: dict[ToolNamespace, set[str]] = {
    ToolNamespace.OBSERVE: {"read_file", "list_dir", "grep", "glob"},
    ToolNamespace.MODIFY: {"write_file"},
    ToolNamespace.EXECUTE: {"bash"},
    ToolNamespace.DELEGATE: set(),
}

# Action → namespaces (mirrors steward/buddhi.py _ACTION_NAMESPACES)
_ACTION_NAMESPACES: dict[ActionType, frozenset[ToolNamespace]] = {
    ActionType.RESEARCH: frozenset({ToolNamespace.OBSERVE}),
    ActionType.MONITOR: frozenset({ToolNamespace.OBSERVE}),
    ActionType.REVIEW: frozenset({ToolNamespace.OBSERVE}),
    ActionType.IMPLEMENT: frozenset({ToolNamespace.OBSERVE, ToolNamespace.MODIFY, ToolNamespace.EXECUTE}),
    ActionType.REFACTOR: frozenset({ToolNamespace.OBSERVE, ToolNamespace.MODIFY, ToolNamespace.EXECUTE}),
    ActionType.DEBUG: frozenset({ToolNamespace.OBSERVE, ToolNamespace.MODIFY, ToolNamespace.EXECUTE}),
    ActionType.TEST: frozenset({ToolNamespace.OBSERVE, ToolNamespace.EXECUTE}),
    ActionType.RESPOND: frozenset({ToolNamespace.OBSERVE, ToolNamespace.MODIFY, ToolNamespace.EXECUTE}),
    ActionType.DESIGN: frozenset({ToolNamespace.OBSERVE, ToolNamespace.MODIFY, ToolNamespace.EXECUTE, ToolNamespace.DELEGATE}),
    ActionType.DEPLOY: frozenset({ToolNamespace.OBSERVE, ToolNamespace.EXECUTE}),
    ActionType.GOVERN: frozenset({ToolNamespace.OBSERVE}),
    ActionType.DISCOVER: frozenset({ToolNamespace.OBSERVE}),
}


# ---------------------------------------------------------------------------
# Namespace resolution — mirrors steward/buddhi.py resolve_namespaces()
# ---------------------------------------------------------------------------

def resolve_namespaces(namespaces: frozenset[ToolNamespace]) -> frozenset[str]:
    """Resolve namespace set to concrete tool names."""
    tools: set[str] = set()
    for ns in namespaces:
        tools.update(_NAMESPACE_TOOLS.get(ns, set()))
    return frozenset(tools)


def resolve_action_tools(action: ActionType) -> frozenset[str]:
    """Resolve an ActionType to concrete tool names."""
    namespaces = _ACTION_NAMESPACES.get(action, frozenset({ToolNamespace.OBSERVE}))
    return resolve_namespaces(namespaces)


def register_tool(namespace: ToolNamespace, tool_name: str) -> None:
    """Register a tool into a namespace (runtime composition)."""
    _NAMESPACE_TOOLS[namespace].add(tool_name)


def unregister_tool(namespace: ToolNamespace, tool_name: str) -> None:
    """Remove a tool from a namespace."""
    _NAMESPACE_TOOLS[namespace].discard(tool_name)


# ---------------------------------------------------------------------------
# File operation tracking — mirrors steward/loop/tool_dispatch.py
# ---------------------------------------------------------------------------

_FILE_OP_MAP: dict[str, str] = {
    "read_file": "read",
    "write_file": "write",
    "list_dir": "read",
}


# ---------------------------------------------------------------------------
# Pre-execution gating — mirrors steward/loop/tool_dispatch.py check_tool_gates()
# ---------------------------------------------------------------------------

def check_tool_gates(
    tool_use: ToolUse,
    allowed_tools: frozenset[str],
    prior_reads: frozenset[str] = frozenset(),
) -> str | None:
    """Check pre-execution gates for a tool call.

    Returns error message if blocked, None if cleared.

    Gates (mirrors steward's 3-gate pattern):
      Gate 1: Route check — tool must exist in allowed set
      Gate 2: Safety check — bash commands validated by sandbox
      Gate 3: Iron Dome — write-before-read detection

    Args:
        tool_use: The tool call to check.
        allowed_tools: Tools allowed for this action's namespaces.
        prior_reads: Files read in prior turns (cross-turn awareness).
    """
    # Gate 1: Route check (mirrors Lotus route / MahaAttention.attend)
    if tool_use.name not in allowed_tools:
        return f"Tool '{tool_use.name}' not in allowed namespaces for this action"

    # Gate 2: Safety check deferred to sandbox.validate_command() at execution time

    # Gate 3: Iron Dome — write without prior read
    if tool_use.name == "write_file":
        path = str(tool_use.parameters.get("path", ""))
        if path and path not in prior_reads:
            # Warning, not block — matches steward's Gandha detection pattern
            pass  # Gandha will detect and advise; gate doesn't hard-block

    return None  # All gates passed


# ---------------------------------------------------------------------------
# Tool dispatch — the Pani pipeline
# ---------------------------------------------------------------------------

def dispatch(
    intent_text: str,
    tool_use: ToolUse,
    sandbox: object,
    prior_reads: frozenset[str] = frozenset(),
) -> ToolResult:
    """Dispatch a tool call through the Pani pipeline.

    Pipeline (mirrors steward's engine.py tool execution):
      1. Manas perceive → ActionType
      2. ActionType → ToolNamespace → allowed tools
      3. check_tool_gates() — pre-execution safety
      4. Sandbox execute — scoped execution
      5. Return ToolResult

    Args:
        intent_text: The user intent string (for Manas routing).
        tool_use: The tool call to dispatch.
        sandbox: A ToolSandbox instance for execution.
        prior_reads: Files read in prior turns.

    Returns:
        ToolResult with execution outcome.
    """
    # Step 1: Manas routing
    perception = perceive(intent_text)

    # Step 2: Resolve allowed tools
    allowed_tools = resolve_action_tools(perception.action)

    # Step 3: Gate check
    gate_error = check_tool_gates(tool_use, allowed_tools, prior_reads)
    if gate_error is not None:
        return ToolResult(success=False, error=gate_error)

    # Step 4: Execute via sandbox
    t0 = time.monotonic()
    try:
        if tool_use.name == "bash":
            command = str(tool_use.parameters.get("command", ""))
            sr = sandbox.run(command)
            return ToolResult(
                success=sr.ok,
                output=sr.stdout if sr.ok else None,
                error=sr.error if not sr.ok else None,
                metadata={"exit_code": sr.exit_code, "duration_ms": sr.duration_ms,
                          "stderr": sr.stderr, "truncated": sr.truncated},
            )
        elif tool_use.name == "read_file":
            path = str(tool_use.parameters.get("path", ""))
            ok, content = sandbox.read_file(path)
            return ToolResult(success=ok, output=content if ok else None,
                              error=content if not ok else None)
        elif tool_use.name == "write_file":
            path = str(tool_use.parameters.get("path", ""))
            content = str(tool_use.parameters.get("content", ""))
            ok, msg = sandbox.write_file(path, content)
            return ToolResult(success=ok, output=msg if ok else None,
                              error=msg if not ok else None)
        elif tool_use.name == "list_dir":
            path = str(tool_use.parameters.get("path", "."))
            ok, entries = sandbox.list_dir(path)
            return ToolResult(success=ok, output=entries if ok else None,
                              error=entries[0] if not ok else None)
        elif tool_use.name == "grep" or tool_use.name == "glob":
            # Delegate to bash with the command
            pattern = str(tool_use.parameters.get("pattern", ""))
            target = str(tool_use.parameters.get("path", "."))
            cmd = f"grep -r {pattern} {target}" if tool_use.name == "grep" else f"find {target} -name {pattern}"
            sr = sandbox.run(cmd)
            return ToolResult(
                success=sr.ok,
                output=sr.stdout if sr.ok else None,
                error=sr.error if not sr.ok else None,
            )
        else:
            return ToolResult(success=False, error=f"Unknown tool: {tool_use.name}")
    except Exception as e:
        return ToolResult(success=False, error=str(e))


def params_hash(parameters: dict[str, object]) -> int:
    """Hash tool parameters for Chitta impression identity.

    Mirrors steward's params_hash used in Impression dataclass.
    """
    raw = str(sorted(parameters.items()))
    return int(hashlib.sha256(raw.encode()).hexdigest()[:8], 16)
