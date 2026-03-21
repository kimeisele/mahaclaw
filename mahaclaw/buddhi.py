"""Buddhi — Intellect / Antahkarana Coordinator.

PrakritiElement #3 — Protocol Layer: decision
Category: ANTAHKARANA (Internal Instrument)

BG 3.42: "The senses are higher than the body, the mind (Manas) is higher
than the senses, the intelligence (Buddhi) is higher than the mind, and
the soul is higher than the intelligence."

Buddhi is the DRIVER of the chariot (Katha Upanishad). It OWNS Manas, Chitta,
and Gandha as internal components and orchestrates them as ONE cognitive unit.

Buddhi DISCRIMINATES (Viveka) between Sat and Asat by reading:
  1. Manas perception — what IS this intent? (action, guna, function, approach)
  2. Chitta state — what HAS happened? (impressions, phase, prior_reads)
  3. Gandha signals — what patterns EMERGE? (consecutive errors, blind writes)

Then it DECIDES: allowed tools, model tier, max_tokens, phase constraints.

The philosophical test: "If I remove the LLM entirely, does Buddhi still
make correct decisions?" → YES. Everything here is deterministic.

Narasimha (kill-switch) runs BEFORE Buddhi — see narasimha.py.
Narasimha blocks dangerous strings. Buddhi discriminates with intelligence.

Mirrors steward/buddhi.py (618 lines). Pure stdlib.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field

from mahaclaw.chitta import (
    Chitta,
    ExecutionPhase,
    Impression,
    VerdictAction,
    Detection,
    detect_patterns,
)
from mahaclaw.manas import (
    ActionType,
    IntentGuna,
    Function,
    Approach,
    ManasPerception,
    perceive,
)
from mahaclaw.narasimha import gate as narasimha_gate
from mahaclaw.pani import (
    ToolNamespace,
    resolve_namespaces,
    resolve_action_tools,
    _ACTION_NAMESPACES,
)


# ---------------------------------------------------------------------------
# ModelTier — resource allocation (mirrors steward/buddhi.py)
# ---------------------------------------------------------------------------

class ModelTier(str, enum.Enum):
    """LLM resource tier. Buddhi selects this WITHOUT the LLM."""
    FLASH = "flash"         # Fast, cheap, read-only tasks
    STANDARD = "standard"   # Normal development work
    PRO = "pro"             # Complex design, architecture


# ---------------------------------------------------------------------------
# Constants — ported from steward/buddhi.py gold standard
# ---------------------------------------------------------------------------

# Action → task weight (DSP signal: how "write-heavy" is this action?)
_ACTION_WEIGHT: dict[ActionType, float] = {
    ActionType.RESEARCH: 0.0,
    ActionType.IMPLEMENT: 1.0,
    ActionType.DEBUG: 1.0,
    ActionType.REFACTOR: 0.8,
    ActionType.REVIEW: 0.2,
    ActionType.MONITOR: 0.0,
    ActionType.RESPOND: 0.5,
    ActionType.DESIGN: 0.3,
    ActionType.TEST: 0.8,
    ActionType.DEPLOY: 0.6,
    ActionType.GOVERN: 0.1,
    ActionType.DISCOVER: 0.0,
}

# Action → base model tier
_ACTION_TIER: dict[ActionType, ModelTier] = {
    ActionType.RESEARCH: ModelTier.FLASH,
    ActionType.IMPLEMENT: ModelTier.STANDARD,
    ActionType.DEBUG: ModelTier.STANDARD,
    ActionType.REFACTOR: ModelTier.STANDARD,
    ActionType.REVIEW: ModelTier.FLASH,
    ActionType.MONITOR: ModelTier.FLASH,
    ActionType.RESPOND: ModelTier.STANDARD,
    ActionType.DESIGN: ModelTier.PRO,
    ActionType.TEST: ModelTier.STANDARD,
    ActionType.DEPLOY: ModelTier.STANDARD,
    ActionType.GOVERN: ModelTier.FLASH,
    ActionType.DISCOVER: ModelTier.FLASH,
}

# Phase → modulation factor (DSP: how much to scale task_weight)
_PHASE_MODULATION: dict[ExecutionPhase, float] = {
    ExecutionPhase.ORIENT: 0.5,
    ExecutionPhase.EXECUTE: 1.0,
    ExecutionPhase.VERIFY: 0.5,
    ExecutionPhase.COMPLETE: 0.5,
}

# Phase → namespace overlay (what namespaces are ALLOWED in this phase)
# ORIENT: read-only (no overlay — base action namespaces only)
# EXECUTE: full access (add MODIFY + EXECUTE)
# VERIFY: no new writes (OBSERVE + EXECUTE for running tests)
# COMPLETE: wrap up (OBSERVE only)
_PHASE_NS_OVERLAY: dict[ExecutionPhase, frozenset[ToolNamespace]] = {
    ExecutionPhase.ORIENT: frozenset(),
    ExecutionPhase.EXECUTE: frozenset({ToolNamespace.MODIFY, ToolNamespace.EXECUTE}),
    ExecutionPhase.VERIFY: frozenset({ToolNamespace.OBSERVE, ToolNamespace.EXECUTE}),
    ExecutionPhase.COMPLETE: frozenset({ToolNamespace.OBSERVE}),
}

# Guna → namespace fallback (if action has no tools, use guna)
_GUNA_NAMESPACES: dict[IntentGuna, frozenset[ToolNamespace]] = {
    IntentGuna.SATTVA: frozenset({ToolNamespace.OBSERVE}),
    IntentGuna.RAJAS: frozenset({ToolNamespace.OBSERVE, ToolNamespace.MODIFY, ToolNamespace.EXECUTE}),
    IntentGuna.TAMAS: frozenset({ToolNamespace.OBSERVE, ToolNamespace.MODIFY}),
    IntentGuna.SUDDHA: frozenset({ToolNamespace.OBSERVE, ToolNamespace.MODIFY, ToolNamespace.EXECUTE, ToolNamespace.DELEGATE}),
}

# Guardians that trigger tier escalation (from RAMA encoding)
_GUARDIAN_ESCALATE = frozenset({
    "nrisimha", "prahlada", "shambhu", "kumaras",
})

# Phase transition guidance messages
_PHASE_GUIDANCE: dict[tuple[str, str], str] = {
    ("EXECUTE", "VERIFY"): "Consider running tests to verify your changes.",
    ("VERIFY", "COMPLETE"): "Changes verified. Prepare final summary.",
    ("ORIENT", "EXECUTE"): "Understanding gathered. Begin implementation.",
}

# Valid priorities and NADI types (for intent validation)
VALID_PRIORITIES = frozenset({"tamas", "rajas", "sattva", "suddha"})
VALID_NADI_TYPES = frozenset({"prana", "apana", "vyana", "udana", "samana"})

# Restricted targets (elevated trust required)
_RESTRICTED_TARGETS = frozenset({"steward", "agent-world"})

# Tier ordering for escalation/demotion
_TIER_ORDER = (ModelTier.FLASH, ModelTier.STANDARD, ModelTier.PRO)


# ---------------------------------------------------------------------------
# HebbianSynaptic — learning signal (mirrors steward/buddhi.py)
# ---------------------------------------------------------------------------

class HebbianSynaptic:
    """Hebbian synaptic learning — success strengthens, failure weakens.

    From Prabhupada: "By practice and detachment, one can control the mind."
    The synaptic weights encode accumulated practice — what works and what doesn't.

    Success: w += 0.1 * (1 - w) → asymptotic to 1.0
    Failure: w -= 0.1 * w → asymptotic to 0.0
    """

    def __init__(self) -> None:
        self._weights: dict[str, float] = {}

    def update(self, tool_name: str, success: bool) -> None:
        """Update weight after tool execution."""
        w = self._weights.get(tool_name, 0.5)
        if success:
            w += 0.1 * (1 - w)
        else:
            w -= 0.1 * w
        self._weights[tool_name] = w

    @property
    def confidence(self) -> float:
        """Average confidence across all tracked tools."""
        if not self._weights:
            return 0.5
        return sum(self._weights.values()) / len(self._weights)

    def weight(self, tool_name: str) -> float:
        """Get weight for a specific tool."""
        return self._weights.get(tool_name, 0.5)

    @property
    def weights(self) -> dict[str, float]:
        """Snapshot of all weights."""
        return dict(self._weights)


# ---------------------------------------------------------------------------
# BuddhiVerdict — post-execution judgment
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BuddhiVerdict:
    """Buddhi's post-execution verdict (from evaluate)."""
    action: VerdictAction
    reason: str = ""
    suggestion: str = ""


