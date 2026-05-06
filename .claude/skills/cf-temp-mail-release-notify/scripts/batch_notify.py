#!/usr/bin/env python3
"""
batch_notify.py - Send release notifications to multiple Telegram targets.

Supports sending a single release notification to multiple chat IDs or
channels defined in the config, with retry logic and rate limiting.
"""

import json
import time
import sys
import argparse
import logging
from pathlib import Path
from typing import Optional

# Reuse helpers from sibling scripts
sys.path.insert(0, str(Path(__file__).parent))
from send_release_to_telegram import load_config, fetch_release, md_render, die

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

DEFAULT_CONFIG = Path(__file__).parent.parent / "config.json"
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
RETRY_DELAYS = [2, 5, 10]  # seconds between retries
RATE_LIMIT_DELAY = 0.5      # seconds between successful sends


def send_message(token: str, chat_id: str, text: str, retries: int = 3) -> bool:
    """Send a Markdown message to a single Telegram chat, with retries."""
    import urllib.request
    import urllib.error

    url = TELEGRAM_API.format(token=token)
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": False,
    }).encode()

    for attempt, delay in enumerate(RETRY_DELAYS[:retries], start=1):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=15) as resp:
                result = json.loads(resp.read())
                if result.get("ok"):
                    log.info("  ✓ Sent to %s", chat_id)
                    return True
                log.warning("  Telegram error for %s: %s", chat_id, result)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")
            log.warning("  HTTP %s for %s: %s", exc.code, chat_id, body)
        except Exception as exc:  # noqa: BLE001
            log.warning("  Attempt %d failed for %s: %s", attempt, chat_id, exc)

        if attempt < retries:
            log.info("  Retrying in %ds…", delay)
            time.sleep(delay)

    log.error("  ✗ Failed to send to %s after %d attempts", chat_id, retries)
    return False


def batch_notify(
    config_path: Path,
    tag: Optional[str] = None,
    dry_run: bool = False,
) -> int:
    """Fetch a release and notify all configured Telegram targets.

    Returns the number of failed deliveries.
    """
    config = load_config(config_path)

    token = config.get("telegram_bot_token") or die("Missing telegram_bot_token in config")
    targets: list[str] = config.get("telegram_chat_ids", [])

    if not targets:
        # Fall back to single chat_id for backward compat
        single = config.get("telegram_chat_id")
        if single:
            targets = [single]
        else:
            die("No telegram_chat_ids (or telegram_chat_id) defined in config")

    log.info("Fetching release%s…", f" {tag}" if tag else " (latest)")
    release = fetch_release(config, tag)
    if not release:
        die("Could not fetch release data")

    message = md_render(release)
    log.info("Release: %s — %s", release.get("tag_name"), release.get("name"))
    log.info("Notifying %d target(s)…", len(targets))

    failures = 0
    for chat_id in targets:
        if dry_run:
            log.info("  [dry-run] Would send to %s", chat_id)
            continue
        ok = send_message(token, str(chat_id), message)
        if not ok:
            failures += 1
        time.sleep(RATE_LIMIT_DELAY)

    if failures:
        log.error("%d/%d deliveries failed.", failures, len(targets))
    else:
        log.info("All %d notification(s) delivered successfully.", len(targets))

    return failures


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-notify Telegram targets about a GitHub release."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG),
        help="Path to config.json (default: %(default)s)",
    )
    parser.add_argument(
        "--tag",
        default=None,
        help="Release tag to announce (default: latest)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print targets without actually sending messages",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    failed = batch_notify(
        config_path=Path(args.config),
        tag=args.tag,
        dry_run=args.dry_run,
    )
    sys.exit(1 if failed else 0)
