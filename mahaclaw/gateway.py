"""Maha Claw Gateway — Python-native agent gateway.

asyncio WebSocket server on port 18789 (same port as OpenClaw Gateway).
Accepts JSON messages, runs them through the 5-gate pipeline, and optionally
waits for federation responses.

Pure stdlib: asyncio + hashlib + struct for the WebSocket handshake.
No websockets pip package needed.

Usage:
    python3 -m mahaclaw.gateway
    python3 -m mahaclaw.gateway --port 18789 --host 127.0.0.1
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import signal
import struct
import sys
import time
from pathlib import Path

from .intercept import parse_intent
from .tattva import classify
from .rama import encode_rama
from .lotus import resolve_route
from .envelope import build_and_enqueue
from .inbox import poll_response, extract_response_payload

logger = logging.getLogger("mahaclaw.gateway")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18789
WS_MAGIC = b"258EAFA5-E914-47DA-95CA-5AB9964DA7F3"


# ---------------------------------------------------------------------------
# Minimal RFC 6455 WebSocket (stdlib only, no pip)
# ---------------------------------------------------------------------------

def _ws_accept_key(client_key: bytes) -> str:
    """Compute Sec-WebSocket-Accept from client key."""
    digest = hashlib.sha1(client_key.strip() + WS_MAGIC).digest()
    return base64.b64encode(digest).decode()


async def _ws_handshake(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> bool:
    """Perform the WebSocket opening handshake.  Returns True on success."""
    request = b""
    while not request.endswith(b"\r\n\r\n"):
        chunk = await asyncio.wait_for(reader.read(4096), timeout=5.0)
        if not chunk:
            return False
        request += chunk

    headers = {}
    for line in request.decode("utf-8", errors="replace").split("\r\n")[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()

    client_key = headers.get("sec-websocket-key", "")
    if not client_key:
        # Not a WebSocket request — send HTTP health response
        body = json.dumps({"status": "ok", "service": "mahaclaw-gateway", "ts": time.time()})
        resp = (
            f"HTTP/1.1 200 OK\r\n"
            f"Content-Type: application/json\r\n"
            f"Content-Length: {len(body)}\r\n"
            f"Connection: close\r\n"
            f"\r\n{body}"
        )
        writer.write(resp.encode())
        await writer.drain()
        return False

    accept_key = _ws_accept_key(client_key.encode())
    response = (
        "HTTP/1.1 101 Switching Protocols\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Accept: {accept_key}\r\n"
        "\r\n"
    )
    writer.write(response.encode())
    await writer.drain()
    return True


async def _ws_read_frame(reader: asyncio.StreamReader) -> bytes | None:
    """Read a single WebSocket frame.  Returns payload or None on close."""
    header = await reader.readexactly(2)
    opcode = header[0] & 0x0F
    masked = (header[1] & 0x80) != 0
    length = header[1] & 0x7F

    if opcode == 0x8:  # Close frame
        return None

    if length == 126:
        length = struct.unpack("!H", await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", await reader.readexactly(8))[0]

    mask = await reader.readexactly(4) if masked else b"\x00" * 4
    data = await reader.readexactly(length)

    if masked:
        data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))

    return data


def _ws_frame(payload: bytes, opcode: int = 0x1) -> bytes:
    """Build a WebSocket frame (server → client, unmasked)."""
    frame = bytearray()
    frame.append(0x80 | opcode)  # FIN + opcode

    length = len(payload)
    if length < 126:
        frame.append(length)
    elif length < 65536:
        frame.append(126)
        frame.extend(struct.pack("!H", length))
    else:
        frame.append(127)
        frame.extend(struct.pack("!Q", length))

    frame.extend(payload)
    return bytes(frame)


def _ws_close_frame(code: int = 1000) -> bytes:
    """Build a WebSocket close frame."""
    return _ws_frame(struct.pack("!H", code), opcode=0x8)


# ---------------------------------------------------------------------------
# Message handling
# ---------------------------------------------------------------------------

async def _process_message(text: str) -> dict:
    """Run a message through the 5-gate pipeline."""
    data = json.loads(text)

    # If it's a raw text message (from chat), wrap it as an intent
    if "intent" not in data and "message" in data:
        target = data.get("target", "agent-research")
        msg = data["message"]
        # Auto-detect intent
        intent_type = "inquiry"
        lower = msg.lower()
        if any(kw in lower for kw in ("build", "code", "compile", "debug")):
            intent_type = "code_analysis"
        elif any(kw in lower for kw in ("govern", "vote", "policy")):
            intent_type = "governance_proposal"
        elif any(kw in lower for kw in ("find", "discover", "search", "who")):
            intent_type = "discover_peers"
        elif any(kw in lower for kw in ("status", "ping", "health")):
            intent_type = "heartbeat"

        data = {"intent": intent_type, "target": target, "payload": {"message": msg}}

    raw = json.dumps(data)
    intent = parse_intent(raw)
    tattva = classify(intent)
    rama = encode_rama(intent, tattva)
    route = resolve_route(intent, rama)
    envelope_id, correlation_id = build_and_enqueue(intent, rama, route)

    result = {
        "ok": True,
        "envelope_id": envelope_id,
        "correlation_id": correlation_id,
        "target": route["target_city_id"],
        "element": tattva.dominant,
        "zone": tattva.zone,
        "guardian": rama.guardian,
    }

    # Quick poll for response (non-blocking, 2s)
    wait_s = data.get("wait", 2.0)
    if wait_s > 0:
        response = poll_response(correlation_id, timeout_s=min(wait_s, 30.0))
        if response is not None:
            result["response"] = extract_response_payload(response)
            result["responded"] = True
        else:
            result["responded"] = False

    return result


async def handle_ws_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """Handle a single WebSocket client connection."""
    addr = writer.get_extra_info("peername") or "unknown"
    logger.info("connection from %s", addr)

    try:
        is_ws = await _ws_handshake(reader, writer)
        if not is_ws:
            writer.close()
            await writer.wait_closed()
            return

        logger.info("websocket established: %s", addr)

        while True:
            try:
                data = await asyncio.wait_for(_ws_read_frame(reader), timeout=300.0)
            except asyncio.TimeoutError:
                # Send ping, close on timeout
                break

            if data is None:
                break  # Close frame

            text = data.decode("utf-8", errors="replace").strip()
            if not text:
                continue

            try:
                result = await _process_message(text)
            except Exception as exc:
                result = {"ok": False, "error": str(exc)}

            frame = _ws_frame(json.dumps(result).encode())
            writer.write(frame)
            await writer.drain()

    except (ConnectionResetError, asyncio.IncompleteReadError, asyncio.TimeoutError):
        pass
    except Exception as exc:
        logger.warning("client error: %s", exc)
    finally:
        try:
            writer.write(_ws_close_frame())
            await writer.drain()
        except Exception:
            pass
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        logger.info("disconnected: %s", addr)


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

async def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Start the Maha Claw Gateway."""
    server = await asyncio.start_server(handle_ws_client, host, port)

    loop = asyncio.get_running_loop()
    stop = loop.create_future()

    def _shutdown(sig: int) -> None:
        if not stop.done():
            stop.set_result(sig)

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _shutdown, sig)

    logger.info("mahaclaw gateway listening on ws://%s:%d", host, port)
    logger.info("health check: http://%s:%d/health", host, port)

    try:
        await stop
    finally:
        server.close()
        await server.wait_closed()
        logger.info("mahaclaw gateway stopped")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    host = DEFAULT_HOST
    port = DEFAULT_PORT
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--host" and i + 1 < len(args):
            host = args[i + 1]
        elif arg == "--port" and i + 1 < len(args):
            port = int(args[i + 1])

    asyncio.run(serve(host, port))


if __name__ == "__main__":
    main()
