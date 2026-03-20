"""Shared types for the skill system (avoids circular imports)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class SkillMetadata:
    """Skill descriptor."""
    name: str
    description: str
    user_invocable: bool = True
    requires_bins: tuple[str, ...] = ()
    requires_env: tuple[str, ...] = ()
    os_platforms: tuple[str, ...] = ()
    source_path: str = ""
    kind: str = "python"  # "python" | "skillmd"


@dataclass
class SkillContext:
    """Context passed to a skill's run() function."""
    message: str
    session_id: str
    target: str
    payload: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class SkillResult:
    """Result from a skill execution."""
    ok: bool
    output: str = ""
    data: dict = field(default_factory=dict)
    error: str = ""


# Type for a native skill's run function
SkillRunner = Callable[[SkillContext], SkillResult]
