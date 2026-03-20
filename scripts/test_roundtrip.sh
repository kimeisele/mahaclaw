#!/bin/bash
# Manual roundtrip test: send an inquiry to steward and wait for response.
#
# Usage:
#   ./scripts/test_roundtrip.sh              # inquiry to steward
#   ./scripts/test_roundtrip.sh heartbeat    # heartbeat to steward
#   ./scripts/test_roundtrip.sh status       # quick status check

set -euo pipefail

INTENT="${1:-inquiry}"
WAIT="${MAHACLAW_WAIT:-30}"

case "$INTENT" in
  inquiry)
    echo '{"intent":"inquiry","target":"steward","payload":{"query":"What agents are in the federation?"}}' \
      | python3 -m mahaclaw.cli --wait "$WAIT"
    ;;
  heartbeat)
    echo '{"intent":"heartbeat","target":"steward","payload":{"agent_id":"mahaclaw","health":1.0}}' \
      | python3 -m mahaclaw.cli --wait "$WAIT"
    ;;
  status)
    echo '{"intent":"heartbeat","target":"steward","payload":{"query":"status"}}' \
      | python3 -m mahaclaw.cli --wait "$WAIT"
    ;;
  *)
    echo "Usage: $0 [inquiry|heartbeat|status]"
    exit 1
    ;;
esac
