#!/usr/bin/env python3
"""List GitHub releases for cloudflare_temp_email with optional filtering.

Usage:
    python list_releases.py [--limit N] [--format text|json|table] [--pre-release]
"""

import argparse
import json
import sys
from datetime import datetime, timezone

try:
    from unified_config import load_config, github_headers
except ImportError:
    from scripts.unified_config import load_config, github_headers

try:
    import requests
except ImportError:
    print("ERROR: 'requests' library not found. Run: pip install requests", file=sys.stderr)
    sys.exit(1)


def fetch_releases(repo: str, headers: dict, limit: int = 10, include_prerelease: bool = False) -> list:
    """Fetch releases from GitHub API.

    Args:
        repo: GitHub repo in 'owner/name' format.
        headers: HTTP headers (auth, accept, etc.).
        limit: Maximum number of releases to return.
        include_prerelease: Whether to include pre-release entries.

    Returns:
        List of release dicts.
    """
    url = f"https://api.github.com/repos/{repo}/releases"
    params = {"per_page": min(limit, 100)}
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    releases = resp.json()

    if not include_prerelease:
        releases = [r for r in releases if not r.get("prerelease", False)]

    return releases[:limit]


def _age_label(published_at: str) -> str:
    """Return a human-readable age string for a release timestamp."""
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        delta = datetime.now(timezone.utc) - dt
        days = delta.days
        if days == 0:
            return "today"
        if days == 1:
            return "1 day ago"
        if days < 30:
            return f"{days} days ago"
        months = days // 30
        return f"{months} month{'s' if months > 1 else ''} ago"
    except Exception:
        return published_at


def format_text(releases: list) -> str:
    """Format releases as plain text lines."""
    lines = []
    for r in releases:
        tag = r.get("tag_name", "?")
        name = r.get("name") or tag
        published = r.get("published_at", "")
        age = _age_label(published)
        pre = " [pre-release]" if r.get("prerelease") else ""
        lines.append(f"{tag}  {name}  ({age}){pre}")
    return "\n".join(lines)


def format_table(releases: list) -> str:
    """Format releases as an ASCII table."""
    headers_row = ["Tag", "Name", "Published", "Pre-release"]
    rows = []
    for r in releases:
        tag = r.get("tag_name", "")
        name = (r.get("name") or tag)[:40]
        published = r.get("published_at", "")[:10]
        pre = "yes" if r.get("prerelease") else "no"
        rows.append([tag, name, published, pre])

    col_widths = [len(h) for h in headers_row]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(cell))

    def fmt_row(cells):
        return "  ".join(c.ljust(col_widths[i]) for i, c in enumerate(cells))

    separator = "  ".join("-" * w for w in col_widths)
    lines = [fmt_row(headers_row), separator]
    for row in rows:
        lines.append(fmt_row(row))
    return "\n".join(lines)


def format_json(releases: list) -> str:
    """Format releases as compact JSON."""
    simplified = [
        {
            "tag": r.get("tag_name"),
            "name": r.get("name"),
            "published_at": r.get("published_at"),
            "prerelease": r.get("prerelease", False),
            "url": r.get("html_url"),
        }
        for r in releases
    ]
    return json.dumps(simplified, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="List GitHub releases for cloudflare_temp_email."
    )
    parser.add_argument(
        "--limit", type=int, default=10, metavar="N",
        help="Number of releases to list (default: 10)"
    )
    parser.add_argument(
        "--format", choices=["text", "json", "table"], default="table",
        help="Output format (default: table)"
    )
    parser.add_argument(
        "--pre-release", action="store_true",
        help="Include pre-release versions"
    )
    parser.add_argument(
        "--config", metavar="FILE",
        help="Path to config JSON (auto-detected if omitted)"
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        cfg = load_config(args.config)
    except Exception as exc:
        print(f"ERROR loading config: {exc}", file=sys.stderr)
        sys.exit(1)

    repo = cfg.get("github_repo", "dreamhunter2333/cloudflare_temp_email")
    headers = github_headers(cfg)

    try:
        releases = fetch_releases(repo, headers, limit=args.limit, include_prerelease=args.pre_release)
    except Exception as exc:
        print(f"ERROR fetching releases: {exc}", file=sys.stderr)
        sys.exit(1)

    if not releases:
        print("No releases found.")
        return

    if args.format == "json":
        print(format_json(releases))
    elif args.format == "text":
        print(format_text(releases))
    else:
        print(format_table(releases))


if __name__ == "__main__":
    main()
