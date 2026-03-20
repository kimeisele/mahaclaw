# Maha Claw — Architecture

## What this is

Maha Claw bridges [OpenClaw](https://github.com/openclaw/openclaw) (214k+ stars,
TypeScript/Node.js personal AI agent, 13k+ skills on ClawHub) into the
kimeisele RAMA/NADI federation.

OpenClaw is an external, real-world project: a daemon that connects to 12+
messaging platforms (Telegram, WhatsApp, Slack, Discord, Signal, iMessage...),
runs LLM-powered agent turns with tool use, and has a heartbeat scheduler,
skill system, hooks engine, and sub-agent spawning.

Our federation (steward-protocol, agent-city, agent-internet) uses a completely
different transport: NADI envelopes with Five-Prana typing, Guna priorities,
MahaHeader routing, and TattvaGate pipelines.

**Maha Claw sits between these two worlds.** Pure Python, zero npm, zero pip deps.

## The two sides

### OpenClaw side (TypeScript, Node.js)

- **Gateway daemon** on `127.0.0.1:18789` (typed WebSocket API)
- **Skills**: SKILL.md files with YAML frontmatter (`name`, `description`, `user-invocable`, `metadata`)
- **Hooks**: event-driven scripts on `command:new`, `agent:bootstrap`, tool lifecycle
- **Heartbeat**: periodic agent turns reading HEARTBEAT.md, default every 30min
- **Sessions**: JSONL files, layered memory (session → daily logs → MEMORY.md → vector search)
- **Sub-agents**: isolated background sessions with restricted tools
- **Channel bridges**: normalize messages from all platforms into common format
- **Message flow**: Channel bridge → Session manager → Command queue → Prompt assembly → LLM → Tool execution

### Federation side (Python)

- **NADI transport**: `nadi_outbox.json` / `nadi_inbox.json`, relay via agent-internet
- **Five NADI types**: prana, apana, vyana, udana, samana
- **Guna priorities**: tamas (1), rajas (5), sattva (8), suddha (10)
- **MahaHeader**: SHA-256 hex of `source:target:operation:nadi_type:priority:ttl_ms`
- **TattvaGate pipeline**: PARSE → VALIDATE → EXECUTE → RESULT → SYNC
- **Lotus routing**: RegistryRouter with trust + health gating
- **RAMA coordinates**: element (Tattva) + zone + guardian (Mahajana position)
- **DeliveryEnvelope**: canonical wire format with envelope_id, correlation_id, nadi metadata

## Integration architecture

```
OpenClaw Gateway (Node.js, :18789 WebSocket)
       │
       │  hooks: command:new / agent:bootstrap
       │  or: SKILL.md that shells out to mahaclaw CLI
       │
       ▼
┌─────────────────────────────────────────────────┐
│              MAHA CLAW (Pure Python)             │
│                                                  │
│  Input:  OpenClaw hook event / skill invocation  │
│          JSON via Unix socket or stdin pipe       │
│                                                  │
│  Gate 1  PARSE     ─── validate + normalize      │
│  Gate 2  VALIDATE  ─── Tattva classify (5D)      │
│  Gate 3  EXECUTE   ─── RAMA encode (7-layer)     │
│  Gate 4  RESULT    ─── Lotus route resolve       │
│  Gate 5  SYNC      ─── envelope → nadi_outbox    │
│                                                  │
│  Reverse: nadi_inbox → OpenClaw webhook/event    │
│                                                  │
└─────────────────────────────────────────────────┘
       │
       ▼
nadi_outbox.json → agent-internet relay pump → federation
```

## How OpenClaw connects to Maha Claw

Three integration modes, from simplest to deepest:

### Mode 1: OpenClaw Skill (simplest)

An OpenClaw skill that shells out to the mahaclaw CLI:

```yaml
# skills/federation-bridge/SKILL.md
---
name: federation-bridge
description: Send a message to the kimeisele agent federation via NADI transport
user-invocable: true
metadata: {"openclaw.requires.bins": ["python3"]}
---
When the user wants to send something to the federation, run:

echo '{"intent":"<operation>","target":"<node>","payload":<payload>}' | \
  python3 -m mahaclaw.cli

Report the envelope_id from the response.
```

### Mode 2: OpenClaw Hook (automatic)

A `command:new` hook that intercepts specific operations and forwards them:

```bash
#!/bin/bash
# hooks/federation-relay.sh
# Triggered on command:new events
echo "$OPENCLAW_EVENT" | python3 -m mahaclaw.cli --from-hook
```

### Mode 3: WebSocket bridge (deepest)

A Python asyncio task that connects to the OpenClaw Gateway WebSocket at
`:18789`, subscribes to events, and translates them in real-time.
This is Phase 3 — requires understanding the Gateway's typed WS protocol.

## Input format

Maha Claw accepts this JSON (via socket, stdin, or CLI):

```json
{
  "intent": "inquiry",
  "target": "agent-research",
  "payload": {"question": "What is dark matter?"},
  "priority": "rajas",
  "ttl_ms": 24000,
  "openclaw_session": "agent:default:telegram:dm:12345",
  "openclaw_skill": "federation-bridge"
}
```

`intent` and `target` are required. Everything else has defaults.
`openclaw_session` and `openclaw_skill` are preserved in the envelope payload
for the reverse path (federation response → OpenClaw).

## OpenClaw operation → Tattva mapping

| OpenClaw context | Tattva | Zone | NADI type | Rationale |
|---|---|---|---|---|
| Heartbeat (HEARTBEAT.md) | Vayu | general | vyana | periodic status, distributed |
| Skill invocation (tool use) | Prithvi | engineering | prana | active execution |
| Research / question | Jala | research | udana | upward to knowledge layer |
| Governance / voting | Agni | governance | prana | authoritative action |
| Discovery / search | Akasha | discovery | udana | exploratory |
| Sub-agent spawn | Vayu | general | vyana | delegation |
| Webhook / automation | Prithvi | engineering | samana | sync/balance |
| Memory write | Jala | research | samana | knowledge consolidation |

## NADI wire format (output)

Every envelope written to `nadi_outbox.json`:

```json
{
  "source": "mahaclaw",
  "source_city_id": "mahaclaw",
  "target": "agent-research",
  "target_city_id": "kimeisele/agent-research",
  "operation": "inquiry",
  "payload": {
    "question": "What is dark matter?",
    "_rama": {"element":"jala","zone":"research","guardian":"prahlada","quarter":"karma","guna":"rajas","position":9,"affinity":{"akasha":0.4,"vayu":0,"agni":0,"jala":0.9,"prithvi":0}},
    "_openclaw": {"session":"agent:default:telegram:dm:12345","skill":"federation-bridge"}
  },
  "envelope_id": "env_a1b2c3d4e5f6g7h8",
  "correlation_id": "uuid",
  "id": "uuid",
  "timestamp": 1711000000.0,
  "priority": 5,
  "ttl_s": 24.0,
  "ttl_ms": 24000,
  "nadi_type": "udana",
  "nadi_op": "send",
  "nadi_priority": "rajas",
  "maha_header_hex": "sha256_first_32_chars"
}
```

## File layout

```
mahaclaw/
  __init__.py         package marker
  intercept.py        Gate 1 PARSE — validate JSON from OpenClaw
  tattva.py           Gate 2 VALIDATE — Five Tattva classifier
  rama.py             Gate 3 EXECUTE — 7-layer RAMA encoder
  lotus.py            Gate 4 RESULT — O(1) Lotus route resolver
  envelope.py         Gate 5 SYNC — DeliveryEnvelope → outbox
  daemon.py           asyncio Unix socket server
  cli.py              CLI entry point (stdin/pipe mode for OpenClaw skills)
```

## Upstream references

### OpenClaw (external)
- Repo: https://github.com/openclaw/openclaw
- Docs: https://docs.openclaw.ai/
- Skills: https://docs.openclaw.ai/tools/skills
- Heartbeat: https://docs.openclaw.ai/gateway/heartbeat
- Gateway WebSocket: `127.0.0.1:18789`
- Architecture: https://gist.github.com/royosherove/971c7b4a350a30ac8a8dad41604a95a0

### Federation (kimeisele)
- steward-protocol: MahaMantra engine, TattvaGate, NADI substrate
- agent-city: zones (Five Tattvas), RAMA coordinates, MURALI governance
- agent-internet: Lotus routing, NADI relay, trust ledger
- steward-federation: nadi_inbox/outbox hub, cross-agent transport
- steward: Open-Claw superagent engine (Sankhya-25 cognitive model)
