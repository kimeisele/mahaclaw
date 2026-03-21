"""Manas — The Mind (Deterministic Router).

PrakritiElement #1 — classifies intent WITHOUT an LLM.

Mirrors steward/antahkarana/manas.py — the gold standard.
Steward uses MahaCompression + MahaBuddhi substrate primitives.
We replicate the same deterministic logic via pure stdlib:
  SHA-256 → phonetic vibration → MahaModularSynth → position → perception.

ZERO keywords. Everything derives from the seed.

Output: ManasPerception(action, guna, function, approach, position)
"""
from __future__ import annotations

import enum
import hashlib
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Mahamantra constants (from steward-protocol seed axioms)
# ---------------------------------------------------------------------------

WORDS = 16              # 16 Mahamantra positions
QUARTERS = 4            # 4 quarters of 4 positions each
MAHA_QUANTUM = 137      # Sacred prime (steward-protocol _secondary.py)
PARAMPARA = 37           # Succession constant (steward-protocol _secondary.py)
HEAD_POSITIONS = (0, 4, 8, 12)  # Quarter heads (steward-protocol _primary.py)
QUARTER_NAMES = ("genesis", "dharma", "karma", "moksha")

# Hare/Krishna/Rama position sets (steward-protocol _extended.py)
HARE_POSITIONS = frozenset({0, 2, 6, 7, 8, 10, 14, 15})
KRISHNA_POSITIONS = frozenset({1, 3, 4, 5})
RAMA_POSITIONS = frozenset({9, 11, 12, 13})

# Guna opcode sets (steward-protocol guna.py)
# Each position 0-15 maps to a MantraOpCode, each opcode to a guna.
SATTVA_POSITIONS = frozenset({6, 7, 14, 15})
RAJAS_POSITIONS = frozenset({0, 1, 2, 4, 5, 8, 9, 10, 11})
TAMAS_POSITIONS = frozenset({3, 12, 13})


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
    """Trinity function from position. Hare=carrier, Krishna=source, Rama=deliverer."""
    CARRIER = "carrier"       # Hare positions — transport/build
    SOURCE = "source"         # Krishna positions — originate/maintain
    DELIVERER = "deliverer"   # Rama positions — deliver/respond


class Approach(str, enum.Enum):
    """MURALI cycle phase. Derived from quarter (position // 4)."""
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
    position: int  # 0-15 Mahamantra position


# ---------------------------------------------------------------------------
# Seed computation — mirrors MahaCompression.compress() pipeline
# ---------------------------------------------------------------------------

def _phonetic_vibration(text: str) -> int:
    """Phonetic vibration sum. Mirrors MahaCompression phonetic component.

    Sanskrit-inspired: each character's ordinal weighted by position,
    producing a deterministic vibration signature of the text.
    """
    return sum(ord(c) * (i + 1) for i, c in enumerate(text)) & 0xFFFFFFFF


def _synth_transform(seed: int) -> int:
    """MahaModularSynth deterministic transform.

    Uses Mahamantra constants (MAHA_QUANTUM=137, PARAMPARA=37) for
    modular arithmetic mixing. Mirrors MahaModularSynth("quantum").transform().
    """
    x = seed & 0xFFFFFFFF
    x = (x * MAHA_QUANTUM + PARAMPARA) & 0xFFFFFFFF
    x = x ^ (x >> 13)
    x = (x * MAHA_QUANTUM) & 0xFFFFFFFF
    x = x ^ (x >> 17)
    return x


def _compute_seed(text: str) -> int:
    """Full seed pipeline. Mirrors MahaCompression.compress().

    Steps (from steward-protocol compression.py):
    1. SHA-256(text.lower()) → raw hash integer
    2. XOR with phonetic vibration sum → merged
    3. merged % WORDS → category (which of 16 positions)
    4. (category * MAHA_QUANTUM) + (merged % MAHA_QUANTUM) → base_seed
    5. MahaModularSynth.transform(base_seed) → transformed
    6. transformed % MAHA_QUANTUM → attractor_component
    7. Bit-pack: (category << 24) | (transformed << 12) | attractor_component → final_seed
    """
    lower = text.lower()
    raw = int(hashlib.sha256(lower.encode()).hexdigest()[:8], 16)
    vibration = _phonetic_vibration(lower)
    merged = raw ^ vibration

    category = merged % WORDS
    base_seed = (category * MAHA_QUANTUM) + (merged % MAHA_QUANTUM)

    transformed = _synth_transform(base_seed)
    attractor_component = transformed % MAHA_QUANTUM

    final_seed = ((category << 24) | (transformed << 12) | attractor_component) & 0xFFFFFFFF
    return final_seed


