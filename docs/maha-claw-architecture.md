# Maha Claw — Research Findings & Architecture Proposal

## Phase 1: Research Findings

### 1. The Federation Stack (Actual Structure)

```
steward-protocol    substrate: kernel, identity (ECDSA), MahaMantra engine, Sankhya-25
    |
agent-world         world truth: registry, policies, governance
    |
agent-city          local runtime: zones (Five Tattvas), RAMA coordinates, MURALI governance
    |
agent-internet      control plane: Lotus routing, NADI relay, trust ledger, discovery
    |
steward-federation  transport hub: nadi_inbox.json / nadi_outbox.json per route pair
    |
YOUR NODE           mahaclaw — this is where the bridge lives
```

### 2. MahaMantra Engine (steward-protocol: `vibe_core/mahamantra/`)

The MahaMantra is a 16-position system based on the Hare Krishna mantra. Each position maps to:

| POS | WORD    | QUARTER | GUARDIAN     | OPCODE          |
|-----|---------|---------|--------------|-----------------|
| 0   | HARE    | GENESIS | VYASA (HEAD) | SYS_WAKE        |
| 1   | KRISHNA | GENESIS | BRAHMA       | LOAD_ROOT       |
| 2   | HARE    | GENESIS | NARADA       | ALLOC_MEM       |
| 3   | KRISHNA | GENESIS | SHAMBHU      | BIND_CTX        |
| 4   | KRISHNA | DHARMA  | PRITHU (HEAD)| ASSERT_TRUTH    |
| 5   | KRISHNA | DHARMA  | KUMARAS      | RESOLVE_REQ     |
| 6   | HARE    | DHARMA  | KAPILA       | GARBAGE_COLLECT |
| 7   | HARE    | DHARMA  | MANU         | PULSE_SYNC      |
| 8   | HARE    | KARMA   | PARASHURAMA (HEAD)| FETCH_RES  |
| 9   | RAMA    | KARMA   | PRAHLADA     | EXEC_SERVICE    |
| 10  | HARE    | KARMA   | JANAKA       | CHECK_DHARMA    |
| 11  | RAMA    | KARMA   | BHISHMA      | COMMIT_LOG      |
| 12  | RAMA    | MOKSHA  | NRISIMHA (HEAD)| CACHE_STATE   |
| 13  | RAMA    | MOKSHA  | BALI         | OPTIMIZE        |
| 14  | HARE    | MOKSHA  | SHUKA        | YIELD_CPU       |
| 15  | HARE    | MOKSHA  | YAMARAJA     | RESET_IP        |

**Key constants from the Lotus protocol:**
- `WORDS = 16` (mantra positions = Lotus petals)
- `QUARTERS = 4` (Genesis, Dharma, Karma, Moksha)
- `PARAMPARA = 37` (24 elements + 12 Mahajanas + 1 Ksetrajna)
- `KSETRAJNA = 1` (the knower)
- `PANCHA = 5` (Five Tattvas)
- `SEVEN = 7`, `TEN = 10`, `TRINITY = 3`

**The MahaMantra ASGI gateway** (`gateway/mahamantra_asgi.py`) shows the pattern we must replicate:
1. **VIBRATE**: Input → `mahamantra.vibrate(input)`
2. **CLASSIFY**: Result → Purna (136 = complete) vs Lila (dynamic cycle)
3. **SANCTIFY**: Inject `X-Mahamantra-*` headers (attractor, state, verse, seed)
4. **DELEGATE**: Pass through to next layer

### 3. NADI Transport (The Actual Wire Format)

**Five NADI Types** (from `steward_protocol_compat.py`):
- `prana` — vital/primary
- `apana` — downward/response
- `vyana` — distributed/default
- `udana` — upward/escalation
- `samana` — equalizing/balancing

**NADI Operations:**
`receive`, `send`, `cache`, `process`, `validate`, `request`, `delegate`, `connect`, `commit`

