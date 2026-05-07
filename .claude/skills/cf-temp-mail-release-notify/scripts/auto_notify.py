#!/usr/bin/env python3
"""
auto_notify.py — Main entry point for automated release notification.

Checks for new releases on GitHub and sends Telegram notifications
if a release hasn't been notified yet. Designed to be run via cron
or CI/CD pipeline.

Usage:
    python auto_notify.py [--config config.json] [--dry-run] [--force]
"""

import argparse
import json
import sys
import os
from pathlib import Path

# Allow imports from the same scripts directory
scripts_dir = Path(__file__).parent
sys.path.insert(0, str(scripts_dir))

from fetch_latest_release import load_config as fetch_load_config, fetch_latest_release, parse_release
from check_notify_status import load_state, is_notified, mark_as_sent
from send_release_to_telegram import load_config as tg_load_config, send_telegram_message, format_release_message


DEFAULT_CONFIG = scripts_dir.parent / "config.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Auto-notify Telegram when a new GitHub release is published."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to config.json (default: ../config.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and format the message but do NOT send it or update state.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Send notification even if this release was already notified.",
    )
    parser.add_argument(
        "--state-file",
        default=None,
        help="Override path to the notification state file.",
    )
    return parser.parse_args()


def load_unified_config(config_path: str) -> dict:
    """Load and validate the unified config file."""
    path = Path(config_path)
    if not path.exists():
        print(f"[ERROR] Config file not found: {config_path}", file=sys.stderr)
        print("  Copy config.example.json to config.json and fill in your values.", file=sys.stderr)
        sys.exit(1)

    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)

    required_keys = ["github_repo", "telegram_bot_token", "telegram_chat_id"]
    missing = [k for k in required_keys if not config.get(k)]
    if missing:
        print(f"[ERROR] Missing required config keys: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    return config


def run(args: argparse.Namespace) -> int:
    """Main logic. Returns exit code (0 = success, 1 = error, 2 = no new release)."""
    config = load_unified_config(args.config)

    repo = config["github_repo"]
    print(f"[INFO] Checking latest release for: {repo}")

    # Fetch latest release from GitHub
    raw_release = fetch_latest_release(repo)
    if raw_release is None:
        print("[WARN] No releases found for this repository.")
        return 2

    release = parse_release(raw_release)
    tag = release.get("tag_name", "unknown")
    print(f"[INFO] Latest release: {tag} — {release.get('name', '')}")

    # Resolve state file path
    state_file = args.state_file or config.get("state_file", str(scripts_dir.parent / "notify_state.json"))
    state = load_state(state_file)

    # Check if already notified
    if is_notified(state, tag) and not args.force:
        print(f"[INFO] Release {tag} already notified. Use --force to re-send.")
        return 2

    # Format the Telegram message
    message = format_release_message(release)

    if args.dry_run:
        print("[DRY-RUN] Would send the following message:")
        print("-" * 60)
        print(message)
        print("-" * 60)
        return 0

    # Send via Telegram
    bot_token = config["telegram_bot_token"]
    chat_id = config["telegram_chat_id"]
    parse_mode = config.get("parse_mode", "MarkdownV2")

    print(f"[INFO] Sending notification to chat {chat_id} ...")
    success = send_telegram_message(bot_token, chat_id, message, parse_mode=parse_mode)

    if not success:
        print("[ERROR] Failed to send Telegram message.", file=sys.stderr)
        return 1

    # Mark as sent in state file
    mark_as_sent(state, tag, release)
    # Persist updated state
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

    print(f"[OK] Notification sent and state updated for {tag}.")
    return 0


def main():
    args = parse_args()
    exit_code = run(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
