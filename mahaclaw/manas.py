"""Manas — The Mind (Deterministic Router).

PrakritiElement #1 — classifies intent WITHOUT an LLM.

Mirrors steward/antahkarana/manas.py but pure stdlib.
Steward uses MahaCompression + MahaBuddhi substrate primitives.
We replicate the same deterministic logic via seed hashing.

Output: ManasPerception(action, guna, function, approach)
"""
from __future__ import annotations

import enum
import hashlib
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Types — mirrors steward's SemanticActionType and IntentGuna
# ---------------------------------------------------------------------------

class ActionType(str, enum.Enum):
    """What kind of task this is. Maps to steward's SemanticActionType."""
    RESEARCH = "research"
    IMPLEMENT = "implement"
    REFACTOR = "refactor"
    DEBUG = "debug"
    REVIEW = "review"
    MONITOR = "monitor"
    RESPOND = "respond"
    DESIGN = "design"
    TEST = "test"
    DEPLOY = "deploy"
    GOVERN = "govern"
    DISCOVER = "discover"


class IntentGuna(str, enum.Enum):
    """Quality/mode of the intent. Maps to steward's IntentGuna."""
    TAMAS = "tamas"       # inertia, maintenance
    RAJAS = "rajas"       # action, creation
    SATTVA = "sattva"     # knowledge, observation
    SUDDHA = "suddha"     # transcendent, governance


class Function(str, enum.Enum):
    """Trinity function. BRAHMA=create, VISHNU=maintain, SHIVA=transform."""
    BRAHMA = "creator"
    VISHNU = "maintainer"
    SHIVA = "destroyer"


class Approach(str, enum.Enum):
    """MURALI cycle phase."""
    GENESIS = "genesis"
    DHARMA = "dharma"
    KARMA = "karma"
    MOKSHA = "moksha"


@dataclass(frozen=True, slots=True)
class ManasPerception:
    """Structured perception of an intent. Mirrors steward's ManasPerception."""
    action: ActionType
    guna: IntentGuna
    function: Function
    approach: Approach


# ---------------------------------------------------------------------------
# Seed computation — mirrors MahaCompression.compress() logic
# ---------------------------------------------------------------------------

def _compute_seed(text: str) -> int:
    """Deterministic seed from text. Mirrors Mahamantra VM seed generation."""
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)


def _seed_to_guna(seed: int) -> IntentGuna:
    """Map seed to guna. Mirrors MahaCompression.decode_samskara_intent().

    The distribution follows the Vedic proportion:
    - suddha: rare (12.5%)
    - sattva: uncommon (25%)
    - rajas: common (37.5%)
    - tamas: common (25%)
    """
    bucket = seed % 8
    if bucket < 2:
        return IntentGuna.TAMAS
    if bucket < 5:
        return IntentGuna.RAJAS
    if bucket < 7:
        return IntentGuna.SATTVA
    return IntentGuna.SUDDHA


def _seed_to_function(seed: int) -> Function:
    """Map seed to trinity function. Mirrors MahaBuddhi.think() function field."""
    bucket = (seed >> 8) % 3
    return [Function.BRAHMA, Function.VISHNU, Function.SHIVA][bucket]


def _seed_to_approach(seed: int) -> Approach:
    """Map seed to MURALI approach. Mirrors MahaBuddhi.think() approach field."""
    bucket = (seed >> 16) % 4
    return [Approach.GENESIS, Approach.DHARMA, Approach.KARMA, Approach.MOKSHA][bucket]


# ---------------------------------------------------------------------------
# Keyword-based overrides — supplements seed classification
# ---------------------------------------------------------------------------

# Intent keywords → ActionType (checked first, overrides seed).
# More specific patterns first — "code_analysis" should match "code" not "analysis".
_KEYWORD_ACTIONS: list[tuple[str, ActionType]] = [
    # Engineering / code (most specific first)
    ("code", ActionType.IMPLEMENT),
    ("build", ActionType.IMPLEMENT),
    ("implement", ActionType.IMPLEMENT),
    ("create", ActionType.IMPLEMENT),
    ("fix", ActionType.DEBUG),
    ("debug", ActionType.DEBUG),
    ("test", ActionType.TEST),
    ("refactor", ActionType.REFACTOR),
    ("deploy", ActionType.DEPLOY),
    ("review", ActionType.REVIEW),
    # Research / knowledge
    ("research", ActionType.RESEARCH),
    ("inquiry", ActionType.RESEARCH),
    ("question", ActionType.RESEARCH),
    ("analysis", ActionType.RESEARCH),
    ("investigate", ActionType.RESEARCH),
    # Discovery
    ("explore", ActionType.DISCOVER),
    ("discover", ActionType.DISCOVER),
    ("search", ActionType.DISCOVER),
    # Governance
    ("governance", ActionType.GOVERN),
    ("policy", ActionType.GOVERN),
    ("vote", ActionType.GOVERN),
    ("trust", ActionType.GOVERN),
    # Communication
    ("heartbeat", ActionType.MONITOR),
    ("ping", ActionType.MONITOR),
    ("status", ActionType.MONITOR),
    ("respond", ActionType.RESPOND),
    ("reply", ActionType.RESPOND),
]

