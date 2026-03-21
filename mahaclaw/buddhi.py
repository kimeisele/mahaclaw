"""Buddhi — Intellect / Safety Gate.

PrakritiElement #3 — Protocol Layer: decision
Category: ANTAHKARANA (Internal Instrument)

Buddhi DISCRIMINATES and DECIDES. It doesn't perceive (Manas), doesn't store
(Chitta), doesn't detect patterns (Gandha). It reads their output and makes
safety decisions.

Buddhi's responsibilities:
  - Pre-flight intent safety check (check_intent)
  - Evaluate Chitta impressions via Gandha (evaluate)
  - VerdictAction: CONTINUE / REFLECT / REDIRECT / ABORT

Gandha lives in chitta.py (pattern detection is a memory function).
Buddhi CALLS Gandha but doesn't duplicate it.

Mirrors steward/buddhi.py but pure stdlib.
"""
from __future__ import annotations

from dataclasses import dataclass

from mahaclaw.chitta import (
    Chitta,
    Impression,
    VerdictAction,
    Detection,
    detect_patterns,
)


# ---------------------------------------------------------------------------
# BuddhiVerdict — Buddhi's decision format
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BuddhiVerdict:
    """Buddhi's decision on an intent or tool result."""
    action: VerdictAction
    reason: str = ""
    suggestion: str = ""


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
# Buddhi evaluate — reads Chitta, calls Gandha, returns verdict
# ---------------------------------------------------------------------------

def evaluate(chitta: Chitta) -> BuddhiVerdict:
    """Run Gandha pattern detection on Chitta's impressions.

    Buddhi reads Chitta → asks Gandha → wraps Detection as BuddhiVerdict.
    This is the steward pattern: Gandha detects, Buddhi decides.
    """
    detection = detect_patterns(chitta.impressions, chitta.prior_reads)
    if detection is None:
        return BuddhiVerdict(action=VerdictAction.CONTINUE)
    return BuddhiVerdict(
        action=detection.severity,
        reason=detection.reason,
        suggestion=detection.suggestion,
    )
