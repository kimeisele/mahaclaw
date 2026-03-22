# Sankhya-25 → Federation Codebase Map

> Produced by auditing all 8 kimeisele repos via GitHub API.
> This map IS the architecture. It replaces all previous architecture docs.

## The Principle

LLM (Jiva) = 1 of 25 elements. Everything that CAN be deterministic IS deterministic.

---

## 1. Purusha (पुरुष) — Pure Consciousness / Observer

- **steward-protocol**: `vibe_core/state/persona.py` → `AgentPersona` (Layer 3: PURUSHA)
- Human operator. Intent comes from outside. Not code per se — but the persona layer models it.
- **Maha Claw**: Channel adapters (telegram, webchat) are the Purusha's voice into the system.
- **Status**: ✅ Working

## 2. Prakriti (प्रकृति) — Primordial Nature / Unified State

- **steward-protocol**: `vibe_core/state/prakriti.py` → `Prakriti(PrakritiProtocol)` — 3-layer state (STHULA/PRANA/PURUSHA), singleton, DI-registered, 13+ snapshots on disk
- **steward-protocol**: `vibe_core/protocols/mahajanas/kapila/samkhya.py` → `PrakritiElement` enum (values 1–24)
- **steward**: `steward/kshetra.py` → `STEWARD_KSHETRA` — maps all 25 elements to steward modules
- **agent-city**: `city/pokedex.py` → `Pokedex` (SQLite agent registry), `city/prana_engine.py` → `PranaEngine` (O(1) memory + SQL flush)
- **Maha Claw**: `session.py` → `SessionManager` (SQLite hash-chained ledger) — local state only
- **Wire**: session.py needs to speak Prakriti's snapshot format
- **Status**: ✅ Working in steward-protocol + agent-city. Maha Claw has local stub.

## 3. Mahat/Buddhi (बुद्धि) — Intellect / Decision Gate

Two implementations in steward-protocol:

- **steward-protocol (substrate)**: `vibe_core/mahamantra/substrate/buddhi.py` → `MahaBuddhi` — `think()` → `BuddhiResult`, `evaluate()` → `BuddhiEvaluation`
- **steward-protocol (plugin)**: `vibe_core/plugins/opus_assistant/manas/buddhi.py` → `Buddhi` — combines `VivekaSense` (priority scoring) + `DharmaSense` (ethical filtering) → `BuddhiVerdict(approved, dharmic, dharma_reason)`. Unapproved intents blocked before execution.
- **steward**: `steward/buddhi.py` → `Buddhi` — phase-machine ORIENT→EXECUTE→VERIFY→COMPLETE, `BuddhiDirective`/`BuddhiVerdict`, token budget control
- **agent-city**: `city/gateway.py` → calls `get_buddhi()`, `city/council.py` → governance proposals, `city/brain.py` → `Brain` (deliberative, reads but does NOT act)
- **agent-city**: `city/immune.py` → `CytokineBreaker` — circuit breaker aborts healing if test failures increase
- **Maha Claw**: ✅ WIRED. `mahaclaw/buddhi.py` → `Buddhi` class — Antahkarana coordinator. Owns Manas, Chitta, Gandha, HebbianSynaptic. `pre_flight()` → `BuddhiDirective` (tools, tier, max_tokens, phase). `evaluate()` → `BuddhiVerdict`. Phase-aware tool selection (ORIENT=read-only, EXECUTE=full, VERIFY=no-writes, COMPLETE=observe). 5-layer tier cascade: action→Hebbian→guardian→phase→context. DSP signal chain for token budget. Narasimha kill-switch extracted to `mahaclaw/narasimha.py`.
- **Status**: ✅ Working in steward + steward-protocol + Maha Claw.

## 4. Ahamkara (अहंकार) — Ego / Identity / Crypto Signing

