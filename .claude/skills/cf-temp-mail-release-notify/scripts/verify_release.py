#!/usr/bin/env python3
"""
verify_release.py - Verify that a GitHub release was successfully published
and matches expected metadata before sending notifications.

Usage:
    python verify_release.py --tag v1.2.3
    python verify_release.py --tag v1.2.3 --config config.json
    python verify_release.py --latest
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library not found. Run: pip install requests")
    sys.exit(1)


DEFAULT_CONFIG = Path(__file__).parent.parent / "config.json"
GITHUB_API_BASE = "https://api.github.com"


def load_config(config_path: str = None) -> dict:
    """Load configuration from JSON file."""
    path = Path(config_path) if config_path else DEFAULT_CONFIG
    if not path.exists():
        example = path.parent / "config.example.json"
        print(f"ERROR: Config not found at {path}")
        if example.exists():
            print(f"  Copy {example} to {path} and fill in your values.")
        sys.exit(1)
    with open(path) as f:
        return json.load(f)


def fetch_release(repo: str, tag: str = None, token: str = None) -> dict:
    """
    Fetch a specific release by tag, or the latest release if tag is None.
    Returns the release data dict from GitHub API.
    """
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    if tag:
        url = f"{GITHUB_API_BASE}/repos/{repo}/releases/tags/{tag}"
    else:
        url = f"{GITHUB_API_BASE}/repos/{repo}/releases/latest"

    resp = requests.get(url, headers=headers, timeout=15)
    if resp.status_code == 404:
        label = tag if tag else "latest release"
        print(f"ERROR: Release '{label}' not found in {repo}")
        sys.exit(1)
    resp.raise_for_status()
    return resp.json()


def check_release_age(published_at: str, max_hours: int = 48) -> tuple[bool, float]:
    """Return (is_recent, age_hours) for a release publish timestamp."""
    dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    age_hours = (now - dt).total_seconds() / 3600
    return age_hours <= max_hours, age_hours


def verify_release(release: dict, expected_tag: str = None) -> list[str]:
    """
    Run a series of checks on the release dict.
    Returns a list of warning/error strings (empty = all good).
    """
    issues = []

    # Tag check
    actual_tag = release.get("tag_name", "")
    if expected_tag and actual_tag != expected_tag:
        issues.append(f"Tag mismatch: expected '{expected_tag}', got '{actual_tag}'")

    # Draft / prerelease flags
    if release.get("draft"):
        issues.append("Release is still a DRAFT — not publicly visible")
    if release.get("prerelease"):
        issues.append("Release is marked as PRE-RELEASE")

    # Body / changelog
    body = (release.get("body") or "").strip()
    if not body:
        issues.append("Release body/changelog is empty")
    elif len(body) < 30:
        issues.append(f"Release body is very short ({len(body)} chars) — may be incomplete")

    # Age
    published_at = release.get("published_at", "")
    if published_at:
        is_recent, age_hours = check_release_age(published_at)
        if not is_recent:
            issues.append(
                f"Release is {age_hours:.1f}h old — notification may be redundant"
            )
    else:
        issues.append("Release has no 'published_at' timestamp")

    return issues


def print_summary(release: dict, issues: list[str]) -> None:
    """Pretty-print verification results to stdout."""
    tag = release.get("tag_name", "unknown")
    name = release.get("name") or tag
    url = release.get("html_url", "")
    published_at = release.get("published_at", "N/A")

    print("\n" + "=" * 60)
    print(f"  Release: {name}  ({tag})")
    print(f"  URL    : {url}")
    print(f"  Published: {published_at}")
    print(f"  Draft  : {release.get('draft', False)}")
    print(f"  Pre-rel: {release.get('prerelease', False)}")
    print("=" * 60)

    if issues:
        print(f"\n⚠  {len(issues)} issue(s) found:")
        for i, msg in enumerate(issues, 1):
            print(f"   {i}. {msg}")
        print()
    else:
        print("\n✅  All checks passed — release looks good to notify.\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify a GitHub release before sending Telegram notifications."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--tag", help="Release tag to verify (e.g. v1.2.3)")
    group.add_argument("--latest", action="store_true", help="Verify the latest release")
    parser.add_argument("--config", help="Path to config.json (default: ../config.json)")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any issues are found",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_config(args.config)

    repo = config.get("github_repo")
    token = config.get("github_token") or os.environ.get("GITHUB_TOKEN")

    if not repo:
        print("ERROR: 'github_repo' missing from config (e.g. 'owner/repo')")
        sys.exit(1)

    tag = args.tag if not args.latest else None
    print(f"Fetching release from {repo} ...", end=" ", flush=True)
    release = fetch_release(repo, tag=tag, token=token)
    print("OK")

    issues = verify_release(release, expected_tag=tag)
    print_summary(release, issues)

    if args.strict and issues:
        sys.exit(1)


if __name__ == "__main__":
    main()
