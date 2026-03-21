"""Chitta — Consciousness / Impression Storage.

PrakritiElement #4 — Protocol Layer: awareness
Category: ANTAHKARANA (Internal Instrument)

In Sankhya, Chitta stores impressions (samskaras) from past actions.
It answers: "WHAT has happened?" — the accumulated experience.

Mirrors steward/antahkarana/chitta.py exactly:
  - Impression dataclass: {name, params_hash, success, error, path}
  - ExecutionPhase: ORIENT → EXECUTE → VERIFY → COMPLETE
  - Phase derived deterministically from impressions
  - Cross-turn awareness via prior_reads
  - to_summary() / load_summary() for persistence
  - Thread-safe with Lock

Also includes Gandha pattern detection (steward/antahkarana/gandha.py):
  - Stateless pure functions over impression lists
  - consecutive_errors, identical_calls, blind_writes, tool_streaks, error_ratio

Pure stdlib. No pip deps.
"""
from __future__ import annotations

import enum
import threading
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# ExecutionPhase — mirrors steward/antahkarana/chitta.py
# ---------------------------------------------------------------------------

class ExecutionPhase(str, enum.Enum):
    """Execution phases — derived from Chitta impressions."""
    ORIENT = "ORIENT"
    EXECUTE = "EXECUTE"
    VERIFY = "VERIFY"
    COMPLETE = "COMPLETE"


# ---------------------------------------------------------------------------
# Impression — mirrors steward/antahkarana/chitta.py
# ---------------------------------------------------------------------------

_READ_NAMES = frozenset({"read_file", "glob", "grep", "list_dir"})
_WRITE_NAMES = frozenset({"write_file"})


@dataclass
class Impression:
    """A recorded tool call impression (samskara).

    Mirrors steward's Impression exactly.
    """
    name: str
    params_hash: int
    success: bool
    error: str = ""
    path: str = ""


# ---------------------------------------------------------------------------
# Chitta — mirrors steward/antahkarana/chitta.py
# ---------------------------------------------------------------------------

