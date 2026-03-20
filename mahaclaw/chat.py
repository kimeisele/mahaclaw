"""Maha Claw Standalone Chat — direct terminal interface to the federation.

No OpenClaw required.  Reads user input, runs the 5-gate pipeline, writes
to nadi_outbox.json, and optionally waits for a federation response via
nadi_inbox.json.

Usage:
    python3 -m mahaclaw.chat
    python3 -m mahaclaw.chat --target agent-research --wait 30
"""
from __future__ import annotations

import json
import readline  # noqa: F401 — enables line editing in input()
import sys
import time

from .intercept import parse_intent
from .tattva import classify
from .rama import encode_rama
from .lotus import resolve_route, buddy_bubble
from .envelope import build_and_enqueue
from .inbox import poll_response, extract_response_payload

DEFAULT_TARGET = "agent-research"
DEFAULT_WAIT_S = 10.0

BANNER = """\
┌──────────────────────────────────────────┐
│         MAHA CLAW — Federation Chat      │
│  Pure Python edge client · no OpenClaw   │
│  Type /help for commands · /quit to exit │
└──────────────────────────────────────────┘"""

HELP = """\
Commands:
  /target <name>   Switch target agent (current: {target})
  /wait <seconds>  Set response wait timeout (current: {wait}s)
  /routes          Show Lotus routing table (buddy_bubble)
  /status          Show current session config
  /nowait          Disable response waiting (fire-and-forget)
  /quit            Exit

Anything else is sent as an intent to the federation."""


def _parse_args() -> dict:
    """Parse CLI args for --target and --wait."""
    args = sys.argv[1:]
    cfg = {"target": DEFAULT_TARGET, "wait": DEFAULT_WAIT_S}
    i = 0
    while i < len(args):
        if args[i] == "--target" and i + 1 < len(args):
            cfg["target"] = args[i + 1]
            i += 2
        elif args[i] == "--wait" and i + 1 < len(args):
            try:
                cfg["wait"] = float(args[i + 1])
            except ValueError:
                pass
            i += 2
        elif args[i] == "--nowait":
            cfg["wait"] = 0.0
            i += 1
        else:
            i += 1
    return cfg


def _send(text: str, target: str, wait_s: float) -> None:
    """Run the 5-gate pipeline and optionally wait for response."""
    # Detect intent from text
    intent_type = "inquiry"
    lower = text.lower()
    if any(kw in lower for kw in ("build", "code", "compile", "debug", "test")):
        intent_type = "code_analysis"
    elif any(kw in lower for kw in ("govern", "vote", "policy", "proposal")):
        intent_type = "governance_proposal"
    elif any(kw in lower for kw in ("find", "discover", "search", "who")):
        intent_type = "discover_peers"
    elif any(kw in lower for kw in ("status", "ping", "health", "alive")):
        intent_type = "heartbeat"

    raw = json.dumps({
        "intent": intent_type,
        "target": target,
        "payload": {"message": text},
        "priority": "rajas",
    })

    t0 = time.monotonic()

    try:
        intent = parse_intent(raw)
        tattva = classify(intent)
        rama = encode_rama(intent, tattva)
        route = resolve_route(intent, rama)
        envelope_id, correlation_id = build_and_enqueue(intent, rama, route)
    except Exception as exc:
        print(f"  error: {exc}")
        return

    elapsed_ms = (time.monotonic() - t0) * 1000
    print(f"  -> {route['target_city_id']}  [{tattva.dominant}/{tattva.zone}]"
          f"  {envelope_id[:12]}...  ({elapsed_ms:.0f}ms)")

    if wait_s <= 0:
        return

    print(f"  waiting up to {wait_s:.0f}s for response...", end="", flush=True)
    response = poll_response(correlation_id, timeout_s=wait_s)

    if response is None:
        print(" timeout (no response yet)")
        print(f"  track with correlation_id: {correlation_id}")
    else:
        print(" received!")
        extracted = extract_response_payload(response)
        print(f"  <- {extracted['source']}  [{extracted['operation']}]")
        if extracted["data"]:
            for k, v in extracted["data"].items():
                val = str(v)
                if len(val) > 120:
                    val = val[:117] + "..."
                print(f"     {k}: {val}")


def main() -> int:
    cfg = _parse_args()
    target = cfg["target"]
    wait_s = cfg["wait"]

    print(BANNER)
    print(f"  target: {target}  |  wait: {wait_s}s")
    print()

    while True:
        try:
            line = input("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            return 0

        if not line:
            continue

        if line == "/quit" or line == "/exit":
            print("bye")
            return 0

        if line == "/help":
            print(HELP.format(target=target, wait=wait_s))
            continue

        if line.startswith("/target "):
            target = line.split(None, 1)[1].strip()
            print(f"  target -> {target}")
            continue

        if line.startswith("/wait "):
            try:
                wait_s = float(line.split(None, 1)[1])
                print(f"  wait -> {wait_s}s")
            except ValueError:
                print("  usage: /wait <seconds>")
            continue

        if line == "/nowait":
            wait_s = 0.0
            print("  wait -> disabled (fire-and-forget)")
            continue

        if line == "/routes":
            bubble = buddy_bubble()
            print(f"  {bubble['route_count']} routes:")
            for name, city_id in sorted(bubble["routes"].items()):
                print(f"    {name} -> {city_id}")
            continue

        if line == "/status":
            print(f"  target: {target}")
            print(f"  wait: {wait_s}s")
            bubble = buddy_bubble()
            print(f"  routes: {bubble['route_count']}")
            continue

        _send(line, target, wait_s)


if __name__ == "__main__":
    raise SystemExit(main())
