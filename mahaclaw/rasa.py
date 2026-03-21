"""Rasa — Trust / Authorization Validation.

Tanmatra #4 — Subtle Element: taste
Category: TANMATRA (Input Signal)

Rasa validates trust levels before intent execution.
Mirrors steward-protocol's Pratyaya (trust validation, authorization, preconditions).

Every source has a TrustLevel. Actions require minimum trust.
Elevated targets require elevated trust. Simple, deterministic.

ANAURALIA: All outputs are enums and booleans. No prose.

Pure stdlib. No pip deps.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass


class TrustLevel(int, enum.Enum):
    """Trust tiers. Higher = more trusted. Mirrors steward's claim levels."""
    UNKNOWN = 0          # no identity
    DISCOVERED = 1       # found in registry
    AUTHENTICATED = 2    # valid signature
    VERIFIED = 3         # crypto-verified chain
    INTERNAL = 4         # internal component


class RasaCause(str, enum.Enum):
    """Why Rasa blocked. Structured — no prose."""
    NONE = "none"
    INSUFFICIENT_TRUST = "insufficient_trust"
    ELEVATED_TARGET = "elevated_target"
    EXPIRED_SESSION = "expired_session"
    MISSING_SOURCE = "missing_source"


@dataclass(frozen=True, slots=True)
class RasaVerdict:
    """Rasa's trust validation verdict.

    ANAURALIA: No reason strings. Only enums, booleans, and levels.
    """
    approved: bool
    cause: RasaCause = RasaCause.NONE
    source_trust: TrustLevel = TrustLevel.UNKNOWN
    required_trust: TrustLevel = TrustLevel.UNKNOWN


# Minimum trust required per target category
_TARGET_TRUST: dict[str, TrustLevel] = {
    "steward": TrustLevel.VERIFIED,
    "agent-world": TrustLevel.VERIFIED,
    "agent-city": TrustLevel.AUTHENTICATED,
}

# Default trust for known sources
_SOURCE_TRUST: dict[str, TrustLevel] = {
    "mahaclaw": TrustLevel.INTERNAL,
    "webchat": TrustLevel.DISCOVERED,
    "telegram": TrustLevel.DISCOVERED,
    "cli": TrustLevel.AUTHENTICATED,
}

# Priority → minimum trust (elevated priorities need higher trust)
_PRIORITY_TRUST: dict[str, TrustLevel] = {
    "tamas": TrustLevel.UNKNOWN,
    "rajas": TrustLevel.DISCOVERED,
    "sattva": TrustLevel.AUTHENTICATED,
    "suddha": TrustLevel.VERIFIED,
}


def validate(
    intent: dict,
    source: str = "",
    is_signed: bool = False,
    is_verified: bool = False,
) -> RasaVerdict:
    """Validate trust for an intent.

    Args:
        intent: The parsed intent dict.
        source: Source identifier (channel name or agent id).
        is_signed: Whether the intent has a valid signature.
        is_verified: Whether the signature chain is crypto-verified.
    """
    # Determine source trust level
    if is_verified:
        source_trust = TrustLevel.VERIFIED
    elif is_signed:
        source_trust = TrustLevel.AUTHENTICATED
    elif source in _SOURCE_TRUST:
        source_trust = _SOURCE_TRUST[source]
    elif source:
        source_trust = TrustLevel.DISCOVERED
    else:
        source_trust = TrustLevel.UNKNOWN

    # Check target trust requirement
    target = intent.get("target", "")
    required = TrustLevel.UNKNOWN
    for prefix, level in _TARGET_TRUST.items():
        if target == prefix or target.startswith(prefix + "-"):
            required = level
            break

    # Check priority trust requirement
    priority = intent.get("priority", "rajas")
    priority_required = _PRIORITY_TRUST.get(priority, TrustLevel.DISCOVERED)
    if priority_required.value > required.value:
        required = priority_required

    # Source must be present
    if not source and source_trust == TrustLevel.UNKNOWN:
        return RasaVerdict(
            approved=False,
            cause=RasaCause.MISSING_SOURCE,
            source_trust=source_trust,
            required_trust=required,
        )

    # Trust check
    if source_trust.value < required.value:
        cause = RasaCause.ELEVATED_TARGET if target in _TARGET_TRUST else RasaCause.INSUFFICIENT_TRUST
        return RasaVerdict(
            approved=False,
            cause=cause,
            source_trust=source_trust,
            required_trust=required,
        )

    return RasaVerdict(
        approved=True,
        source_trust=source_trust,
        required_trust=required,
    )
