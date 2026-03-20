# CLAUDE.md — Maha Claw Project Memory

## What this project IS

Maha Claw bridges **[OpenClaw](https://github.com/openclaw/openclaw)** (214k+ GitHub
stars, TypeScript/Node.js personal AI agent by Peter Steinberger) into the
**kimeisele RAMA/NADI federation** (steward-protocol, agent-city, agent-internet).

OpenClaw is a real, external, massively popular open-source project. It runs as a
Gateway daemon with 12+ messaging platform adapters, a skill system (13k+ skills
on ClawHub), heartbeat scheduler, hooks engine, sub-agent spawning, and layered
memory. Its Gateway listens on `127.0.0.1:18789` (typed WebSocket).

Our federation uses a completely different transport: NADI envelopes with
Five-Prana typing, Guna priorities, TattvaGate pipelines, and Lotus routing.

**Maha Claw is the pure Python adapter between these two worlds.**

## Current state

PoC is working. 5-gate pipeline, 26 tests passing, wire-compatible envelopes.

| Gate     | File                    | What it does                          |
|----------|-------------------------|---------------------------------------|
| PARSE    | `mahaclaw/intercept.py` | Validate incoming JSON intent         |
| VALIDATE | `mahaclaw/tattva.py`    | 5D Tattva affinity → element/zone     |
| EXECUTE  | `mahaclaw/rama.py`      | 7-layer RAMA signal encoding          |
| RESULT   | `mahaclaw/lotus.py`     | O(1) route resolution + buddy_bubble  |
| SYNC     | `mahaclaw/envelope.py`  | DeliveryEnvelope → nadi_outbox.json   |

Additional: `mahaclaw/daemon.py` (asyncio Unix socket), `mahaclaw/cli.py` (stdin pipe for OpenClaw skills).

## OpenClaw integration points

OpenClaw connects to Maha Claw in three ways:

1. **Skill mode**: An OpenClaw SKILL.md that shells out to `python3 -m mahaclaw.cli`
2. **Hook mode**: A `command:new` hook script that pipes event JSON to mahaclaw
3. **WebSocket mode** (future): Direct connection to Gateway at `:18789`

OpenClaw metadata (`openclaw_session`, `openclaw_skill`) is preserved in the
envelope payload under `_openclaw` for the reverse path.

## Hard rules

1. **Pure Python stdlib only.** No pip deps at runtime. `curl` subprocess for HTTP.
2. **Short commit messages.** 3-8 words. `"add tattva classifier"`, `"fix lotus fallback"`.
3. **No new files without a reason.** Edit existing first.
4. **Tests must pass before push.** `python -m pytest tests/test_mahaclaw.py -q`
5. **Wire compatibility is sacred.** Envelope format matches `agent-internet/transport.py:DeliveryEnvelope`.
6. **Do not touch `.well-known/` files.** Auto-generated.
7. **OpenClaw is real.** Do not hallucinate its API. Check https://docs.openclaw.ai/ when unsure.

## Architecture decisions (locked)

- Unix domain socket for local IPC (not HTTP)
- NADI type derived from dominant Tattva element
- MahaHeader = SHA-256(`source:target:op:nadi_type:priority:ttl_ms`)[:32]
- Parampara vector = `(position + 1) * 37`
- Unknown intents default to position 9 (Prahlada/EXEC_SERVICE), vayu (general)
- OpenClaw session/skill metadata preserved in `payload._openclaw`

## Upstream wire format

Envelopes in `nadi_outbox.json` must have:
```
source, source_city_id, target, target_city_id, operation, payload,
envelope_id, correlation_id, id, timestamp, priority, ttl_s, ttl_ms,
nadi_type, nadi_op, nadi_priority, maha_header_hex
```

NADI types: `prana`, `apana`, `vyana`, `udana`, `samana`
Guna priorities: `tamas` (1), `rajas` (5), `sattva` (8), `suddha` (10)

## Roadmap

### Next: OpenClaw skill package
Create a proper SKILL.md that can be installed in any OpenClaw workspace.
Include metadata gates (`openclaw.requires.bins: ["python3"]`).

### Then: Reverse path
Watch `nadi_inbox.json` for federation responses. Translate back to OpenClaw
format. Either write to OpenClaw memory files or call back via webhook.

### Then: WebSocket bridge
Connect directly to OpenClaw Gateway at `:18789`. Subscribe to events.
Translate in real-time without shelling out.

### Then: Dynamic Tattva classification
Replace static `_AFFINITY_RULES` with config file or Jiva model integration.

### Then: Federation registration
Update capabilities.json: `produces: ["nadi_envelope"]`, `consumes: ["openclaw_intent"]`.
Register in agent-city Engineering zone.

## How to run

```bash
# Tests
python -m pytest tests/test_mahaclaw.py -q

# Daemon mode (Unix socket)
python -m mahaclaw.daemon

# CLI mode (pipe from OpenClaw skill)
echo '{"intent":"inquiry","target":"agent-research","payload":{"q":"test"}}' | python -m mahaclaw.cli

# CLI with response wait (blocks up to 10s for federation reply)
echo '{"intent":"inquiry","target":"agent-research","payload":{"q":"test"}}' | python -m mahaclaw.cli --wait 10

# Socket client
echo '{"intent":"inquiry","target":"agent-research"}' | \
  python -c "import socket,sys; s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.connect('mahaclaw.sock'); s.sendall(sys.stdin.buffer.read()); s.shutdown(1); print(s.recv(65536).decode())"

# Inspect
python -c "from mahaclaw.lotus import buddy_bubble; import json; print(json.dumps(buddy_bubble(),indent=2))"
```

## File map

```
mahaclaw/
  __init__.py           package
  intercept.py          Gate 1 PARSE
  tattva.py             Gate 2 VALIDATE
  rama.py               Gate 3 EXECUTE
  lotus.py              Gate 4 RESULT
  envelope.py           Gate 5 SYNC
  inbox.py              Return loop — poll nadi_inbox.json for responses
  daemon.py             asyncio Unix socket server
  cli.py                stdin/pipe entry point for OpenClaw skills
  chat.py               standalone terminal chat (no OpenClaw needed)
  __main__.py           python -m mahaclaw.cli alias

openclaw_skill/
  SKILL.md              OpenClaw skill definition (install in any workspace)
  HEARTBEAT.md          Federation heartbeat checklist for OpenClaw heartbeat
  hooks/
    federation-relay.sh command:new hook for automatic forwarding

tests/
  test_mahaclaw.py      39 tests (gates + inbox + CLI + chat + e2e + socket)
  integration/
    mock_openclaw.js    Node.js mock gateway (44 integration tests)

docs/
  maha-claw-architecture.md   architecture with real OpenClaw integration points

scripts/                inherited federation template scripts (don't modify)
data/federation/        seed descriptors (read by lotus.py)
nadi_outbox.json        relay outbox
nadi_inbox.json         relay inbox (federation responses land here)
```

## Key references

- OpenClaw repo: https://github.com/openclaw/openclaw
- OpenClaw docs: https://docs.openclaw.ai/
- OpenClaw skills: https://docs.openclaw.ai/tools/skills
- OpenClaw heartbeat: https://docs.openclaw.ai/gateway/heartbeat
- OpenClaw architecture: https://gist.github.com/royosherove/971c7b4a350a30ac8a8dad41604a95a0
- steward-protocol (MahaMantra): https://github.com/kimeisele/steward-protocol
- agent-internet (Lotus/NADI): https://github.com/kimeisele/agent-internet
