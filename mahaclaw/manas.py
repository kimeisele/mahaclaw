"""Manas — The Mind (Deterministic Router).

PrakritiElement #1 — classifies intent WITHOUT an LLM.

Mirrors steward/antahkarana/manas.py — the gold standard.
Steward uses MahaCompression + MahaBuddhi substrate primitives.
We replicate the same deterministic logic via pure stdlib:
  SHA-256 → Shabda vibration → MahaModularSynth 16-step → position → perception.

ZERO keywords. Everything derives from the seed.

Output: ManasPerception(action, guna, function, approach, position)
"""
from __future__ import annotations

import enum
import hashlib
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Mahamantra constants (from steward-protocol seed axioms/derivations)
# ---------------------------------------------------------------------------

# Tier 0 axioms (_axioms.py)
WORDS = 16              # 16 Mahamantra positions
TRINITY = 3             # 3 Names
HARE_COUNT = 8          # Hare appears 8 times
KRISHNA_COUNT = 4       # Krishna appears 4 times
RAMA_COUNT = 4          # Rama appears 4 times
HALVES = 2              # 2 halves
PANCHA = 5              # 5 elements

# Tier 1 primary (_primary.py)
QUARTERS = KRISHNA_COUNT  # 4
KSETRAJNA = TRINITY - HALVES  # 1
HALF_SIZE = WORDS // HALVES  # 8
LILA = WORDS * TRINITY  # 48
KSHETRA = WORDS + HARE_COUNT  # 24
NAVA = HARE_COUNT + KSETRAJNA  # 9
SHARANAGATI = PANCHA + KSETRAJNA  # 6

# Tier 2 secondary (_secondary.py)
MAHAJANA_COUNT = KSHETRA // HALVES  # 12
MALA = MAHAJANA_COUNT * NAVA  # 108
JIVA_CYCLE = MALA * QUARTERS  # 432
PARAMPARA = KSHETRA + MAHAJANA_COUNT + KSETRAJNA  # 37
SEVEN = HALF_SIZE - KSETRAJNA  # 7
TEN = MAHAJANA_COUNT - HALVES  # 10
NADI_RESONANCE = JIVA_CYCLE // SHARANAGATI  # 72
AKSARA_COUNT = KSHETRA + HALF_SIZE  # 32

# Tier 3 extended (_extended.py)
POSITION_SUM_HARE = sum((0, 2, 6, 7, 8, 10, 14, 15))  # 62... wait
# Actually computed from positions: sum of 0-indexed Hare positions
MAHA_QUANTUM = 137  # POSITION_SUM_TOTAL(136) + KSETRAJNA(1)

QUARTER_NAMES = ("genesis", "dharma", "karma", "moksha")

# Mahamantra word pattern: H K H K K K H H | H R H R R R H H
# Built from HALF_BINARY = (0, 1, 0, 1, 1, 1, 0, 0)
# First half: 0→H, 1→K; Second half: 0→H, 1→R
_HALF_BINARY = (0, 1, 0, 1, 1, 1, 0, 0)
WORD_PATTERN = tuple(
    "H" if _HALF_BINARY[i % HALF_SIZE] == 0
    else ("K" if i < HALF_SIZE else "R")
    for i in range(WORDS)
)
# = ("H","K","H","K","K","K","H","H","H","R","H","R","R","R","H","H")

# Position sets (from word pattern)
HARE_POSITIONS = frozenset(i for i, n in enumerate(WORD_PATTERN) if n == "H")
KRISHNA_POSITIONS = frozenset(i for i, n in enumerate(WORD_PATTERN) if n == "K")
RAMA_POSITIONS = frozenset(i for i, n in enumerate(WORD_PATTERN) if n == "R")

# Algorithm coefficients (_algorithm.py)
# H=0 (INPUT), K=1 (COMPUTE), R=2 (OUTPUT)
_OP_MAP = {"H": 0, "K": 1, "R": 2}
_MULT = (SEVEN, 1, 1)   # H*7, K*1, R*1
_ADD = (0, TEN, 0)       # H+0, K+10, R+0
_SQ = (0, 0, 1)          # H→linear, K→linear, R→square

# ADSR envelope (from maha.py)
ADSR_ATTACK = PANCHA       # 5
ADSR_DECAY = MAHAJANA_COUNT  # 12
ADSR_SUSTAIN = PANCHA       # 5
ADSR_RELEASE = MAHAJANA_COUNT  # 12


