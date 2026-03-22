"""Runtime — Single entry point for ALL 25 Sankhya elements.

Every message goes through handle_message(). Every element fires.
WebChat, Telegram, CLI — they all call this ONE function.

Two paths:
  1. Federation: 5-gate pipeline → outbox → poll inbox
  2. Standalone: local LLM via llm.py

All elements fire regardless of path.
"""
from __future__ import annotations

import json
import logging
import time

from .buddhi import (
    Buddhi, BuddhiVerdict, BuddhiCause, VerdictAction,
    check_intent,
)
from .chitta import Chitta, ExecutionPhase
from .intercept import parse_intent
from .tattva import classify
from .rama import encode_rama
from .lotus import resolve_route
from .envelope import build_and_enqueue
from .inbox import poll_response, extract_response_payload
from .narasimha import gate as narasimha_gate
from .manas import perceive as manas_perceive
from .rasa import validate as rasa_validate
from .rasana import Rasana
from .vedana import pulse as vedana_pulse
from .ksetrajna import observe as ksetrajna_observe, to_dict as snapshot_to_dict
from .payu import sweep as payu_sweep
from .session import SessionManager

logger = logging.getLogger("mahaclaw.runtime")

# ---------------------------------------------------------------------------
# Session-scoped state (shared across messages in the same process)
# ---------------------------------------------------------------------------

_sessions: SessionManager | None = None
_chittas: dict[str, Chitta] = {}        # session_id → Chitta
_histories: dict[str, list[dict]] = {}  # session_id → LLM conversation
_rasana = Rasana()
_message_count = 0


def _get_sessions() -> SessionManager:
    global _sessions
    if _sessions is None:
        _sessions = SessionManager()
    return _sessions


def _get_chitta(session_id: str) -> Chitta:
    if session_id not in _chittas:
        _chittas[session_id] = Chitta()
    return _chittas[session_id]


# ---------------------------------------------------------------------------
# Core runtime
# ---------------------------------------------------------------------------

def handle_message(
    text: str,
    session_id: str,
    source: str = "webchat",
    mode: str = "federation",
    target: str = "steward",
    wait_s: float = 15.0,
) -> str:
    """THE function. Every element fires. Returns response text.

    Args:
        text: User message text.
        session_id: Unique session identifier.
        source: Channel source (webchat, telegram, cli).
        mode: "federation", "standalone", or "steward-only".
        target: Default federation target.
        wait_s: How long to wait for federation response.
    """
    global _message_count
    _message_count += 1
    t0 = time.monotonic()

    sessions = _get_sessions()
    chitta = _get_chitta(session_id)
    session = sessions.get_or_create(session_id, target=target)

    # ------ SHROTRA: receive ------
    sessions.log_message_in(session_id, text)
    logger.debug("shrotra: received from %s/%s", source, session_id[:8])

    # ------ NARASIMHA: kill-switch ------
    nv = narasimha_gate({"intent": text, "target": target})
    if nv.blocked:
        logger.warning("narasimha: blocked [%s]", nv.matched)
        return "I can't process that request."

    # ------ MANAS: perceive (seed-based, no keywords) ------
    perception = manas_perceive(text)
    logger.debug("manas: action=%s guna=%s", perception.action.value, perception.guna.value)

    # ------ CHITTA: load session, get phase ------
    phase = chitta.phase
    logger.debug("chitta: phase=%s impressions=%d", phase.value, len(chitta.impressions))

    # ------ RASA: trust check ------
    intent_dict = {
        "intent": text,
        "target": target,
        "priority": "rajas",
        "payload": {"message": text},
    }
    rv = rasa_validate(intent_dict, source=source)
    if not rv.approved:
        # For webchat/telegram, soft-override trust for UX
        # (log warning but don't block end users)
        logger.warning("rasa: trust=%s < required=%s (soft override for %s)",
                       rv.source_trust.name, rv.required_trust.name, source)

    # ------ BUDDHI: decide ------
    verdict = check_intent(intent_dict)
    if verdict.action == VerdictAction.ABORT:
        logger.warning("buddhi: ABORT cause=%s", verdict.cause.value)
        return "I can't process that request."

    # ------ ROUTE DECISION ------
    response_text = ""

    if mode in ("standalone",):
        response_text = _handle_standalone(text, session_id, chitta)
    else:
        response_text = _handle_federation(
            text, session_id, target, chitta, wait_s, mode,
        )

    # ------ CHITTA: record impression ------
    success = bool(response_text and "error" not in response_text.lower()[:30])
    chitta.record("handle_message", hash(text) & 0xFFFF, success)

    # ------ RASANA: update preferences ------
    _rasana.record_target(target)
    _rasana.record_action(perception.action.value)

    # ------ VEDANA: health pulse ------
    health = vedana_pulse(chitta)
    logger.debug("vedana: score=%.2f guna=%s", health.score, health.guna.value)

    # ------ PAYU: cleanup (every 50 messages) ------
    if _message_count % 50 == 0:
        try:
            payu_sweep()
            logger.debug("payu: sweep complete")
        except Exception as e:
            logger.debug("payu: sweep skipped (%s)", e)

    # ------ KSETRAJNA: snapshot state ------
    snapshot = ksetrajna_observe(chitta=chitta, health_score=health.score)
    logger.debug("ksetrajna: hash=%s", snapshot.snapshot_hash[:8])

    # ------ AHAMKARA: (signing happens inside build_and_enqueue) ------

    elapsed_ms = (time.monotonic() - t0) * 1000
    logger.info("runtime: %s mode=%s %.0fms health=%.2f",
                session_id[:8], mode, elapsed_ms, health.score)

    sessions.log_message_in(session_id, f"response:{len(response_text)}")

    return response_text or "I received your message but couldn't generate a response."