class Chitta:
    """Impression storage — accumulated experience.

    Stores tool execution impressions for pattern analysis.
    Phase derivation: ORIENT → EXECUTE → VERIFY → COMPLETE.
    Regression: errors pull back to ORIENT.
    Cross-turn awareness: prior_reads tracks files read in previous turns.
    """

    def __init__(self) -> None:
        self._impressions: list[Impression] = []
        self._round: int = 0
        self._prior_reads: set[str] = set()
        self._lock = threading.Lock()

    def record(
        self,
        name: str,
        params_hash: int,
        success: bool,
        error: str = "",
        path: str = "",
    ) -> None:
        """Record a tool execution impression."""
        imp = Impression(name=name, params_hash=params_hash, success=success,
                         error=error, path=path)
        with self._lock:
            self._impressions.append(imp)

    def advance_round(self) -> int:
        """Advance to next round, return new round number."""
        with self._lock:
            self._round += 1
            return self._round

    @property
    def impressions(self) -> list[Impression]:
        """All recorded impressions (snapshot copy for thread safety)."""
        with self._lock:
            return list(self._impressions)

    @property
    def round(self) -> int:
        return self._round

    def recent(self, n: int) -> list[Impression]:
        """Get the last n impressions."""
        with self._lock:
            if n <= len(self._impressions):
                return list(self._impressions[-n:])
            return list(self._impressions)

    def clear(self) -> None:
        """Clear all impressions and reset round counter."""
        with self._lock:
            self._impressions.clear()
            self._round = 0
            self._prior_reads.clear()

    def end_turn(self) -> None:
        """End current turn — merge reads into prior, clear impressions.

        Retains cross-turn file awareness while clearing per-turn history.
        Round counter NOT reset — tracks cumulative rounds across turns.
        """
        with self._lock:
            for imp in self._impressions:
                if imp.name in _READ_NAMES and imp.success and imp.path:
                    self._prior_reads.add(imp.path)
            self._impressions.clear()

    @property
    def phase(self) -> ExecutionPhase:
        """Derive current execution phase from accumulated impressions.

        Deterministic — same impressions always produce same phase.
        Mirrors steward/antahkarana/chitta.py exactly.
        """
        with self._lock:
            impressions = list(self._impressions)

        if not impressions:
            return ExecutionPhase.ORIENT

        total_writes = sum(1 for i in impressions if i.name in _WRITE_NAMES and i.success)

        recent = impressions[-3:] if len(impressions) >= 3 else impressions
        recent_errors = sum(1 for i in recent if not i.success)
        recent_writes = sum(1 for i in recent if i.name in _WRITE_NAMES and i.success)
        recent_bash_ok = sum(1 for i in recent if i.name == "bash" and i.success)

        # Error regression: 2+ recent errors → back to reading
        if recent_errors >= 2:
            return ExecutionPhase.ORIENT

        # Wrote files + recent successful bash → done
        if total_writes > 0 and recent_bash_ok >= 1:
            return ExecutionPhase.COMPLETE

        # Wrote files, no recent writes → time to verify
        if total_writes > 0 and recent_writes == 0:
            return ExecutionPhase.VERIFY

        # Actively writing
        if recent_writes > 0:
            return ExecutionPhase.EXECUTE

        # Read enough → ready to act
        total_reads = sum(1 for i in impressions if i.name in _READ_NAMES)
        if total_reads >= 2:
            return ExecutionPhase.EXECUTE

        return ExecutionPhase.ORIENT

    @property
    def prior_reads(self) -> frozenset[str]:
        """Files read in previous turns (cross-turn awareness)."""
        with self._lock:
            return frozenset(self._prior_reads)

    def was_file_read(self, path: str) -> bool:
        """Check if a file was read in current OR prior turns."""
        with self._lock:
            if path in self._prior_reads:
                return True
            return any(i.name in _READ_NAMES and i.success and i.path == path
                       for i in self._impressions)

    @property
    def files_read(self) -> list[str]:
        """Unique file paths read (current turn only)."""
        with self._lock:
            seen: set[str] = set()
            result: list[str] = []
            for i in self._impressions:
                if i.name in _READ_NAMES and i.success and i.path and i.path not in seen:
                    seen.add(i.path)
                    result.append(i.path)
            return result

    @property
    def files_written(self) -> list[str]:
        """Unique file paths written."""
        with self._lock:
            return self._files_written_unlocked()

    def _files_written_unlocked(self) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for i in self._impressions:
            if i.name in _WRITE_NAMES and i.success and i.path and i.path not in seen:
                seen.add(i.path)
                result.append(i.path)
        return result

    def to_summary(self) -> dict[str, object]:
        """Serialize cross-turn state for persistence.

        Mirrors steward's Chitta.to_summary() exactly.
        """
        with self._lock:
            all_reads = set(self._prior_reads)
            for imp in self._impressions:
                if imp.name in _READ_NAMES and imp.success and imp.path:
                    all_reads.add(imp.path)
            written = self._files_written_unlocked()
        return {
            "prior_reads": sorted(all_reads),
            "files_written": written,
            "last_phase": self.phase.value,
        }

    def load_summary(self, summary: dict[str, object]) -> None:
        """Restore cross-turn state from a persisted summary."""
        prior = summary.get("prior_reads", [])
        with self._lock:
            if isinstance(prior, list):
                self._prior_reads = set(prior)

    @property
    def stats(self) -> dict[str, object]:
        """Diagnostic stats from accumulated impressions."""
        with self._lock:
            total = len(self._impressions)
            errors = sum(1 for r in self._impressions if not r.success)
            tool_counts: dict[str, int] = {}
            for r in self._impressions:
                tool_counts[r.name] = tool_counts.get(r.name, 0) + 1
            n_prior = len(self._prior_reads)
        return {
            "rounds": self._round,
            "total_calls": total,
            "errors": errors,
            "error_ratio": errors / total if total else 0.0,
            "tool_distribution": tool_counts,
            "phase": self.phase.value,
            "prior_reads": n_prior,
        }


# ---------------------------------------------------------------------------
# Gandha — Stateless pattern detection (steward/antahkarana/gandha.py)
# ---------------------------------------------------------------------------

