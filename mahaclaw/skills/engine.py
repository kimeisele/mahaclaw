"""Skill Engine — discover, load, and dispatch Python skill modules.

Skills can be:
  1. Python modules in a skills directory (native, typed)
  2. OpenClaw SKILL.md files (parsed for compatibility)

Native Python skills are modules with a `run(context: SkillContext) -> SkillResult`
function and an optional `METADATA` dict.

Pure stdlib only.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

from ._types import SkillMetadata, SkillContext, SkillResult, SkillRunner
from .compat import parse_skill_md


class SkillEngine:
    """Discovers, loads, and dispatches skills."""

    def __init__(self) -> None:
        self._skills: dict[str, SkillMetadata] = {}
        self._runners: dict[str, SkillRunner] = {}

    @property
    def skill_count(self) -> int:
        return len(self._skills)

    def list_skills(self) -> list[SkillMetadata]:
        return list(self._skills.values())

    def get_skill(self, name: str) -> SkillMetadata | None:
        return self._skills.get(name)

    # --- Registration ---

    def register(self, name: str, runner: SkillRunner, metadata: SkillMetadata | None = None) -> None:
        """Register a skill programmatically."""
        if metadata is None:
            metadata = SkillMetadata(name=name, description=f"Skill: {name}")
        self._skills[name] = metadata
        self._runners[name] = runner

    # --- Discovery ---

    def discover_python(self, directory: Path) -> int:
        """Discover Python skill modules in a directory.

        Each .py file must have a `run(context: SkillContext) -> SkillResult` function
        and optionally a `METADATA` dict.

        Returns number of skills loaded.
        """
        if not directory.is_dir():
            return 0

        count = 0
        for path in sorted(directory.glob("*.py")):
            if path.name.startswith("_"):
                continue
            try:
                skill = self._load_python_skill(path)
                if skill:
                    count += 1
            except Exception:
                pass
        return count

    def discover_skillmd(self, directory: Path) -> int:
        """Discover OpenClaw SKILL.md files.

        Returns number of skills loaded.
        """
        if not directory.is_dir():
            return 0

        count = 0
        for path in sorted(directory.rglob("SKILL.md")):
            try:
                meta = parse_skill_md(path)
                if meta:
                    self._skills[meta.name] = meta
                    count += 1
            except Exception:
                pass
        return count

    def _load_python_skill(self, path: Path) -> SkillMetadata | None:
        """Load a single Python skill module."""
        name = path.stem
        spec = importlib.util.spec_from_file_location(f"mahaclaw.skills.{name}", path)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        runner = getattr(module, "run", None)
        if not callable(runner):
            return None

        raw_meta = getattr(module, "METADATA", {})
        metadata = SkillMetadata(
            name=raw_meta.get("name", name),
            description=raw_meta.get("description", f"Python skill: {name}"),
            user_invocable=raw_meta.get("user_invocable", True),
            requires_bins=tuple(raw_meta.get("requires_bins", ())),
            requires_env=tuple(raw_meta.get("requires_env", ())),
            source_path=str(path),
            kind="python",
        )

        self._skills[metadata.name] = metadata
        self._runners[metadata.name] = runner
        return metadata

    # --- Execution ---

    def can_run(self, name: str) -> tuple[bool, str]:
        """Check if a skill can run (bins/env available).  Returns (ok, reason)."""
        meta = self._skills.get(name)
        if meta is None:
            return False, f"skill '{name}' not found"

        for b in meta.requires_bins:
            if not any((Path(d) / b).is_file() for d in os.environ.get("PATH", "").split(":")):
                return False, f"required binary not found: {b}"

        for env in meta.requires_env:
            if not os.environ.get(env):
                return False, f"required env var not set: {env}"

        return True, "ok"

    def run(self, name: str, context: SkillContext) -> SkillResult:
        """Run a skill by name."""
        runner = self._runners.get(name)
        if runner is None:
            return SkillResult(ok=False, error=f"skill '{name}' has no runner (maybe SKILL.md?)")

        ok, reason = self.can_run(name)
        if not ok:
            return SkillResult(ok=False, error=reason)

        try:
            return runner(context)
        except Exception as exc:
            return SkillResult(ok=False, error=str(exc))

    def match_skill(self, message: str) -> str | None:
        """Try to match a message to a skill by slash-command or keyword."""
        lower = message.lower().strip()
        if lower.startswith("/"):
            cmd = lower.split()[0][1:]
            if cmd in self._skills:
                return cmd
        return None