# ---------------------------------------------------------------------------
# BuddhiDirective — pre-flight instruction set
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class BuddhiDirective:
    """Buddhi's pre-flight directive — the complete instruction set for a turn.

    This is what Buddhi DECIDES before the LLM runs:
      - What tools are allowed?
      - What model tier to use?
      - How many tokens?
      - What phase constraints apply?
    """
    allowed_tools: frozenset[str]
    tier: ModelTier
    max_tokens: int
    phase: ExecutionPhase
    action: ActionType
    guna: IntentGuna
    namespaces: frozenset[ToolNamespace]


# ---------------------------------------------------------------------------
# CBR Signal Processing (mirrors steward/buddhi.py process_cbr)
# ---------------------------------------------------------------------------

def _process_cbr(effective_weight: float) -> int:
    """Convert effective weight to max_tokens via DSP curve.

    Maps 0.0 → 1024, 1.0 → 4096 (linear interpolation).
    """
    return int(1024 + effective_weight * 3072)


def _escalate_tier(tier: ModelTier) -> ModelTier:
    """Move tier up one level."""
    idx = _TIER_ORDER.index(tier)
    return _TIER_ORDER[min(idx + 1, len(_TIER_ORDER) - 1)]


def _demote_tier(tier: ModelTier) -> ModelTier:
    """Move tier down one level."""
    idx = _TIER_ORDER.index(tier)
    return _TIER_ORDER[max(idx - 1, 0)]


