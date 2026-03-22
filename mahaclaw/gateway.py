"""Maha Claw Gateway — Python-native agent gateway.

asyncio WebSocket server on port 18789 (same port as OpenClaw Gateway).
Serves the webchat UI on GET / and handles WebSocket on /ws.
All messages routed through runtime.handle_message().

Pure stdlib: asyncio + hashlib + struct for the WebSocket handshake.
No websockets pip package needed.

Usage:
    python3 -m mahaclaw.gateway
    python3 -m mahaclaw.gateway --port 18789 --host 0.0.0.0
    python3 -m mahaclaw.gateway --web --standalone
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

logger = logging.getLogger("mahaclaw.gateway")

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18789
WS_MAGIC = b"258EAFA5-E914-47DA-95CA-5AB9964DA7F3"

# Web assets
WEB_DIR = Path(__file__).parent / "web"

# Runtime mode (set by CLI args)
_runtime_mode = "federation"


# ---------------------------------------------------------------------------
# Minimal RFC 6455 WebSocket (stdlib only, no pip)
# ---------------------------------------------------------------------------

def _ws_accept_key(client_key: bytes) -> str:
    """Compute Sec-WebSocket-Accept from client key."""
    digest = hashlib.sha1(client_key.strip() + WS_MAGIC).digest()
    return base64.b64encode(digest).decode()


def _parse_http_request(request: bytes) -> tuple[str, str, dict[str, str]]:
    """Parse HTTP request → (method, path, headers)."""
    text = request.decode("utf-8", errors="replace")
    lines = text.split("\r\n")
    parts = lines[0].split(" ") if lines else ["GET", "/", "HTTP/1.1"]
    method = parts[0] if len(parts) > 0 else "GET"
    path = parts[1] if len(parts) > 1 else "/"

    headers = {}
    for line in lines[1:]:
        if ":" in line:
            k, v = line.split(":", 1)
            headers[k.strip().lower()] = v.strip()

    return method, path, headers


async def _handle_http(
    method: str, path: str, headers: dict,
    writer: asyncio.StreamWriter,
) -> None:
    """Handle plain HTTP requests (not WebSocket)."""

    if path == "/" or path == "/index.html":
        # Serve webchat HTML
        html_path = WEB_DIR / "index.html"
        if html_path.exists():
            body = html_path.read_bytes()
            resp = (
                b"HTTP/1.1 200 OK\r\n"
                b"Content-Type: text/html; charset=utf-8\r\n"
                b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                b"Connection: close\r\n"
                b"\r\n"
            ) + body
        else:
            body = b"webchat not found"
            resp = (
                b"HTTP/1.1 404 Not Found\r\n"
                b"Content-Length: " + str(len(body)).encode() + b"\r\n"
                b"Connection: close\r\n\r\n"
            ) + body
    elif path == "/health":
        body = json.dumps({
            "status": "ok", "service": "mahaclaw-gateway",
            "ts": time.time(), "mode": _runtime_mode,
        }).encode()
        resp = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"Connection: close\r\n\r\n"
        ) + body
    elif path == "/status":
        from .runtime import get_status
        body = json.dumps(get_status(), indent=2).encode()
        resp = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"Connection: close\r\n\r\n"
        ) + body
    else:
        body = b"not found"
        resp = (
            b"HTTP/1.1 404 Not Found\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\n"
            b"Connection: close\r\n\r\n"
        ) + body

    writer.write(resp)
    await writer.drain()


async def _ws_handshake(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter,
) -> bool:
    """Perform WebSocket opening handshake or handle HTTP. Returns True for WS."""
    request = b""
    while not request.endswith(b"\r\n\r\n"):
        chunk = await asyncio.wait_for(reader.read(4096), timeout=5.0)
        if not chunk:
            return False
        request += chunk

    method, path, headers = _parse_http_request(request)

    client_key = headers.get("sec-websocket-key", "")
    if not client_key:
        # Plain HTTP request
        await _handle_http(method, path, headers, writer)
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
    """Read a single WebSocket frame. Returns payload or None on close."""
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
    frame.append(0x80 | opcode)

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
# Message handling via runtime
# ---------------------------------------------------------------------------

async def _process_ws_message(text: str) -> dict:
    """Process a WebSocket message through the runtime."""
    from .runtime import handle_message

    data = json.loads(text)
    user_text = data.get("text", data.get("message", ""))
    session_id = data.get("session_id", "anon")

    if not user_text:
        return {"text": "", "error": "empty message"}

    # Run the blocking runtime in a thread pool
    # wait_s=5 keeps WebSocket responsive; federation poll won't block too long
    loop = asyncio.get_running_loop()
    response_text = await loop.run_in_executor(
        None,
        lambda: handle_message(
            text=user_text,
            session_id=session_id,
            source="webchat",
            mode=_runtime_mode,
            wait_s=5.0,
        ),
    )

    return {
        "text": response_text,
        "session_id": session_id,
        "mode": _runtime_mode,
    }


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """Handle a single client connection (HTTP or WebSocket)."""
    addr = writer.get_extra_info("peername") or "unknown"

    try:
        is_ws = await _ws_handshake(reader, writer)
        if not is_ws:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            return

        logger.info("ws connected: %s", addr)

        while True:
            try:
                data = await asyncio.wait_for(_ws_read_frame(reader), timeout=300.0)
            except asyncio.TimeoutError:
                break

            if data is None:
                break

            text = data.decode("utf-8", errors="replace").strip()
            if not text:
                continue

            try:
                result = await _process_ws_message(text)
            except Exception as exc:
                logger.warning("message error: %s", exc)
                result = {"text": "", "error": str(exc)}

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
        logger.info("ws disconnected: %s", addr)


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

async def serve(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Start the Maha Claw Gateway."""
    server = await asyncio.start_server(handle_client, host, port)

    loop = asyncio.get_running_loop()
    stop = loop.create_future()

    def _shutdown(sig: int) -> None:
        if not stop.done():
            stop.set_result(sig)

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _shutdown, sig)

    logger.info("mahaclaw gateway on http://%s:%d", host, port)
    logger.info("  webchat:  http://%s:%d/", host, port)
    logger.info("  health:   http://%s:%d/health", host, port)
    logger.info("  status:   http://%s:%d/status", host, port)
    logger.info("  ws:       ws://%s:%d/ws", host, port)
    logger.info("  mode:     %s", _runtime_mode)

    try:
        await stop
    finally:
        server.close()
        await server.wait_closed()
        logger.info("mahaclaw gateway stopped")


