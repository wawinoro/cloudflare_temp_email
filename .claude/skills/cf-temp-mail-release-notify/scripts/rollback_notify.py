#!/usr/bin/env python3
"""
rollback_notify.py — Remove a release tag from the notified state file,
allowing it to be re-sent on the next auto_notify / schedule_notify run.

Usage:
    python rollback_notify.py <tag>          # rollback a specific tag
    python rollback_notify.py --list         # list all notified tags
    python rollback_notify.py --all          # clear entire state file
"""

import argparse
import json
import sys
from pathlib import Path

# Re-use the shared state helpers from check_notify_status
from check_notify_status import load_state, save_state, list_notified

DEFAULT_STATE_FILE = Path(__file__).parent.parent / "state" / "notified.json"


def rollback_tag(tag: str, state_file: Path) -> bool:
    """
    Remove *tag* from the notified state.

    Returns True if the tag was present and removed, False if it was not found.
    """
    state = load_state(state_file)
    notified: list = state.get("notified", [])

    if tag not in notified:
        return False

    notified.remove(tag)
    state["notified"] = notified
    save_state(state_file, state)
    return True


def rollback_all(state_file: Path) -> int:
    """
    Clear all notified tags from the state file.

    Returns the number of tags that were removed.
    """
    state = load_state(state_file)
    count = len(state.get("notified", []))
    state["notified"] = []
    save_state(state_file, state)
    return count


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rollback Telegram notification state for one or all release tags."
    )
    parser.add_argument(
        "tag",
        nargs="?",
        help="Release tag to roll back (e.g. v1.2.3). Omit when using --list or --all.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all tags currently marked as notified and exit.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Remove ALL tags from the notified state (full reset).",
    )
    parser.add_argument(
        "--state-file",
        default=str(DEFAULT_STATE_FILE),
        help=f"Path to the JSON state file (default: {DEFAULT_STATE_FILE}).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    state_file = Path(args.state_file)

    # --list: print current state and exit
    if args.list:
        tags = list_notified(state_file)
        if not tags:
            print("No tags have been marked as notified yet.")
        else:
            print(f"Notified tags ({len(tags)}):")
            for t in tags:
                print(f"  • {t}")
        sys.exit(0)

    # --all: wipe everything
    if args.all:
        removed = rollback_all(state_file)
        print(f"Cleared {removed} tag(s) from {state_file}.")
        sys.exit(0)

    # Single tag rollback
    if not args.tag:
        print(
            "Error: provide a tag to roll back, or use --list / --all.",
            file=sys.stderr,
        )
        sys.exit(1)

    tag = args.tag.strip()
    removed = rollback_tag(tag, state_file)
    if removed:
        print(f"Tag '{tag}' has been removed from the notified state.")
        print("It will be re-sent on the next notification run.")
    else:
        print(
            f"Tag '{tag}' was not found in the notified state — nothing to roll back.",
            file=sys.stderr,
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
