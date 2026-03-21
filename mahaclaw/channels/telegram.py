"""Telegram channel adapter — bridges Telegram Bot API to Maha Claw.

Uses the Telegram Bot HTTP API directly via curl (pure stdlib).
No python-telegram-bot or other SDK required.

Environment:
    TELEGRAM_BOT_TOKEN  — required, from @BotFather

Usage:
    python3 -m mahaclaw.channels.telegram             # long-polling mode
    python3 -m mahaclaw.channels.telegram --webhook    # (future) webhook mode
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass

from . import IncomingMessage, MessageHandler

BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
API_BASE = "https://api.telegram.org/bot"
POLL_TIMEOUT_S = 30  # Telegram long-polling timeout
MAX_MESSAGE_LENGTH = 4096


@dataclass
class TelegramConfig:
    token: str
    poll_timeout: int = POLL_TIMEOUT_S
    allowed_users: frozenset[str] = frozenset()  # Empty = allow all


def config_from_env() -> TelegramConfig:
    """Load config from environment."""
    token = os.environ.get(BOT_TOKEN_ENV, "")
    if not token:
        raise RuntimeError(f"{BOT_TOKEN_ENV} not set")

    allowed = os.environ.get("TELEGRAM_ALLOWED_USERS", "")
    users = frozenset(u.strip() for u in allowed.split(",") if u.strip()) if allowed else frozenset()

    return TelegramConfig(token=token, allowed_users=users)


def _api_call(token: str, method: str, data: dict | None = None,
              timeout_s: int = 35) -> tuple[bool, dict]:
    """Call Telegram Bot API via curl.  Returns (ok, result_dict)."""
    url = f"{API_BASE}{token}/{method}"
    cmd = ["curl", "-s", "--max-time", str(timeout_s), url]

    if data:
        cmd.extend([
            "-X", "POST",
            "-H", "Content-Type: application/json",
            "-d", json.dumps(data),
        ])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s + 5)
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, {"description": str(e)}

    if result.returncode != 0:
        return False, {"description": result.stderr or f"curl exit {result.returncode}"}

    try:
        resp = json.loads(result.stdout)
        return resp.get("ok", False), resp.get("result", resp)
    except json.JSONDecodeError:
        return False, {"description": f"invalid JSON: {result.stdout[:200]}"}


def get_me(token: str) -> dict | None:
    """Get bot info.  Returns bot dict or None."""
    ok, data = _api_call(token, "getMe")
    return data if ok else None


def send_message(token: str, chat_id: str, text: str,
                 reply_to: str = "") -> tuple[bool, str]:
    """Send a text message.  Returns (ok, message_id or error)."""
    # Split long messages
    chunks = [text[i:i + MAX_MESSAGE_LENGTH] for i in range(0, len(text), MAX_MESSAGE_LENGTH)]

    last_msg_id = ""
    for chunk in chunks:
        data = {"chat_id": chat_id, "text": chunk, "parse_mode": "Markdown"}
        if reply_to:
            data["reply_to_message_id"] = reply_to

        ok, result = _api_call(token, "sendMessage", data)
        if not ok:
            desc = result.get("description", "unknown error")
            # Retry without Markdown if parse fails
            if "parse" in desc.lower():
                data["parse_mode"] = ""
                ok, result = _api_call(token, "sendMessage", data)
                if not ok:
                    return False, result.get("description", "send failed")

            else:
                return False, desc

        last_msg_id = str(result.get("message_id", ""))

    return True, last_msg_id


def send_typing(token: str, chat_id: str) -> None:
    """Send typing indicator."""
    _api_call(token, "sendChatAction", {"chat_id": chat_id, "action": "typing"}, timeout_s=5)


def _normalize_update(update: dict) -> IncomingMessage | None:
    """Convert a Telegram Update to IncomingMessage."""
    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return None

    text = msg.get("text", "")
    if not text:
        # Could be a photo, sticker, etc. — skip for now
        return None

    user = msg.get("from", {})
    chat = msg.get("chat", {})

    return IncomingMessage(
        channel="telegram",
        user_id=str(user.get("id", "")),
        username=user.get("username", user.get("first_name", "unknown")),
        text=text,
        chat_id=str(chat.get("id", "")),
        reply_to=str(msg.get("message_id", "")),
        raw=update,
    )


class TelegramAdapter:
    """Telegram long-polling adapter."""

    def __init__(self, config: TelegramConfig, handler: MessageHandler) -> None:
        self._config = config
        self._handler = handler
        self._running = False
        self._offset = 0

    def start(self) -> None:
        """Start long-polling loop (blocking)."""
        bot = get_me(self._config.token)
        if bot:
            name = bot.get("username", "unknown")
            print(f"  telegram: connected as @{name}")
        else:
            print("  telegram: could not verify bot token", file=__import__('sys').stderr)
            print("  Check that your TELEGRAM_BOT_TOKEN is correct.", file=__import__('sys').stderr)
            print("  Get a new one from @BotFather if needed.", file=__import__('sys').stderr)

        self._running = True
        while self._running:
            try:
                self._poll_once()
            except Exception as e:
                print(f"  telegram: poll error — {e}")
                time.sleep(5)

    def stop(self) -> None:
        """Signal the polling loop to stop."""
        self._running = False

    def _poll_once(self) -> None:
        """Fetch updates and dispatch to handler."""
        data = {
            "offset": self._offset,
            "timeout": self._config.poll_timeout,
            "allowed_updates": ["message", "edited_message"],
        }
        ok, result = _api_call(
            self._config.token, "getUpdates", data,
            timeout_s=self._config.poll_timeout + 5,
        )

        if not ok or not isinstance(result, list):
            return

        for update in result:
            update_id = update.get("update_id", 0)
            self._offset = max(self._offset, update_id + 1)

            msg = _normalize_update(update)
            if msg is None:
                continue

            # User allowlist check
            if self._config.allowed_users and msg.user_id not in self._config.allowed_users:
                continue

            try:
                self._handler(msg)
            except Exception as e:
                print(f"  telegram: handler error for {msg.user_id} — {e}")


# --- Standalone runner (for testing / direct use) ---

def _default_handler(msg: IncomingMessage) -> None:
    """Echo handler for testing — prints incoming messages."""
    print(f"  [{msg.username}] {msg.text}")


def main() -> int:
    """Run the Telegram adapter standalone (for testing)."""
    try:
        config = config_from_env()
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print("Maha Claw — Telegram Adapter")
    print("  mode: echo (standalone test)")
    adapter = TelegramAdapter(config, _default_handler)

    try:
        adapter.start()
    except KeyboardInterrupt:
        print("\nshutting down")
        adapter.stop()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
