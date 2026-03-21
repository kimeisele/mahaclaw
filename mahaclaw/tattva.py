"""Gate 2: VALIDATE — Five Tattva classifier.

Maps OpenClaw intents to a 5-dimensional affinity vector across the
Pancha Mahabhuta elements.  The dominant element determines the
federation zone and NADI type for routing.

Powered by Manas (deterministic seed router). Zero keywords. Zero LLM.
Manas perceives the intent → position → ActionType → zone → element → affinity.
"""
from __future__ import annotations

from dataclasses import dataclass

from .manas import perceive, route_zone, route_nadi, ActionType

# Element → agent-city zone mapping
ELEMENT_ZONES = {
    "akasha": "discovery",
    "vayu": "general",
    "agni": "governance",
    "jala": "research",
    "prithvi": "engineering",
}

# Element → default NADI type mapping
ELEMENT_NADI = {
    "akasha": "udana",
    "vayu": "vyana",
    "agni": "prana",
    "jala": "udana",
    "prithvi": "prana",
}

# Zone → dominant element (reverse of ELEMENT_ZONES)
_ZONE_TO_ELEMENT = {
    "discovery": "akasha",
    "general": "vayu",
    "governance": "agni",
    "research": "jala",
    "engineering": "prithvi",
}

# ActionType → element affinity weights
_ACTION_AFFINITIES: dict[ActionType, dict[str, float]] = {
    ActionType.RESEARCH:  {"jala": 0.9, "akasha": 0.4},
    ActionType.IMPLEMENT: {"prithvi": 1.0},
    ActionType.REFACTOR:  {"prithvi": 0.8, "agni": 0.3},
    ActionType.DEBUG:     {"prithvi": 0.9},
    ActionType.REVIEW:    {"agni": 0.8, "jala": 0.3},
    ActionType.MONITOR:   {"vayu": 1.0},
    ActionType.RESPOND:   {"vayu": 0.8, "akasha": 0.3},
    ActionType.DESIGN:    {"prithvi": 0.7, "jala": 0.5},
    ActionType.TEST:      {"prithvi": 0.9, "agni": 0.2},
    ActionType.DEPLOY:    {"prithvi": 0.8, "agni": 0.3},
    ActionType.GOVERN:    {"agni": 1.0},
    ActionType.DISCOVER:  {"akasha": 1.0},
}

ELEMENTS = ("akasha", "vayu", "agni", "jala", "prithvi")


@dataclass(frozen=True, slots=True)
class TattvaResult:
    """Result of Five Tattva classification."""
    affinity: tuple[float, float, float, float, float]  # (akasha, vayu, agni, jala, prithvi)
    dominant: str       # element name
    zone: str           # agent-city zone
    nadi_type: str      # recommended NADI type

    def to_dict(self) -> dict:
        return {
            "affinity": {e: v for e, v in zip(ELEMENTS, self.affinity)},
            "dominant": self.dominant,
            "zone": self.zone,
            "nadi_type": self.nadi_type,
        }


def classify(intent: dict) -> TattvaResult:
    """Classify an OpenClaw intent into the Five Tattva dimensions.

    Uses Manas (deterministic seed router) to perceive the intent, then maps
    the perception to a 5D affinity vector. Zero keywords. Zero LLM.
    """
    intent_str = intent["intent"]

    # Manas perceives the intent (pure seed pipeline)
    perception = perceive(intent_str)
    zone = route_zone(perception)
    nadi_type = route_nadi(perception)

    # Build affinity vector from ActionType
    weights = _ACTION_AFFINITIES.get(perception.action, {})
    scores = {e: 0.0 for e in ELEMENTS}
    for element, weight in weights.items():
        scores[element] = weight

    dominant = _ZONE_TO_ELEMENT.get(zone, "vayu")
    affinity = tuple(scores[e] for e in ELEMENTS)

    return TattvaResult(
        affinity=affinity,  # type: ignore[arg-type]
        dominant=dominant,
        zone=zone,
        nadi_type=nadi_type,
    )
