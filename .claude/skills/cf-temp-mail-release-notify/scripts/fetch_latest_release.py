#!/usr/bin/env python3
"""
fetch_latest_release.py — Fetch the latest GitHub release info for cloudflare_temp_email.

Usage:
    python fetch_latest_release.py [--config config.json] [--output json|text]

Outputs release metadata to stdout in JSON or human-readable text format.
Useful for piping into send_release_to_telegram.py or other notification scripts.
"""

import argparse
import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# Default GitHub repo to query
DEFAULT_REPO = "dreamhunter2333/cloudflare_temp_email"
GITHUB_API_BASE = "https://api.github.com"


def load_config(config_path: str) -> dict:
    """Load configuration from a JSON file, returning an empty dict on failure."""
    path = Path(config_path)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"[warn] Could not load config '{config_path}': {exc}", file=sys.stderr)
        return {}


def fetch_latest_release(repo: str, token: str | None = None) -> dict:
    """
    Fetch the latest release from the GitHub Releases API.

    Args:
        repo:  GitHub repository in 'owner/name' format.
        token: Optional GitHub personal access token for higher rate limits.

    Returns:
        Parsed JSON dict from the GitHub API response.

    Raises:
        SystemExit on HTTP or network errors.
    """
    url = f"{GITHUB_API_BASE}/repos/{repo}/releases/latest"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "cf-temp-mail-release-notify/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        print(f"[error] GitHub API returned HTTP {exc.code}: {exc.reason}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as exc:
        print(f"[error] Network error while contacting GitHub: {exc.reason}", file=sys.stderr)
        sys.exit(1)


def parse_release(data: dict) -> dict:
    """
    Extract the fields we care about from a raw GitHub release payload.

    Returns a normalised dict with consistent keys used by downstream scripts.
    """
    published_raw = data.get("published_at") or data.get("created_at", "")
    try:
        published_dt = datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
        published_iso = published_dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except (ValueError, AttributeError):
        published_iso = published_raw

    assets = [
        {
            "name": a["name"],
            "size": a["size"],
            "download_url": a["browser_download_url"],
            "download_count": a["download_count"],
        }
        for a in data.get("assets", [])
    ]

    return {
        "tag": data.get("tag_name", ""),
        "name": data.get("name") or data.get("tag_name", ""),
        "url": data.get("html_url", ""),
        "author": data.get("author", {}).get("login", "unknown"),
        "published_at": published_iso,
        "prerelease": data.get("prerelease", False),
        "draft": data.get("draft", False),
        "body": (data.get("body") or "").strip(),
        "assets": assets,
    }


def format_text(release: dict) -> str:
    """Render a release dict as a human-readable text summary."""
    lines = [
        f"Release : {release['name']} ({release['tag']})",
        f"Author  : {release['author']}",
        f"Date    : {release['published_at']}",
        f"URL     : {release['url']}",
    ]
    if release["prerelease"]:
        lines.append("Status  : PRE-RELEASE")
    if release["draft"]:
        lines.append("Status  : DRAFT")
    if release["body"]:
        lines.append("")
        lines.append("--- Release Notes ---")
        lines.append(release["body"])
    if release["assets"]:
        lines.append("")
        lines.append("--- Assets ---")
        for asset in release["assets"]:
            size_kb = asset["size"] // 1024
            lines.append(f"  {asset['name']}  ({size_kb} KB, {asset['download_count']} downloads)")
            lines.append(f"  → {asset['download_url']}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch the latest GitHub release for cloudflare_temp_email."
    )
    parser.add_argument(
        "--config",
        default="config.json",
        help="Path to config.json (default: config.json)",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help=f"GitHub repo in owner/name format (default: {DEFAULT_REPO})",
    )
    parser.add_argument(
        "--output",
        choices=["json", "text"],
        default="json",
        help="Output format: json (default) or text",
    )
    args = parser.parse_args()

    config = load_config(args.config)
    repo = args.repo or config.get("github_repo", DEFAULT_REPO)
    token = config.get("github_token")  # optional; avoids rate-limiting

    raw = fetch_latest_release(repo, token)
    release = parse_release(raw)

    if args.output == "text":
        print(format_text(release))
    else:
        print(json.dumps(release, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
