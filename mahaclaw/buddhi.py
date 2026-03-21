"""Buddhi — Intellect / Safety Gate.

Deterministic decision engine. Zero LLM. Inspects every intent before it
enters the pipeline and can ABORT, REFLECT, or REDIRECT.

Mirrors steward/buddhi.py + steward/antahkarana/gandha.py but pure stdlib.
"""
from __future__ import annotations

import enum
import threading
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class VerdictAction(str, enum.Enum):
    """What Buddhi decides to do with an intent."""
    CONTINUE = "continue"    # proceed normally
    REFLECT = "reflect"      # warn but allow
    REDIRECT = "redirect"    # suggest alternative
    ABORT = "abort"          # stop — unsafe or stuck


@dataclass(frozen=True, slots=True)
class BuddhiVerdict:
    """Buddhi's decision on an intent or tool result."""
    action: VerdictAction
    reason: str = ""
    suggestion: str = ""


@dataclass(frozen=True, slots=True)
class Impression:
    """A single tool/pipeline invocation record (Chitta samskara)."""
    name: str
    params_hash: int = 0
    success: bool = True
    error: str = ""
    path: str = ""


# ---------------------------------------------------------------------------
# Gandha — Stateless pattern detection (the "smell" sense)
# ---------------------------------------------------------------------------

MAX_IDENTICAL_CALLS = 3
MAX_CONSECUTIVE_ERRORS = 5
MAX_SAME_TOOL_STREAK = 8
ERROR_RATIO_THRESHOLD = 0.7


def detect_patterns(
    impressions: list[Impression],
    prior_reads: frozenset[str] = frozenset(),
) -> BuddhiVerdict | None:
    """Pure function. Detects stuck loops, error cascades, blind writes.

    Returns a verdict if a problematic pattern is found, else None.
    Mirrors steward/antahkarana/gandha.py detect_patterns().
    """
    if not impressions:
        return None

    # 1. Consecutive errors → abort
    consecutive_errors = 0
    for imp in reversed(impressions):
        if not imp.success:
            consecutive_errors += 1
        else:
            break
    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
        return BuddhiVerdict(
            action=VerdictAction.ABORT,
            reason=f"{consecutive_errors} consecutive errors",
            suggestion="stop and investigate root cause",
        )

    # 2. Identical calls (same name + params) → stuck loop
    if len(impressions) >= MAX_IDENTICAL_CALLS:
        recent = impressions[-MAX_IDENTICAL_CALLS:]
        if (len({(i.name, i.params_hash) for i in recent}) == 1
                and all(not i.success for i in recent)):
            return BuddhiVerdict(
                action=VerdictAction.REFLECT,
                reason=f"same call failed {MAX_IDENTICAL_CALLS}x",
                suggestion="try a different approach",
            )

    # 3. Same tool streak (excluding reads)
    if len(impressions) >= MAX_SAME_TOOL_STREAK:
        recent = impressions[-MAX_SAME_TOOL_STREAK:]
        names = {i.name for i in recent}
        if len(names) == 1 and "read" not in next(iter(names)):
            return BuddhiVerdict(
                action=VerdictAction.REFLECT,
                reason=f"same tool {MAX_SAME_TOOL_STREAK}x in a row",
                suggestion="diversify approach",
            )

    # 4. Error ratio too high
    if len(impressions) >= 5:
        failures = sum(1 for i in impressions if not i.success)
        ratio = failures / len(impressions)
        if ratio > ERROR_RATIO_THRESHOLD:
            return BuddhiVerdict(
                action=VerdictAction.REFLECT,
                reason=f"error ratio {ratio:.0%} exceeds threshold",
                suggestion="re-evaluate strategy",
            )

    # 5. Write without read (blind write)
    for imp in impressions:
        if imp.path and imp.name in ("write", "edit", "write_file", "edit_file"):
            if imp.path not in prior_reads:
                return BuddhiVerdict(
                    action=VerdictAction.REDIRECT,
                    reason=f"writing {imp.path} without reading it first",
                    suggestion=f"read {imp.path} before modifying",
                )

    return None


