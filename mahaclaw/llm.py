"""Provider-agnostic LLM client — OpenAI-compatible HTTP API.

Supports any OpenAI-compatible endpoint:
  - Ollama (default, localhost:11434)
  - OpenRouter, Together, Groq, etc.
  - OpenAI itself

Two modes:
  1. standalone: Direct LLM call via HTTP (this module)
  2. steward: Delegate to federation via NADI (envelope.py)

Pure stdlib: uses subprocess curl for HTTP calls.
"""
from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass, field


# --- Configuration ---

DEFAULT_BASE_URL = "http://localhost:11434/v1"  # Ollama
DEFAULT_MODEL = "qwen2.5:0.5b"  # Small, fast, runs on anything
DEFAULT_TIMEOUT_S = 60
MAX_RETRIES = 2
SYSTEM_PROMPT = (
    "You are Maha Claw, a federation edge agent. "
    "Answer concisely. If you don't know, say so."
)


@dataclass(frozen=True)
class LLMConfig:
    """LLM provider configuration."""
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    api_key: str = ""
    timeout_s: int = DEFAULT_TIMEOUT_S
    system_prompt: str = SYSTEM_PROMPT
    temperature: float = 0.7
    max_tokens: int = 1024


@dataclass
class LLMResponse:
    """Normalized response from any provider."""
    ok: bool
    content: str = ""
    model: str = ""
    usage: dict = field(default_factory=dict)
    duration_ms: float = 0.0
    error: str = ""
    provider: str = ""


def config_from_env() -> LLMConfig:
    """Build config from environment variables with sensible defaults."""
    return LLMConfig(
        base_url=os.environ.get("MAHACLAW_LLM_URL", DEFAULT_BASE_URL),
        model=os.environ.get("MAHACLAW_LLM_MODEL", DEFAULT_MODEL),
        api_key=os.environ.get("MAHACLAW_LLM_KEY", ""),
        timeout_s=int(os.environ.get("MAHACLAW_LLM_TIMEOUT", str(DEFAULT_TIMEOUT_S))),
        system_prompt=os.environ.get("MAHACLAW_SYSTEM_PROMPT", SYSTEM_PROMPT),
        temperature=float(os.environ.get("MAHACLAW_LLM_TEMP", "0.7")),
        max_tokens=int(os.environ.get("MAHACLAW_LLM_MAX_TOKENS", "1024")),
    )


# --- HTTP via curl (pure stdlib, no requests/httpx) ---

def _curl_post(url: str, data: dict, api_key: str = "",
               timeout_s: int = DEFAULT_TIMEOUT_S) -> tuple[bool, int, str]:
    """POST JSON via curl subprocess.  Returns (ok, status_code, body)."""
    cmd = [
        "curl", "-s", "-w", "\n%{http_code}",
        "-X", "POST", url,
        "-H", "Content-Type: application/json",
        "--max-time", str(timeout_s),
        "-d", json.dumps(data),
    ]
    if api_key:
        cmd.extend(["-H", f"Authorization: Bearer {api_key}"])

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout_s + 5,
        )
    except subprocess.TimeoutExpired:
        return False, 0, "curl timeout"
    except FileNotFoundError:
        return False, 0, "curl not found"

    if result.returncode != 0:
        return False, 0, result.stderr or f"curl exit code {result.returncode}"

    # curl -w appends status code on last line
    lines = result.stdout.rsplit("\n", 1)
    if len(lines) == 2:
        body, status_str = lines
        try:
            status = int(status_str.strip())
        except ValueError:
            status = 0
            body = result.stdout
    else:
        body = result.stdout
        status = 0

    return status == 200, status, body


# --- Chat completion ---

def chat(messages: list[dict], config: LLMConfig | None = None) -> LLMResponse:
    """Send a chat completion request to any OpenAI-compatible endpoint.

    Args:
        messages: List of {"role": "system"|"user"|"assistant", "content": "..."}
        config: LLM configuration (defaults to env-based config)

    Returns:
        LLMResponse with content or error
    """
    if config is None:
        config = config_from_env()

    url = f"{config.base_url.rstrip('/')}/chat/completions"

    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
    }

    t0 = time.monotonic()
    ok, status, body = _curl_post(url, payload, config.api_key, config.timeout_s)
    duration_ms = (time.monotonic() - t0) * 1000

    if not ok:
        # Retry once on 5xx or timeout
        if status >= 500 or status == 0:
            time.sleep(1)
            t0 = time.monotonic()
            ok, status, body = _curl_post(url, payload, config.api_key, config.timeout_s)
            duration_ms = (time.monotonic() - t0) * 1000

        if not ok:
            return LLMResponse(
                ok=False,
                error=f"HTTP {status}: {body[:200]}",
                duration_ms=duration_ms,
                provider=config.base_url,
            )

    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return LLMResponse(
            ok=False,
            error=f"invalid JSON response: {body[:200]}",
            duration_ms=duration_ms,
            provider=config.base_url,
        )

    # Extract from OpenAI-compatible response format
    choices = data.get("choices", [])
    if not choices:
        return LLMResponse(
            ok=False,
            error="no choices in response",
            duration_ms=duration_ms,
            provider=config.base_url,
            model=data.get("model", config.model),
        )

    content = choices[0].get("message", {}).get("content", "")

    return LLMResponse(
        ok=True,
        content=content,
        model=data.get("model", config.model),
        usage=data.get("usage", {}),
        duration_ms=duration_ms,
        provider=config.base_url,
    )


def ask(question: str, config: LLMConfig | None = None,
        history: list[dict] | None = None) -> LLMResponse:
    """Simple question → answer interface with optional conversation history.

    Prepends system prompt, appends history, then the question.
    """
    if config is None:
        config = config_from_env()

    messages = [{"role": "system", "content": config.system_prompt}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": question})

    return chat(messages, config)


def is_available(config: LLMConfig | None = None) -> tuple[bool, str]:
    """Check if the LLM endpoint is reachable.  Returns (ok, info)."""
    if config is None:
        config = config_from_env()

    url = f"{config.base_url.rstrip('/')}/models"
    cmd = [
        "curl", "-s", "--max-time", "5", url,
    ]
    if config.api_key:
        cmd.extend(["-H", f"Authorization: Bearer {config.api_key}"])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return False, f"curl error: {result.stderr}"

        data = json.loads(result.stdout)
        models = data.get("data", [])
        model_ids = [m.get("id", "?") for m in models[:5]]
        return True, f"{len(models)} models: {', '.join(model_ids)}"
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, "endpoint unreachable"
    except json.JSONDecodeError:
        return False, f"unexpected response: {result.stdout[:100]}"
