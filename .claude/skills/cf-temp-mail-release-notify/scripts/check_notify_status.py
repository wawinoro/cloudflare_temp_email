#!/usr/bin/env python3
"""
check_notify_status.py - Verify notification delivery status and history.

Checks whether a given release version has already been notified,
and optionally writes/reads a simple JSON state file to prevent
duplicate Telegram notifications.

Usage:
    python check_notify_status.py --version v1.2.3
    python check_notify_status.py --version v1.2.3 --mark-sent
    python check_notify_status.py --list
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Default state file location (relative to this script)
DEFAULT_STATE_FILE = Path(__file__).parent.parent / ".notify_state.json"


def load_state(state_file: Path) -> dict:
    """Load notification state from JSON file."""
    if not state_file.exists():
        return {"notified": {}}
    try:
        with open(state_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "notified" not in data:
            data["notified"] = {}
        return data
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[WARN] Could not read state file {state_file}: {exc}", file=sys.stderr)
        return {"notified": {}}


def save_state(state: dict, state_file: Path) -> None:
    """Persist notification state to JSON file."""
    state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)
        f.write("\n")


def is_notified(version: str, state: dict) -> bool:
    """Return True if this version was already marked as notified."""
    return version in state.get("notified", {})


def mark_as_sent(version: str, state: dict, extra: dict | None = None) -> dict:
    """Record that a notification was sent for the given version."""
    entry = {
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        entry.update(extra)
    state["notified"][version] = entry
    return state


def list_notified(state: dict) -> None:
    """Print all versions that have been notified."""
    notified = state.get("notified", {})
    if not notified:
        print("No notifications recorded yet.")
        return

    print(f"{'Version':<20} {'Sent At':<30} {'Notes'}")
    print("-" * 70)
    for version, info in sorted(notified.items(), key=lambda x: x[1].get("sent_at", "")):
        sent_at = info.get("sent_at", "unknown")
        notes = info.get("notes", "")
        print(f"{version:<20} {sent_at:<30} {notes}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check or update Telegram notification status for releases."
    )
    parser.add_argument(
        "--version",
        help="Release version tag to check or mark (e.g. v1.2.3)",
    )
    parser.add_argument(
        "--mark-sent",
        action="store_true",
        help="Mark the given version as notified in the state file",
    )
    parser.add_argument(
        "--notes",
        default="",
        help="Optional notes to store alongside the sent record",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all recorded notifications",
    )
    parser.add_argument(
        "--state-file",
        default=str(DEFAULT_STATE_FILE),
        help=f"Path to state JSON file (default: {DEFAULT_STATE_FILE})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    state_file = Path(args.state_file)
    state = load_state(state_file)

    if args.list:
        list_notified(state)
        return

    if not args.version:
        print("[ERROR] --version is required unless --list is specified.", file=sys.stderr)
        sys.exit(1)

    version = args.version.strip()

    if args.mark_sent:
        extra = {"notes": args.notes} if args.notes else None
        state = mark_as_sent(version, state, extra)
        save_state(state, state_file)
        print(f"[OK] Marked {version} as notified in {state_file}")
        return

    # Default action: check status
    if is_notified(version, state):
        info = state["notified"][version]
        print(f"[ALREADY SENT] {version} was notified at {info.get('sent_at', 'unknown')}")
        sys.exit(0)
    else:
        print(f"[NOT SENT] {version} has not been notified yet")
        sys.exit(2)  # Exit code 2 = not yet sent (useful in shell scripts)


if __name__ == "__main__":
    main()