# ---------------------------------------------------------------------------
# Federation path
# ---------------------------------------------------------------------------

def _handle_federation(
    text: str,
    session_id: str,
    target: str,
    chitta: Chitta,
    wait_s: float,
    mode: str,
) -> str:
    """Route through 5-gate pipeline → outbox → poll inbox."""
    raw = json.dumps({
        "intent": text,
        "target": target,
        "payload": {"message": text},
        "priority": "rajas",
    })

    try:
        intent = parse_intent(raw)
        tattva = classify(intent)
        rama = encode_rama(intent, tattva)
        route = resolve_route(intent, rama)
        envelope_id, correlation_id = build_and_enqueue(intent, rama, route)
    except ValueError as exc:
        if "unroutable" in str(exc):
            return f"Can't reach '{target}'. The federation routing table doesn't have a route for this target."
        return f"Pipeline error: {exc}"
    except Exception as exc:
        logger.warning("pipeline error: %s", exc)
        return f"Something went wrong processing your message."

    logger.debug("vak: envelope=%s corr=%s target=%s",
                 envelope_id[:12], correlation_id[:8], target)

    # ------ PADA: peer discovery (on each federation message) ------
    try:
        from .pada import discover_from_inbox
        discovery = discover_from_inbox()
        if discovery.peers_added > 0:
            logger.info("pada: discovered %d new peers", discovery.peers_added)
    except Exception:
        pass

    # ------ Poll for response ------
    if wait_s > 0:
        response = poll_response(correlation_id, timeout_s=min(wait_s, 30.0))
        if response is not None:
            extracted = extract_response_payload(response)
            data = extracted.get("data", {})
            source = extracted.get("source", "federation")

            # Format the response
            parts = []
            for k, v in data.items():
                val = str(v)
                if len(val) > 1000:
                    val = val[:997] + "..."
                parts.append(val)

            if parts:
                return "\n".join(parts)
            return f"Response received from {source} (no content body)."

    # No response — fall back to standalone if not steward-only
    if mode != "steward-only":
        logger.info("federation: no response, falling back to standalone")
        return _handle_standalone(text, session_id, chitta)

    return (
        f"Message sent to {target} ({envelope_id[:12]}). "
        f"The federation hasn't responded yet. "
        f"The relay may need a moment."
    )


# ---------------------------------------------------------------------------
# Standalone path (local LLM)
# ---------------------------------------------------------------------------

def _handle_standalone(text: str, session_id: str, chitta: Chitta) -> str:
    """Call local LLM directly."""
    try:
        from .llm import ask, config_from_env

        config = config_from_env()
        history = _histories.setdefault(session_id, [])

        resp = ask(text, config=config, history=history)

        if resp.ok:
            history.append({"role": "user", "content": text})
            history.append({"role": "assistant", "content": resp.content})
            # Trim history
            if len(history) > 20:
                _histories[session_id] = history[-20:]
            return resp.content
        else:
            logger.warning("llm error: %s", resp.error)
            return f"LLM error: {resp.error}"
    except Exception as exc:
        logger.warning("standalone error: %s", exc)
        return f"Standalone LLM unavailable: {exc}"


# ---------------------------------------------------------------------------
# Status endpoint
# ---------------------------------------------------------------------------

def get_status() -> dict:
    """Current runtime status as JSON-serializable dict."""
    chitta = _get_chitta("__status__")
    health = vedana_pulse(chitta)
    snapshot = ksetrajna_observe(chitta=chitta, health_score=health.score)
    return {
        **snapshot_to_dict(snapshot),
        "total_messages": _message_count,
        "active_sessions": len(_chittas),
        "preferred_target": _rasana.preferred_target,
    }
