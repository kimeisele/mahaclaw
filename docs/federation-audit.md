# Federation Infrastructure Audit — Findings Report

**Date:** 2026-03-20
**Auditor:** Opus (automated)
**Repos scanned:** steward-protocol, steward, agent-city, agent-internet, agent-research, agent-world, steward-federation, steward-test

---

## Executive Summary

**The federation already has a full LLM runtime, multi-provider failover, tool dispatch, and gateway.
What it does NOT have: any user-facing channel adapters (Telegram, Discord, Slack, etc.).**

**Verdict: Pattern B — Steward has LLM but no user-facing channels.
Maha Claw adds the channel layer and delegates ALL thinking to Steward via NADI.**

---

## 1. LLM Provider Infrastructure

### steward-protocol (`vibe_core/runtime/providers/`)

| Provider | SDK | Default Model | Auth |
|----------|-----|---------------|------|
| Anthropic | `anthropic` | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |
| Google | `google-generativeai` | `gemini-2.0-flash` | `GOOGLE_API_KEY` |
| OpenRouter | `openai` (compat) | `deepseek/deepseek-v3.2` | `OPENROUTER_API_KEY` |
| Local Llama | `llama-cpp-python` | `qwen2.5-0.5b-instruct-q4_k_m.gguf` | none |
| SmartLocal | none (keyword) | n/a | none |
| StewardProvider | stdin/stdout | n/a (Claude Code) | none |

**Config:** `config/llm.yaml`, `config/providers.yaml`
**Factory:** `vibe_core/runtime/providers/factory.py` — `create_provider(name, key, model)`
**Chaining:** `vibe_core/llm/chain.py:ChainProvider` — cascade through providers with auto-fallback
**Degradation:** `vibe_core/llm/degradation_chain.py:DegradationChain` — graceful offline: SemanticRouter → LocalLLM → Templates → Error

### steward (`steward/provider/`)

| Component | File | What it does |
|-----------|------|-------------|
| `ProviderChamber` | `chamber.py` | Multi-LLM failover with prana-ordered MahaCellUnified cells. Free providers get more prana = tried first. CircuitBreaker per cell. |
| `GoogleAdapter` | `adapters.py` | Google Gemini normalize → NormalizedResponse |
| `MistralAdapter` | `adapters.py` | Mistral API with streaming |
| `AnthropicAdapter` | `adapters.py` | Anthropic with tool use + streaming |

**Streaming:** Yes — `invoke_stream()` yields `StreamDelta` objects
**Tool use:** Yes — `ToolUse` dataclass with id/name/params, accumulated from streaming deltas
**Failover:** Prana-based priority + CircuitBreaker + transient error retry (429, 503, timeout)
**Quota:** Daily call + token limits per provider via `OperationalQuota`

### agent-research (`agent_research/jiva.py`)

Adapted from steward's provider pattern. Has its own `GoogleAdapter`, `MistralAdapter`, `GroqAdapter`, `AnthropicAdapter`. Independent ProviderChamber with failover. Used for research-specific LLM reasoning (turning data → knowledge).

### Conclusion: LLM infra is RICH and DISTRIBUTED
Three repos have independent LLM provider code. All share the same pattern (NormalizedResponse, failover, adapters). The steward repo's ProviderChamber is the most complete (streaming + tools + circuit breaker).

---

## 2. Gateway / Server Components