# ---------------------------------------------------------------------------
# Sanskrit phoneme map (from shabda.py — the real phonetic vibration)
# ---------------------------------------------------------------------------

# ArticulationPoint: KANTHA=0, TALU=1, MURDHA=2, DANTA=3, OSHTHA=4
# VoicingType: UNVOICED=0, UNVOICED_ASPIRATED=1, VOICED=2, VOICED_ASPIRATED=3
# signature_id = (articulation * 4 + voicing) * NADI_RESONANCE + base_freq * AKSARA_COUNT + duration

_PHONEME_MAP: dict[str, tuple[int, int, int, int]] = {
    # (articulation, voicing, base_frequency, duration_ratio)
    # VOWELS
    "a":  (0, 2, 72, 1),
    "e":  (1, 2, 108, 2),
    "i":  (1, 2, 72, 1),
    "o":  (4, 2, 108, 2),
    "u":  (4, 2, 72, 1),
    # CONSONANTS (English letter → Sanskrit articulation)
    "b":  (4, 2, 48, 1),
    "c":  (0, 0, 48, 1),
    "d":  (3, 2, 48, 1),
    "f":  (4, 0, 48, 1),
    "g":  (0, 2, 48, 1),
    "h":  (0, 3, 72, 1),
    "j":  (1, 2, 48, 1),
    "k":  (0, 0, 48, 1),
    "l":  (2, 2, 48, 1),
    "m":  (4, 2, 48, 1),
    "n":  (3, 2, 48, 1),
    "p":  (4, 0, 48, 1),
    "q":  (0, 0, 48, 1),
    "r":  (2, 2, 48, 1),
    "s":  (3, 0, 36, 1),
    "t":  (3, 0, 48, 1),
    "v":  (4, 2, 48, 1),
    "w":  (4, 2, 48, 1),
    "x":  (0, 0, 36, 1),
    "y":  (1, 2, 54, 1),
    "z":  (3, 2, 36, 1),
    # Multi-char (checked first by shabda.py)
    "ha": (0, 3, 72, 1),
    "re": (2, 2, 72, 1),
    "ma": (4, 2, 48, 1),
    "ai": (1, 2, 144, 2),
    "au": (4, 2, 144, 2),
}


def _signature_id(articulation: int, voicing: int, base_freq: int, duration: int) -> int:
    """VibrationSignature.signature_id — mirrors shabda.py."""
    return (articulation * QUARTERS + voicing) * NADI_RESONANCE + base_freq * AKSARA_COUNT + duration


def _text_to_vibration_sum(text: str) -> int:
    """Convert text to sum of vibration signature IDs.

    Mirrors shabda.text_to_vibration() + sum(sig.signature_id for sig in vibrations).
    Multi-char phonemes checked first (length 3, then 2), then single chars.
    """
    text_lower = text.lower()
    total = 0
    i = 0
    while i < len(text_lower):
        found = False
        # Check multi-char phonemes first (lengths 3, then 2) — mirrors shabda.py
        for length in (TRINITY, HALVES):  # 3, 2
            if i + length <= len(text_lower):
                chunk = text_lower[i:i + length]
                if chunk in _PHONEME_MAP:
                    total += _signature_id(*_PHONEME_MAP[chunk])
                    i += length
                    found = True
                    break
        if not found:
            char = text_lower[i]
            if char in _PHONEME_MAP:
                total += _signature_id(*_PHONEME_MAP[char])
            i += KSETRAJNA  # 1
    return total


# ---------------------------------------------------------------------------
# MahaModularSynth transform (16-step, from maha.py — the REAL algorithm)
# ---------------------------------------------------------------------------