- **steward-protocol**: `vibe_core/steward/crypto.py` → `generate_keys()`, `sign_content()`, `verify_signature()` — ECDSA NIST256p, keys in `.steward/keys/`
- **steward-protocol**: `vibe_core/plugins/opus_assistant/manas/cortex/mukha.py` → `AgentIdentity`, `IdentityScanner`, `MukhaGenerator`
- **steward**: `steward/identity.py` → `StewardIdentity` — SHA-256 fingerprint from `STEWARD_IDENTITY_SEED`
- **agent-city**: `city/identity.py` → `AgentIdentity` (ECDSA NIST256p), `city/claims.py` → `ClaimLevel` (DISCOVERED→CRYPTO_VERIFIED)
- **Maha Claw**: ✅ WIRED. `mahaclaw/ahamkara.py` → `Identity`, `stamp_envelope()`, `sign_envelope()`, `verify_envelope()`. HMAC-SHA256 (stdlib) + optional ECDSA NIST256p. Fingerprint = SHA-256(public_material)[:16]. All envelopes signed via `build_and_enqueue()`.
- **Status**: ✅ Working in steward + agent-city + Maha Claw.

## 5. Manas (मनस्) — Mind / Deterministic Router

- **steward-protocol**: `vibe_core/plugins/opus_assistant/manas/cognitive_kernel.py` → `CognitiveKernel` — OODA loop (Observe→Orient→Decide→Act), 10 cortex modules
- **steward-protocol**: `vibe_core/mahamantra/substrate/manas/manas_core.py` → `MahaManas` — `perceive()`, `decide()`, `record_outcome()`
- **steward-protocol**: `config/manas.yaml` — config-driven routing
- **steward-protocol**: `MANAS.md` — full architecture doc, 8 senses, intent lifecycle, handler routing
- **steward**: `steward/antahkarana/manas.py` → `Manas` — `MahaCompression.decode_samskara_intent()` for guna, `MahaBuddhi.think()` for function → `ManasPerception(action, guna, function, approach)`. Zero LLM.
- **agent-city**: `city/attention.py` → `CityAttention` (O(1) intent→handler via `MahaAttention`), `city/router.py` → `CityRouter` (cap/dom/tier routing), `city/signal_router.py` → 5D coordinate routing
- **Maha Claw**: `manas.py` → `perceive()` — exact port of steward's pipeline: SHA-256 + Shabda phonetic vibration + MahaModularSynth 16-step → seed → two-position system (guna from seed, function/approach from attractor) → affinity chain → ActionType. Zero keywords, zero LLM. Verified against steward-protocol with 10-string ground truth (64 parametrized tests).
- **Status**: ✅ **WIRED**. Verified compatible with steward-protocol.

## 6. Chitta (चित्त) — Memory / Impression Store

- **steward**: `steward/antahkarana/chitta.py` → `Chitta` — stores tool-execution impressions (Samskaras), derives execution phase, cross-turn awareness via `prior_reads`
- **steward-protocol**: Part of Prakriti's PRANA layer
- **Maha Claw**: `chitta.py` → `Chitta` — exact port of steward's impression model: `Impression{name, params_hash, success, error, path}`, `ExecutionPhase` derivation (ORIENT→EXECUTE→VERIFY→COMPLETE), cross-turn `prior_reads`, `end_turn()`, `to_summary()`/`load_summary()`. Also includes Gandha pattern detection. Session ledger (`session.py`) provides persistence layer underneath.
- **Status**: ✅ **WIRED**. Verified with 31 tests.

---

## Tanmatras — 5 Subtle Elements (Input Signals)

### 7. Shabda (शब्द) — Sound / Signal

- **steward-protocol**: `vibe_core/plugins/opus_assistant/manas/cortex/veda.py` → `class Shabda` — tokenize, detect language, extract keywords
- **steward**: `vibe_core.steward.bus` → `SignalBus` — inter-component events
- **Maha Claw**: `intercept.py` parse_intent = proto-Shabda (tokenize JSON input)
- **Status**: ✅ steward-protocol. ⚠️ Maha Claw has parse-only stub.

### 8. Sparsha (स्पर्श) — Touch / Context Parse

