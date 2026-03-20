#!/bin/bash
# OpenClaw hook: command:new → federation relay
#
# Install: copy to your OpenClaw workspace hooks/ directory.
# Triggers on every new command. Filters for federation-targeted intents.
#
# The hook receives the OpenClaw event JSON via $OPENCLAW_EVENT.
# It extracts relevant fields and pipes them to mahaclaw.

set -euo pipefail

# Only relay if the event payload contains a federation target
if echo "$OPENCLAW_EVENT" | python3 -c "
import sys, json
ev = json.load(sys.stdin)
# Check if this event is tagged for federation
payload = ev.get('payload', {})
if not payload.get('federation_target'):
    sys.exit(1)
print(json.dumps({
    'intent': payload.get('intent', 'inquiry'),
    'target': payload['federation_target'],
    'payload': {k: v for k, v in payload.items() if k not in ('intent', 'federation_target')},
    'openclaw_session': ev.get('session', ''),
    'openclaw_channel': ev.get('channel', ''),
    'openclaw_agent': ev.get('agent', ''),
}))
" 2>/dev/null | python3 -m mahaclaw.cli; then
    :  # Relayed successfully
fi
