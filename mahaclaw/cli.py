"""Maha Claw CLI — stdin/pipe entry point for OpenClaw skills.

Usage from an OpenClaw SKILL.md:
    echo '{"intent":"inquiry","target":"agent-research","payload":{"q":"test"}}' | python3 -m mahaclaw.cli

Usage from an OpenClaw hook:
    echo "$OPENCLAW_EVENT" | python3 -m mahaclaw.cli --from-hook
"""
from __future__ import annotations

import json
import sys

from .intercept import parse_intent
from .tattva import classify
from .rama import encode_rama
from .lotus import resolve_route
from .envelope import build_and_enqueue


def main() -> int:
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"ok": False, "error": "empty input"}))
        return 1

    try:
        intent = parse_intent(raw)
        tattva = classify(intent)
        rama = encode_rama(intent, tattva)
        route = resolve_route(intent, rama)
        envelope_id = build_and_enqueue(intent, rama, route)

        print(json.dumps({
            "ok": True,
            "envelope_id": envelope_id,
            "target": route["target_city_id"],
            "element": tattva.dominant,
            "zone": tattva.zone,
            "guardian": rama.guardian,
        }))
        return 0

    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
