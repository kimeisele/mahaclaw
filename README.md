# Maha Claw

A pure-Python AI agent gateway that routes messages through 25 deterministic processing
elements before they reach an LLM. The LLM is element 25 of 25 — everything else
(routing, trust, safety, health, signing, garbage collection) is stdlib Python with
zero pip dependencies.

## The insight

Most agent frameworks are "LLM + tools." The LLM decides everything: what to call,
when to stop, whether to trust input. This makes every routing decision vulnerable
to prompt injection.

Maha Claw inverts this. 24 deterministic elements process every message before
the LLM sees it. A kill-switch (Narasimha) blocks dangerous intents. A trust gate
(Rasa) validates source authority. A pattern detector (Gandha) catches stuck loops.
A coordinator (Buddhi) selects tools by phase, not by prompt. The routing layer
communicates via enums, hashes, and integers — never natural language.

**The LLM generates text. It does not make routing decisions.**

This is the Anauralia property: no natural language flows between routing components.
It's enforced by 13 lint tests that scan module source code. A prompt injection that
reaches the routing layer finds nothing to inject into — just seed values and enum comparisons.

## Quick start

```bash
git clone https://github.com/kimeisele/mahaclaw && cd mahaclaw

# Option 1: Webchat with local LLM (Ollama)
ollama serve &
python3 -m mahaclaw.gateway --web --standalone
# Open http://localhost:18789

# Option 2: Webchat with federation (no API key needed)
python3 -m mahaclaw.gateway --web --steward-only
# Open http://localhost:18789

# Option 3: Telegram bot
export TELEGRAM_BOT_TOKEN=your-token-from-botfather
python3 -m mahaclaw.channels.run_telegram --steward-only

# Option 4: Terminal chat
python3 -m mahaclaw.chat --standalone
```

Requirements: Python 3.10+, `curl`. No pip install needed.

## The 25 elements

Every message goes through `runtime.handle_message()`. Every element fires.

| # | Element | Module | What it does |
|---|---------|--------|-------------|
| 1 | Purusha | channels/ | User input arrives (Telegram, webchat, CLI, socket) |
| 2 | Prakriti | session.py | Unified state (SQLite hash-chained session ledger) |
| 3 | Buddhi | buddhi.py | Decision coordinator (phase-aware, Hebbian learning) |
| 4 | Ahamkara | ahamkara.py | Identity + signing (HMAC-SHA256, optional ECDSA) |
| 5 | Manas | manas.py | Deterministic routing (SHA-256 seed, zero keywords) |
| 6 | Chitta | chitta.py | Memory (impressions, phase derivation, pattern detection) |
| 7 | Shabda | intercept.py | Signal parsing (JSON intent validation) |
| 8 | Sparsha | bridge.py | Context parsing (channel → intent wrapping) |
| 9 | Rupa | gateway.py, chat.py | Display (webchat HTML, terminal output) |
| 10 | Rasa | rasa.py | Trust validation (source trust vs target requirements) |
| 11 | Gandha | chitta.py | Pattern detection (stuck loops, error cascades) |
| 12 | Shrotra | channels/ | Message reception (4 input channels) |
| 13 | Tvak | session.py | Context sensing (conversation history) |
| 14 | Chakshu | — | Code perception (N/A for chat runtime) |
| 15 | Rasana | rasana.py | Preference learning (target/action/tool tracking) |
| 16 | Ghrana | narasimha.py | Kill-switch (token blocklist, runs before Buddhi) |
| 17 | Vak | envelope.py | NADI transport (5-gate pipeline → outbox) |
| 18 | Pani | pani.py | Tool dispatch (namespaces, gates, sandbox) |
| 19 | Pada | pada.py | Dynamic routing (peer discovery from inbox) |
| 20 | Payu | payu.py | Garbage collection (outbox rotation, session expiry) |
| 21 | Upastha | upastha.py | Generation (skill output → envelope pipeline) |
| 22 | Akasha | daemon.py, gateway.py | Network field (Unix socket + WebSocket) |
| 23 | Vayu | intercept→envelope | Process flow (5-gate pipeline) |
| 24 | Agni | llm.py | Compute (provider-agnostic LLM client) |
| 25 | Jiva | llm.py | The LLM itself (element 25 of 25) |

Plus: **Vedana** (health pulse), **KsetraJna** (meta-observer), **Cetana** (heartbeat daemon).

## Two execution paths

```
User message
    │
    ▼
runtime.handle_message()
    │
    ├── Narasimha (kill-switch)
    ├── Manas (seed routing)
    ├── Rasa (trust check)
    ├── Buddhi (decision gate)
    │
    ├─── Federation path ──────────────────┐
    │    intercept → tattva → rama →       │
    │    lotus → envelope → outbox →       │
    │    poll inbox for response           │
    │                                      │
    ├─── Standalone path ──────────────────┤
    │    llm.ask() → response              │
    │                                      │
    ├── Chitta (record impression)         │
    ├── Rasana (update preferences)        │
    ├── Vedana (health pulse)              │
    ├── KsetraJna (state snapshot)         │
    │                                      │
    ▼                                      │
Response text ◄────────────────────────────┘
```

## Modes

| Mode | Flag | What happens |
|------|------|-------------|
| **Steward-only** | `--steward-only` | Routes to federation, waits for response. No local LLM needed. Uses Steward's free LLMs. |
| **Standalone** | `--standalone` | Calls local LLM directly (Ollama, OpenRouter, any OpenAI-compat). No federation. |
| **Federation** | (default) | Routes to federation, falls back to standalone if no response. |

## Tests

```bash
python -m pytest tests/ -q    # 401 passing
```

| Test file | Count | Coverage |
|-----------|-------|---------|
| test_mahaclaw.py | 130 | Gates, inbox, CLI, chat, session, skills, sandbox, gateway, LLM, channels |
| test_manas_compat.py | 64 | Seed routing, steward-protocol compatibility |
| test_pani_chitta.py | 53 | Tool dispatch, impressions, Gandha patterns |
| test_elements.py | 51 | Vedana, Rasa, Rasana, Payu, KsetraJna, Upastha, Pada, Cetana |
| test_buddhi_antahkarana.py | 49 | Buddhi coordinator, Narasimha, Hebbian, tiers |
| test_runtime.py | 18 | Full 25-element flow, blocking, standalone, federation, sessions |
| test_anauralia.py | 13 | Lint: no natural language between routing components |
| test_gateway_integration.py | 10 | HTTP endpoints + WebSocket handshake/chat/errors |
| test_federation.py | 7 | Federation agent card rendering |
| test_vertical.py | 4 | Full multi-element integration flows |

## Wire format

Envelopes in `nadi_outbox.json` are compatible with `agent-internet/transport.py:DeliveryEnvelope`:

```
source, source_city_id, target, target_city_id, operation, payload,
envelope_id, correlation_id, id, timestamp, priority, ttl_s, ttl_ms,
nadi_type, nadi_op, nadi_priority, maha_header_hex, _signature
```

## For developers

See [CLAUDE.md](CLAUDE.md) for the full truth document: architecture decisions,
known mistakes, what works and what doesn't, rules for future contributors.

See [docs/sankhya-map.md](docs/sankhya-map.md) for element-by-element mapping
across the kimeisele federation codebase.

## License

Part of the [kimeisele federation](https://github.com/kimeisele).
