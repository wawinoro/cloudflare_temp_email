#!/usr/bin/env python3
"""
notify_changelog.py - Generate and send a formatted changelog diff between two releases.

Usage:
    python notify_changelog.py --from v1.0.0 --to v1.1.0
    python notify_changelog.py --from v1.0.0  # compares to latest
"""

import argparse
import sys
from typing import Optional

import requests

from unified_config import load_config, github_headers, telegram_api_url


def fetch_release_by_tag(repo: str, tag: str, headers: dict) -> Optional[dict]:
    """Fetch a specific GitHub release by tag name."""
    url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code == 404:
        print(f"[warn] Release tag '{tag}' not found.", file=sys.stderr)
        return None
    resp.raise_for_status()
    return resp.json()


def fetch_latest_release(repo: str, headers: dict) -> Optional[dict]:
    """Fetch the latest GitHub release."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()


def build_changelog_message(from_release: dict, to_release: dict) -> str:
    """Build a Telegram-formatted changelog message comparing two releases."""
    from_tag = from_release.get("tag_name", "unknown")
    to_tag = to_release.get("tag_name", "unknown")
    to_url = to_release.get("html_url", "")
    to_name = to_release.get("name") or to_tag
    body = to_release.get("body") or "_No release notes provided._"

    lines = [
        f"\U0001f4cb *Changelog: {escape_md(from_tag)} \u2192 {escape_md(to_tag)}*",
        "",
        f"*{escape_md(to_name)}*",
        "",
    ]

    # Render body lines, truncating if too long
    body_lines = body.strip().splitlines()
    max_lines = 30
    if len(body_lines) > max_lines:
        body_lines = body_lines[:max_lines] + [f"_...and {len(body_lines) - max_lines} more lines_"]

    for line in body_lines:
        lines.append(escape_md(line))

    lines += [
        "",
        f"[View full release]({to_url})",
    ]

    return "\n".join(lines)


def escape_md(text: str) -> str:
    """Escape special MarkdownV2 characters for Telegram."""
    special = r"\_*[]()~`>#+-=|{}.!"
    for ch in special:
        text = text.replace(ch, f"\\{ch}")
    return text


def send_telegram_message(token: str, chat_id: str, text: str) -> bool:
    """Send a message via Telegram Bot API. Returns True on success."""
    url = telegram_api_url(token, "sendMessage")
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": True,
    }
    resp = requests.post(url, json=payload, timeout=15)
    if not resp.ok:
        print(f"[error] Telegram API error {resp.status_code}: {resp.text}", file=sys.stderr)
        return False
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send a changelog diff between two GitHub releases to Telegram."
    )
    parser.add_argument(
        "--from",
        dest="from_tag",
        required=True,
        help="Starting release tag (e.g. v1.0.0)",
    )
    parser.add_argument(
        "--to",
        dest="to_tag",
        default=None,
        help="Ending release tag (default: latest release)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Path to config.json (auto-detected if omitted)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the message without sending it",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)

    repo = config["github_repo"]
    token = config["telegram_token"]
    chat_id = config["telegram_chat_id"]
    headers = github_headers(config)

    print(f"[info] Fetching release '{args.from_tag}'...")
    from_release = fetch_release_by_tag(repo, args.from_tag, headers)
    if from_release is None:
        sys.exit(1)

    if args.to_tag:
        print(f"[info] Fetching release '{args.to_tag}'...")
        to_release = fetch_release_by_tag(repo, args.to_tag, headers)
    else:
        print("[info] Fetching latest release...")
        to_release = fetch_latest_release(repo, headers)

    if to_release is None:
        sys.exit(1)

    if from_release["tag_name"] == to_release["tag_name"]:
        print("[warn] Both tags refer to the same release. Nothing to compare.")
        sys.exit(0)

    message = build_changelog_message(from_release, to_release)

    if args.dry_run:
        print("[dry-run] Message preview:")
        print("-" * 60)
        print(message)
        print("-" * 60)
        return

    print(f"[info] Sending changelog to Telegram chat {chat_id}...")
    ok = send_telegram_message(token, chat_id, message)
    if ok:
        print("[info] Changelog sent successfully.")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
