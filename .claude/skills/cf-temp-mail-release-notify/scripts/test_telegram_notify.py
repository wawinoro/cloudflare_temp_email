#!/usr/bin/env python3
"""
Test script for the Telegram release notification system.
Verifies configuration, API connectivity, and message formatting
without actually sending a full release notification.

Usage:
    python test_telegram_notify.py [--config config.json] [--dry-run]
"""

import argparse
import json
import os
import sys
import requests

# Reuse helpers from the main script
sys.path.insert(0, os.path.dirname(__file__))
from send_release_to_telegram import load_config, md_escape, md_render


DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")

TEST_RELEASE = {
    "tag_name": "v0.0.0-test",
    "name": "Test Release",
    "html_url": "https://github.com/dreamhunter2333/cloudflare_temp_email/releases/tag/v0.0.0-test",
    "body": (
        "## What's Changed\n"
        "- feat: add test notification support\n"
        "- fix: resolve config loading edge case\n"
        "\n"
        "**Full Changelog**: https://github.com/dreamhunter2333/cloudflare_temp_email/compare/v0.0.0-prev...v0.0.0-test"
    ),
    "published_at": "2024-01-01T00:00:00Z",
    "prerelease": False,
    "draft": False,
}


def check_config(config: dict) -> list[str]:
    """Validate required config fields. Returns list of error messages."""
    errors = []
    required = ["telegram_bot_token", "telegram_chat_id"]
    for field in required:
        if not config.get(field):
            errors.append(f"Missing or empty config field: '{field}'")
    return errors


def test_bot_identity(token: str) -> dict | None:
    """Call getMe to verify the bot token is valid."""
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if data.get("ok"):
            return data["result"]
        print(f"  [FAIL] getMe returned ok=false: {data.get('description')}")
        return None
    except requests.RequestException as exc:
        print(f"  [FAIL] Network error during getMe: {exc}")
        return None


def send_test_message(token: str, chat_id: str, dry_run: bool = False) -> bool:
    """Send a short test message to confirm delivery works."""
    text = md_escape("✅ cf-temp-mail release notify — connection test OK")
    if dry_run:
        print(f"  [DRY-RUN] Would send to chat_id={chat_id}: {text}")
        return True

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        if data.get("ok"):
            msg_id = data["result"]["message_id"]
            print(f"  [OK] Test message delivered (message_id={msg_id})")
            return True
        print(f"  [FAIL] sendMessage error: {data.get('description')}")
        return False
    except requests.RequestException as exc:
        print(f"  [FAIL] Network error during sendMessage: {exc}")
        return False


def preview_formatted_message() -> None:
    """Print the formatted release message that would be sent."""
    rendered = md_render(TEST_RELEASE)
    print("\n--- Formatted message preview ---")
    print(rendered)
    print("--- End of preview ---\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Telegram notification setup")
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help="Path to config.json (default: ../config.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip actual API calls; only validate config and preview output",
    )
    args = parser.parse_args()

    print("=== cf-temp-mail Telegram Notify — Self-Test ===")

    # 1. Load config
    print("\n[1/4] Loading config...")
    try:
        config = load_config(args.config)
        print(f"  [OK] Config loaded from {args.config}")
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as exc:
        print(f"  [FAIL] Could not load config: {exc}")
        sys.exit(1)

    # 2. Validate config fields
    print("\n[2/4] Validating config fields...")
    errors = check_config(config)
    if errors:
        for err in errors:
            print(f"  [FAIL] {err}")
        sys.exit(1)
    print("  [OK] All required fields present")

    # 3. Verify bot identity
    print("\n[3/4] Verifying bot token via getMe...")
    if args.dry_run:
        print("  [DRY-RUN] Skipping API call")
    else:
        bot_info = test_bot_identity(config["telegram_bot_token"])
        if bot_info is None:
            sys.exit(1)
        username = bot_info.get("username", "unknown")
        print(f"  [OK] Bot identity confirmed: @{username}")

    # 4. Send test message
    print("\n[4/4] Sending test message...")
    success = send_test_message(
        config["telegram_bot_token"],
        config["telegram_chat_id"],
        dry_run=args.dry_run,
    )
    if not success:
        sys.exit(1)

    # Bonus: preview formatted release message
    preview_formatted_message()

    print("All checks passed. Notification system is ready.")


if __name__ == "__main__":
    main()
