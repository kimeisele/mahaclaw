"""Tool Sandbox — allowlist-based shell execution with filesystem scoping.

Security model:
  - Only explicitly allowed commands can be executed
  - Filesystem access is scoped to a workspace directory
  - No command substitution, no redirections, no pipes in user input
  - Timeout on all commands
  - Output is captured and truncated to prevent OOM

Pure stdlib: subprocess, shlex, pathlib.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

# Default allowlist: safe, read-only commands + common dev tools
DEFAULT_ALLOWLIST = frozenset({
    "cat", "head", "tail", "wc", "sort", "uniq", "diff",
    "ls", "find", "grep", "rg",
    "echo", "printf", "date", "env",
    "python3", "python", "node",
    "git", "curl",
    "jq", "sed", "awk",
    "mkdir", "touch", "cp", "mv",
})

# Commands that are NEVER allowed regardless of allowlist
BLOCKED_COMMANDS = frozenset({
    "rm", "rmdir", "dd", "mkfs", "fdisk", "mount", "umount",
    "chmod", "chown", "chgrp",
    "kill", "killall", "pkill",
    "shutdown", "reboot", "halt", "poweroff",
    "su", "sudo", "doas",
    "nc", "ncat", "netcat", "socat",
    "ssh", "scp", "sftp",
    "eval", "exec",
})

# Dangerous shell metacharacters (prevent injection)
DANGEROUS_CHARS = frozenset(";&|`$(){}!><")

MAX_OUTPUT_BYTES = 65536
DEFAULT_TIMEOUT_S = 30


@dataclass
class SandboxResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    duration_ms: float = 0.0
    error: str = ""
    truncated: bool = False


@dataclass
class ToolSandbox:
    """Scoped, allowlist-based command execution sandbox."""
    workspace: Path
    allowlist: frozenset[str] = DEFAULT_ALLOWLIST
    timeout_s: int = DEFAULT_TIMEOUT_S
    max_output: int = MAX_OUTPUT_BYTES

    def __post_init__(self) -> None:
        self.workspace = Path(self.workspace).resolve()
        if not self.workspace.is_dir():
            self.workspace.mkdir(parents=True, exist_ok=True)

    def validate_command(self, command: str) -> tuple[bool, str]:
        """Validate a command before execution.  Returns (ok, reason)."""
        command = command.strip()
        if not command:
            return False, "empty command"

        # Check for dangerous metacharacters
        for ch in DANGEROUS_CHARS:
            if ch in command:
                return False, f"blocked character: '{ch}'"

        # Parse the command
        try:
            parts = shlex.split(command)
        except ValueError as e:
            return False, f"invalid command syntax: {e}"

        if not parts:
            return False, "empty command after parsing"

        binary = Path(parts[0]).name

        # Check blocked list first
        if binary in BLOCKED_COMMANDS:
            return False, f"command is blocked: {binary}"

        # Check allowlist
        if binary not in self.allowlist:
            return False, f"command not in allowlist: {binary}"

        return True, "ok"

    def validate_path(self, path: str) -> tuple[bool, str]:
        """Check if a path is within the workspace scope."""
        try:
            resolved = (self.workspace / path).resolve()
        except (ValueError, OSError) as e:
            return False, f"invalid path: {e}"

        if not str(resolved).startswith(str(self.workspace)):
            return False, f"path escapes workspace: {path}"

        return True, "ok"

    def run(self, command: str) -> SandboxResult:
        """Execute a command in the sandbox."""
        ok, reason = self.validate_command(command)
        if not ok:
            return SandboxResult(ok=False, error=reason)

        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                shlex.split(command),
                cwd=str(self.workspace),
                capture_output=True,
                timeout=self.timeout_s,
                env={**os.environ, "HOME": str(self.workspace)},
            )
        except subprocess.TimeoutExpired:
            duration = (time.monotonic() - t0) * 1000
            return SandboxResult(ok=False, error=f"timeout after {self.timeout_s}s", duration_ms=duration)
        except FileNotFoundError:
            duration = (time.monotonic() - t0) * 1000
            return SandboxResult(ok=False, error="command not found", duration_ms=duration)
        except OSError as e:
            duration = (time.monotonic() - t0) * 1000
            return SandboxResult(ok=False, error=str(e), duration_ms=duration)

        duration = (time.monotonic() - t0) * 1000

        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
        truncated = False

        if len(stdout) > self.max_output:
            stdout = stdout[:self.max_output] + "\n... (truncated)"
            truncated = True
        if len(stderr) > self.max_output:
            stderr = stderr[:self.max_output] + "\n... (truncated)"
            truncated = True

        return SandboxResult(
            ok=proc.returncode == 0,
            stdout=stdout,
            stderr=stderr,
            exit_code=proc.returncode,
            duration_ms=duration,
            truncated=truncated,
        )

    def read_file(self, path: str) -> tuple[bool, str]:
        """Read a file within the workspace scope."""
        ok, reason = self.validate_path(path)
        if not ok:
            return False, reason

        resolved = (self.workspace / path).resolve()
        if not resolved.is_file():
            return False, f"not a file: {path}"

        try:
            content = resolved.read_text()
            if len(content) > self.max_output:
                return True, content[:self.max_output] + "\n... (truncated)"
            return True, content
        except OSError as e:
            return False, str(e)

    def write_file(self, path: str, content: str) -> tuple[bool, str]:
        """Write a file within the workspace scope."""
        ok, reason = self.validate_path(path)
        if not ok:
            return False, reason

        resolved = (self.workspace / path).resolve()
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(content)
            return True, f"wrote {len(content)} bytes to {path}"
        except OSError as e:
            return False, str(e)

    def list_dir(self, path: str = ".") -> tuple[bool, list[str]]:
        """List files in a directory within the workspace scope."""
        ok, reason = self.validate_path(path)
        if not ok:
            return False, [reason]

        resolved = (self.workspace / path).resolve()
        if not resolved.is_dir():
            return False, [f"not a directory: {path}"]

        try:
            entries = sorted(str(p.relative_to(resolved)) for p in resolved.iterdir())
            return True, entries
        except OSError as e:
            return False, [str(e)]
