#!/usr/bin/env python3
"""
schedule_notify.py - Run auto_notify on a schedule (cron-style loop).

Usage:
    python schedule_notify.py [--interval MINUTES] [--config CONFIG]

Runs the release notification check every N minutes (default: 60).
Useful when a real cron daemon is unavailable (e.g. inside a container).
"""

import argparse
import logging
import signal
import subprocess
import sys
import time
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger(__name__)

SCRIPTS_DIR = Path(__file__).parent
AUTO_NOTIFY = SCRIPTS_DIR / "auto_notify.py"

_shutdown = False


def _handle_signal(signum, _frame):
    """Gracefully stop the loop on SIGINT / SIGTERM."""
    global _shutdown
    log.info("Received signal %s — shutting down after current cycle.", signum)
    _shutdown = True


def run_once(config_path: str | None) -> int:
    """
    Invoke auto_notify.py as a subprocess and return its exit code.
    Inherits stdout/stderr so output is visible in the parent process.
    """
    cmd = [sys.executable, str(AUTO_NOTIFY)]
    if config_path:
        cmd += ["--config", config_path]

    log.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd)  # noqa: S603
    return result.returncode


def schedule_loop(interval_minutes: int, config_path: str | None) -> None:
    """Loop forever, calling run_once every *interval_minutes* minutes."""
    interval_seconds = interval_minutes * 60
    log.info(
        "Scheduler started — interval: %d min(s). Press Ctrl-C to stop.",
        interval_minutes,
    )

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    while not _shutdown:
        rc = run_once(config_path)
        if rc != 0:
            log.warning("auto_notify exited with code %d.", rc)
        else:
            log.info("auto_notify completed successfully.")

        # Sleep in short bursts so we can react to signals quickly.
        slept = 0
        while slept < interval_seconds and not _shutdown:
            time.sleep(5)
            slept += 5

    log.info("Scheduler stopped.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run auto_notify.py on a repeating schedule."
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=60,
        metavar="MINUTES",
        help="How often to check for new releases (default: 60 minutes).",
    )
    parser.add_argument(
        "--config",
        default=None,
        metavar="PATH",
        help="Path to config.json (forwarded to auto_notify.py).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single check and exit (useful for testing).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not AUTO_NOTIFY.exists():
        log.error("auto_notify.py not found at %s", AUTO_NOTIFY)
        sys.exit(1)

    if args.interval < 1:
        log.error("--interval must be at least 1 minute.")
        sys.exit(1)

    if args.once:
        rc = run_once(args.config)
        sys.exit(rc)

    schedule_loop(args.interval, args.config)


if __name__ == "__main__":
    main()