**NADI Priorities (Guna-based):**
- `tamas` — lowest/background
- `rajas` — normal/active (default)
- `sattva` — high/goodness
- `suddha` — pure/critical

**Default timeout:** 24,000ms

**Actual envelope format** (from `steward-federation/nadi/` and `agent-internet/transport.py`):

```python
@dataclass(frozen=True, slots=True)
class DeliveryEnvelope:
    source_city_id: str
    target_city_id: str
    operation: str
    payload: dict
    envelope_id: str          # "env_{token_hex(8)}"
    correlation_id: str
    content_type: str         # "application/json"
    created_at: float         # time.time()
    ttl_s: float | None
    nadi_type: str            # prana|apana|vyana|udana|samana
    nadi_op: str              # send|receive|cache|process|...
    priority: str             # tamas|rajas|sattva|suddha
    ttl_ms: int | None
    maha_header_hex: str      # Hash-based routing header
```

**MahaHeader hex** is built from:
`build_maha_message_header_hex(source_key, target_key, operation_key, nadi_type, priority, ttl_ms)`

### 4. Lotus Routing (agent-internet: `router.py`, `lotus_daemon.py`)

The `RegistryRouter` provides:
- `resolve(source_city_id, target_city_id)` → `CityEndpoint`
- `resolve_public_handle(handle)` → `HostedEndpoint`
- `resolve_service(owner_city_id, service_name)` → `LotusServiceAddress`
- `resolve_next_hop(source, destination)` → `LotusRouteResolution`

**Route resolution** includes:
- Prefix-based matching on destination
- Health check via `DiscoveryService.get_presence()`
- Trust evaluation via `TrustEngine.evaluate()`
- Minimum trust level enforcement

**LotusRouteResolution contains:**
`destination, matched_prefix, route_id, target_city_id, next_hop_city_id, next_hop_endpoint, nadi_type, priority, ttl_ms, maha_header_hex`

**Lotus API scopes** (token-based auth):
`lotus.read`, `lotus.write.contract`, `lotus.write.reconcile`, `lotus.write.address`, `lotus.write.endpoint`, `lotus.write.service`, `lotus.write.intent`, `lotus.write.intent.subject`, `lotus.write.intent.review`, `lotus.write.token`

**Lotus daemon** runs as a `ThreadingHTTPServer` on port 8788.

### 5. Five Tattva / Pancha Tattva Gateway

From `vibe_core/mahamantra/substrate/pancha_tattva.py`:
- `TattvaGate` enum with five gates: `PARSE`, `VALIDATE`, `EXECUTE`, `RESULT`, `SYNC`
- Gate dispatch maps to provider methods: `parse()`, `validate()`, `infer()`, `route()`, `enforce()`
- Each gate receives pipeline context (seed, attractor, position, opcode, guna)
- Providers register via `TattvaRegistry` (from `substrate/tattva_registry.py`)

From `agent-city` zone mapping:
| Zone       | Element          | Domain                    |
|------------|------------------|---------------------------|
| General    | Vayu (Air)       | Communication & Networking|
| Research   | Jala (Water)     | Knowledge & Philosophy    |
| Engineering| Prithvi (Earth)  | Building & Tools          |
| Governance | Agni (Fire)      | Leadership & Policy       |
| Discovery  | Akasha (Ether)   | Abstract thought          |

### 6. RAMA Signal (agent-city)

Agents receive "RAMA coordinates":
1. **Element** — one of the Five Tattvas (maps to city zone)
2. **Zone** — subdivision within the city
3. **Guardian** — Mahajana designation from the 16-position system

The `rama_coords` and `COORD_ELEMENT` lookup tables in `pancha_walk.py` map positions to the 49-letter Sanskrit Varnamala (7² matrix).

### 7. FederationGateway & buddy_bubble

**FederationGateway** is the pattern seen in `agent-internet/filesystem_message_transport.py`:
- `AgentCityFilesystemMessageTransport.send(endpoint, envelope)` → `DeliveryReceipt`
- It writes to the target's inbox via `FilesystemFederationTransport.append_to_inbox()`
- Receipt journaling prevents duplicate delivery