# Thresholds (from steward/antahkarana/gandha.py)
MAX_IDENTICAL_CALLS = 3
MAX_CONSECUTIVE_ERRORS = 5
MAX_SAME_TOOL_STREAK = 8
ERROR_RATIO_THRESHOLD = 0.7


class VerdictAction(str, enum.Enum):
    """Detection severity. Mirrors steward/antahkarana/gandha.py."""
    CONTINUE = "continue"
    REFLECT = "reflect"
    REDIRECT = "redirect"
    ABORT = "abort"
    INFO = "info"


@dataclass(frozen=True)
class Detection:
    """A detected pattern from Gandha analysis."""
    severity: VerdictAction
    pattern: str
    reason: str = ""
    suggestion: str = ""


def detect_patterns(
    impressions: list[Impression],
    prior_reads: frozenset[str] = frozenset(),
) -> Detection | None:
    """Run all Gandha detection checks. Returns first detected pattern or None.

    Mirrors steward/antahkarana/gandha.py detect_patterns().
    """
    for check in [
        _check_consecutive_errors,
        _check_identical_calls,
        _check_tool_streak,
        _check_error_ratio,
    ]:
        result = check(impressions)
        if result is not None:
            return result

    result = _check_write_without_read(impressions, prior_reads)
    if result is not None:
        return result

    return None


def _check_consecutive_errors(impressions: list[Impression]) -> Detection | None:
    if len(impressions) < MAX_CONSECUTIVE_ERRORS:
        return None
    recent = impressions[-MAX_CONSECUTIVE_ERRORS:]
    if all(not r.success for r in recent):
        return Detection(
            severity=VerdictAction.ABORT,
            pattern="consecutive_errors",
            reason=f"{MAX_CONSECUTIVE_ERRORS} consecutive errors",
        )
    return None


def _check_identical_calls(impressions: list[Impression]) -> Detection | None:
    if len(impressions) < MAX_IDENTICAL_CALLS:
        return None
    recent = impressions[-MAX_IDENTICAL_CALLS:]
    if not all(r.name == recent[0].name and r.params_hash == recent[0].params_hash for r in recent):
        return None
    # Recovery pattern: last succeeded after earlier failures → not stuck
    if recent[-1].success and any(not r.success for r in recent[:-1]):
        return None
    return Detection(
        severity=VerdictAction.REFLECT,
        pattern="identical_calls",
        reason=f"Identical call repeated {MAX_IDENTICAL_CALLS}x: {recent[0].name}",
    )


def _check_tool_streak(impressions: list[Impression]) -> Detection | None:
    if len(impressions) < MAX_SAME_TOOL_STREAK:
        return None
    recent = impressions[-MAX_SAME_TOOL_STREAK:]
    if all(r.name == recent[0].name for r in recent):
        if recent[0].name == "read_file":
            return None  # read_file streaks are legitimate
        return Detection(
            severity=VerdictAction.REFLECT,
            pattern="tool_streak",
            reason=f"Same tool '{recent[0].name}' used {MAX_SAME_TOOL_STREAK}x consecutively",
        )
    return None


def _check_error_ratio(impressions: list[Impression]) -> Detection | None:
    if len(impressions) < 6:
        return None
    total = len(impressions)
    errors = sum(1 for r in impressions if not r.success)
    ratio = errors / total
    if ratio >= ERROR_RATIO_THRESHOLD:
        return Detection(
            severity=VerdictAction.REFLECT,
            pattern="error_ratio",
            reason=f"Error ratio {ratio:.0%} exceeds threshold ({ERROR_RATIO_THRESHOLD:.0%})",
        )
    return None


def _check_write_without_read(
    impressions: list[Impression],
    prior_reads: frozenset[str] = frozenset(),
) -> Detection | None:
    """Detect blind writes — writing a file never read."""
    if not impressions:
        return None
    last = impressions[-1]
    if last.name not in _WRITE_NAMES or not last.success or not last.path:
        return None
    if last.path in prior_reads:
        return None
    for imp in impressions[:-1]:
        if imp.name in _READ_NAMES and imp.success and imp.path == last.path:
            return None
    return Detection(
        severity=VerdictAction.REDIRECT,
        pattern="write_without_read",
        reason=f"Blind write to '{last.path}' — file was never read first",
    )
