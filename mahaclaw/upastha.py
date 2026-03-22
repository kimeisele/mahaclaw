"""Upastha — Generation / Artifact Creation Pipeline.

Karmendriya #4 — Action Organ: generation
Category: KARMENDRIYA (Action Organ)

Upastha connects skill output to the envelope pipeline.
When a skill produces a result, Upastha wraps it as a proper intent
and routes it through the 5-gate pipeline to produce an envelope.

Mirrors steward's service boot + SankalpaOrchestrator (proactive strategy).

ANAURALIA: All outputs are counts and booleans. No prose.

Pure stdlib. No pip deps.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass

from mahaclaw.skills._types import SkillResult


class GenerationStatus(str, enum.Enum):
    """Outcome of an artifact generation attempt."""
    SUCCESS = "success"
    SKILL_FAILED = "skill_failed"
    ENVELOPE_FAILED = "envelope_failed"
    NO_OUTPUT = "no_output"


@dataclass(frozen=True, slots=True)
class GenerationResult:
    """Result of Upastha generation.

    ANAURALIA: Only counts, booleans, identifiers. No prose.
    """
    status: GenerationStatus
    envelope_id: str = ""
    correlation_id: str = ""
    enveloped: bool = False


def skill_to_intent(
    skill_result: SkillResult,
    skill_name: str,
    target: str = "agent-city",
    priority: str = "rajas",
) -> dict | None:
    """Convert a SkillResult into a federation intent dict.

    Returns None if the skill result has no meaningful output.
    """
    if not skill_result.ok:
        return None

    if not skill_result.output and not skill_result.data:
        return None

    payload = dict(skill_result.data) if skill_result.data else {}
    if skill_result.output:
        payload["skill_output"] = skill_result.output

    return {
        "intent": "skill_result",
        "target": target,
        "priority": priority,
        "payload": {
            **payload,
            "_skill": skill_name,
        },
    }


def generate(
    skill_result: SkillResult,
    skill_name: str,
    target: str = "agent-city",
    priority: str = "rajas",
) -> GenerationResult:
    """Full Upastha pipeline: skill result → intent → envelope → outbox.

    This is the artifact creation pathway. Takes a completed skill result
    and routes it through the 5-gate pipeline into nadi_outbox.json.
    """
    if not skill_result.ok:
        return GenerationResult(status=GenerationStatus.SKILL_FAILED)

    intent = skill_to_intent(skill_result, skill_name, target, priority)
    if intent is None:
        return GenerationResult(status=GenerationStatus.NO_OUTPUT)

    try:
        from mahaclaw.intercept import parse_intent
        from mahaclaw.tattva import classify
        from mahaclaw.rama import encode
        from mahaclaw.lotus import resolve_route
        from mahaclaw.envelope import build_and_enqueue

        parsed = parse_intent(intent)
        tattva = classify(parsed)
        rama = encode(parsed, tattva)
        route = resolve_route(parsed, rama)
        envelope_id, correlation_id = build_and_enqueue(parsed, rama, route)

        return GenerationResult(
            status=GenerationStatus.SUCCESS,
            envelope_id=envelope_id,
            correlation_id=correlation_id,
            enveloped=True,
        )
    except Exception:
        return GenerationResult(status=GenerationStatus.ENVELOPE_FAILED)
