"""Rasana — Preference Learning / Taste Memory.

Jnanendriya #5 — Knowledge Sense: taste
Category: JNANENDRIYA (Knowledge Organ)

Rasana tracks user preferences from session patterns.
Mirrors steward's TestingSense + DharmaSense — quality sensing.

What it learns (without language):
  - Preferred targets (which agents the user routes to most)
  - Preferred actions (what ActionTypes dominate)
  - Session patterns (time-of-day, message frequency)
  - Success patterns (which tool/action combos work)

ANAURALIA: All data is counts, ratios, and enums. No prose.

Pure stdlib. No pip deps.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field


class PreferenceSignal(str, enum.Enum):
    """What dimension the preference measures."""
    TARGET = "target"         # which agent the user prefers
    ACTION = "action"         # which action type dominates
    TOOL = "tool"             # which tools succeed most
    FREQUENCY = "frequency"   # how often the user sends


@dataclass
class Rasana:
    """Preference tracker — learns from session patterns.

    ANAURALIA: Stores only counts and ratios.
    """
    target_counts: dict[str, int] = field(default_factory=dict)
    action_counts: dict[str, int] = field(default_factory=dict)
    tool_success: dict[str, int] = field(default_factory=dict)
    tool_total: dict[str, int] = field(default_factory=dict)
    total_messages: int = 0

    def record_target(self, target: str) -> None:
        """Record a target selection."""
        self.target_counts[target] = self.target_counts.get(target, 0) + 1
        self.total_messages += 1

    def record_action(self, action: str) -> None:
        """Record an action type (enum value)."""
        self.action_counts[action] = self.action_counts.get(action, 0) + 1

    def record_tool(self, tool_name: str, success: bool) -> None:
        """Record a tool execution result."""
        self.tool_total[tool_name] = self.tool_total.get(tool_name, 0) + 1
        if success:
            self.tool_success[tool_name] = self.tool_success.get(tool_name, 0) + 1

    @property
    def preferred_target(self) -> str:
        """Most frequently used target."""
        if not self.target_counts:
            return ""
        return max(self.target_counts, key=self.target_counts.get)

    @property
    def preferred_action(self) -> str:
        """Most frequently used action type."""
        if not self.action_counts:
            return ""
        return max(self.action_counts, key=self.action_counts.get)

    def tool_success_rate(self, tool_name: str) -> float:
        """Success rate for a specific tool (0.0–1.0)."""
        total = self.tool_total.get(tool_name, 0)
        if total == 0:
            return 0.5  # neutral
        return self.tool_success.get(tool_name, 0) / total

    @property
    def top_tools(self) -> list[tuple[str, float]]:
        """Tools ranked by success rate, descending."""
        tools = []
        for name in self.tool_total:
            tools.append((name, self.tool_success_rate(name)))
        tools.sort(key=lambda t: t[1], reverse=True)
        return tools

    def to_summary(self) -> dict[str, object]:
        """Serialize for persistence."""
        return {
            "target_counts": dict(self.target_counts),
            "action_counts": dict(self.action_counts),
            "tool_success": dict(self.tool_success),
            "tool_total": dict(self.tool_total),
            "total_messages": self.total_messages,
        }

    def load_summary(self, data: dict[str, object]) -> None:
        """Restore from persisted data."""
        self.target_counts = dict(data.get("target_counts", {}))
        self.action_counts = dict(data.get("action_counts", {}))
        self.tool_success = dict(data.get("tool_success", {}))
        self.tool_total = dict(data.get("tool_total", {}))
        self.total_messages = data.get("total_messages", 0)
