#!/usr/bin/env python3
"""diff_releases.py — Compare two GitHub releases and show what changed.

Usage:
    python diff_releases.py                        # latest vs previous
    python diff_releases.py --tag v1.2.0            # specific vs its predecessor
    python diff_releases.py --from v1.1.0 --to v1.2.0
    python diff_releases.py --format markdown
"""

import argparse
import sys
from typing import Optional

from unified_config import load_config, github_headers

try:
    import requests
except ImportError:
    sys.exit("requests is required: pip install requests")


# ---------------------------------------------------------------------------
# GitHub helpers
# ---------------------------------------------------------------------------

def fetch_release(repo: str, tag: str, headers: dict) -> dict:
    """Fetch a single release by tag name."""
    url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    r = requests.get(url, headers=headers, timeout=15)
    r.raise_for_status()
    return r.json()


def fetch_releases(repo: str, headers: dict, per_page: int = 10) -> list:
    """Fetch the most recent releases (sorted newest-first)."""
    url = f"https://api.github.com/repos/{repo}/releases"
    r = requests.get(url, headers=headers, params={"per_page": per_page}, timeout=15)
    r.raise_for_status()
    return r.json()


# ---------------------------------------------------------------------------
# Diff logic
# ---------------------------------------------------------------------------

def _body_lines(release: dict) -> list[str]:
    body = (release.get("body") or "").strip()
    return [ln.rstrip() for ln in body.splitlines()]


def diff_bodies(old_body: list[str], new_body: list[str]) -> dict:
    """Return added / removed / unchanged line counts."""
    old_set = set(old_body)
    new_set = set(new_body)
    added = [l for l in new_body if l not in old_set]
    removed = [l for l in old_body if l not in new_set]
    unchanged = [l for l in new_body if l in old_set]
    return {"added": added, "removed": removed, "unchanged": unchanged}


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_plain(from_rel: dict, to_rel: dict, diff: dict) -> str:
    lines = [
        f"Release diff: {from_rel['tag_name']}  →  {to_rel['tag_name']}",
        f"Published : {to_rel.get('published_at', 'unknown')}",
        "",
        f"  + {len(diff['added'])} lines added",
        f"  - {len(diff['removed'])} lines removed",
        f"  = {len(diff['unchanged'])} lines unchanged",
        "",
    ]
    if diff["added"]:
        lines.append("=== ADDED ===")
        lines.extend(f"  + {l}" for l in diff["added"] if l)
        lines.append("")
    if diff["removed"]:
        lines.append("=== REMOVED ===")
        lines.extend(f"  - {l}" for l in diff["removed"] if l)
        lines.append("")
    return "\n".join(lines)


def format_markdown(from_rel: dict, to_rel: dict, diff: dict) -> str:
    lines = [
        f"## Release diff: `{from_rel['tag_name']}` → `{to_rel['tag_name']}`",
        f"_Published: {to_rel.get('published_at', 'unknown')}_",
        "",
        f"| Added | Removed | Unchanged |",
        f"|------:|--------:|----------:|",
        f"| {len(diff['added'])} | {len(diff['removed'])} | {len(diff['unchanged'])} |",
        "",
    ]
    if diff["added"]:
        lines.append("### ➕ Added")
        lines.extend(f"- {l}" for l in diff["added"] if l)
        lines.append("")
    if diff["removed"]:
        lines.append("### ➖ Removed")
        lines.extend(f"- {l}" for l in diff["removed"] if l)
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Diff two GitHub releases.")
    p.add_argument("--from", dest="from_tag", default=None,
                   help="Older release tag (default: second-latest)")
    p.add_argument("--to", dest="to_tag", default=None,
                   help="Newer release tag (default: latest)")
    p.add_argument("--tag", default=None,
                   help="Shorthand: diff this tag against its predecessor")
    p.add_argument("--format", choices=["plain", "markdown"], default="plain")
    p.add_argument("--config", default=None, help="Path to config.json")
    return p.parse_args()


def resolve_tags(
    args: argparse.Namespace,
    releases: list,
) -> tuple[Optional[str], Optional[str]]:
    """Determine (from_tag, to_tag) from CLI args and available releases."""
    if args.tag:
        tags = [r["tag_name"] for r in releases]
        if args.tag not in tags:
            sys.exit(f"Tag '{args.tag}' not found in recent releases.")
        idx = tags.index(args.tag)
        if idx + 1 >= len(tags):
            sys.exit(f"No predecessor found for '{args.tag}' in fetched releases.")
        return tags[idx + 1], args.tag
    to_tag = args.to_tag or (releases[0]["tag_name"] if releases else None)
    from_tag = args.from_tag or (releases[1]["tag_name"] if len(releases) > 1 else None)
    return from_tag, to_tag


def main() -> None:
    args = parse_args()
    cfg = load_config(args.config)
    repo = cfg["github_repo"]
    headers = github_headers(cfg)

    releases = fetch_releases(repo, headers, per_page=20)
    if not releases:
        sys.exit("No releases found.")

    from_tag, to_tag = resolve_tags(args, releases)
    if not from_tag or not to_tag:
        sys.exit("Could not determine release tags to compare.")

    from_rel = fetch_release(repo, from_tag, headers)
    to_rel = fetch_release(repo, to_tag, headers)

    diff = diff_bodies(_body_lines(from_rel), _body_lines(to_rel))

    if args.format == "markdown":
        print(format_markdown(from_rel, to_rel, diff))
    else:
        print(format_plain(from_rel, to_rel, diff))


if __name__ == "__main__":
    main()