### steward-protocol: FastAPI on port 8080

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/v1/public-chat` | POST | Unauthenticated chat (rate-limited) |
| `/v1/chat` | POST | Signed/authenticated chat (ECDSA + API key) |
| `/v1/public-intents` | POST | Intent submission → Lotus |
| `/v1/intents` | POST | Signed intent submission → Lotus |
| `/v1/pulse` | WS | Telemetry stream (API key required) |
| `/api/agents` | GET | Agent registry |
| `/api/ledger` | GET | Immutable ledger |
| `/api/federation/outbox` | GET | Read NADI outbox |
| `/api/federation/inbox` | POST | Write NADI inbox |
| `/api/federation/stats` | GET | Federation stats |
| `/api/yagya` | POST | Submit research tasks |
| `/api/visa` | POST | Agent citizenship onboarding |

**Server:** `run_server.py` → `uvicorn gateway.api:app --host 0.0.0.0 --port 8080`
**ASGI middleware:** `mahamantra_asgi.py` — injects X-Mahamantra headers on every response
**Security:** `takshaka_lite.py` — size limits, rate limiting, timestamp freshness, ECDSA signature verification, toxicity scan

### agent-internet: Lotus daemon on port 8788

ThreadingHTTPServer serving:
- Route resolution (prefix-match + trust + health)
- Service address registry
- Intent subjects + reviews
- Endpoint management

### Maha Claw: WebSocket on port 18789

Our own gateway. Separate from steward-protocol's FastAPI.

### Conclusion: No port conflicts. Clear separation of concerns.

---

## 3. Tool / Capability Systems

### steward-protocol: 56 Cartridges

| Category | Cartridges |
|----------|------------|
| Archivist | Code audit, observation, verification |
| Auditor | Compliance, verdict |
| Civic | Bank, ledger, license |
| Cleaner | Code scan, status |
| Discoverer | Agent discovery (boots first in gateway) |
| Engineer | Builder |
| Envoy | Campaign, city control, curator, diplomacy |
| Herald | Broadcast, identity, research, scout, visual |
| Manas | Cognitive kernel cartridges |
| Naga | Security detect/scan/status |
| Oracle | Introspection |
| Science | Web search (Tavily) |
| Supreme Court | Appeals, precedent, verdict |
| Watchman | Standards enforcement |

**External tools via env:** Twitter (tweepy), LinkedIn, Reddit (praw), GitHub (PyGithub), Google APIs, web search (Tavily)

### steward: Sankhya-25 Cognitive Pipeline

```
User message
  → Manas (perceive intent, zero LLM, O(1) semantic hash)
  → MahaLLMKernel (L0 guardian classification, zero tokens)
  → Buddhi (discriminate action + model tier + tool namespace)
  → Chitta (track impressions → derive phase: ORIENT/EXECUTE/VERIFY/COMPLETE)
  → Tool execution (gated by Narasimha + Iron Dome + CBR)
  → Gandha (detect patterns in results)
  → Buddhi verdict (CONTINUE/REFLECT/REDIRECT/ABORT)
  → next round or complete
