"""Cetana — Autonomous Heartbeat Daemon.

Additional Element — Beyond Canonical 25
Category: LIFECYCLE (Autonomous Process)

Cetana runs the MURALI heartbeat cycle as an in-process daemon thread.
4 phases: MEASURE → UPDATE → REPORT → ADAPT → LISTEN → INTEGRATE.

Mirrors steward/cetana.py → 4-phase MURALI cycle with adaptive frequency.

ANAURALIA: All outputs are counts, booleans, and timestamps. No prose.

Pure stdlib. No pip deps.
"""
from __future__ import annotations

import enum
import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path


class MuraliPhase(str, enum.Enum):
    """MURALI cycle phases."""
    MEASURE = "measure"
    UPDATE = "update"
    REPORT = "report"
    ADAPT = "adapt"
    LISTEN = "listen"
    INTEGRATE = "integrate"


@dataclass
class HeartbeatState:
    """Current heartbeat state.

    ANAURALIA: Only counts, booleans, timestamps.
    """
    cycle_count: int = 0
    last_beat_at: float = 0.0
    interval_s: float = 300.0     # default 5 minutes
    phase: MuraliPhase = MuraliPhase.MEASURE
    running: bool = False
    errors: int = 0
    successful_beats: int = 0


# Adaptive frequency bounds
MIN_INTERVAL_S = 60.0      # 1 minute minimum
MAX_INTERVAL_S = 3600.0    # 1 hour maximum
DEFAULT_INTERVAL_S = 300.0  # 5 minutes default


def _build_heartbeat_intent() -> dict:
    """Build a heartbeat intent for the federation."""
    return {
        "intent": "heartbeat",
        "target": "agent-city",
        "priority": "tamas",
        "payload": {
            "status": "alive",
            "node": "mahaclaw",
            "timestamp": time.time(),
        },
    }


def _send_heartbeat() -> bool:
    """Send one heartbeat through the 5-gate pipeline.

    Returns True on success, False on failure.
    """
    try:
        from mahaclaw.intercept import parse_intent
        from mahaclaw.tattva import classify
        from mahaclaw.rama import encode
        from mahaclaw.lotus import resolve_route
        from mahaclaw.envelope import build_and_enqueue

        intent = _build_heartbeat_intent()
        parsed = parse_intent(intent)
        tattva = classify(parsed)
        rama = encode(parsed, tattva)
        route = resolve_route(parsed, rama)
        build_and_enqueue(parsed, rama, route)
        return True
    except Exception:
        return False


def beat_once(state: HeartbeatState) -> HeartbeatState:
    """Execute one MURALI cycle. Pure function over state.

    MEASURE: check system health
    UPDATE: prepare heartbeat
    REPORT: send heartbeat envelope
    ADAPT: adjust interval based on success/failure
    LISTEN: check inbox for peer updates (via Pada)
    INTEGRATE: apply discovered routes
    """
    state.phase = MuraliPhase.MEASURE
    state.cycle_count += 1

    # REPORT phase: send heartbeat
    state.phase = MuraliPhase.REPORT
    success = _send_heartbeat()

    if success:
        state.successful_beats += 1
        state.last_beat_at = time.time()
    else:
        state.errors += 1

    # ADAPT phase: adjust interval
    state.phase = MuraliPhase.ADAPT
    if success:
        # Successful → can relax interval slightly
        state.interval_s = min(state.interval_s * 1.1, MAX_INTERVAL_S)
    else:
        # Failed → beat more aggressively
        state.interval_s = max(state.interval_s * 0.5, MIN_INTERVAL_S)

    # LISTEN + INTEGRATE: peer discovery
    state.phase = MuraliPhase.LISTEN
    try:
        from mahaclaw.pada import discover_from_inbox
        discover_from_inbox()
    except Exception:
        pass  # peer discovery failure is non-fatal

    state.phase = MuraliPhase.INTEGRATE

    return state


class CetanaDaemon:
    """In-process heartbeat daemon thread.

    Runs beat_once() at adaptive intervals.
    Thread-safe start/stop.
    """

    def __init__(self, interval_s: float = DEFAULT_INTERVAL_S):
        self._state = HeartbeatState(interval_s=interval_s)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def state(self) -> HeartbeatState:
        return self._state

    @property
    def running(self) -> bool:
        return self._state.running

    def start(self) -> bool:
        """Start the heartbeat daemon. Returns False if already running."""
        if self._state.running:
            return False

        self._stop_event.clear()
        self._state.running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            name="cetana-heartbeat",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> bool:
        """Stop the heartbeat daemon. Returns False if not running."""
        if not self._state.running:
            return False

        self._stop_event.set()
        self._state.running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        return True

    def _run_loop(self) -> None:
        """Main daemon loop. Runs until stop_event is set."""
        while not self._stop_event.is_set():
            beat_once(self._state)
            # Wait for interval or stop signal
            self._stop_event.wait(timeout=self._state.interval_s)
        self._state.running = False