**buddy_bubble** — Not explicitly named in the codebase. The closest concept is the `ControlPlaneStateStore` / `snapshot.py` in agent-internet, which provides introspectable routing state. The Lotus daemon exposes this via HTTP. This is likely what "buddy_bubble" refers to: a real-time introspection bubble of the O(1) routing table state.

### 8. Open-Claw / Steward Architecture

The `steward` repo is described as "Open-Claw architecture" — an autonomous superagent engine with:
- **Sankhya-25 cognitive model**: 24 deterministic elements + 1 LLM (Jiva)
- **Decision components**: Manas (mind/routing), Buddhi (intellect/abort), Samskara (memory)
- Multi-LLM failover, CircuitBreaker pattern, context compaction
- Safety: Narasimha killswitch, Iron Dome, Buddhi abort

---

## Phase 2: Maha Claw Architecture Proposal

### Goal

100% pure Python daemon that translates flat OpenClaw intents into the federation's NADI transport with full MahaMantra/RAMA dimensional enrichment.

### Architecture Overview

```
  OpenClaw Intent (flat JSON)
         │
         ▼
  ┌──────────────────────────────────────────────┐
  │              MAHA CLAW DAEMON                 │
  │                                               │
  │  1. PARSE gate     ─── Validate + extract     │
  │  2. VALIDATE gate  ─── Map to RAMA coords     │
  │  3. EXECUTE gate   ─── Compute MahaHeader     │
  │  4. RESULT gate    ─── Resolve Lotus route     │
  │  5. SYNC gate      ─── Build DeliveryEnvelope  │
  │                                               │
  └──────────────────────────────────────────────┘
         │
         ▼
  nadi_outbox.json  →  relay pickup by agent-internet
```

The five pipeline stages mirror the **TattvaGate** pattern exactly: `PARSE → VALIDATE → EXECUTE → RESULT → SYNC`.

### Component Design

#### 1. Intent Interceptor (`mahaclaw/intercept.py`)

Accepts flat OpenClaw intents via:
- Unix domain socket (daemon mode)
- Stdin pipe (CLI mode)
- Direct Python API call (library mode)

Input schema:
```python
{
    "intent": str,        # e.g. "code_analysis", "inquiry", "heartbeat"
    "target": str,        # e.g. "agent-research", "agent-city"
    "payload": dict,      # arbitrary payload
    "priority": str,      # optional: "tamas"|"rajas"|"sattva"|"suddha"
    "ttl_ms": int,        # optional, default 24000
}
```

#### 2. Tattva Classifier (`mahaclaw/tattva.py`)

Maps intents to the Five Tattvas using a keyword affinity matrix:

```python
AFFINITY_MAP = {
    "heartbeat":      {"vayu": 1.0, "prana": "vyana"},
    "inquiry":        {"jala": 0.9, "akasha": 0.4},
    "code_analysis":  {"prithvi": 1.0},
    "governance":     {"agni": 1.0},
    "discovery":      {"akasha": 1.0},
}
```

Output: a 5D affinity vector `(akasha, vayu, agni, jala, prithvi)` with the dominant element selecting the zone.

#### 3. RAMA Encoder (`mahaclaw/rama.py`)

Enriches the classified intent into a 7-layer RAMA signal matching the upstream `rama_coords` structure:

| Layer | Name       | Derivation |
|-------|------------|------------|
| 1     | Element    | Dominant Tattva from classifier |
| 2     | Zone       | agent-city zone from element map |
| 3     | Operation  | Mapped from OpenClaw intent verb |
| 4     | Affinity   | Full 5D vector |
| 5     | Guardian   | Mahajana position from intent map (`get_position_for_intent`) |
| 6     | Quarter    | Derived from guardian position (Genesis/Dharma/Karma/Moksha) |
| 7     | Guna       | Priority mapped to guna (tamas/rajas/sattva/suddha) |