# ---------------------------------------------------------------------------
# Intent safety checks (pre-flight gate)
# ---------------------------------------------------------------------------

# Intents that should never reach the federation unexamined
_BLOCKED_INTENTS = frozenset({
    "delete_all", "drop_database", "shutdown", "rm_rf",
    "delete_cognitive_kernel", "modify_narasimha",
    "bypass_viveka", "unrestricted_shell",
})

# Targets that require elevated trust
_RESTRICTED_TARGETS = frozenset({
    "steward", "agent-world",
})

VALID_PRIORITIES = frozenset({"tamas", "rajas", "sattva", "suddha"})
VALID_NADI_TYPES = frozenset({"prana", "apana", "vyana", "udana", "samana"})


def check_intent(intent: dict) -> BuddhiVerdict:
    """Pre-flight safety check on a parsed intent.

    Called between Gate 1 (PARSE) and Gate 2 (VALIDATE).
    Returns CONTINUE if safe, ABORT/REDIRECT otherwise.
    """
    intent_str = intent.get("intent", "")

    # Block known-dangerous intents (Narasimha-level threats)
    if intent_str in _BLOCKED_INTENTS:
        return BuddhiVerdict(
            action=VerdictAction.ABORT,
            reason=f"blocked intent: {intent_str}",
            suggestion="this intent is not allowed through the federation",
        )

    # Block dangerous substrings
    for danger in ("drop ", "delete_all", "rm -rf", "shutdown"):
        if danger in intent_str:
            return BuddhiVerdict(
                action=VerdictAction.ABORT,
                reason=f"dangerous pattern in intent: {danger!r}",
            )

    # Validate priority
    priority = intent.get("priority", "rajas")
    if priority not in VALID_PRIORITIES:
        return BuddhiVerdict(
            action=VerdictAction.REDIRECT,
            reason=f"unknown priority: {priority}",
            suggestion=f"use one of: {', '.join(sorted(VALID_PRIORITIES))}",
        )

    # Warn on restricted targets with high priority
    target = intent.get("target", "")
    if target in _RESTRICTED_TARGETS and priority in ("sattva", "suddha"):
        return BuddhiVerdict(
            action=VerdictAction.REFLECT,
            reason=f"elevated priority {priority} to restricted target {target}",
            suggestion="consider using rajas priority unless urgent",
        )

    # Validate TTL bounds
    ttl_ms = intent.get("ttl_ms", 24_000)
    if ttl_ms <= 0:
        return BuddhiVerdict(
            action=VerdictAction.REDIRECT,
            reason="ttl_ms must be positive",
            suggestion="use default 24000ms",
        )
    if ttl_ms > 3_600_000:  # 1 hour max
        return BuddhiVerdict(
            action=VerdictAction.REFLECT,
            reason=f"very long TTL: {ttl_ms}ms",
            suggestion="consider a shorter TTL",
        )

    return BuddhiVerdict(action=VerdictAction.CONTINUE)


# ---------------------------------------------------------------------------
# Chitta — Impression memory (session-scoped)
# ---------------------------------------------------------------------------

class Chitta:
    """Thread-safe impression store. Tracks tool calls within a session.

    Mirrors steward/antahkarana/chitta.py.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._impressions: list[Impression] = []
        self._prior_reads: set[str] = set()

    def record(self, imp: Impression) -> None:
        with self._lock:
            self._impressions.append(imp)
            if imp.success and imp.name in ("read", "read_file") and imp.path:
                self._prior_reads.add(imp.path)

    @property
    def impressions(self) -> list[Impression]:
        with self._lock:
            return list(self._impressions)

    @property
    def prior_reads(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._prior_reads)

    def evaluate(self) -> BuddhiVerdict:
        """Run Gandha pattern detection on current impressions."""
        return detect_patterns(self.impressions, self.prior_reads) or BuddhiVerdict(
            action=VerdictAction.CONTINUE,
        )

    def clear(self) -> None:
        with self._lock:
            self._impressions.clear()
            # prior_reads persists across turns (cross-turn awareness)