- **steward-protocol**: `veda.py` Phase 2 → `class Artha` — semantic meaning, map tokens to intents
- **steward**: `steward/loop/engine.py` → `AgentLoop._extract_tool_calls`
- **Maha Claw**: channel bridge `_detect_intent()` = proto-Sparsha
- **Status**: ✅ steward. ⚠️ Maha Claw partial.

### 9. Rupa (रूप) — Form / Display

- **steward-protocol**: `cortex/mandala.py` → `ConfigWeaver`, `FractalManifest`
- **steward**: `steward/__main__.py` → CLI display
- **Maha Claw**: `chat.py` terminal output, `gateway.py` WebSocket frames
- **Status**: ✅ Both. Maha Claw has working output.

### 10. Rasa (रस) — Taste / Validation

- **steward-protocol**: `veda.py` Phase 3 → `class Pratyaya` — trust validation, authorization, preconditions
- **steward**: `AgentLoop._clamp_params` — parameter validation
- **Maha Claw**: ✅ WIRED. `mahaclaw/rasa.py` → `TrustLevel` enum (UNKNOWN→INTERNAL), `RasaCause` enum, `RasaVerdict`, `validate()`. Checks source trust vs target requirements and priority requirements. Deterministic, no LLM.
- **Status**: ✅ Working.

### 11. Gandha (गन्ध) — Smell / Pattern Detection

- **steward**: `steward/antahkarana/gandha.py` → `detect_patterns()` — detects stuck loops, error cascades, blind writes, duplicate reads, tool streaks, error ratio → `VerdictAction` (CONTINUE/REFLECT/REDIRECT/ABORT/INFO)
- **steward-protocol**: `veda.py` Phase 4 → `class Karma` — execute + record
- **Maha Claw**: `chitta.py` → `detect_patterns()` — port of steward's Gandha: consecutive_errors (ABORT), identical_calls (REFLECT), tool_streak (REFLECT), error_ratio (REFLECT), write_without_read (REDIRECT). Same thresholds (3/5/8/70%). Same `VerdictAction` enum, same `Detection` dataclass.
- **Status**: ✅ **WIRED**. Verified with 10 tests.

---

## Jnanendriyas — 5 Knowledge Senses (Perception)

### 12. Shrotra (श्रोत्र) — Hearing / Message Reception

- **steward**: `steward/senses/git_sense.py` → `GitSense`
- **steward-protocol**: `cortex/samvada.py` → `SamvadaListener` — Unix socket bidirectional
- **Maha Claw**: `channels/telegram.py` (long-polling), `gateway.py` (WebSocket), `daemon.py` (Unix socket), `cli.py` (stdin)
- **Status**: ✅ Both. Maha Claw has 4 input channels.

### 13. Tvak (त्वक्) — Touch / Context Sensing

- **steward**: `steward/senses/project_sense.py` → `ProjectSense`
- **steward-protocol**: `cortex/prakriti_sense.py` → `PrakritiSense` — git dirty/clean, guna classification
- **Maha Claw**: `session.py` → conversation history, session state
- **Status**: ✅ steward. ⚠️ Maha Claw has session but no project/system sensing.

### 14. Chakshu (चक्षुस्) — Sight / Code Perception

- **steward**: `steward/senses/code_sense.py` → `CodeSense` (AST analysis)
- **steward-protocol**: `cortex/sutra_sense.py` → `SutraSense` — code/doc gap detection
- **Maha Claw**: ❌ No file/code perception
- **Wire**: Not needed for chat runtime. Future: skill output parsing.
- **Status**: ✅ steward. N/A for Maha Claw (chat runtime, not code agent).

### 15. Rasana (रसन) — Taste / Preference Learning

- **steward**: `steward/senses/testing_sense.py` → `TestingSense` — code quality via tests
- **steward-protocol**: `cortex/dharma_sense.py` → `DharmaSense` — ethical quality, bhakti score
- **Maha Claw**: ✅ WIRED. `mahaclaw/rasana.py` → `Rasana` class — tracks target_counts, action_counts, tool_success/tool_total. Properties: preferred_target, preferred_action, tool_success_rate(), top_tools. Persistence via to_summary()/load_summary(). All counts and ratios — no prose.
- **Status**: ✅ Working.

