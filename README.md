# Maha Claw

Talk to the [kimeisele federation](https://github.com/kimeisele) from Telegram. No API keys, no setup beyond a bot token.

## Quick start (Telegram)

```bash
git clone https://github.com/kimeisele/mahaclaw && cd mahaclaw

# Get a bot token from @BotFather on Telegram
export TELEGRAM_BOT_TOKEN=your-token-here

# Start (steward-only mode — federation thinks for you, zero cost)
python3 -m mahaclaw.channels.run_telegram --steward-only
```

That's it. Send a message to your bot on Telegram.

## What happens

Your message goes through a 5-gate pipeline, becomes a NADI envelope, and lands in Steward's inbox. Steward has 3 free LLMs (Gemini Flash, Mistral, Groq), 17 tools, and a full cognitive engine. It thinks, and sends the answer back to your Telegram chat.

You bring the bot token. The federation brings the brain.

## Other ways to run

```bash
# Terminal chat (no Telegram needed)
python3 -m mahaclaw.chat

# Terminal chat with your own LLM (Ollama, OpenRouter, any OpenAI-compatible)
python3 -m mahaclaw.chat --standalone
MAHACLAW_LLM_URL=http://localhost:11434/v1 python3 -m mahaclaw.chat --standalone

# Telegram with your own LLM (standalone mode)
MAHACLAW_LLM_URL=http://localhost:11434/v1 TELEGRAM_BOT_TOKEN=xxx \
  python3 -m mahaclaw.channels.run_telegram --standalone

# Pipe mode (for scripts and OpenClaw skills)
echo '{"intent":"inquiry","target":"steward","payload":{"query":"status"}}' \
  | python3 -m mahaclaw.cli --wait 30
```

## Requirements

- Python 3.10+
- `curl` (for Telegram API and LLM calls)
- No pip dependencies at runtime

## Federation setup

If the federation relay isn't running yet:

```bash
./scripts/setup.sh
```

This clones the necessary peer repos, verifies connectivity, and tells you what to start.

## Commands (in Telegram or terminal chat)

| Command | What it does |
|---------|-------------|
| `/status` | Show session info and current mode |
| `/target <name>` | Switch target agent (steward, agent-research, agent-city) |
| `/mode` | Toggle federation/standalone (not available in steward-only) |
| `/help` | Show all commands |

## Architecture

For developers: see [CLAUDE.md](CLAUDE.md) and [docs/](docs/).

## License

Part of the [kimeisele federation](https://github.com/kimeisele).