#### 4. Lotus Resolver (`mahaclaw/lotus.py`)

Pre-indexes the peer registry into an O(1) lookup table:

```python
# Built from .federation/peers.json + authority-descriptor-seeds.json
_route_table: dict[str, str] = {
    "agent-research": "kimeisele/agent-research",
    "agent-city": "kimeisele/agent-city",
    ...
}
```

The **buddy_bubble** is a JSON-serializable snapshot of this routing table plus health/trust state, exportable for observability.

#### 5. Envelope Builder (`mahaclaw/envelope.py`)

Constructs the actual `DeliveryEnvelope` matching the canonical wire format:

```python
{
    "source": "mahaclaw",
    "target": resolved_target,
    "operation": rama.operation,
    "payload": {**original_payload, "_rama": rama.to_dict()},
    "timestamp": time.time(),
    "priority": nadi_priority_int,
    "correlation_id": rama.correlation_id,
    "ttl_s": ttl_ms / 1000.0,
    "id": uuid4(),
    # NADI metadata
    "envelope_id": uuid4(),
    "nadi_type": nadi_type,             # vyana (default), prana, apana, udana, samana
    "nadi_op": "send",
    "nadi_priority": rama.guna,         # rajas (default)
    "ttl_ms": ttl_ms,
    "maha_header_hex": computed_header,  # SHA-based routing header
}
```

Appends to `nadi_outbox.json` — fully compatible with the existing relay pump.

#### 6. Daemon Runner (`mahaclaw/daemon.py`)

`asyncio`-based event loop:
- Watches for inbound intents on the Unix socket
- Runs the 5-gate pipeline: intercept → classify → encode → resolve → enqueue
- Optional reverse path: watches `nadi_inbox.json` for responses
- Graceful SIGTERM handling, PID file, structured logging

### NADI Type Selection Strategy

| Intent Category    | NADI Type | Rationale |
|-------------------|-----------|-----------|
| Heartbeat/status  | `vyana`   | Distributed, default |
| Research inquiry  | `udana`   | Upward escalation to knowledge layer |
| Code execution    | `prana`   | Primary vital action |
| Response/ack      | `apana`   | Downward response flow |
| Sync/balance      | `samana`  | Equalizing cross-node state |

### MahaHeader Computation

Replicate the `build_maha_message_header_hex()` pattern from `steward_protocol_compat.py`:

```python
def build_maha_header_hex(source: str, target: str, operation: str,
                          nadi_type: str, priority: str, ttl_ms: int) -> str:
    raw = f"{source}:{target}:{operation}:{nadi_type}:{priority}:{ttl_ms}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
```

### File Layout

```
mahaclaw/
├── __init__.py
├── intercept.py      # TattvaGate.PARSE  — Intent interceptor
├── tattva.py         # TattvaGate.VALIDATE — Five Tattva classifier
├── rama.py           # TattvaGate.EXECUTE — 7-layer RAMA encoder
├── lotus.py          # TattvaGate.RESULT  — O(1) Lotus resolver + buddy_bubble
├── envelope.py       # TattvaGate.SYNC   — DeliveryEnvelope builder
└── daemon.py         # asyncio event loop + Unix socket server
```

### Constraints Met

1. **100% pure Python** — `asyncio`, `socket`, `json`, `dataclasses`, `hashlib`, `uuid`, `pathlib`. Zero pip dependencies.
2. **No semantic loss** — Original OpenClaw intent preserved verbatim in `payload._rama.original_intent`. RAMA signal is additive metadata.
3. **Wire-compatible** — Output envelopes match the exact format seen in `steward-federation/nadi/*.json` and `agent-internet/transport.py`.
4. **Five Tattva Gateway pattern** — Pipeline stages map 1:1 to `TattvaGate` enum.
5. **O(1) routing** — Dict-based Lotus resolution, not prefix-scan.
6. **Buddy bubble** — Introspectable routing state snapshot, JSON-serializable.