### 16. Ghrana (घ्राण) — Smell / Anomaly Detection

- **steward**: `steward/senses/health_sense.py` → `HealthSense` — file metrics, code entropy
- **steward-protocol**: `cortex/jnana.py` → `JnanaHandler` — knowledge pattern detection
- **steward**: Narasimha kill-switch in `steward/loop/tool_dispatch.py:check_tool_gates()` Gate 2 → `NarasimhaProtocol.audit_agent()`, `ThreatLevel` GREEN→APOCALYPSE, blocks at RED+
- **Maha Claw**: ✅ WIRED. `mahaclaw/narasimha.py` → `gate()` → `NarasimhaVerdict`. String blocklist kill-switch. Runs BEFORE Buddhi. Blocks dangerous intents/substrings.
- **Status**: ✅ Working. Extracted from buddhi.py as philosophically correct separation.
- **Status**: ✅ steward. ❌ Missing in Maha Claw.

---

## Karmendriyas — 5 Action Organs (Tools)

### 17. Vak (वाक्) — Speech / NADI Transport

- **steward**: `steward/loop/engine.py` → `AgentLoop._call_llm`
- **steward-protocol**: `cortex/shell.py` → `ShellCortex`, `samvada.py` → `SamvadaClient` ("The Mouth")
- **agent-internet**: `transport.py` → `DeliveryEnvelope`, `router.py` → `RegistryRouter`
- **Maha Claw**: ✅ 5-gate pipeline → `nadi_outbox.json`. This is DONE.
- **Status**: ✅ Working end-to-end.

### 18. Pani (पाणि) — Hands / Tool Execution

- **steward-protocol**: `vibe_core/tools/tool_registry.py` → `ToolRegistry.execute`
- **steward-protocol**: `cortex/silpa.py` → `SilpaArchitect` — AST transforms, safe refactoring
- **Maha Claw**: `pani.py` → `dispatch()` pipeline: Manas perceive → ActionType → ToolNamespace → allowed tools → gate check → sandbox execute → ToolResult. Ports steward's `ToolResult{success, output, error, metadata}`, `ToolUse{id, name, parameters}`, `ToolNamespace` (OBSERVE/MODIFY/EXECUTE/DELEGATE), `_ACTION_NAMESPACES` mapping, `check_tool_gates()` (route + safety + Iron Dome), `resolve_namespaces()`, `register_tool()`/`unregister_tool()`. Sandbox (`tools/sandbox.py`) provides the execution backend.
- **Status**: ✅ **WIRED**. Verified with 22 tests.

### 19. Pada (पाद) — Feet / Navigation & Routing

- **steward-protocol**: `vibe_core/mahamantra/adapters/attention.py` → `MahaAttention` — O(1) Lotus routing
- **agent-city**: `city/router.py` → `CityRouter` (cap/dom/tier), `city/attention.py` → `CityAttention`
- **agent-internet**: `router.py` → `RegistryRouter.resolve_next_hop()` — prefix-longest-match
- **Maha Claw**: ✅ WIRED. `mahaclaw/pada.py` → `discover_from_inbox()` scans inbox for peer announcements, `extract_peer_from_envelope()` extracts routing info, `refresh_routes()` triggers Lotus reload. Merged with `lotus.py` static routes.
- **Status**: ✅ Working.

### 20. Payu (पायु) — Elimination / Garbage Collection

- **steward**: `steward/context.py` → `SamskaraContext.compact` — context compaction
- **steward-protocol**: `manas/shiva.py` → `ShivaLifecycleManager` — destroys stale intents
- **Maha Claw**: ✅ WIRED. `mahaclaw/payu.py` → `rotate_outbox()` (age + size limits), `expire_sessions()` (SQLite TTL + orphan cleanup), `clean_inbox()`, `sweep()` (full cleanup). Returns `PayuResult` with counts.
- **Status**: ✅ Working.