# Function affinity (from steward's _FUNCTION_AFFINITY)
_FUNCTION_TO_ACTION: dict[Function, ActionType] = {
    Function.BRAHMA: ActionType.IMPLEMENT,
    Function.VISHNU: ActionType.MONITOR,
    Function.SHIVA: ActionType.REFACTOR,
}

# Approach affinity (from steward's _APPROACH_AFFINITY)
_APPROACH_TO_ACTION: dict[Approach, ActionType] = {
    Approach.GENESIS: ActionType.IMPLEMENT,
    Approach.DHARMA: ActionType.REVIEW,
    Approach.KARMA: ActionType.DEBUG,
    Approach.MOKSHA: ActionType.RESEARCH,
}

# Guna defaults (from steward's guna_defaults)
_GUNA_TO_ACTION: dict[IntentGuna, ActionType] = {
    IntentGuna.SATTVA: ActionType.RESEARCH,
    IntentGuna.RAJAS: ActionType.IMPLEMENT,
    IntentGuna.TAMAS: ActionType.DEBUG,
    IntentGuna.SUDDHA: ActionType.IMPLEMENT,
}

# ActionType → zone mapping (how Manas routes to city zones)
ACTION_ZONES: dict[ActionType, str] = {
    ActionType.RESEARCH: "research",
    ActionType.IMPLEMENT: "engineering",
    ActionType.REFACTOR: "engineering",
    ActionType.DEBUG: "engineering",
    ActionType.REVIEW: "governance",
    ActionType.MONITOR: "general",
    ActionType.RESPOND: "general",
    ActionType.DESIGN: "engineering",
    ActionType.TEST: "engineering",
    ActionType.DEPLOY: "engineering",
    ActionType.GOVERN: "governance",
    ActionType.DISCOVER: "discovery",
}

# ActionType → NADI type (how the message is typed on the wire)
ACTION_NADI: dict[ActionType, str] = {
    ActionType.RESEARCH: "udana",
    ActionType.IMPLEMENT: "prana",
    ActionType.REFACTOR: "prana",
    ActionType.DEBUG: "apana",
    ActionType.REVIEW: "samana",
    ActionType.MONITOR: "vyana",
    ActionType.RESPOND: "vyana",
    ActionType.DESIGN: "udana",
    ActionType.TEST: "apana",
    ActionType.DEPLOY: "prana",
    ActionType.GOVERN: "samana",
    ActionType.DISCOVER: "udana",
}


# ---------------------------------------------------------------------------
# Manas — The perceiving mind
# ---------------------------------------------------------------------------

def perceive(intent_str: str) -> ManasPerception:
    """Classify an intent string into a structured perception.

    Deterministic. Zero LLM. Mirrors steward's Manas.perceive().

    Priority chain:
    1. Keyword match → ActionType (most specific)
    2. Approach affinity → ActionType
    3. Function affinity → ActionType
    4. Guna default → ActionType (least specific)
    """
    seed = _compute_seed(intent_str)
    guna = _seed_to_guna(seed)
    function = _seed_to_function(seed)
    approach = _seed_to_approach(seed)

    # Try keyword match first
    action = None
    lower = intent_str.lower()
    for keyword, act in _KEYWORD_ACTIONS:
        if keyword in lower:
            action = act
            break

    # Fall back through the affinity chain (same as steward)
    if action is None:
        action = _APPROACH_TO_ACTION.get(approach)
    if action is None:
        action = _FUNCTION_TO_ACTION.get(function)
    if action is None:
        action = _GUNA_TO_ACTION.get(guna, ActionType.IMPLEMENT)

    return ManasPerception(action=action, guna=guna, function=function, approach=approach)


def route_zone(perception: ManasPerception) -> str:
    """Map a perception to an agent-city zone. Deterministic."""
    return ACTION_ZONES.get(perception.action, "general")


def route_nadi(perception: ManasPerception) -> str:
    """Map a perception to a NADI type for wire transport. Deterministic."""
    return ACTION_NADI.get(perception.action, "vyana")
