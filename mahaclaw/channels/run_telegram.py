"""Run Maha Claw with Telegram channel — wires adapter + bridge together.

Usage:
    # Recommended: steward-only mode (no API key needed, uses Steward's LLMs)
    TELEGRAM_BOT_TOKEN=xxx python3 -m mahaclaw.channels.run_telegram --steward-only

    # Federation mode (default — routes through pipeline, can switch modes)
    TELEGRAM_BOT_TOKEN=xxx python3 -m mahaclaw.channels.run_telegram

    # Standalone mode (bring your own LLM)
    MAHACLAW_LLM_URL=http://localhost:11434/v1 TELEGRAM_BOT_TOKEN=xxx python3 -m mahaclaw.channels.run_telegram --standalone
"""
from __future__ import annotations

import sys

from .telegram import TelegramAdapter, config_from_env as tg_config, send_message, send_typing
from .bridge import ChannelBridge, BridgeConfig


def main() -> int:
    standalone = "--standalone" in sys.argv
    steward_only = "--steward-only" in sys.argv

    if standalone and steward_only:
        print("error: --standalone and --steward-only are mutually exclusive", file=sys.stderr)
        return 1

    try:
        tg_cfg = tg_config()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if steward_only:
        mode = "steward-only"
    elif standalone:
        mode = "standalone"
    else:
        mode = "federation"

    bridge_cfg = BridgeConfig(
        mode=mode,
        steward_only=steward_only,
    )
    bridge = ChannelBridge(bridge_cfg)

    # Register Telegram sender
    def telegram_send(chat_id: str, text: str, reply_to: str = "") -> None:
        send_typing(tg_cfg.token, chat_id)
        send_message(tg_cfg.token, chat_id, text, reply_to=reply_to)

    bridge.register_sender("telegram", telegram_send)

    # Create adapter with bridge as handler
    adapter = TelegramAdapter(tg_cfg, bridge.handle_message)

    print(f"Maha Claw — Telegram ({mode} mode)")
    if steward_only:
        print("  All messages route through Steward (no local LLM)")
    print("  long-polling started")

    try:
        adapter.start()
    except KeyboardInterrupt:
        print("\nshutting down")
        adapter.stop()
        bridge.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