### 21. Upastha (उपस्थ) — Generation / Artifact Creation

- **steward**: `steward/services.py` → `boot` — service wiring
- **steward-protocol**: `cortex/sankalpa.py` → `SankalpaOrchestrator`, `intent_generator.py` → `IntentGenerator` — proactive strategy
- **Maha Claw**: ✅ WIRED. `mahaclaw/upastha.py` → `skill_to_intent()` converts SkillResult to federation intent, `generate()` routes through full 5-gate pipeline to nadi_outbox.json. `GenerationStatus` enum + `GenerationResult` dataclass. Connected to `skills/engine.py`.
- **Status**: ✅ Working.

---

## Mahabhutas — 5 Gross Elements (Infrastructure/Zones)

### 22. Akasha (आकाश) — Ether / Network Field

- **steward**: `vibe_core.steward.bus` → `SignalBus`
- **steward-protocol**: `cortex/akasha.py` → `AkashaSense` — inter-agent network awareness
- **agent-city**: Zone `discovery` (GENESIS quarter)
- **Maha Claw**: `daemon.py` Unix socket + `gateway.py` WebSocket = the local network field
- **Status**: ✅ Working.

### 23. Vayu (वायु) — Air / Process Flow

- **steward**: `steward/loop/engine.py` → `AgentLoop` — the main agent loop
- **agent-city**: Zone capabilities: communicate, relay, announce
- **Maha Claw**: The 5-gate pipeline IS the Vayu flow (intercept→tattva→rama→lotus→envelope)
- **Status**: ✅ Working.

### 24. Agni (अग्नि) — Fire / Compute / Transformation

- **steward**: `steward/provider/` → `ProviderChamber` — 3-tier LLM routing (FLASH/STANDARD/PRO)
- **agent-research**: `agent_research/jiva.py` → `ProviderChamber` with circuit breaker, 6 providers
- **agent-city**: Zone `governance` (DHARMA quarter), capabilities: transform, audit, validate
- **Maha Claw**: `llm.py` → provider-agnostic LLM client (curl-based, OpenAI-compat)
- **Status**: ✅ Working.

### 25. Jala (जल) — Water / Memory / Flow

- **steward**: `steward/memory.py` → `PersistentMemory`
- **agent-city**: Zone `research` (MOKSHA quarter), capabilities: connect, mediate, integrate
- **agent-internet**: `transport.py` → the flow of envelopes between nodes
- **Maha Claw**: `inbox.py` → response flow, `session.py` → memory
- **Status**: ✅ Working.

### 26. Prithvi (पृथ्वी) — Earth / Persistence / Storage

- **steward**: `steward/state.py` → `save_conversation` — disk persistence (Phoenix pattern)
- **agent-city**: Zone `engineering` (KARMA quarter), capabilities: build, maintain, stabilize
- **Maha Claw**: `nadi_outbox.json`, `nadi_inbox.json`, `mahaclaw_sessions.db`
- **Status**: ✅ Working.

---

## The 25th: Jiva (जीव) — Consciousness / LLM

- **steward**: `steward/provider/` → `LLMProvider` — the LLM itself
- **agent-research**: `agent_research/jiva.py` → `ProviderChamber` — multi-provider failover (Google Flash→Mistral→Groq→OpenRouter→Anthropic→OpenAI)
- **steward-protocol**: `vibe_core/state/persona.py` → personas that shape the Jiva's behavior
- **Maha Claw**: `llm.py` → curl-based OpenAI-compat client. Used ONLY in standalone/steward-only mode.
- **Key insight**: In federation mode, Maha Claw does NOT invoke Jiva. It routes to federation agents who have their own Jiva. The LLM is on the other side of NADI.
- **Status**: ✅ Working. Correctly positioned as 1-of-25.

---

## Additional Elements (Beyond Canonical 25)