def main() -> None:
    global _runtime_mode

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
        elif arg == "--standalone":
            _runtime_mode = "standalone"
        elif arg == "--steward-only":
            _runtime_mode = "steward-only"
        elif arg == "--web":
            host = "0.0.0.0"  # bind all interfaces for web access

    # MAHACLAW_MODE env override
    env_mode = os.environ.get("MAHACLAW_MODE", "")
    if env_mode:
        _runtime_mode = env_mode

    # PORT env override (for cloud platforms)
    env_port = os.environ.get("PORT", "")
    if env_port:
        port = int(env_port)

    asyncio.run(serve(host, port))


# ---------------------------------------------------------------------------
# Backward compat (used by tests)
# ---------------------------------------------------------------------------

handle_ws_client = handle_client


async def _process_message(text: str) -> dict:
    """Legacy pipeline-only path (used by existing tests)."""
    from .buddhi import VerdictAction, check_intent
    from .intercept import parse_intent
    from .tattva import classify
    from .rama import encode_rama
    from .lotus import resolve_route
    from .envelope import build_and_enqueue
    from .inbox import poll_response, extract_response_payload

    data = json.loads(text)

    if "intent" not in data and "message" in data:
        target = data.get("target", "agent-research")
        msg = data["message"]
        data = {"intent": msg, "target": target, "payload": {"message": msg}}

    raw = json.dumps(data)
    intent = parse_intent(raw)
    verdict = check_intent(intent)
    if verdict.action == VerdictAction.ABORT:
        return {"ok": False, "error": "blocked"}
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

    wait_s = data.get("wait", 2.0)
    if wait_s > 0:
        response = poll_response(correlation_id, timeout_s=min(wait_s, 30.0))
        if response is not None:
            result["response"] = extract_response_payload(response)
            result["responded"] = True
        else:
            result["responded"] = False

    return result


if __name__ == "__main__":
    main()
