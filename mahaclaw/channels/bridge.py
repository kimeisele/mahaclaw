"""Channel Bridge — connects any channel adapter to the federation pipeline.

Two paths:
  1. Inbound:  IncomingMessage → 5-gate pipeline → NADI outbox
  2. Outbound: NADI inbox → poll response → channel send

Supports two modes:
  - federation: Route through Steward via NADI
  - standalone: Direct LLM call (no federation needed)

Pure stdlib.
"""
from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field

from . import IncomingMessage
from ..intercept import parse_intent
from ..tattva import classify
from ..rama import encode_rama
from ..lotus import resolve_route
from ..envelope import build_and_enqueue
from ..inbox import poll_response, extract_response_payload
from ..session import SessionManager


DEFAULT_TARGET = "steward"
DEFAULT_WAIT_S = 30.0
RESPONSE_POLL_INTERVAL_S = 0.5


@dataclass
class BridgeConfig:
    """Configuration for the channel bridge."""
    mode: str = "federation"        # "federation", "standalone", or "steward-only"
    default_target: str = DEFAULT_TARGET
    response_wait_s: float = DEFAULT_WAIT_S
    session_db: str = "mahaclaw_sessions.db"
    # Standalone mode LLM config (only used when mode="standalone")
    llm_config: object = None
    # steward-only: ALL messages go through pipeline, never call local LLM
    steward_only: bool = False


