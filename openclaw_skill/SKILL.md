---
name: federation-bridge
description: Bridge messages to the kimeisele RAMA/NADI agent federation. Translates OpenClaw intents into NADI envelopes with Tattva classification, RAMA signal encoding, and Lotus routing.
user-invocable: true
metadata: {"openclaw.requires.bins": ["python3"], "openclaw.os": ["darwin", "linux"], "openclaw.emoji": "🌐"}
---
You are the federation bridge skill. When the user wants to send a message, question, or task to the agent federation, use this skill.

## How to use

Run this command with the appropriate intent and target:

```bash
echo '{"intent":"<INTENT>","target":"<TARGET>","payload":<PAYLOAD>}' | python3 -m mahaclaw.cli
```

### Available intents

| Intent | Use when | Target |
|--------|----------|--------|
| `inquiry` | User asks a research question | `agent-research` |
| `code_analysis` | User wants code reviewed or built | `steward` |
| `heartbeat` | Periodic status check | `agent-city` |
| `governance_proposal` | Policy or governance action | `agent-world` |
| `discover_peers` | Find agents in the federation | `agent-internet` |

### Available targets

| Target | Description |
|--------|-------------|
| `agent-research` | Knowledge and research queries |
| `agent-city` | Local runtime and zone management |
| `agent-internet` | Routing, relay, and discovery |
| `agent-world` | Registry, policies, governance |
| `steward` | Core protocol and identity |
| `steward-protocol` | MahaMantra engine |
| `steward-federation` | Cross-agent transport hub |

### Waiting for a response

To block and wait for a federation response (up to N seconds):

```bash
echo '{"intent":"inquiry","target":"agent-research","payload":{"question":"What is quantum computing?"}}' | python3 -m mahaclaw.cli --wait 10
```

### Including OpenClaw context

Pass your session and skill info so the federation can route responses back:

```bash
echo '{"intent":"inquiry","target":"agent-research","payload":{"question":"..."},"openclaw_session":"'"$OPENCLAW_SESSION"'","openclaw_skill":"federation-bridge","openclaw_channel":"'"$OPENCLAW_CHANNEL"'"}' | python3 -m mahaclaw.cli --wait 10
```

### Response format

The command returns JSON on stdout:

```json
{
  "ok": true,
  "envelope_id": "env_a1b2c3d4...",
  "correlation_id": "uuid",
  "target": "kimeisele/agent-research",
  "element": "jala",
  "zone": "research",
  "guardian": "prahlada",
  "responded": true,
  "response": {
    "source": "agent-research",
    "operation": "inquiry_response",
    "data": {"answer": "..."}
  }
}
```

If `responded` is `false` or missing, the request was sent but no reply arrived within the wait window. The `envelope_id` can be used to track it later.

### Error handling

On failure, the command returns exit code 1 with:

```json
{"ok": false, "error": "description of what went wrong"}
```

Common errors:
- `"missing required fields: ['intent']"` — JSON missing `intent` or `target`
- `"unroutable target: xyz"` — target not found in federation routing table
- `"payload exceeds 65536 bytes"` — message too large
