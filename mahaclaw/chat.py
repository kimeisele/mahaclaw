"""Maha Claw Standalone Chat — direct terminal interface to the federation.

No OpenClaw required.  Two modes:
  1. federation (default): 5-gate pipeline → NADI → wait for Steward response
  2. standalone (--standalone): Direct LLM call via any OpenAI-compat endpoint

Usage:
    python3 -m mahaclaw.chat
    python3 -m mahaclaw.chat --target agent-research --wait 30
    python3 -m mahaclaw.chat --standalone
    python3 -m mahaclaw.chat --standalone --model llama3.2
    MAHACLAW_LLM_URL=https://openrouter.ai/api/v1 MAHACLAW_LLM_KEY=sk-... python3 -m mahaclaw.chat --standalone
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

BANNER_FED = """\
┌──────────────────────────────────────────┐
│         MAHA CLAW — Federation Chat      │
│  Pure Python edge client · no OpenClaw   │
│  Type /help for commands · /quit to exit │
└──────────────────────────────────────────┘"""

BANNER_STANDALONE = """\
┌──────────────────────────────────────────┐
│       MAHA CLAW — Standalone Chat        │
│  Direct LLM · no federation needed       │
│  Type /help for commands · /quit to exit │
└──────────────────────────────────────────┘"""

HELP_FED = """\
Commands:
  /target <name>   Switch target agent (current: {target})
  /wait <seconds>  Set response wait timeout (current: {wait}s)
  /routes          Show Lotus routing table (buddy_bubble)
  /status          Show current session config
  /nowait          Disable response waiting (fire-and-forget)
  /standalone      Switch to standalone LLM mode
  /quit            Exit

Anything else is sent as an intent to the federation."""

HELP_STANDALONE = """\
Commands:
  /model <name>    Switch model (current: {model})
  /status          Show LLM config
  /clear           Clear conversation history
  /federation      Switch to federation mode
  /quit            Exit

Anything else is sent directly to the LLM."""


def _parse_args() -> dict:
    """Parse CLI args."""
    args = sys.argv[1:]
    cfg = {"target": DEFAULT_TARGET, "wait": DEFAULT_WAIT_S, "standalone": False, "model": None}
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
        elif args[i] == "--standalone":
            cfg["standalone"] = True
            i += 1
        elif args[i] == "--model" and i + 1 < len(args):
            cfg["model"] = args[i + 1]
            cfg["standalone"] = True  # --model implies standalone
            i += 2
        else:
            i += 1
    return cfg


def _send(text: str, target: str, wait_s: float) -> None:
    """Run the 5-gate pipeline and optionally wait for response."""
    # Pass raw text as intent — Manas routes by seed, not keywords
    raw = json.dumps({
        "intent": text,
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


def _send_standalone(text: str, config, history: list[dict]) -> None:
    """Send a message directly to the LLM and print the response."""
    from .llm import ask

    history.append({"role": "user", "content": text})
    resp = ask(text, config=config, history=history[:-1])  # history excludes current

    if resp.ok:
        print(f"  [{resp.model}] ({resp.duration_ms:.0f}ms)")
        print(resp.content)
        history.append({"role": "assistant", "content": resp.content})
    else:
        print(f"  error: {resp.error}")
        history.pop()  # remove failed user message


def main() -> int:
    cfg = _parse_args()
    target = cfg["target"]
    wait_s = cfg["wait"]
    standalone = cfg["standalone"]

    if standalone:
        from .llm import config_from_env, LLMConfig, is_available

        env_config = config_from_env()
        if cfg["model"]:
            env_config = LLMConfig(
                base_url=env_config.base_url, model=cfg["model"],
                api_key=env_config.api_key, timeout_s=env_config.timeout_s,
                system_prompt=env_config.system_prompt,
                temperature=env_config.temperature, max_tokens=env_config.max_tokens,
            )
        llm_config = env_config
        history: list[dict] = []

        print(BANNER_STANDALONE)
        avail, info = is_available(llm_config)
        if avail:
            print(f"  model: {llm_config.model}  |  endpoint: {llm_config.base_url}")
            print(f"  {info}")
        else:
            print(f"  model: {llm_config.model}  |  endpoint: {llm_config.base_url}")
            print(f"  warning: endpoint check failed ({info})")
        print()
    else:
        llm_config = None
        history = []
        print(BANNER_FED)
        print(f"  target: {target}  |  wait: {wait_s}s")
        print()

    while True:
        try:
            prompt = "you> " if not standalone else "you> "
            line = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye")
            return 0

        if not line:
            continue

        if line == "/quit" or line == "/exit":
            print("bye")
            return 0

        # --- Mode switch commands ---
        if line == "/standalone" and not standalone:
            from .llm import config_from_env, is_available
            standalone = True
            llm_config = config_from_env()
            history = []
            avail, info = is_available(llm_config)
            print(f"  switched to standalone mode")
            print(f"  model: {llm_config.model}  |  {info if avail else 'endpoint unreachable'}")
            continue

        if line == "/federation" and standalone:
            standalone = False
            print(f"  switched to federation mode")
            print(f"  target: {target}  |  wait: {wait_s}s")
            continue

        # --- Standalone commands ---
        if standalone:
            if line == "/help":
                print(HELP_STANDALONE.format(model=llm_config.model))
                continue

            if line.startswith("/model "):
                from .llm import LLMConfig
                new_model = line.split(None, 1)[1].strip()
                llm_config = LLMConfig(
                    base_url=llm_config.base_url, model=new_model,
                    api_key=llm_config.api_key, timeout_s=llm_config.timeout_s,
                    system_prompt=llm_config.system_prompt,
                    temperature=llm_config.temperature, max_tokens=llm_config.max_tokens,
                )
                print(f"  model -> {new_model}")
                continue

            if line == "/clear":
                history.clear()
                print("  conversation cleared")
                continue

            if line == "/status":
                print(f"  mode: standalone")
                print(f"  model: {llm_config.model}")
                print(f"  endpoint: {llm_config.base_url}")
                print(f"  history: {len(history)} messages")
                continue

            _send_standalone(line, llm_config, history)
            continue

        # --- Federation commands ---
        if line == "/help":
            print(HELP_FED.format(target=target, wait=wait_s))
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
            print(f"  mode: federation")
            print(f"  target: {target}")
            print(f"  wait: {wait_s}s")
            bubble = buddy_bubble()
            print(f"  routes: {bubble['route_count']}")
            continue

        _send(line, target, wait_s)


if __name__ == "__main__":
    raise SystemExit(main())
