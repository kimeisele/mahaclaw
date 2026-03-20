"""Maha Claw Daemon — asyncio Unix socket server.

Listens for OpenClaw intents on a Unix domain socket, runs them through the
Five Tattva Gate pipeline (PARSE → VALIDATE → EXECUTE → RESULT → SYNC),
and writes DeliveryEnvelopes to nadi_outbox.json for relay pickup.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

from .intercept import parse_intent
from .tattva import classify
from .rama import encode_rama
from .lotus import resolve_route
from .envelope import build_and_enqueue

logger = logging.getLogger("mahaclaw.daemon")

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOCKET = REPO_ROOT / "mahaclaw.sock"
PID_FILE = REPO_ROOT / "mahaclaw.pid"


async def handle_client(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """Handle a single client connection through the 5-gate pipeline."""
    addr = writer.get_extra_info("peername") or "unix"
    try:
        raw = await asyncio.wait_for(reader.read(65536), timeout=10.0)
        if not raw:
            return
        text = raw.decode("utf-8", errors="replace").strip()

        # Gate 1: PARSE
        intent = parse_intent(text)

        # Gate 2: VALIDATE (Tattva classification)
        tattva_result = classify(intent)

        # Gate 3: EXECUTE (RAMA encoding)
        rama_signal = encode_rama(intent, tattva_result)

        # Gate 4: RESULT (Lotus route resolution)
        route = resolve_route(intent, rama_signal)

        # Gate 5: SYNC (build envelope, append to outbox)
        envelope_id, correlation_id = build_and_enqueue(intent, rama_signal, route)

        response = {"ok": True, "envelope_id": envelope_id, "correlation_id": correlation_id}
        logger.info("relayed %s → %s (%s)", intent["intent"], route["target_city_id"], envelope_id[:8])

    except Exception as exc:
        response = {"ok": False, "error": str(exc)}
        logger.warning("rejected: %s", exc)

    writer.write(json.dumps(response).encode() + b"\n")
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def serve(socket_path: str | Path | None = None) -> None:
    """Start the Maha Claw daemon on a Unix domain socket."""
    sock = Path(socket_path or DEFAULT_SOCKET)

    # Clean stale socket
    if sock.exists():
        sock.unlink()

    server = await asyncio.start_unix_server(handle_client, path=str(sock))
    sock.chmod(0o660)

    # PID file
    PID_FILE.write_text(str(os.getpid()))

    loop = asyncio.get_running_loop()
    stop = loop.create_future()

    def _shutdown(sig: int) -> None:
        if not stop.done():
            stop.set_result(sig)

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _shutdown, sig)

    logger.info("mahaclaw listening on %s (pid %d)", sock, os.getpid())

    try:
        await stop
    finally:
        server.close()
        await server.wait_closed()
        sock.unlink(missing_ok=True)
        PID_FILE.unlink(missing_ok=True)
        logger.info("mahaclaw stopped")


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
    path = sys.argv[1] if len(sys.argv) > 1 else None
    asyncio.run(serve(path))


if __name__ == "__main__":
    main()