### Vedana — Health Pulse
- **steward**: `steward/antahkarana/vedana.py` → `VedanaSignal` — composite health (0.0–1.0), guna derived from health
- **Maha Claw**: ✅ WIRED. `mahaclaw/vedana.py` → `pulse()` → `VedanaSignal`. Weighted composite: error_rate (0.4) + confidence (0.3) + phase_health (0.2) + queue_pressure (0.1). `HealthGuna`: SATTVA (≥0.7), RAJAS (0.4–0.7), TAMAS (<0.4).
- **Status**: ✅ Working.

### KsetraJna — Meta-Observer
- **steward**: `steward/antahkarana/ksetrajna.py` → `KsetraJna` → `BubbleSnapshot` — frozen peer-readable state digest
- **Maha Claw**: ✅ WIRED. `mahaclaw/ksetrajna.py` → `observe()` → `BubbleSnapshot`. Full state digest: routing (route_count, peers_available), Chitta (impressions, phase, errors), health (Vedana score), identity (fingerprint, signing_method), pipeline (outbox/inbox depth), integrity (snapshot_hash). Expands buddy_bubble().
- **Status**: ✅ Working.

### Narasimha — Kill Switch
- **steward**: `steward/loop/tool_dispatch.py` Gate 2 → `NarasimhaProtocol.audit_agent()`, `ThreatLevel` GREEN→APOCALYPSE
- **Maha Claw**: ✅ WIRED. `mahaclaw/narasimha.py` → `gate()` → `NarasimhaVerdict`. `NarasimhaCause` enum. Token-matching kill-switch, runs BEFORE Buddhi. Extracted from buddhi.py as separate guardian.
- **Status**: ✅ Working.

### Cetana — Autonomous Heartbeat
- **steward**: `steward/cetana.py` → 4-phase MURALI cycle, adaptive frequency
- **Maha Claw**: ✅ WIRED. `mahaclaw/cetana.py` → `CetanaDaemon` (daemon thread), `beat_once()` (MURALI cycle: MEASURE→UPDATE→REPORT→ADAPT→LISTEN→INTEGRATE). Adaptive interval (60s–3600s). Integrates with Pada for peer discovery on LISTEN phase.
- **Status**: ✅ Working.

---

## Wiring Priority Matrix

| Element | Status in Maha Claw | Priority | Action |
|---------|-------------------|----------|--------|
| **Buddhi** | ✅ WIRED | ~~P0~~ | Antahkarana coordinator with Hebbian learning |
| **Ahamkara** | ✅ WIRED | ~~P0~~ | HMAC-SHA256 + optional ECDSA envelope signing |
| **Manas** | ✅ WIRED | ~~P1~~ | Seed-based routing, verified compat |
| **Gandha** | ✅ WIRED | ~~P1~~ | Pattern detection in chitta.py |
| **Pani** | ✅ WIRED | ~~P1~~ | Tool dispatch pipeline |
| **Payu** | ✅ WIRED | ~~P2~~ | Outbox rotation + session expiry |
| **Rasa** | ✅ WIRED | ~~P2~~ | Trust/auth validation |
| **Narasimha** | ✅ WIRED | ~~P2~~ | Kill-switch extracted from Buddhi |
| **Chitta** | ✅ WIRED | ~~P2~~ | Impression model + phase derivation |
| **Vedana** | ✅ WIRED | ~~P3~~ | Health pulse composite score |
| **KsetraJna** | ✅ WIRED | ~~P3~~ | Full state digest (BubbleSnapshot) |
| **Cetana** | ✅ WIRED | ~~P3~~ | In-process MURALI heartbeat daemon |
| **Rasana** | ✅ WIRED | ~~P3~~ | Preference learning from session patterns |
| **Vak** | ✅ Done | — | 5-gate pipeline works |
| **Shrotra** | ✅ Done | — | 4 input channels work |
| **Pada** | ✅ WIRED | ~~P2~~ | Dynamic route discovery from inbox |
| **Upastha** | ✅ WIRED | ~~P2~~ | Skill output → envelope pipeline |