# ---------------------------------------------------------------------------
# Buddhi — The Antahkarana Coordinator
# ---------------------------------------------------------------------------

class Buddhi:
    """Buddhi — Intellect / Discrimination / Chariot Driver.

    Owns and coordinates the four Antahkarana components:
      - Manas: perceive(intent) → ManasPerception
      - Chitta: impression storage → ExecutionPhase
      - Gandha: detect_patterns(impressions) → Detection
      - Hebbian: synaptic learning → confidence

    Two main operations:
      - pre_flight(): BEFORE tool execution — decide tools, tier, tokens
      - evaluate(): AFTER tool execution — judge results, detect patterns
    """

    def __init__(self) -> None:
        self.chitta = Chitta()
        self.synaptic = HebbianSynaptic()
        # Cached from first pre_flight (Manas perceives ONCE per session)
        self._perception: ManasPerception | None = None
        self._last_phase: ExecutionPhase | None = None

    @property
    def perception(self) -> ManasPerception | None:
        return self._perception

    def pre_flight(
        self,
        user_message: str,
        round_num: int = 0,
        context_pct: float = 0.0,
        guardian: str = "",
    ) -> BuddhiDirective:
        """Pre-flight discrimination — decide everything BEFORE the LLM runs.

        Pipeline (mirrors steward/buddhi.py exactly):
          1. Round 0: Manas.perceive() → cache perception
          2. Action → namespace → base_tools
          3. Guna fallback if no tools
          4. Phase overlay from Chitta
          5. DSP: task_weight × phase_mod → effective_weight → max_tokens
          6. Error recovery: 2+ recent errors → add bash
          7. Tier: action → Hebbian → guardian → phase → context pressure
        """
        # Step 1: Manas perceives ONCE (round 0)
        if round_num == 0 or self._perception is None:
            self._perception = perceive(user_message)
        perception = self._perception

        # Step 2: Action → namespace → base tools
        action_ns = _ACTION_NAMESPACES.get(
            perception.action,
            frozenset({ToolNamespace.OBSERVE}),
        )

        # Step 3: Guna fallback (if action gives no tools)
        if not action_ns:
            action_ns = _GUNA_NAMESPACES.get(
                perception.guna,
                frozenset({ToolNamespace.OBSERVE}),
            )

        # Step 4: Phase overlay from Chitta
        phase = self.chitta.phase
        phase_ns = _PHASE_NS_OVERLAY.get(phase, frozenset())

        if phase == ExecutionPhase.ORIENT:
            # ORIENT: restrict to OBSERVE only (read before you write)
            effective_ns = action_ns & frozenset({ToolNamespace.OBSERVE})
            if not effective_ns:
                effective_ns = frozenset({ToolNamespace.OBSERVE})
        elif phase == ExecutionPhase.COMPLETE:
            # COMPLETE: OBSERVE only
            effective_ns = frozenset({ToolNamespace.OBSERVE})
        elif phase == ExecutionPhase.VERIFY:
            # VERIFY: OBSERVE + EXECUTE (run tests, no new writes)
            effective_ns = action_ns & phase_ns
            if not effective_ns:
                effective_ns = frozenset({ToolNamespace.OBSERVE})
        else:
            # EXECUTE: full action namespaces
            effective_ns = action_ns

        # Resolve to concrete tool names
        base_tools = resolve_namespaces(effective_ns)

        # Step 6: Error recovery — 2+ recent errors → inject bash
        recent = self.chitta.recent(3)
        recent_errors = sum(1 for r in recent if not r.success)
        if recent_errors >= 2 and "bash" not in base_tools:
            base_tools = base_tools | frozenset({"bash"})

        # Step 5: DSP signal chain
        task_weight = _ACTION_WEIGHT.get(perception.action, 0.5)
        phase_mod = _PHASE_MODULATION.get(phase, 0.5)
        effective_weight = task_weight * phase_mod
        max_tokens = _process_cbr(effective_weight)

        # Step 7: Tier selection (5-layer cascade)
        # Layer 1: Base tier from action
        tier = _ACTION_TIER.get(perception.action, ModelTier.STANDARD)

        # Layer 2: Hebbian adjustment
        confidence = self.synaptic.confidence
        if confidence < 0.25:
            tier = ModelTier.PRO
        elif confidence < 0.4:
            tier = _escalate_tier(tier)

        # Layer 3: Guardian modulation
        if guardian in _GUARDIAN_ESCALATE:
            tier = _escalate_tier(tier)

        # Layer 4: Phase demotion (PRO → STANDARD in VERIFY/COMPLETE)
        if phase in (ExecutionPhase.VERIFY, ExecutionPhase.COMPLETE):
            if tier == ModelTier.PRO:
                tier = _demote_tier(tier)

        # Layer 5: Context pressure (≥70% → FLASH)
        if context_pct >= 0.7:
            tier = ModelTier.FLASH

        return BuddhiDirective(
            allowed_tools=base_tools,
            tier=tier,
            max_tokens=max_tokens,
            phase=phase,
            action=perception.action,
            guna=perception.guna,
            namespaces=effective_ns,
        )

    def evaluate(
        self,
        tool_calls: list[tuple[str, int, bool, str, str]] | None = None,
    ) -> BuddhiVerdict:
        """Post-execution evaluation — judge results via Gandha.

        Pipeline:
          1. Record impressions in Chitta (if provided)
          2. Update Hebbian weights
          3. Run Gandha pattern detection
          4. Tool failure → REDIRECT
          5. Phase transition → REFLECT with guidance

        Args:
            tool_calls: List of (name, params_hash, success, error, path) tuples.
        """
        # Step 1 + 2: Record and learn
        if tool_calls:
            for name, ph, success, error, path in tool_calls:
                self.chitta.record(name, ph, success, error=error, path=path)
                self.synaptic.update(name, success)

        # Step 3: Gandha detection
        detection = detect_patterns(self.chitta.impressions, self.chitta.prior_reads)
        if detection is not None:
            return BuddhiVerdict(
                action=detection.severity,
                reason=detection.reason,
                suggestion=detection.suggestion,
            )

        # Step 4: Recent tool failure → REDIRECT
        recent = self.chitta.recent(1)
        if recent and not recent[0].success:
            return BuddhiVerdict(
                action=VerdictAction.REDIRECT,
                reason=f"Tool '{recent[0].name}' failed: {recent[0].error}",
                suggestion="try a different approach",
            )

        # Step 5: Phase transition guidance
        current_phase = self.chitta.phase
        if self._last_phase is not None and self._last_phase != current_phase:
            guidance_key = (self._last_phase.value, current_phase.value)
            guidance = _PHASE_GUIDANCE.get(guidance_key, "")
            if guidance:
                self._last_phase = current_phase
                return BuddhiVerdict(
                    action=VerdictAction.REFLECT,
                    reason=f"Phase transition: {guidance_key[0]} → {guidance_key[1]}",
                    suggestion=guidance,
                )
        self._last_phase = current_phase

        return BuddhiVerdict(action=VerdictAction.CONTINUE)

    def end_turn(self) -> None:
        """End current turn — Chitta merges reads, clears impressions."""
        self.chitta.end_turn()

    def chitta_summary(self) -> dict[str, object]:
        """Cross-turn state for persistence."""
        return self.chitta.to_summary()

    def synaptic_weights(self) -> dict[str, float]:
        """Current Hebbian weights snapshot."""
        return self.synaptic.weights


