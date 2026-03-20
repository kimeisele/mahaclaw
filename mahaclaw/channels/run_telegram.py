"""Run Maha Claw with Telegram channel — wires adapter + bridge together.

Usage:
    TELEGRAM_BOT_TOKEN=xxx python3 -m mahaclaw.channels.run_telegram
    TELEGRAM_BOT_TOKEN=xxx python3 -m mahaclaw.channels.run_telegram --standalone
"""
from __future__ import annotations

import sys

from .telegram import TelegramAdapter, config_from_env as tg_config, send_message, send_typing
from .bridge import ChannelBridge, BridgeConfig


def main() -> int:
    # Parse mode
    standalone = "--standalone" in sys.argv

    try:
        tg_cfg = tg_config()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    bridge_cfg = BridgeConfig(
        mode="standalone" if standalone else "federation",
    )
    bridge = ChannelBridge(bridge_cfg)

    # Register Telegram sender
    def telegram_send(chat_id: str, text: str, reply_to: str = "") -> None:
        send_typing(tg_cfg.token, chat_id)
        send_message(tg_cfg.token, chat_id, text, reply_to=reply_to)

    bridge.register_sender("telegram", telegram_send)

    # Create adapter with bridge as handler
    adapter = TelegramAdapter(tg_cfg, bridge.handle_message)

    mode_label = "standalone" if standalone else "federation"
    print(f"Maha Claw — Telegram ({mode_label} mode)")
    print(f"  long-polling started")

    try:
        adapter.start()
    except KeyboardInterrupt:
        print("\nshutting down")
        adapter.stop()
        bridge.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