def _synth_transform(seed: int) -> int:
    """MahaModularSynth.transform() with 'quantum' preset.

    Exact port of steward-protocol/substrate/algorithm/maha.py.
    16-step Maha Algorithm with ADSR envelope, LFO, and feedback.

    Preset 'quantum': mod_space=137, feedback=1, lfo_enabled=True, lfo_rate=4.
    """
    mod = MAHA_QUANTUM  # 137
    feedback = KSETRAJNA  # 1
    lfo_rate = QUARTERS  # 4

    value = seed % mod
    feedback_acc = 0

    # ADSR table indexed by phase (0-3)
    adsr_table = (ADSR_ATTACK, ADSR_DECAY, ADSR_SUSTAIN, ADSR_RELEASE)  # (5, 12, 5, 12)

    for step_idx in range(WORDS):  # 16 steps
        name = WORD_PATTERN[step_idx]
        # position is 1-indexed in steward (step.position = pos + 1)
        position_1 = step_idx + KSETRAJNA

        # Effective position (no phase_offset in quantum preset)
        effective_pos = ((position_1 - KSETRAJNA) % WORDS) + KSETRAJNA

        # LFO modulation (lfo_enabled=True in quantum preset)
        binary_val = 0 if name == "H" else KSETRAJNA  # BINARY_PATTERN
        phase_in_lfo = (position_1 - KSETRAJNA) % lfo_rate
        lfo = binary_val * phase_in_lfo

        # ADSR by phase (phase index = step_idx // QUARTERS)
        phase_idx = step_idx // QUARTERS
        adsr = adsr_table[phase_idx]

        # Branchless operation
        op = _OP_MAP[name]

        # Coefficients per operation type:
        # HARE(0): mult=SEVEN*adsr, add=lfo
        # KRISHNA(1): mult=1, add=TEN+effective_pos+feedback_acc
        # RAMA(2): mult=1, add=feedback_acc
        mult_coeff = (SEVEN * adsr, KSETRAJNA, KSETRAJNA)[op]
        add_coeff = (lfo, TEN + effective_pos + feedback_acc, feedback_acc)[op]

        v = (value * mult_coeff + add_coeff) % mod
        squared = (v * v) % mod
        value = _SQ[op] * squared + (KSETRAJNA - _SQ[op]) * v

        feedback_acc = (feedback_acc + value * feedback) % mod

    return value


# ---------------------------------------------------------------------------
# Seed computation — mirrors _compute_seed_cached() from compression.py
# ---------------------------------------------------------------------------

def _compute_seed(text: str) -> int:
    """Full seed pipeline. Exact port of MahaCompression._compute_seed_cached().

    Pipeline:
    1. SHA-256(text.lower()) → first 4 bytes as big-endian int
    2. text_to_vibration() → sum of signature IDs
    3. XOR hash with vibration_sum → merged
    4. merged % WORDS → category
    5. (category * MAHA_QUANTUM) + (merged % MAHA_QUANTUM) → base_seed
    6. MahaModularSynth('quantum').transform(base_seed) → transformed
    7. transformed % MAHA_QUANTUM → attractor
    8. (category << 24) | (transformed << 12) | attractor → final_seed
    """
    lower = text.lower()

    # Layer 1: SHA-256 hash (structural identity)
    text_bytes = hashlib.sha256(lower.encode("utf-8")).digest()
    text_hash = int.from_bytes(text_bytes[:4], "big")

    # Layer 2: Shabda vibration sum (phonetic identity)
    vibration_sum = _text_to_vibration_sum(text)

    # Merge: XOR hash with vibration_sum
    merged = text_hash ^ (vibration_sum & 0xFFFFFFFF)

    category = merged % WORDS
    base_seed = (category * MAHA_QUANTUM) + (merged % MAHA_QUANTUM)

    transformed = _synth_transform(base_seed)
    attractor = transformed % MAHA_QUANTUM

    final_seed = (category << 24) | (transformed << 12) | attractor
    return final_seed & 0xFFFFFFFF


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
    TAMAS = "tamas"       # Quarter 0 (positions 0-3)
    RAJAS = "rajas"       # Quarter 1 (positions 4-7)
    SATTVA = "sattva"     # Quarter 2 (positions 8-11)
    SUDDHA = "suddha"     # Quarter 3 (positions 12-15)


class Function(str, enum.Enum):
    """Trinity function from position. Hare=carrier, Krishna=source, Rama=deliverer."""
    CARRIER = "carrier"       # Hare positions
    SOURCE = "source"         # Krishna positions
    DELIVERER = "deliverer"   # Rama positions


class Approach(str, enum.Enum):
    """MURALI cycle phase. Derived from quarter (vm_position // 4)."""
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
    position: int  # VM position (attractor % 16)


# ---------------------------------------------------------------------------
# Position → perception components
# ---------------------------------------------------------------------------

