"""Zero-leak .env configuration loader and secret redactor for OmniOps."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_KEYS = {
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "GEMINI_MODEL",
    "GROQ_REASONING_MODEL",
    "OPENROUTER_MODEL",
    "HOST",
    "PORT",
    "JIRA_BASE_URL",
    "JIRA_EMAIL",
    "JIRA_API_TOKEN",
    "JIRA_PROJECT_KEY",
    "JIRA_BOARD_ID",
}

_TOKEN_PATTERN = re.compile(
    r"(?:gsk_[A-Za-z0-9_-]+|AIza[A-Za-z0-9_-]+|sk-or-v1-[A-Za-z0-9_-]+|ATATT[A-Za-z0-9_=-]+)"
)


def parse_env(content: str) -> dict[str, str]:
    """Parse .env lines without modifying os.environ."""
    values: dict[str, str] = {}
    for line in content.splitlines():
        match = re.match(r"^\s*(?:export\s+)?([A-Z_][A-Z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if not match or match[1] not in ENV_KEYS:
            continue
        raw_val = match[2]
        if raw_val.startswith(("'", '"')):
            quote = raw_val[0]
            escaped = False
            end = None
            for idx, ch in enumerate(raw_val[1:], start=1):
                if ch == quote and not escaped:
                    end = idx
                    break
                escaped = ch == "\\" and not escaped
                if ch != "\\":
                    escaped = False
            value = raw_val[1:end] if end is not None else raw_val[1:]
        else:
            value = re.sub(r"\s+#.*$", "", raw_val)
        cleaned = value.strip()
        if cleaned:
            values[match[1]] = cleaned
    return values


@dataclass(frozen=True)
class Settings:
    """Immutable application and LLM provider settings with hidden secret reprs."""

    gemini_key: str = field(default="", repr=False)
    groq_key: str = field(default="", repr=False)
    openrouter_key: str = field(default="", repr=False)
    jira_api_token: str = field(default="", repr=False)
    gemini_model: str = "gemini-3.5-flash-lite"
    groq_reasoning_model: str = "openai/gpt-oss-20b"
    openrouter_model: str = "openai/gpt-oss-20b"
    host: str = "127.0.0.1"
    port: int = 4320
    jira_base_url: str = ""
    jira_email: str = ""
    jira_project_key: str = "OO"
    timeout_seconds: float = 25.0


def load_settings(
    environment: Mapping[str, str] | None = None,
    *,
    load_files: bool | None = None,
) -> Settings:
    """Load settings from untracked .env files and environment mapping."""
    values: dict[str, str] = {}
    should_read_files = (environment is None) if load_files is None else load_files

    if should_read_files:
        candidate_paths = [
            *(PROJECT_ROOT.parents[i] / ".env" for i in (2, 1) if len(PROJECT_ROOT.parents) > i),
            PROJECT_ROOT.parent / "Voice_Coach" / ".env",
            PROJECT_ROOT / ".env",
        ]
        for path in candidate_paths:
            if path.is_file():
                values.update(parse_env(path.read_text(encoding="utf-8")))

    env_source = os.environ if environment is None else environment
    for key, raw_value in env_source.items():
        if key in ENV_KEYS and isinstance(raw_value, str):
            cleaned = raw_value.strip()
            if cleaned:
                values[key] = cleaned

    raw_port = values.get("PORT", "4320")
    try:
        port = int(raw_port)
    except ValueError:
        raise ValueError("PORT must be a valid port number.") from None
    if not 0 <= port <= 65535:
        raise ValueError("PORT must be a valid port number.")

    return Settings(
        gemini_key=values.get("GEMINI_API_KEY") or values.get("GOOGLE_API_KEY", ""),
        groq_key=values.get("GROQ_API_KEY", ""),
        openrouter_key=values.get("OPENROUTER_API_KEY", ""),
        jira_api_token=values.get("JIRA_API_TOKEN", ""),
        gemini_model=values.get("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        groq_reasoning_model=values.get("GROQ_REASONING_MODEL", "openai/gpt-oss-20b"),
        openrouter_model=values.get("OPENROUTER_MODEL", "openai/gpt-oss-20b"),
        host=values.get("HOST", "127.0.0.1"),
        port=port,
        jira_base_url=values.get("JIRA_BASE_URL", ""),
        jira_email=values.get("JIRA_EMAIL", ""),
        jira_project_key=values.get("JIRA_PROJECT_KEY") or values.get("JIRA_BOARD_ID") or "OO",
    )


def redact_secrets(text: str, settings: Settings | None = None) -> str:
    """Scrub configured API keys and known token formats from diagnostic logs."""
    cleaned = text
    if settings is not None:
        for secret in (
            settings.gemini_key,
            settings.groq_key,
            settings.openrouter_key,
            settings.jira_api_token,
        ):
            if secret:
                cleaned = cleaned.replace(secret, "[redacted]")
    return _TOKEN_PATTERN.sub("[redacted]", cleaned)