def _seed_to_position(seed: int) -> int:
    """Position from seed. Mirrors Lotus pada_sevanam() + dasyam().

    attractor = synth_transform(seed)
    position = attractor % WORDS
    """
    attractor = _synth_transform(seed)
    return attractor % WORDS


# ---------------------------------------------------------------------------
# Position → perception components (all deterministic from position)
# ---------------------------------------------------------------------------

def _position_to_guna(position: int) -> IntentGuna:
    """Map position to guna via MantraOpCode sets.

    From steward-protocol guna.py:
    - SATTVA_OPCODES = {6, 7, 14, 15}
    - RAJAS_OPCODES = {0, 1, 2, 4, 5, 8, 9, 10, 11}
    - TAMAS_OPCODES = {3, 12, 13}
    """
    if position in SATTVA_POSITIONS:
        return IntentGuna.SATTVA
    if position in TAMAS_POSITIONS:
        return IntentGuna.TAMAS
    return IntentGuna.RAJAS


def _position_to_function(position: int) -> Function:
    """Map position to trinity function via Hare/Krishna/Rama sets.

    From steward-protocol _extended.py:
    - HARE positions → carrier (transport/build)
    - KRISHNA positions → source (originate/maintain)
    - RAMA positions → deliverer (deliver/respond)
    """
    if position in HARE_POSITIONS:
        return Function.CARRIER
    if position in KRISHNA_POSITIONS:
        return Function.SOURCE
    if position in RAMA_POSITIONS:
        return Function.DELIVERER
    return Function.CARRIER  # unreachable but safe


def _position_to_approach(position: int) -> Approach:
    """Map position to approach via quarter.

    From steward-protocol _primary.py:
    quarter = position // QUARTERS
    0-3: genesis, 4-7: dharma, 8-11: karma, 12-15: moksha
    """
    quarter_idx = position // QUARTERS
    return [Approach.GENESIS, Approach.DHARMA, Approach.KARMA, Approach.MOKSHA][quarter_idx]


# ---------------------------------------------------------------------------
# Affinity chains — ActionType from perception (steward gold standard)
# ---------------------------------------------------------------------------

# Approach affinity (from steward/antahkarana/manas.py _APPROACH_AFFINITY)
_APPROACH_TO_ACTION: dict[Approach, ActionType] = {
    Approach.GENESIS: ActionType.IMPLEMENT,
    Approach.DHARMA: ActionType.REVIEW,
    Approach.KARMA: ActionType.DEBUG,
    Approach.MOKSHA: ActionType.RESEARCH,
}

# Function affinity (from steward/antahkarana/manas.py _FUNCTION_AFFINITY)
_FUNCTION_TO_ACTION: dict[Function, ActionType] = {
    Function.CARRIER: ActionType.IMPLEMENT,
    Function.SOURCE: ActionType.MONITOR,
    Function.DELIVERER: ActionType.RESPOND,
}

# Guna defaults (from steward/antahkarana/manas.py guna_defaults)
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

    Deterministic. Zero LLM. Zero keywords. Pure seed.
    Mirrors steward/antahkarana/manas.py gold standard.

    Pipeline:
    1. text → seed (SHA-256 + phonetic vibration + MahaModularSynth)
    2. seed → position (synth_transform + mod 16)
    3. position → guna, function, approach (lookup tables)
    4. approach → ActionType (primary affinity)
       function → ActionType (secondary affinity)
       guna → ActionType (tertiary default)
    """
    seed = _compute_seed(intent_str)
    position = _seed_to_position(seed)

    guna = _position_to_guna(position)
    function = _position_to_function(position)
    approach = _position_to_approach(position)

    # Affinity chain: approach > function > guna (same as steward)
    action = _APPROACH_TO_ACTION.get(approach)
    if action is None:
        action = _FUNCTION_TO_ACTION.get(function)
    if action is None:
        action = _GUNA_TO_ACTION.get(guna, ActionType.IMPLEMENT)

    return ManasPerception(
        action=action,
        guna=guna,
        function=function,
        approach=approach,
        position=position,
    )


def route_zone(perception: ManasPerception) -> str:
    """Map a perception to an agent-city zone. Deterministic."""
    return ACTION_ZONES.get(perception.action, "general")


def route_nadi(perception: ManasPerception) -> str:
    """Map a perception to a NADI type for wire transport. Deterministic."""
    return ACTION_NADI.get(perception.action, "vyana")