# Guna from seed position (seed % WORDS → quarter → guna)
# From decode_samskara_intent(): quarter 0=TAMAS, 1=RAJAS, 2=SATTVA, 3=SUDDHA
_QUARTER_TO_GUNA = (IntentGuna.TAMAS, IntentGuna.RAJAS, IntentGuna.SATTVA, IntentGuna.SUDDHA)


def _position_to_guna(guna_position: int) -> IntentGuna:
    """Guna from seed position. Mirrors decode_samskara_intent().

    position = seed % WORDS
    quarter = position // QUARTERS
    ALL_INTENT_LEVELS[quarter].guna
    """
    quarter = guna_position // QUARTERS
    return _QUARTER_TO_GUNA[quarter]


def _position_to_function(vm_position: int) -> Function:
    """Trinity function from VM position (attractor % WORDS)."""
    if vm_position in HARE_POSITIONS:
        return Function.CARRIER
    if vm_position in KRISHNA_POSITIONS:
        return Function.SOURCE
    if vm_position in RAMA_POSITIONS:
        return Function.DELIVERER
    return Function.CARRIER  # unreachable


def _position_to_approach(vm_position: int) -> Approach:
    """Approach from VM position quarter."""
    quarter_idx = vm_position // QUARTERS
    return (Approach.GENESIS, Approach.DHARMA, Approach.KARMA, Approach.MOKSHA)[quarter_idx]


# ---------------------------------------------------------------------------
# Affinity chains — ActionType from perception (steward gold standard)
# ---------------------------------------------------------------------------

# From steward/antahkarana/manas.py
_APPROACH_TO_ACTION: dict[Approach, ActionType] = {
    Approach.GENESIS: ActionType.IMPLEMENT,
    Approach.DHARMA: ActionType.REVIEW,
    Approach.KARMA: ActionType.DEBUG,
    Approach.MOKSHA: ActionType.RESEARCH,
}

_FUNCTION_TO_ACTION: dict[str, ActionType] = {
    "creator": ActionType.IMPLEMENT,
    "maintainer": ActionType.MONITOR,
    "destroyer": ActionType.REFACTOR,
    "carrier": ActionType.IMPLEMENT,
    "deliverer": ActionType.RESPOND,
    "enhancer": ActionType.REFACTOR,
}

_GUNA_TO_ACTION: dict[IntentGuna, ActionType] = {
    IntentGuna.SATTVA: ActionType.RESEARCH,
    IntentGuna.RAJAS: ActionType.IMPLEMENT,
    IntentGuna.TAMAS: ActionType.DEBUG,
    IntentGuna.SUDDHA: ActionType.IMPLEMENT,
}

# ActionType → zone mapping
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

# ActionType → NADI type
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
    1. text → seed (_compute_seed: SHA-256 + Shabda vibration + MahaModularSynth)
    2. Guna from seed: seed % WORDS → quarter → TAMAS/RAJAS/SATTVA/SUDDHA
    3. Function/Approach from VM: synth_transform(seed) % WORDS → position
       → trinity_function (carrier/source/deliverer)
       → quarter (genesis/dharma/karma/moksha)
    4. ActionType: approach > function > guna (affinity chain)
    """
    seed = _compute_seed(intent_str)

    # Guna from seed position (MahaCompression.decode_samskara_intent)
    guna_position = seed % WORDS
    guna = _position_to_guna(guna_position)

    # Function and approach from VM position (MahaBuddhi.think → Lotus VM)
    attractor = _synth_transform(seed)
    vm_position = attractor % WORDS
    function = _position_to_function(vm_position)
    approach = _position_to_approach(vm_position)

    # ActionType via priority chain (same as steward)
    action = _APPROACH_TO_ACTION.get(approach)
    if action is None:
        action = _FUNCTION_TO_ACTION.get(function.value)
    if action is None:
        action = _GUNA_TO_ACTION.get(guna, ActionType.IMPLEMENT)

    return ManasPerception(
        action=action,
        guna=guna,
        function=function,
        approach=approach,
        position=vm_position,
    )


def route_zone(perception: ManasPerception) -> str:
    """Map a perception to an agent-city zone. Deterministic."""
    return ACTION_ZONES.get(perception.action, "general")


def route_nadi(perception: ManasPerception) -> str:
    """Map a perception to a NADI type for wire transport. Deterministic."""
    return ACTION_NADI.get(perception.action, "vyana")
