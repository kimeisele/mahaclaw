# Buddhi Audit — steward/buddhi.py (618 lines)

Source: `steward/antahkarana/buddhi.py` (read in full via GitHub API).

## Architecture Summary

Buddhi is the **Antahkarana coordinator** — it OWNS Manas, Chitta, and Gandha
as internal components and orchestrates them as ONE cognitive unit.

### Class: `Buddhi`

```python
class Buddhi:
    def __init__(self):
        self.manas = Manas()           # Perceiving mind
        self.chitta = Chitta()          # Impression storage
        self.synaptic = HebbianSynaptic()  # Learning signal
        # Cached from first pre_flight call:
        self.action = None
        self.guna = None
        self.function = None
        self.approach = None
        self.tier = None
```

### Method: `pre_flight(user_message, round_num, context_pct, seed, l0_guardian)`

Returns `BuddhiDirective` — the complete instruction set for the LLM turn.

Pipeline:
1. **Round 0 only**: Call `Manas.perceive(user_message)` → cache action/guna/function/approach
2. **Action → Namespace → base_tools** (primary routing)
3. **Guna fallback**: If no tools from action, use `_GUNA_NAMESPACES[guna]`
4. **Phase overlay from Chitta**: `_PHASE_NS_OVERLAY[chitta.phase]` intersected with base
5. **DSP signal chain**: task_weight × phase_mod → effective_weight → `process_cbr()` → max_tokens
6. **Error recovery**: 2+ recent errors → inject `bash` into allowed tools
7. **Tier selection** (5-layer cascade):
   - Base: `_ACTION_TIER[action]` (RESEARCH→FLASH, IMPLEMENT→STANDARD, DESIGN→PRO)
   - Hebbian: confidence < 0.4 → escalate; < 0.25 → escalate to PRO
   - Guardian: deliverer/source guardians in `_GUARDIAN_ESCALATE` → +1 tier
   - Phase: PRO demoted to STANDARD in VERIFY/COMPLETE
   - Context pressure: ≥70% context → FLASH (save tokens)

### Method: `evaluate(tool_calls, results)`

Returns `BuddhiVerdict` — post-execution judgment.

Pipeline:
1. Record each tool result as `Impression` in Chitta
2. Run `Gandha.detect_patterns(chitta.impressions)`
3. Tool failure → REDIRECT verdict
4. Phase transition → REFLECT with guidance message

### Constants (gold standard)

```python
_ACTION_WEIGHT = {
    RESEARCH: 0.0, IMPLEMENT: 1.0, DEBUG: 1.0, REFACTOR: 0.8,
    REVIEW: 0.2, MONITOR: 0.0, RESPOND: 0.5, DESIGN: 0.3,
    TEST: 0.8, DEPLOY: 0.6, GOVERN: 0.1, DISCOVER: 0.0,
}

_ACTION_TIER = {
    RESEARCH: FLASH, IMPLEMENT: STANDARD, DEBUG: STANDARD,
    REFACTOR: STANDARD, REVIEW: FLASH, MONITOR: FLASH,
    RESPOND: STANDARD, DESIGN: PRO, TEST: STANDARD,
    DEPLOY: STANDARD, GOVERN: FLASH, DISCOVER: FLASH,
}

_PHASE_MODULATION = {
    ORIENT: 0.5, EXECUTE: 1.0, VERIFY: 0.5, COMPLETE: 0.5,
}

_PHASE_NS_OVERLAY = {
    ORIENT: frozenset(),                    # read-only
    EXECUTE: {MODIFY, EXECUTE},             # full access
    VERIFY: {OBSERVE, EXECUTE},             # no new writes
    COMPLETE: {OBSERVE},                    # wrap up
}

_GUNA_NAMESPACES = {
    SATTVA: {OBSERVE},
    RAJAS: {OBSERVE, MODIFY, EXECUTE},
    TAMAS: {OBSERVE, MODIFY},
    SUDDHA: {OBSERVE, MODIFY, EXECUTE, DELEGATE},
}

_GUARDIAN_ESCALATE = {"nrisimha", "prahlada", "shambhu", "kumaras"}
```

### HebbianSynaptic

```python
class HebbianSynaptic:
    def __init__(self):
        self.weights = {}  # tool_name → confidence (0.0 to 1.0)

    def update(self, tool_name, success):
        w = self.weights.get(tool_name, 0.5)
        if success:
            w += 0.1 * (1 - w)   # asymptotic to 1.0
        else:
            w -= 0.1 * w         # asymptotic to 0.0
        self.weights[tool_name] = w

    @property
    def confidence(self):
        if not self.weights:
            return 0.5
        return sum(self.weights.values()) / len(self.weights)
```

### CBR Signal Processing

```python
def process_cbr(effective_weight):
    """Convert effective weight to max_tokens via DSP curve."""
    # Maps 0.0 → 1024, 1.0 → 4096 (linear interpolation)
    return int(1024 + effective_weight * 3072)
```

### Phase Guidance

```python
_PHASE_GUIDANCE = {
    (EXECUTE, VERIFY): "Consider running tests to verify your changes.",
    (VERIFY, COMPLETE): "Changes verified. Prepare final summary.",
    (ORIENT, EXECUTE): "Understanding gathered. Begin implementation.",
}
```

## What Mahaclaw Needs

Our Buddhi must be the **chariot driver** (Katha Upanishad):
- Senses = tools (Pani)
- Manas = mind (perception)
- Chitta = memory (impressions)
- Buddhi = intellect (discrimination)

The philosophical test: **"If I remove the LLM entirely, does Buddhi still make correct decisions?"** → YES.

Buddhi discriminates (Viveka) between Sat (beneficial) and Asat (harmful) by reading:
1. Manas perception (what IS this intent?)
2. Chitta state (what HAS happened?)
3. Gandha signals (what patterns EMERGE?)

Then it DECIDES: tools, tier, phase constraints, max_tokens.

## What Current buddhi.py Gets Wrong

The current `check_intent()` is **Narasimha** (the kill-switch — last line of defense).
String matching (`"rm -rf" in intent`) is NOT discrimination. It's a blocklist.

Buddhi should never need to see the literal text. It reads Manas's structured perception
and Chitta's accumulated impressions, then applies discriminative logic.

The blocklist belongs in `narasimha.py` — a separate safety layer that runs BEFORE Buddhi.
