#!/usr/bin/env bash
# create_release.sh — Automates GitHub release creation for cloudflare_temp_email
# Usage: ./create_release.sh <version> [--dry-run]
#
# Prerequisites:
#   - gh (GitHub CLI) authenticated
#   - git with a clean working tree on main/master
#   - CHANGELOG.md or release notes in references/release-template.md

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REFERENCES_DIR="${SCRIPT_DIR}/../references"
RELEASE_TEMPLATE="${REFERENCES_DIR}/release-template.md"

# ── helpers ──────────────────────────────────────────────────────────────────

die() {
  echo "[ERROR] $*" >&2
  exit 1
}

info() {
  echo "[INFO]  $*"
}

usage() {
  echo "Usage: $(basename "$0") <version> [--dry-run]"
  echo "  version   Semver tag, e.g. v1.2.3"
  echo "  --dry-run Print actions without executing them"
  exit 1
}

# ── argument parsing ──────────────────────────────────────────────────────────

[[ $# -lt 1 ]] && usage

VERSION="$1"
DRY_RUN=false

if [[ "${2:-}" == "--dry-run" ]]; then
  DRY_RUN=true
fi

# Validate semver-ish format (vX.Y.Z)
if ! [[ "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  die "Version '${VERSION}' does not match vX.Y.Z format."
fi

# ── preflight checks ──────────────────────────────────────────────────────────

command -v gh  >/dev/null 2>&1 || die "GitHub CLI (gh) is not installed."
command -v git >/dev/null 2>&1 || die "git is not installed."

# Ensure we are on main or master
CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$CURRENT_BRANCH" != "main" && "$CURRENT_BRANCH" != "master" ]]; then
  die "Releases must be cut from 'main' or 'master'. Current branch: ${CURRENT_BRANCH}"
fi

# Ensure working tree is clean
if ! git diff --quiet || ! git diff --cached --quiet; then
  die "Working tree is dirty. Commit or stash changes before releasing."
fi

# Check tag does not already exist
if git tag --list | grep -qx "$VERSION"; then
  die "Tag ${VERSION} already exists locally."
fi

# ── build release notes ───────────────────────────────────────────────────────

NOTES_FILE="$(mktemp /tmp/release-notes-XXXXXX.md)"
trap 'rm -f "$NOTES_FILE"' EXIT

if [[ -f "$RELEASE_TEMPLATE" ]]; then
  # Replace {{version}} placeholder in template
  sed "s/{{version}}/${VERSION}/g" "$RELEASE_TEMPLATE" > "$NOTES_FILE"
  info "Release notes generated from template: ${RELEASE_TEMPLATE}"
else
  # Fallback: auto-generate from git log since last tag
  PREV_TAG="$(git describe --tags --abbrev=0 2>/dev/null || echo '')"
  if [[ -n "$PREV_TAG" ]]; then
    info "Generating release notes from git log since ${PREV_TAG}"
    {
      echo "## What's Changed"
      echo ""
      git log "${PREV_TAG}..HEAD" --pretty=format:'- %s (%h)' --no-merges
      echo ""
    } > "$NOTES_FILE"
  else
    echo "Initial release ${VERSION}" > "$NOTES_FILE"
  fi
fi

info "Release notes preview:"
echo "────────────────────────────────────────"
cat "$NOTES_FILE"
echo "────────────────────────────────────────"

# ── create tag & GitHub release ───────────────────────────────────────────────

if $DRY_RUN; then
  info "[DRY RUN] Would create git tag: ${VERSION}"
  info "[DRY RUN] Would push tag to origin"
  info "[DRY RUN] Would create GitHub release: ${VERSION}"
else
  info "Creating git tag ${VERSION} ..."
  git tag -a "$VERSION" -m "Release ${VERSION}"

  info "Pushing tag to origin ..."
  git push origin "$VERSION"

  info "Creating GitHub release ..."
  gh release create "$VERSION" \
    --title "${VERSION}" \
    --notes-file "$NOTES_FILE" \
    --verify-tag

  info "Release ${VERSION} created successfully."
  info "View it at: $(gh release view "$VERSION" --json url -q .url)"
fi
