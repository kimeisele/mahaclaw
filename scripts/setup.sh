#!/bin/bash
# Maha Claw federation setup — checks dependencies and peer connectivity.
#
# Usage:
#   ./scripts/setup.sh           # check everything
#   ./scripts/setup.sh --clone   # also clone peer repos if missing

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC} $1"; }
warn() { echo -e "  ${YELLOW}!${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; }

CLONE_PEERS=false
[ "${1:-}" = "--clone" ] && CLONE_PEERS=true

echo "Maha Claw — Federation Setup"
echo "=============================="
echo

# --- 1. Python ---
echo "Checking dependencies..."

if command -v python3 >/dev/null 2>&1; then
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    ok "Python $PY_VER"
else
    fail "Python 3 not found"
    echo "  Install Python 3.10+ and try again."
    exit 1
fi

if command -v curl >/dev/null 2>&1; then
    ok "curl"
else
    fail "curl not found (needed for Telegram API and LLM calls)"
    exit 1
fi

if command -v git >/dev/null 2>&1; then
    ok "git"
else
    fail "git not found"
    exit 1
fi

# --- 2. Pytest ---
echo
echo "Running tests..."
if python3 -m pytest tests/test_mahaclaw.py -q 2>&1 | tail -1 | grep -q "passed"; then
    RESULT=$(python3 -m pytest tests/test_mahaclaw.py -q 2>&1 | tail -1)
    ok "Tests: $RESULT"
else
    fail "Tests failed. Run: python3 -m pytest tests/test_mahaclaw.py -v"
    exit 1
fi

# --- 3. NADI files ---
echo
echo "Checking NADI transport..."

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [ -f "$REPO_ROOT/nadi_outbox.json" ]; then
    ok "nadi_outbox.json exists"
else
    echo '[]' > "$REPO_ROOT/nadi_outbox.json"
    ok "nadi_outbox.json created"
fi

if [ -f "$REPO_ROOT/nadi_inbox.json" ]; then
    ok "nadi_inbox.json exists"
else
    echo '[]' > "$REPO_ROOT/nadi_inbox.json"
    ok "nadi_inbox.json created"
fi

# --- 4. Peer repos ---
echo
echo "Checking federation peers..."

PARENT_DIR="$(dirname "$REPO_ROOT")"
PEERS=("steward" "steward-protocol" "steward-federation" "agent-city" "agent-internet" "agent-research" "agent-world")
MISSING=()

for peer in "${PEERS[@]}"; do
    if [ -d "$PARENT_DIR/$peer" ]; then
        ok "$peer"
    else
        warn "$peer not found at $PARENT_DIR/$peer"
        MISSING+=("$peer")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo
    if [ "$CLONE_PEERS" = true ]; then
        echo "Cloning missing peers..."
        for peer in "${MISSING[@]}"; do
            echo -n "  Cloning $peer... "
            if git clone --depth 1 "https://github.com/kimeisele/$peer.git" "$PARENT_DIR/$peer" 2>/dev/null; then
                echo -e "${GREEN}done${NC}"
            else
                echo -e "${RED}failed${NC} (check network/permissions)"
            fi
        done
    else
        echo "Missing ${#MISSING[@]} peer(s). To clone them:"
        echo "  ./scripts/setup.sh --clone"
        echo
        echo "Or manually:"
        for peer in "${MISSING[@]}"; do
            echo "  git clone https://github.com/kimeisele/$peer.git $PARENT_DIR/$peer"
        done
    fi
fi

# --- 5. Telegram token ---
echo
echo "Checking Telegram..."

if [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
    # Verify token with getMe
    BOT_RESP=$(curl -s "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe" 2>/dev/null || true)
    if echo "$BOT_RESP" | grep -q '"ok":true'; then
        BOT_NAME=$(echo "$BOT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['username'])" 2>/dev/null || echo "unknown")
        ok "Telegram bot: @$BOT_NAME"
    else
        warn "TELEGRAM_BOT_TOKEN is set but bot verification failed"
    fi
else
    warn "TELEGRAM_BOT_TOKEN not set"
    echo "  Get one from @BotFather on Telegram, then:"
    echo "  export TELEGRAM_BOT_TOKEN=your-token-here"
fi

# --- 6. Summary ---
echo
echo "=============================="

if [ ${#MISSING[@]} -eq 0 ] && [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
    echo -e "${GREEN}Ready to run!${NC}"
    echo
    echo "  # Steward-only mode (recommended)"
    echo "  python3 -m mahaclaw.channels.run_telegram --steward-only"
    echo
    echo "  # Terminal chat"
    echo "  python3 -m mahaclaw.chat"
elif [ -n "${TELEGRAM_BOT_TOKEN:-}" ]; then
    echo -e "${YELLOW}Telegram ready, but some federation peers are missing.${NC}"
    echo "  Bot will work but federation responses need the relay running."
    echo
    echo "  python3 -m mahaclaw.channels.run_telegram --steward-only"
else
    echo -e "${YELLOW}Set TELEGRAM_BOT_TOKEN to start the bot.${NC}"
    echo "  Or use terminal chat: python3 -m mahaclaw.chat"
fi
