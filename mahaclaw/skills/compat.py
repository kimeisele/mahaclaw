"""OpenClaw SKILL.md compatibility parser.

Reads SKILL.md files with YAML frontmatter and extracts metadata
compatible with the Maha Claw skill engine.

Pure stdlib: no PyYAML needed (simple line-by-line frontmatter parsing).
"""
from __future__ import annotations

import json
from pathlib import Path

from ..skills._types import SkillMetadata


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML frontmatter from text.  Returns (metadata_dict, body)."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text

    meta: dict = {}
    end_idx = -1
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            end_idx = i
            break
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip()
            value = value.strip()
            # Try to parse JSON values (for metadata field)
            if value.startswith("{") or value.startswith("["):
                try:
                    value = json.loads(value)
                except json.JSONDecodeError:
                    pass
            elif value.lower() in ("true", "false"):
                value = value.lower() == "true"
            meta[key] = value

    body = "\n".join(lines[end_idx + 1:]) if end_idx > 0 else text
    return meta, body


def parse_skill_md(path: Path) -> SkillMetadata | None:
    """Parse an OpenClaw SKILL.md file into a SkillMetadata object."""
    if not path.exists():
        return None

    text = path.read_text()
    meta, body = _parse_frontmatter(text)

    name = meta.get("name")
    if not name:
        # Derive from directory name
        name = path.parent.name

    description = meta.get("description", "")

    # Parse OpenClaw metadata block
    oc_meta = meta.get("metadata", {})
    if isinstance(oc_meta, str):
        try:
            oc_meta = json.loads(oc_meta)
        except json.JSONDecodeError:
            oc_meta = {}

    requires_bins = tuple(oc_meta.get("openclaw.requires.bins", ()))
    requires_env = tuple(oc_meta.get("openclaw.requires.env", ()))
    os_platforms = tuple(oc_meta.get("openclaw.os", ()))
    user_invocable = meta.get("user-invocable", True)

    return SkillMetadata(
        name=name,
        description=description,
        user_invocable=user_invocable,
        requires_bins=requires_bins,
        requires_env=requires_env,
        os_platforms=os_platforms,
        source_path=str(path),
        kind="skillmd",
    )
