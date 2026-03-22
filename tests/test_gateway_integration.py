"""Gateway integration tests — HTTP + WebSocket via real asyncio server.

Tests the rewritten gateway: HTML serving, health/status endpoints,
and WebSocket message handling via runtime.handle_message().
"""
from __future__ import annotations

import asyncio
import json
import struct
import time
from pathlib import Path

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def _redirect_io(tmp_path, monkeypatch):
    """Redirect outbox/inbox/sessions to tmp_path."""
    import mahaclaw.envelope as env_mod
    import mahaclaw.inbox as inbox_mod
    import mahaclaw.session as sess_mod
    import mahaclaw.runtime as rt

    outbox = tmp_path / "nadi_outbox.json"
    outbox.write_text("[]\n")
    inbox = tmp_path / "nadi_inbox.json"
    inbox.write_text("[]\n")
    db = tmp_path / "sessions.db"

    monkeypatch.setattr(env_mod, "OUTBOX_PATH", outbox)
    monkeypatch.setattr(inbox_mod, "INBOX_PATH", inbox)
    monkeypatch.setattr(sess_mod, "DEFAULT_DB", db)

    # Reset runtime state
    rt._chittas.clear()
    rt._histories.clear()
    rt._message_count = 0
    rt._sessions = None

    yield tmp_path

    rt._chittas.clear()
    rt._histories.clear()
    rt._sessions = None


@pytest_asyncio.fixture
async def gateway_server(_redirect_io, monkeypatch):
    """Start the gateway on a random port. Yields (host, port)."""
    import mahaclaw.gateway as gw

    monkeypatch.setattr(gw, "_runtime_mode", "steward-only")

    server = await asyncio.start_server(gw.handle_client, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]

    yield ("127.0.0.1", port)

    server.close()
    await server.wait_closed()


# ---------------------------------------------------------------------------
# HTTP Tests
# ---------------------------------------------------------------------------

