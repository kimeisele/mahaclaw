"""Channel adapters — bridge user-facing platforms to the federation.

Each adapter implements the ChannelAdapter protocol:
  - start(): Begin listening for messages
  - stop(): Gracefully shut down
  - send(session_id, text): Deliver a message to a user

Pure stdlib where possible. Platform SDKs are imported lazily and
only at runtime — import errors are caught and reported cleanly.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass
class IncomingMessage:
    """Normalized incoming message from any channel."""
    channel: str        # "telegram", "discord", "slack"
    user_id: str        # Platform-specific user ID
    username: str       # Display name
    text: str           # Message content
    chat_id: str        # Chat/channel/room ID
    reply_to: str = ""  # Message ID being replied to
    raw: dict = None    # Original platform-specific data

    def __post_init__(self):
        if self.raw is None:
            self.raw = {}

    @property
    def session_id(self) -> str:
        """Generate a consistent session ID for this user/chat combo."""
        return f"mahaclaw:{self.channel}:{self.chat_id}:{self.user_id}"


# Callback type: adapter calls this when a message arrives
MessageHandler = Callable[[IncomingMessage], None]
