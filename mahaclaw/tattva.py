"""Gate 2: VALIDATE — Five Tattva classifier.

Maps OpenClaw intents to a 5-dimensional affinity vector across the
Pancha Mahabhuta elements.  The dominant element determines the
federation zone and NADI type for routing.
"""
from __future__ import annotations

from dataclasses import dataclass

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

# Intent keyword → element affinity weights.
# Keys are substring-matched against the intent string.
_AFFINITY_RULES: list[tuple[str, dict[str, float]]] = [
    # Communication / status
    ("heartbeat",       {"vayu": 1.0}),
    ("ping",            {"vayu": 1.0}),
    ("status",          {"vayu": 0.8, "akasha": 0.3}),
    # Research / knowledge
    ("inquiry",         {"jala": 0.9, "akasha": 0.4}),
    ("research",        {"jala": 1.0}),
    ("question",        {"jala": 0.9, "akasha": 0.3}),
    ("analysis",        {"jala": 0.7, "prithvi": 0.5}),
    # Engineering / code
    ("code",            {"prithvi": 1.0}),
    ("build",           {"prithvi": 1.0}),
    ("test",            {"prithvi": 0.9, "agni": 0.2}),
    ("deploy",          {"prithvi": 0.8, "agni": 0.3}),
    ("fix",             {"prithvi": 0.9}),
    # Governance / policy
    ("governance",      {"agni": 1.0}),
    ("policy",          {"agni": 1.0}),
    ("vote",            {"agni": 0.9, "vayu": 0.3}),
    ("trust",           {"agni": 0.8, "akasha": 0.3}),
    # Discovery / exploration
    ("discover",        {"akasha": 1.0}),
    ("explore",         {"akasha": 0.9, "jala": 0.3}),
    ("search",          {"akasha": 0.8, "jala": 0.4}),
]

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
    """Classify an OpenClaw intent into the Five Tattva dimensions."""
    intent_str = intent["intent"]
    scores = {e: 0.0 for e in ELEMENTS}

    matched = False
    for keyword, weights in _AFFINITY_RULES:
        if keyword in intent_str:
            for element, weight in weights.items():
                scores[element] = max(scores[element], weight)
            matched = True

    # Fallback: if no rule matched, default to vayu (general communication)
    if not matched:
        scores["vayu"] = 0.5

    # Determine dominant element
    dominant = max(scores, key=scores.__getitem__) # type: ignore[arg-type]
    affinity = tuple(scores[e] for e in ELEMENTS)

    return TattvaResult(
        affinity=affinity,  # type: ignore[arg-type]
        dominant=dominant,
        zone=ELEMENT_ZONES[dominant],
        nadi_type=ELEMENT_NADI[dominant],
    )