class TestHTTPEndpoints:

    @pytest.mark.asyncio
    async def test_get_root_returns_html(self, gateway_server):
        """GET / returns the webchat HTML."""
        host, port = gateway_server

        reader, writer = await asyncio.open_connection(host, port)
        writer.write(b"GET / HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()

        resp = await asyncio.wait_for(reader.read(8192), timeout=5.0)
        writer.close()
        await writer.wait_closed()

        assert b"200 OK" in resp
        assert b"text/html" in resp
        assert b"Maha Claw" in resp  # Page title

    @pytest.mark.asyncio
    async def test_get_health_returns_json(self, gateway_server):
        """GET /health returns {"status": "ok"}."""
        host, port = gateway_server

        reader, writer = await asyncio.open_connection(host, port)
        writer.write(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()

        resp = await asyncio.wait_for(reader.read(4096), timeout=5.0)
        writer.close()
        await writer.wait_closed()

        assert b"200 OK" in resp
        assert b"application/json" in resp
        # Extract body after headers
        body = resp.split(b"\r\n\r\n", 1)[1]
        data = json.loads(body)
        assert data["status"] == "ok"
        assert data["service"] == "mahaclaw-gateway"

    @pytest.mark.asyncio
    async def test_get_status_returns_ksetrajna(self, gateway_server):
        """GET /status returns a valid KsetraJna snapshot."""
        host, port = gateway_server

        reader, writer = await asyncio.open_connection(host, port)
        writer.write(b"GET /status HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()

        resp = await asyncio.wait_for(reader.read(4096), timeout=5.0)
        writer.close()
        await writer.wait_closed()

        assert b"200 OK" in resp
        body = resp.split(b"\r\n\r\n", 1)[1]
        data = json.loads(body)
        assert data["kind"] == "bubble_snapshot"
        assert "snapshot_hash" in data
        assert "total_messages" in data

    @pytest.mark.asyncio
    async def test_get_404(self, gateway_server):
        """GET /nonexistent returns 404."""
        host, port = gateway_server

        reader, writer = await asyncio.open_connection(host, port)
        writer.write(b"GET /nonexistent HTTP/1.1\r\nHost: localhost\r\n\r\n")
        await writer.drain()

        resp = await asyncio.wait_for(reader.read(4096), timeout=5.0)
        writer.close()
        await writer.wait_closed()

        assert b"404" in resp


# ---------------------------------------------------------------------------
# WebSocket Tests
# ---------------------------------------------------------------------------

import base64
import hashlib
import os

WS_MAGIC = b"258EAFA5-E914-47DA-95CA-5AB9964DA7F3"


async def _ws_connect(host, port):
    """Perform WebSocket handshake. Returns (reader, writer)."""
    reader, writer = await asyncio.open_connection(host, port)

    # Generate key
    key = base64.b64encode(os.urandom(16)).decode()

    # Send upgrade request
    request = (
        f"GET /ws HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"\r\n"
    )
    writer.write(request.encode())
    await writer.drain()

    # Read response
    resp = b""
    while not resp.endswith(b"\r\n\r\n"):
        chunk = await asyncio.wait_for(reader.read(4096), timeout=5.0)
        if not chunk:
            raise ConnectionError("no response")
        resp += chunk

    assert b"101" in resp, f"Expected 101 Switching Protocols, got: {resp[:100]}"

    return reader, writer


def _ws_send_frame(writer, payload: bytes):
    """Send a masked WebSocket text frame."""
    frame = bytearray()
    frame.append(0x81)  # FIN + TEXT

    length = len(payload)
    if length < 126:
        frame.append(0x80 | length)  # masked
    elif length < 65536:
        frame.append(0x80 | 126)
        frame.extend(struct.pack("!H", length))
    else:
        frame.append(0x80 | 127)
        frame.extend(struct.pack("!Q", length))

    # Mask key
    mask = os.urandom(4)
    frame.extend(mask)

    # Masked payload
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    frame.extend(masked)

    writer.write(bytes(frame))


async def _ws_read_frame(reader, timeout=15.0) -> bytes:
    """Read a WebSocket frame. Returns payload."""
    header = await asyncio.wait_for(reader.readexactly(2), timeout=timeout)
    length = header[1] & 0x7F

    if length == 126:
        length = struct.unpack("!H", await reader.readexactly(2))[0]
    elif length == 127:
        length = struct.unpack("!Q", await reader.readexactly(8))[0]

    data = await asyncio.wait_for(reader.readexactly(length), timeout=timeout)
    return data


class TestWebSocket:

    @pytest.mark.asyncio
    async def test_ws_handshake(self, gateway_server):
        """WebSocket handshake succeeds."""
        host, port = gateway_server
        reader, writer = await _ws_connect(host, port)
        writer.close()
        await writer.wait_closed()

    @pytest.mark.asyncio
    async def test_ws_send_receive(self, gateway_server):
        """Send a message, receive a response with text and session_id."""
        host, port = gateway_server
        reader, writer = await _ws_connect(host, port)

        msg = json.dumps({"text": "hello world", "session_id": "ws-test-001"})
        _ws_send_frame(writer, msg.encode())
        await writer.drain()

        data = await _ws_read_frame(reader)
        resp = json.loads(data)

        assert "text" in resp
        assert isinstance(resp["text"], str)
        assert len(resp["text"]) > 0
        assert resp["session_id"] == "ws-test-001"

        writer.close()
        await writer.wait_closed()

    @pytest.mark.asyncio
    async def test_ws_invalid_json(self, gateway_server):
        """Invalid JSON on WebSocket returns an error, doesn't crash."""
        host, port = gateway_server
        reader, writer = await _ws_connect(host, port)

        _ws_send_frame(writer, b"not json at all{{{")
        await writer.drain()

        data = await _ws_read_frame(reader)
        resp = json.loads(data)

        assert "error" in resp or "text" in resp
        # Server is still alive — send another message
        msg = json.dumps({"text": "still alive?", "session_id": "err-test"})
        _ws_send_frame(writer, msg.encode())
        await writer.drain()

        data2 = await _ws_read_frame(reader)
        resp2 = json.loads(data2)
        assert "text" in resp2

        writer.close()
        await writer.wait_closed()

    @pytest.mark.asyncio
    async def test_ws_missing_session_id(self, gateway_server):
        """Missing session_id doesn't crash — uses default."""
        host, port = gateway_server
        reader, writer = await _ws_connect(host, port)

        msg = json.dumps({"text": "no session here"})
        _ws_send_frame(writer, msg.encode())
        await writer.drain()

        data = await _ws_read_frame(reader)
        resp = json.loads(data)

        assert "text" in resp
        assert len(resp["text"]) > 0

        writer.close()
        await writer.wait_closed()

    @pytest.mark.asyncio
    async def test_ws_empty_text(self, gateway_server):
        """Empty text returns appropriate response."""
        host, port = gateway_server
        reader, writer = await _ws_connect(host, port)

        msg = json.dumps({"text": "", "session_id": "empty-test"})
        _ws_send_frame(writer, msg.encode())
        await writer.drain()

        data = await _ws_read_frame(reader)
        resp = json.loads(data)

        # Should get some response (error or empty message response)
        assert "text" in resp or "error" in resp

        writer.close()
        await writer.wait_closed()

    @pytest.mark.asyncio
    async def test_ws_multiple_messages(self, gateway_server):
        """Multiple messages on same connection work."""
        host, port = gateway_server
        reader, writer = await _ws_connect(host, port)

        for i in range(3):
            msg = json.dumps({"text": f"message {i}", "session_id": "multi-test"})
            _ws_send_frame(writer, msg.encode())
            await writer.drain()

            data = await _ws_read_frame(reader)
            resp = json.loads(data)
            assert "text" in resp
            assert len(resp["text"]) > 0

        writer.close()
        await writer.wait_closed()
