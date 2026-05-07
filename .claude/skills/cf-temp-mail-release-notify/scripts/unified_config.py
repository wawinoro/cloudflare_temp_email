#!/usr/bin/env python3
"""
unified_config.py - Shared configuration loader and validator for release notify scripts.

Provides a single source of truth for loading, validating, and accessing
configuration used across all release notification scripts.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config.json"
EXAMPLE_CONFIG_PATH = Path(__file__).parent.parent / "config.example.json"

REQUIRED_KEYS = [
    "telegram_bot_token",
    "telegram_chat_id",
    "github_repo",
]

OPTIONAL_KEYS = {
    "github_token": None,
    "state_file": ".notify_state.json",
    "release_max_age_days": 7,
    "message_parse_mode": "MarkdownV2",
    "disable_web_page_preview": True,
}


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""
    pass


def find_config(path: Optional[str] = None) -> Path:
    """Resolve the config file path, falling back to the default location."""
    if path:
        resolved = Path(path)
        if not resolved.exists():
            raise ConfigError(f"Config file not found: {resolved}")
        return resolved

    env_path = os.environ.get("NOTIFY_CONFIG")
    if env_path:
        resolved = Path(env_path)
        if not resolved.exists():
            raise ConfigError(f"Config file from NOTIFY_CONFIG not found: {resolved}")
        return resolved

    if DEFAULT_CONFIG_PATH.exists():
        return DEFAULT_CONFIG_PATH

    raise ConfigError(
        f"No config file found. Copy {EXAMPLE_CONFIG_PATH} to {DEFAULT_CONFIG_PATH} "
        "and fill in your values, or set the NOTIFY_CONFIG environment variable."
    )


def load_config(path: Optional[str] = None) -> dict[str, Any]:
    """
    Load and validate configuration from a JSON file.

    Args:
        path: Optional explicit path to the config file.

    Returns:
        Merged dict of required + optional config values.

    Raises:
        ConfigError: If the file is missing, malformed, or incomplete.
    """
    config_path = find_config(path)

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in config file {config_path}: {exc}") from exc

    # Validate required keys
    missing = [k for k in REQUIRED_KEYS if not raw.get(k)]
    if missing:
        raise ConfigError(
            f"Missing required config keys: {', '.join(missing)}\n"
            f"See {EXAMPLE_CONFIG_PATH} for reference."
        )

    # Merge with defaults for optional keys
    config: dict[str, Any] = {**OPTIONAL_KEYS, **raw}

    # Normalise repo format (strip leading https://github.com/ if present)
    repo: str = config["github_repo"]
    for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
        if repo.startswith(prefix):
            repo = repo[len(prefix):]
            break
    config["github_repo"] = repo.rstrip("/")

    return config


def github_headers(config: dict[str, Any]) -> dict[str, str]:
    """Build HTTP headers for GitHub API requests."""
    headers = {"Accept": "application/vnd.github+json"}
    token = config.get("github_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def telegram_api_url(config: dict[str, Any], method: str) -> str:
    """Return the Telegram Bot API URL for the given method."""
    token = config["telegram_bot_token"]
    return f"https://api.telegram.org/bot{token}/{method}"


def resolve_state_file(config: dict[str, Any]) -> Path:
    """Resolve the absolute path for the notification state file."""
    raw = config.get("state_file") or OPTIONAL_KEYS["state_file"]
    p = Path(raw)  # type: ignore[arg-type]
    if not p.is_absolute():
        # Store relative paths next to the config file
        try:
            config_path = find_config()
            p = config_path.parent / p
        except ConfigError:
            p = Path.cwd() / p
    return p


if __name__ == "__main__":
    # Quick smoke-test: print resolved config (masking secrets)
    try:
        cfg = load_config()
    except ConfigError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    safe = {k: ("***" if "token" in k else v) for k, v in cfg.items()}
    print(json.dumps(safe, indent=2))
