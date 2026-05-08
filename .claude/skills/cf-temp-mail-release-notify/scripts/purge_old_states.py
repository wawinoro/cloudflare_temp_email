#!/usr/bin/env python3
"""
purge_old_states.py — Remove stale notification state entries.

Entries older than a configurable retention window (default 90 days) are
removed from the state file so it does not grow unbounded over time.

Usage:
    python purge_old_states.py [--dry-run] [--days 90] [--state PATH]
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
DEFAULT_STATE_FILE = Path(__file__).parent.parent / "state.json"
DEFAULT_RETENTION_DAYS = 90


# ---------------------------------------------------------------------------
# State helpers
# ---------------------------------------------------------------------------

def load_state(state_path: Path) -> dict:
    """Load the JSON state file, returning an empty dict if missing."""
    if not state_path.exists():
        return {}
    try:
        with state_path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[warn] Could not read state file {state_path}: {exc}", file=sys.stderr)
        return {}


def save_state(state_path: Path, state: dict) -> None:
    """Persist *state* back to *state_path* atomically."""
    tmp = state_path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    tmp.replace(state_path)


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------

def parse_timestamp(value: str) -> datetime | None:
    """Try to parse an ISO-8601 timestamp string; return None on failure."""
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def purge_old_states(
    state_path: Path,
    retention_days: int = DEFAULT_RETENTION_DAYS,
    dry_run: bool = False,
) -> tuple[int, int]:
    """
    Remove entries from the state file that are older than *retention_days*.

    Returns
    -------
    (kept, removed)  — counts of entries kept and removed.
    """
    state = load_state(state_path)
    if not state:
        print("[info] State file is empty or missing — nothing to purge.")
        return 0, 0

    cutoff = datetime.now(tz=timezone.utc) - timedelta(days=retention_days)
    kept: dict = {}
    removed: list[str] = []

    for tag, entry in state.items():
        # Each entry may be a dict with a 'sent_at' key, or a plain string.
        if isinstance(entry, dict):
            raw_ts = entry.get("sent_at") or entry.get("notified_at", "")
        else:
            raw_ts = str(entry)

        dt = parse_timestamp(raw_ts) if raw_ts else None

        if dt is None:
            # Cannot determine age — keep to be safe
            kept[tag] = entry
            continue

        if dt < cutoff:
            removed.append(tag)
        else:
            kept[tag] = entry

    if removed:
        print(f"[info] Entries to remove ({len(removed)}):")
        for tag in removed:
            print(f"  - {tag}")
    else:
        print("[info] No entries are old enough to purge.")

    if not dry_run and removed:
        save_state(state_path, kept)
        print(f"[ok] Purged {len(removed)} entr{'y' if len(removed) == 1 else 'ies'} "
              f"from {state_path}.")
    elif dry_run and removed:
        print("[dry-run] No changes written.")

    return len(kept), len(removed)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Purge old notification state entries.",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_RETENTION_DAYS,
        metavar="N",
        help=f"Retention window in days (default: {DEFAULT_RETENTION_DAYS}).",
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=DEFAULT_STATE_FILE,
        metavar="PATH",
        help="Path to the state JSON file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be removed without writing changes.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    kept, removed = purge_old_states(
        state_path=args.state,
        retention_days=args.days,
        dry_run=args.dry_run,
    )
    print(f"[summary] kept={kept}  removed={removed}")


if __name__ == "__main__":
    main()