# ---------------------------------------------------------------------------
# Backward-compatible functions (used by existing pipeline + tests)
# ---------------------------------------------------------------------------

def check_intent(intent: dict) -> BuddhiVerdict:
    """Pre-flight intent check — Narasimha + Buddhi validation.

    This combines:
      1. Narasimha kill-switch (string blocklist → ABORT)
      2. Buddhi validation (priority, TTL, restricted targets → REDIRECT/REFLECT)

    Kept as a standalone function for the 5-gate pipeline where
    a full Buddhi instance isn't instantiated yet.
    """
    # Layer 1: Narasimha kill-switch
    nv = narasimha_gate(intent)
    if nv.blocked:
        return BuddhiVerdict(
            action=VerdictAction.ABORT,
            reason=nv.reason,
        )

    # Layer 2: Buddhi validation (priority, TTL, restricted targets)
    priority = intent.get("priority", "rajas")
    if priority not in VALID_PRIORITIES:
        return BuddhiVerdict(
            action=VerdictAction.REDIRECT,
            reason=f"unknown priority: {priority}",
            suggestion=f"use one of: {', '.join(sorted(VALID_PRIORITIES))}",
        )

    target = intent.get("target", "")
    if target in _RESTRICTED_TARGETS and priority in ("sattva", "suddha"):
        return BuddhiVerdict(
            action=VerdictAction.REFLECT,
            reason=f"elevated priority {priority} to restricted target {target}",
            suggestion="consider using rajas priority unless urgent",
        )

    ttl_ms = intent.get("ttl_ms", 24_000)
    if ttl_ms <= 0:
        return BuddhiVerdict(
            action=VerdictAction.REDIRECT,
            reason="ttl_ms must be positive",
            suggestion="use default 24000ms",
        )
    if ttl_ms > 3_600_000:
        return BuddhiVerdict(
            action=VerdictAction.REFLECT,
            reason=f"very long TTL: {ttl_ms}ms",
            suggestion="consider a shorter TTL",
        )

    return BuddhiVerdict(action=VerdictAction.CONTINUE)


def evaluate(chitta: Chitta) -> BuddhiVerdict:
    """Standalone evaluate — runs Gandha on Chitta's impressions.

    Kept for backward compatibility. For full Antahkarana coordination,
    use Buddhi().evaluate() instead.
    """
    detection = detect_patterns(chitta.impressions, chitta.prior_reads)
    if detection is None:
        return BuddhiVerdict(action=VerdictAction.CONTINUE)
    return BuddhiVerdict(
        action=detection.severity,
        reason=detection.reason,
        suggestion=detection.suggestion,
    )
