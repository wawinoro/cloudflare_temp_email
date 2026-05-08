#!/usr/bin/env python3
"""
validate_config.py — Validate the notify skill configuration file.

Checks that all required fields are present, the GitHub token has
the correct scopes, and the Telegram bot token / chat-id are reachable.

Usage:
    python validate_config.py [--config PATH]

Exit codes:
    0  all checks passed
    1  one or more checks failed
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("[error] 'requests' is not installed. Run: pip install requests", file=sys.stderr)
    sys.exit(1)

from unified_config import find_config, load_config, ConfigError, github_headers, telegram_api_url

# ── helpers ──────────────────────────────────────────────────────────────────

OK   = "\033[32m✔\033[0m"
FAIL = "\033[31m✘\033[0m"
WARN = "\033[33m⚠\033[0m"


def _result(ok: bool, label: str, detail: str = "") -> bool:
    icon = OK if ok else FAIL
    line = f"  {icon}  {label}"
    if detail:
        line += f"  ({detail})"
    print(line)
    return ok


# ── individual checks ─────────────────────────────────────────────────────────

def check_required_keys(cfg: dict) -> bool:
    """Ensure every mandatory key exists and is non-empty."""
    required = {
        "github_token": str,
        "github_repo": str,
        "telegram_bot_token": str,
        "telegram_chat_id": (str, int),
    }
    passed = True
    for key, expected_type in required.items():
        value = cfg.get(key)
        if value is None:
            _result(False, f"config key '{key}'", "missing")
            passed = False
        elif not str(value).strip():
            _result(False, f"config key '{key}'", "empty")
            passed = False
        elif not isinstance(value, expected_type):
            _result(False, f"config key '{key}'", f"expected {expected_type}, got {type(value).__name__}")
            passed = False
        else:
            _result(True, f"config key '{key}'")
    return passed


def check_github_token(cfg: dict) -> bool:
    """Verify the GitHub token is valid and can read the target repo."""
    repo  = cfg["github_repo"]
    url   = f"https://api.github.com/repos/{repo}"
    try:
        resp = requests.get(url, headers=github_headers(cfg), timeout=10)
    except requests.RequestException as exc:
        return _result(False, "GitHub API reachable", str(exc))

    if resp.status_code == 200:
        data = resp.json()
        return _result(True, "GitHub token & repo", data.get("full_name", repo))
    elif resp.status_code == 401:
        return _result(False, "GitHub token", "invalid or expired")
    elif resp.status_code == 404:
        return _result(False, "GitHub repo", f"'{repo}' not found or no access")
    else:
        return _result(False, "GitHub API", f"HTTP {resp.status_code}")


def check_telegram_bot(cfg: dict) -> bool:
    """Call getMe to verify the Telegram bot token."""
    url = telegram_api_url(cfg, "getMe")
    try:
        resp = requests.get(url, timeout=10)
    except requests.RequestException as exc:
        return _result(False, "Telegram API reachable", str(exc))

    data = resp.json()
    if data.get("ok"):
        bot = data["result"]
        return _result(True, "Telegram bot token", f"@{bot.get('username', '?')}")
    else:
        desc = data.get("description", "unknown error")
        return _result(False, "Telegram bot token", desc)


def check_telegram_chat(cfg: dict) -> bool:
    """Call getChat to verify the chat-id is accessible by the bot."""
    url = telegram_api_url(cfg, "getChat")
    chat_id = cfg["telegram_chat_id"]
    try:
        resp = requests.get(url, params={"chat_id": chat_id}, timeout=10)
    except requests.RequestException as exc:
        return _result(False, "Telegram chat-id reachable", str(exc))

    data = resp.json()
    if data.get("ok"):
        chat = data["result"]
        title = chat.get("title") or chat.get("username") or str(chat_id)
        return _result(True, "Telegram chat-id", title)
    else:
        desc = data.get("description", "unknown error")
        return _result(False, "Telegram chat-id", f"{chat_id} — {desc}")


# ── main ──────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Validate notify skill configuration.")
    p.add_argument("--config", metavar="PATH", help="Path to config.json (auto-detected if omitted)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # locate & load config
    try:
        config_path = Path(args.config) if args.config else find_config()
        cfg = load_config(config_path)
    except ConfigError as exc:
        print(f"{FAIL}  {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"\nValidating config: {config_path}\n")

    results = [
        check_required_keys(cfg),
    ]

    # only run network checks if required keys are present
    if results[0]:
        results += [
            check_github_token(cfg),
            check_telegram_bot(cfg),
            check_telegram_chat(cfg),
        ]

    print()
    total   = len(results)
    passed  = sum(results)
    failed  = total - passed

    if failed == 0:
        print(f"{OK}  All {total} checks passed.")
    else:
        print(f"{FAIL}  {failed}/{total} check(s) failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()
