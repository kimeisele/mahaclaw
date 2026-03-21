"""Vedana — Health Pulse / System Vitals.

PrakritiElement — Protocol Layer: health
Category: ANTAHKARANA (Internal Instrument)

Vedana monitors system health and produces a composite score (0.0–1.0).
Mirrors steward/antahkarana/vedana.py → VedanaSignal.

ANAURALIA: All outputs are numeric. No prose health descriptions.
Guna derived from health: SATTVA (healthy), RAJAS (stressed), TAMAS (degraded).

Pure stdlib. No pip deps.
"""
from __future__ import annotations

import enum
import time
from dataclasses import dataclass

from mahaclaw.chitta import Chitta, ExecutionPhase


class HealthGuna(str, enum.Enum):
    """Health-derived guna. Mirrors steward's VedanaSignal."""
    SATTVA = "sattva"   # healthy (score ≥ 0.7)
    RAJAS = "rajas"     # stressed (0.4 ≤ score < 0.7)
    TAMAS = "tamas"     # degraded (score < 0.4)


@dataclass(frozen=True, slots=True)
class VedanaSignal:
    """Composite health signal.

    ANAURALIA: All fields are numeric or enum. No prose.
    """
    score: float              # 0.0–1.0 composite health
    guna: HealthGuna          # derived from score
    error_rate: float         # 0.0–1.0
    uptime_s: float           # seconds since start
    queue_depth: int          # outbox size
    phase: ExecutionPhase     # current Chitta phase
    impression_count: int     # total impressions recorded
    confidence: float         # Hebbian confidence (0.0–1.0)


# Component weights for composite score
_W_ERROR_RATE = 0.4      # error rate has highest impact
_W_CONFIDENCE = 0.3      # Hebbian confidence
_W_PHASE_HEALTH = 0.2    # phase progression health
_W_QUEUE = 0.1           # queue pressure

# Phase health scores (progressing is healthy)
_PHASE_SCORE: dict[ExecutionPhase, float] = {
    ExecutionPhase.ORIENT: 0.6,     # reading, normal start
    ExecutionPhase.EXECUTE: 1.0,    # actively working
    ExecutionPhase.VERIFY: 0.9,     # verifying, good
    ExecutionPhase.COMPLETE: 0.8,   # done, healthy
}

_start_time = time.monotonic()


def pulse(
    chitta: Chitta,
    confidence: float = 0.5,
    queue_depth: int = 0,
) -> VedanaSignal:
    """Take a health reading. Pure computation, no I/O.

    Args:
        chitta: Current Chitta state (impressions, phase).
        confidence: Hebbian confidence from Buddhi (0.0–1.0).
        queue_depth: Number of envelopes in outbox.
    """
    impressions = chitta.impressions
    total = len(impressions)
    errors = sum(1 for i in impressions if not i.success)
    error_rate = errors / total if total > 0 else 0.0
    phase = chitta.phase
    uptime_s = time.monotonic() - _start_time

    # Component scores (each 0.0–1.0)
    error_score = 1.0 - error_rate
    confidence_score = max(0.0, min(1.0, confidence))
    phase_score = _PHASE_SCORE.get(phase, 0.5)
    queue_score = max(0.0, 1.0 - (queue_depth / 100.0))  # degrade above 100

    # Weighted composite
    score = (
        error_score * _W_ERROR_RATE
        + confidence_score * _W_CONFIDENCE
        + phase_score * _W_PHASE_HEALTH
        + queue_score * _W_QUEUE
    )
    score = max(0.0, min(1.0, score))

    # Guna from score
    if score >= 0.7:
        guna = HealthGuna.SATTVA
    elif score >= 0.4:
        guna = HealthGuna.RAJAS
    else:
        guna = HealthGuna.TAMAS

    return VedanaSignal(
        score=score,
        guna=guna,
        error_rate=error_rate,
        uptime_s=uptime_s,
        queue_depth=queue_depth,
        phase=phase,
        impression_count=total,
        confidence=confidence_score,
    )