```

80% deterministic substrate, 20% LLM — and the LLM share shrinks as the substrate learns.

### agent-research: Research Engine

4-phase pipeline mirroring MahaMantra quarters:
- GENESIS: intake + normalize inquiry
- DHARMA: classify domain + select methodology (deterministic, zero LLM)
- KARMA: execute research (LLM via Jiva)
- MOKSHA: synthesize + publish

7 research faculties: agent_physics, agent_governance, agent_health, agent_economics, cognitive_architecture, security_and_trust, cross_domain

---

## 4. Channel / Messaging Adapters

**NONE.** Zero channel adapters across all 8 repos.

No Telegram, no Discord, no Slack, no WhatsApp, no IRC, no Matrix, no email, no webhook, no chat widget.

The only user-facing interfaces are:
1. `POST /v1/public-chat` (HTTP JSON)
2. `WS /v1/pulse` (WebSocket telemetry)
3. `steward` CLI (terminal)
4. `StewardProvider` (stdin/stdout inside Claude Code)

**This is the gap Maha Claw fills.**

---

## 5. Federation Transport

### steward-protocol: `FederationNadi` (`vibe_core/mahamantra/federation/nadi_consumer.py`)

- File I/O on `data/federation/`
- Atomic writes (`.tmp` → rename)
- TTL-based cleanup (24s local, 900s cross-repo)
- Priority sorting (SUDDHA > SATTVA > RAJAS > TAMAS)
- Deduplication by (source, timestamp)
- Max 144 messages per file
- HTTP bridge: `GET /api/federation/outbox`, `POST /api/federation/inbox`

### steward-federation

NADI transport hub. Routes envelopes between nodes. The relay pump reads from each node's outbox and writes to the target's inbox.

### Maha Claw: `nadi_outbox.json` / `nadi_inbox.json`

Compatible format. Our envelopes match the `FederationMessage` structure.

---

## 6. Recommendation: What to REUSE vs BUILD

### REUSE (do not rebuild)

| What | Where | How Maha Claw uses it |
|------|-------|-----------------------|
| LLM Provider failover | steward `ProviderChamber` | Route via NADI → Steward handles LLM |
| Cognitive pipeline | steward `Manas → Buddhi → Chitta` | Route via NADI → Steward reasons |
| Research engine | agent-research | Route "inquiry" intents via NADI |
| Federation transport | steward-protocol `FederationNadi` | Our outbox/inbox is already compatible |
| Gateway API | steward-protocol FastAPI :8080 | POST to `/api/federation/inbox` |
| Tool cartridges (56) | steward-protocol | Available via Steward dispatch |
| Security (Takshaka) | steward-protocol | ECDSA signature verification |
| Governance | agent-world | Route governance intents via NADI |

### BUILD (Maha Claw's job)

| What | Why | How |
|------|-----|-----|
| Channel adapters | **Nobody has them** | Telegram, Discord, Slack via pip packages |
| Edge LLM client | For standalone mode (no Steward) | Provider-agnostic, OpenAI-compat format |
| Channel → NADI bridge | Connect user messages to federation | Wrap in intent, run 5-gate pipeline |
| NADI → Channel bridge | Deliver federation responses to users | Poll inbox, match correlation_id, push to channel |
| Standalone chat | Already built (`mahaclaw/chat.py`) | Extend with LLM client |

### DO NOT BUILD

- LLM provider failover (Steward has it)
- Cognitive routing (Steward's Manas/Buddhi does this)
- Research synthesis (agent-research does this)
- Federation transport (compatible as-is)
- Tool dispatch (Steward's cartridge system is complete)
- Security middleware (Takshaka exists)

---

## 7. Integration Architecture

```
User (Telegram / Discord / Slack)
       │
       ▼
┌─ MAHA CLAW (Edge Client) ──────────────────────┐
│                                                  │
│  Channel Adapter (receives user message)         │
│       │                                          │
│       ▼                                          │
│  5-Gate Pipeline (PARSE → VALIDATE → EXECUTE     │
│                   → RESULT → SYNC)               │
│       │                                          │
│       ├── [steward-only mode] ──────────────┐    │
│       │   Write to nadi_outbox.json         │    │
│       │   OR POST to :8080/api/fed/inbox    │    │
│       │                                     │    │
│       ├── [standalone mode] ────────────┐   │    │
│       │   Local LLM (Ollama/any)       │   │    │
│       │   OR cloud API (any provider)  │   │    │
│       │                                │   │    │
│       ▼                                │   │    │
│  Response (from Steward OR local LLM)  │   │    │
│       │                                │   │    │
│       ▼                                │   │    │
│  Channel Adapter (delivers response)   │   │    │
│                                        │   │    │
└────────────────────────────────────────┘   │    │
                                             │    │
steward-protocol (:8080) ←───────────────────┘    │
       │                                          │
       ▼                                          │
  ProviderChamber → Google/Anthropic/Mistral      │
  Manas → Buddhi → Chitta → Tools → Response      │
       │                                          │
       ▼                                          │
  nadi_inbox.json (response) ─────────────────────┘
```

Two modes:
1. **steward-only**: All thinking delegated to Steward. Maha Claw is pure edge client.
2. **standalone**: Maha Claw runs its own LLM client for quick responses. Falls back to Steward for complex tasks.

---

## 8. Port Map

| Service | Port | Protocol |
|---------|------|----------|
| steward-protocol gateway | 8080 | HTTP/WS (FastAPI) |
| agent-internet Lotus | 8788 | HTTP (ThreadingHTTPServer) |
| Maha Claw gateway | 18789 | WebSocket (asyncio, RFC 6455) |
| Ollama (optional) | 11434 | HTTP (OpenAI-compat) |