class ChannelBridge:
    """Bridges channel messages to the federation or a local LLM."""

    def __init__(self, config: BridgeConfig | None = None) -> None:
        self._config = config or BridgeConfig()
        self._sessions = SessionManager(self._config.session_db)
        self._send_fns: dict[str, callable] = {}  # channel -> send function
        self._conversation_history: dict[str, list[dict]] = {}  # session_id -> messages

    def register_sender(self, channel: str, send_fn: callable) -> None:
        """Register a function to send messages back to a channel.

        send_fn(chat_id: str, text: str, reply_to: str) -> None
        """
        self._send_fns[channel] = send_fn

    def handle_message(self, msg: IncomingMessage) -> None:
        """Process an incoming message from any channel.

        This is the main entry point — pass this as the MessageHandler
        to any channel adapter.
        """
        session = self._sessions.get_or_create(
            msg.session_id,
            target=self._config.default_target,
        )
        self._sessions.log_message_in(msg.session_id, msg.text)

        # Check for slash commands
        if msg.text.startswith("/"):
            self._handle_command(msg)
            return

        if self._config.steward_only or self._config.mode == "steward-only":
            self._handle_federation(msg)
        elif self._config.mode == "standalone":
            self._handle_standalone(msg)
        else:
            self._handle_federation(msg)

    def _handle_command(self, msg: IncomingMessage) -> None:
        """Handle slash commands from channel users."""
        parts = msg.text.split(None, 1)
        cmd = parts[0].lower()

        if cmd == "/start":
            self._reply(msg, "Welcome to Maha Claw! Send any message to talk to the federation.")
        elif cmd == "/help":
            self._reply(msg, (
                "Commands:\n"
                "/status — show session info\n"
                "/target <name> — switch target agent\n"
                "/mode — toggle federation/standalone\n"
                "/clear — clear conversation history"
            ))
        elif cmd == "/status":
            session = self._sessions.get_or_create(msg.session_id)
            mode = self._config.mode
            self._reply(msg, (
                f"Session: {msg.session_id}\n"
                f"Mode: {mode}\n"
                f"Target: {session.target}\n"
                f"Messages: {session.message_count}"
            ))
        elif cmd == "/target" and len(parts) > 1:
            new_target = parts[1].strip()
            self._sessions.get_or_create(msg.session_id, target=new_target)
            self._reply(msg, f"Target switched to: {new_target}")
        elif cmd == "/mode":
            if self._config.steward_only:
                self._reply(msg, "Mode locked: steward-only (all messages route through Steward)")
            else:
                self._config.mode = "standalone" if self._config.mode == "federation" else "federation"
                self._reply(msg, f"Mode switched to: {self._config.mode}")
        elif cmd == "/clear":
            self._conversation_history.pop(msg.session_id, None)
            self._reply(msg, "Conversation history cleared.")
        else:
            self._reply(msg, f"Unknown command: {cmd}")

    def _handle_federation(self, msg: IncomingMessage) -> None:
        """Route message through the 5-gate pipeline to the federation."""
        session = self._sessions.get_or_create(msg.session_id)
        target = session.target or self._config.default_target

        # Detect intent type from message content
        intent_type = _detect_intent(msg.text)

        raw = json.dumps({
            "intent": intent_type,
            "target": target,
            "payload": {"message": msg.text},
            "priority": "rajas",
            "openclaw_channel": msg.channel,
            "openclaw_session": msg.session_id,
        })

        try:
            intent = parse_intent(raw)
            tattva = classify(intent)
            rama = encode_rama(intent, tattva)
            route = resolve_route(intent, rama)
            envelope_id, correlation_id = build_and_enqueue(intent, rama, route)
        except Exception as exc:
            self._reply(msg, f"Pipeline error: {exc}")
            return

        self._sessions.log_message_out(
            msg.session_id, envelope_id, correlation_id,
            target, tattva.dominant, tattva.zone,
        )

        # Async wait for response in background thread
        if self._config.response_wait_s > 0:
            self._reply(msg, f"[{tattva.dominant}/{tattva.zone}] Sent to {target}...")
            thread = threading.Thread(
                target=self._wait_for_response,
                args=(msg, correlation_id),
                daemon=True,
            )
            thread.start()
        else:
            self._reply(msg, f"[{tattva.dominant}/{tattva.zone}] Sent to {target} ({envelope_id[:12]})")

    def _wait_for_response(self, original_msg: IncomingMessage,
                           correlation_id: str) -> None:
        """Poll inbox for federation response and deliver to channel."""
        response = poll_response(
            correlation_id,
            timeout_s=self._config.response_wait_s,
        )

        if response is None:
            if self._config.steward_only:
                self._reply(original_msg,
                            "Federation is not responding. Steward may be offline or relay is not running.\n"
                            "Check that the MURALI cycle and federation relay are active.")
            else:
                self._reply(original_msg, "No response from federation (timeout)")
            return

        extracted = extract_response_payload(response)
        source = extracted.get("source", "unknown")
        operation = extracted.get("operation", "response")
        data = extracted.get("data", {})

        # Format response for the channel
        parts = [f"[{source}] ({operation})"]
        for k, v in data.items():
            val = str(v)
            if len(val) > 500:
                val = val[:497] + "..."
            parts.append(f"{k}: {val}")

        self._reply(original_msg, "\n".join(parts))
        self._sessions.log_message_in(
            original_msg.session_id,
            f"federation_response:{correlation_id}",
        )

    def _handle_standalone(self, msg: IncomingMessage) -> None:
        """Send message directly to LLM."""
        from ..llm import ask, config_from_env

        config = self._config.llm_config or config_from_env()

        # Maintain conversation history per session
        history = self._conversation_history.setdefault(msg.session_id, [])

        resp = ask(msg.text, config=config, history=history)

        if resp.ok:
            history.append({"role": "user", "content": msg.text})
            history.append({"role": "assistant", "content": resp.content})
            # Trim history to last 20 messages to prevent context overflow
            if len(history) > 20:
                self._conversation_history[msg.session_id] = history[-20:]
            self._reply(msg, resp.content)
        else:
            self._reply(msg, f"LLM error: {resp.error}")

    def _reply(self, msg: IncomingMessage, text: str) -> None:
        """Send a reply back to the channel the message came from."""
        send_fn = self._send_fns.get(msg.channel)
        if send_fn:
            try:
                send_fn(msg.chat_id, text, msg.reply_to)
            except Exception as e:
                print(f"  bridge: send error on {msg.channel} — {e}")
        else:
            # Fallback: print to stdout
            print(f"  [{msg.channel}:{msg.chat_id}] {text}")

    def close(self) -> None:
        """Clean up resources."""
        self._sessions.close()


def _detect_intent(text: str) -> str:
    """Detect intent type from natural language message."""
    lower = text.lower()
    if any(kw in lower for kw in ("build", "code", "compile", "debug", "test", "fix bug", "refactor")):
        return "code_analysis"
    if any(kw in lower for kw in ("govern", "vote", "policy", "proposal", "regulation")):
        return "governance_proposal"
    if any(kw in lower for kw in ("research", "study", "paper", "analyze", "investigate")):
        return "inquiry"
    if any(kw in lower for kw in ("find", "discover", "search", "who", "list agents", "what agents")):
        return "discover_peers"
    if any(kw in lower for kw in ("status", "ping", "health", "alive", "heartbeat")):
        return "heartbeat"
    return "inquiry"
