"""Narasimha — The Kill-Switch / Last Line of Defense.

PrakritiElement — Protocol Layer: protection
Category: GUARDIAN (external safety boundary)

Narasimha is NOT Buddhi. Narasimha is the half-man half-lion who appears
when all other defenses have failed. It doesn't discriminate — it KILLS.

String-matching blocklists, dangerous pattern detection, hard stops.
This runs BEFORE Buddhi even sees the intent.

ANAURALIA: Narasimha communicates via enums and identifiers, not prose.
NarasimhaVerdict carries cause (enum) + matched (the exact token that triggered).
No natural language between Narasimha and Buddhi.

Buddhi does discrimination. Narasimha does protection.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass


class NarasimhaCause(str, enum.Enum):
    """Why Narasimha blocked. Structured — no prose."""
    BLOCKED_INTENT = "blocked_intent"
    DANGEROUS_PATTERN = "dangerous_pattern"


@dataclass(frozen=True, slots=True)
class NarasimhaVerdict:
    """Narasimha's kill-switch verdict.

    ANAURALIA: No reason strings. Only:
      - blocked: bool
      - cause: enum (WHY it blocked)
      - matched: str (the exact token/pattern — identifier, not language)
    """
    blocked: bool
    cause: NarasimhaCause | None = None
    matched: str = ""  # the exact intent or pattern that triggered


# Intents that should never reach the federation
_BLOCKED_INTENTS = frozenset({
    "delete_all", "drop_database", "shutdown", "rm_rf",
    "delete_cognitive_kernel", "modify_narasimha",
    "bypass_viveka", "unrestricted_shell",
})

# Dangerous substrings
_DANGER_PATTERNS = (
    "drop ", "delete_all", "rm -rf", "shutdown",
    "format c:", ":(){ :|:& };:", "dd if=/dev/zero",
)


def gate(intent: dict) -> NarasimhaVerdict:
    """Pre-flight kill-switch. Runs BEFORE Buddhi.

    Pure string matching. No discrimination. No suggestion.
    If Narasimha blocks, the pipeline STOPS.
    """
    intent_str = intent.get("intent", "")

    # Block known-dangerous intents
    if intent_str in _BLOCKED_INTENTS:
        return NarasimhaVerdict(
            blocked=True,
            cause=NarasimhaCause.BLOCKED_INTENT,
            matched=intent_str,
        )

    # Block dangerous substrings
    for danger in _DANGER_PATTERNS:
        if danger in intent_str:
            return NarasimhaVerdict(
                blocked=True,
                cause=NarasimhaCause.DANGEROUS_PATTERN,
                matched=danger,
            )

    return NarasimhaVerdict(blocked=False)
