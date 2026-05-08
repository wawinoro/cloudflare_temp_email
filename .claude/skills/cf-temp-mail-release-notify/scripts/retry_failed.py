#!/usr/bin/env python3
"""Retry failed Telegram notifications by re-sending releases that were not
successfully delivered.

Usage:
    python retry_failed.py [--config CONFIG] [--dry-run] [--tag TAG]
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Allow imports from the same scripts directory
sys.path.insert(0, str(Path(__file__).parent))

from unified_config import load_config, telegram_api_url
from check_notify_status import load_state, save_state, is_notified, mark_as_sent
from send_release_to_telegram import fetch_release, md_render

FAILED_LOG = Path(__file__).parent.parent / ".failed_notifications.json"


def load_failed_log() -> list[dict]:
    """Load the list of failed notification attempts."""
    if not FAILED_LOG.exists():
        return []
    try:
        return json.loads(FAILED_LOG.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def save_failed_log(entries: list[dict]) -> None:
    """Persist the failed notification log."""
    FAILED_LOG.write_text(
        json.dumps(entries, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def record_failure(tag: str, reason: str) -> None:
    """Append a failed delivery entry to the log."""
    entries = load_failed_log()
    # Avoid duplicate entries for the same tag
    entries = [e for e in entries if e.get("tag") != tag]
    entries.append({"tag": tag, "reason": reason, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    save_failed_log(entries)


def clear_failure(tag: str) -> None:
    """Remove a tag from the failed log after a successful retry."""
    entries = [e for e in load_failed_log() if e.get("tag") != tag]
    save_failed_log(entries)


def send_message(token: str, chat_id: str, text: str) -> bool:
    """Send a Telegram message; return True on success."""
    import urllib.request
    import urllib.error

    url = telegram_api_url(token, "sendMessage")
    payload = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "MarkdownV2"}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            return bool(result.get("ok"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        print(f"  [HTTP {exc.code}] {body}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"  [ERROR] {exc}", file=sys.stderr)
    return False


def retry_tag(cfg: dict, tag: str, dry_run: bool = False) -> bool:
    """Attempt to re-send the notification for *tag*.

    Returns True when the message was delivered (or would be in dry-run).
    """
    print(f"→ Retrying tag: {tag}")

    release = fetch_release(cfg, tag)
    if release is None:
        print(f"  Could not fetch release data for {tag}", file=sys.stderr)
        record_failure(tag, "fetch_failed")
        return False

    message = md_render(release)

    if dry_run:
        print("  [DRY-RUN] Would send:\n" + message[:300] + ("..." if len(message) > 300 else ""))
        return True

    token = cfg["telegram_bot_token"]
    chat_id = cfg["telegram_chat_id"]
    ok = send_message(token, chat_id, message)
    if ok:
        mark_as_sent(tag)
        clear_failure(tag)
        print(f"  ✓ Delivered {tag}")
    else:
        record_failure(tag, "send_failed")
        print(f"  ✗ Delivery failed for {tag}", file=sys.stderr)
    return ok


def retry_all_failed(cfg: dict, dry_run: bool = False) -> tuple[int, int]:
    """Retry every tag recorded in the failed log.

    Returns (success_count, failure_count).
    """
    entries = load_failed_log()
    if not entries:
        print("No failed notifications found.")
        return 0, 0

    success, failure = 0, 0
    for entry in entries:
        tag = entry["tag"]
        if is_notified(tag):
            print(f"  Skipping {tag} — already marked as sent.")
            clear_failure(tag)
            continue
        ok = retry_tag(cfg, tag, dry_run=dry_run)
        if ok:
            success += 1
        else:
            failure += 1
        time.sleep(1)  # Respect Telegram rate limits

    return success, failure


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Retry failed Telegram release notifications.")
    parser.add_argument("--config", default=None, help="Path to config.json (auto-detected if omitted)")
    parser.add_argument("--tag", default=None, help="Retry a specific release tag only")
    parser.add_argument("--dry-run", action="store_true", help="Preview without sending")
    parser.add_argument("--list", action="store_true", dest="list_failed", help="List failed tags and exit")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)

    if args.list_failed:
        entries = load_failed_log()
        if not entries:
            print("No failed notifications logged.")
        else:
            print(f"{'TAG':<30} {'REASON':<20} TIMESTAMP")
            print("-" * 70)
            for e in entries:
                print(f"{e.get('tag','?'):<30} {e.get('reason','?'):<20} {e.get('ts','?')}")
        return

    if args.tag:
        ok = retry_tag(cfg, args.tag, dry_run=args.dry_run)
        sys.exit(0 if ok else 1)

    success, failure = retry_all_failed(cfg, dry_run=args.dry_run)
    print(f"\nDone — {success} succeeded, {failure} failed.")
    sys.exit(0 if failure == 0 else 1)


if __name__ == "__main__":
    main()
