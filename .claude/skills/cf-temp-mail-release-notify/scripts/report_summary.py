#!/usr/bin/env python3
"""
report_summary.py — Print a summary report of notification activity.

Reads the state file (notified releases) and the failed-log, then
prints a human-readable table covering:
  • total releases notified
  • last notified tag & timestamp
  • any pending retries (from failed log)
  • config health (token/chat presence)

Usage:
    python report_summary.py [--config PATH] [--json]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Local imports (same directory)
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
from unified_config import load_config, ConfigError  # noqa: E402
from check_notify_status import load_state           # noqa: E402
from retry_failed import load_failed_log             # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _age(iso: str) -> str:
    """Return a human-readable age string for an ISO-8601 timestamp."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes = remainder // 60
        if days:
            return f"{days}d {hours}h ago"
        if hours:
            return f"{hours}h {minutes}m ago"
        return f"{minutes}m ago"
    except Exception:
        return "unknown"


def build_report(config: dict, state: dict, failed: dict) -> dict:
    """
    Assemble a structured report dict from config, notify state, and
    failed-retry log.
    """
    notified = state.get("notified", {})
    sorted_tags = sorted(
        notified.items(),
        key=lambda kv: kv[1].get("sent_at", ""),
        reverse=True,
    )

    last_tag, last_meta = (sorted_tags[0] if sorted_tags else (None, {}))

    pending_retries = [
        {"tag": tag, "attempts": meta.get("attempts", 0), "last_error": meta.get("last_error", "")}
        for tag, meta in failed.items()
    ]

    config_ok = bool(
        config.get("github_token")
        and config.get("telegram_bot_token")
        and config.get("telegram_chat_id")
    )

    return {
        "generated_at": _utc_now(),
        "config_healthy": config_ok,
        "repo": config.get("github_repo", "(not set)"),
        "total_notified": len(notified),
        "last_notified_tag": last_tag,
        "last_notified_at": last_meta.get("sent_at", ""),
        "last_notified_age": _age(last_meta.get("sent_at", "")) if last_tag else "n/a",
        "pending_retries": pending_retries,
        "recent_tags": [tag for tag, _ in sorted_tags[:5]],
    }


def print_report(report: dict) -> None:
    """Pretty-print the report to stdout."""
    sep = "-" * 52
    tick = "✓" if report["config_healthy"] else "✗"
    print(sep)
    print(f"  Cloudflare Temp Email — Notify Report")
    print(f"  Generated : {report['generated_at']}")
    print(sep)
    print(f"  Repo      : {report['repo']}")
    print(f"  Config OK : {tick}")
    print(f"  Notified  : {report['total_notified']} release(s)")
    if report["last_notified_tag"]:
        print(f"  Last tag  : {report['last_notified_tag']}  ({report['last_notified_age']})")
    else:
        print("  Last tag  : (none yet)")
    if report["recent_tags"]:
        print(f"  Recent    : {', '.join(report['recent_tags'])}")
    retries = report["pending_retries"]
    if retries:
        print(f"  Retries   : {len(retries)} pending")
        for r in retries:
            print(f"    • {r['tag']}  attempts={r['attempts']}  err={r['last_error'][:60]}")
    else:
        print("  Retries   : none")
    print(sep)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print a summary report of release-notification activity."
    )
    parser.add_argument(
        "--config", metavar="PATH",
        help="Path to config.json (default: auto-detect)",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output raw JSON instead of formatted text",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        config = load_config(args.config)
    except ConfigError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)

    state = load_state()
    failed = load_failed_log()

    report = build_report(config, state, failed)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_report(report)


if __name__ == "__main__":
    main()
