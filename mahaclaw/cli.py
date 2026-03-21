"""Maha Claw CLI — stdin/pipe entry point for OpenClaw skills.

Usage from an OpenClaw SKILL.md:
    echo '{"intent":"inquiry","target":"agent-research"}' | python3 -m mahaclaw.cli

With response wait (blocks up to N seconds for federation reply):
    echo '...' | python3 -m mahaclaw.cli --wait 10

Usage from an OpenClaw hook:
    echo "$OPENCLAW_EVENT" | python3 -m mahaclaw.cli --from-hook
"""
from __future__ import annotations

import json
import sys

from .buddhi import VerdictAction, check_intent
from .intercept import parse_intent
from .tattva import classify
from .rama import encode_rama
from .lotus import resolve_route
from .envelope import build_and_enqueue
from .inbox import poll_response, extract_response_payload


def _parse_wait_arg() -> float:
    """Parse --wait <seconds> from argv.  Returns 0 if not present."""
    args = sys.argv[1:]
    for i, arg in enumerate(args):
        if arg == "--wait" and i + 1 < len(args):
            try:
                return float(args[i + 1])
            except ValueError:
                return 0.0
    return 0.0


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"ok": False, "error": "empty input"}))
        return 1

    wait_s = _parse_wait_arg()

    try:
        intent = parse_intent(raw)
        verdict = check_intent(intent)
        if verdict.action == VerdictAction.ABORT:
            raise ValueError(f"Buddhi ABORT: {verdict.reason}")
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

        # If --wait, poll inbox for federation response
        if wait_s > 0:
            response = poll_response(correlation_id, timeout_s=wait_s)
            if response is not None:
                result["response"] = extract_response_payload(response)
                result["responded"] = True
            else:
                result["responded"] = False

        print(json.dumps(result))
        return 0

    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
