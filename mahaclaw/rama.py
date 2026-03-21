"""Gate 3: EXECUTE — 7-layer RAMA signal encoder.

Enriches a classified intent into a full RAMA vector compatible with the
upstream steward-protocol coordinate system.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .manas import perceive
from .tattva import TattvaResult

QUARTERS = ("genesis", "dharma", "karma", "moksha")

GUARDIANS = (
    "vyasa", "brahma", "narada", "shambhu",
    "prithu", "kumaras", "kapila", "manu",
    "parashurama", "prahlada", "janaka", "bhishma",
    "nrisimha", "bali", "shuka", "yamaraja",
)

GUNA_PRIORITIES = ("tamas", "rajas", "sattva", "suddha")


@dataclass(frozen=True, slots=True)
class RAMASignal:
    """7-layer RAMA vector."""
    element: str                 # Layer 1: dominant Tattva
    zone: str                    # Layer 2: agent-city zone
    operation: str               # Layer 3: mapped operation
    affinity: tuple              # Layer 4: 5D Tattva vector
    guardian: str                # Layer 5: Mahajana name
    quarter: str                 # Layer 6: Genesis/Dharma/Karma/Moksha
    guna: str                    # Layer 7: priority guna
    position: int                # Mahajana position (0-15)

    def to_dict(self) -> dict:
        return {
            "element": self.element,
            "zone": self.zone,
            "operation": self.operation,
            "affinity": dict(zip(
                ("akasha", "vayu", "agni", "jala", "prithvi"),
                self.affinity,
            )),
            "guardian": self.guardian,
            "quarter": self.quarter,
            "guna": self.guna,
            "position": self.position,
        }

    @property
    def parampara_vector(self) -> int:
        """Parampara connection: (position + 1) * 37."""
        return (self.position + 1) * 37


def _find_position(intent_str: str) -> int:
    """Find the Mahajana position for an intent string via seed pipeline.

    Uses Manas perception (pure seed, zero keywords) to derive position.
    """
    perception = perceive(intent_str)
    return perception.position


def encode_rama(intent: dict, tattva: TattvaResult) -> RAMASignal:
    """Encode an intent + Tattva classification into a 7-layer RAMA signal."""
    intent_str = intent["intent"]
    priority = intent.get("priority", "rajas")

    if priority not in GUNA_PRIORITIES:
        priority = "rajas"

    position = _find_position(intent_str)
    quarter = QUARTERS[position // 4]
    guardian = GUARDIANS[position]

    return RAMASignal(
        element=tattva.dominant,
        zone=tattva.zone,
        operation=intent_str,
        affinity=tattva.affinity,
        guardian=guardian,
        quarter=quarter,
        guna=priority,
        position=position,
    )
