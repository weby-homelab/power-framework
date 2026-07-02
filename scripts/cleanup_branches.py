#!/usr/bin/env python3
"""
P.O.W.E.R. Branch Cleanup Script.

Automatically detects and deletes merged branches from GitHub.
Uses GitHub REST API with token from environment variable.

Environment variables:
    GITHUB_RELEASE_TOKEN - GitHub PAT with repo scope (required)
    GITHUB_OWNER         - Repository owner/organization (required)
    GITHUB_REPO          - Repository name (required)

Usage:
    python cleanup_branches.py
    python cleanup_branches.py --dry-run
    python cleanup_branches.py --owner weby-homelab --repo P.O.W.E.R
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

PROTECTED_BRANCHES = frozenset({"main", "master", "develop", "release"})

API_BASE = "https://api.github.com"


def get_token() -> str:
    """Get GitHub token from environment."""
    token = os.getenv("GITHUB_RELEASE_TOKEN") or os.getenv("GITHUB_TOKEN")
    if not token:
        print("ERROR: GITHUB_RELEASE_TOKEN or GITHUB_TOKEN environment variable is required.")
        sys.exit(1)
    return token.strip()


def api_request(
    url: str,
    token: str,
    method: str = "GET",
    data: dict | None = None,
) -> dict:
    """Make authenticated GitHub API request."""
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "P.O.W.E.R.-cleanup/1.3.0",
    }

    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"API Error {e.code}: {e.reason} for {url}")
        sys.exit(1)


def get_merged_prs(owner: str, repo: str, token: str) -> list[str]:
    """Get branch names from all merged/closed PRs."""
    merged_branches: list[str] = []
    page = 1

    while True:
        url = f"{API_BASE}/repos/{owner}/{repo}/pulls?state=closed&per_page=100&page={page}"
        prs = api_request(url, token)

        if not prs:
            break

        for pr in prs:
            if pr.get("merged_at") or pr.get("state") == "closed":
                head_ref = pr.get("head", {}).get("ref", "")
                if head_ref and head_ref not in PROTECTED_BRANCHES:
                    merged_branches.append(head_ref)

        page += 1

    return list(set(merged_branches))


def get_all_branches(owner: str, repo: str, token: str) -> list[str]:
    """Get all branch names from the repository."""
    branches: list[str] = []
    page = 1

    while True:
        url = f"{API_BASE}/repos/{owner}/{repo}/branches?per_page=100&page={page}"
        result = api_request(url, token)

        if not result:
            break

        for branch in result:
            name = branch.get("name", "")
            if name and name not in PROTECTED_BRANCHES:
                branches.append(name)

        page += 1

    return branches


def delete_branch(owner: str, repo: str, branch: str, token: str) -> bool:
    """Delete a branch from the remote repository."""
    url = f"{API_BASE}/repos/{owner}/{repo}/git/refs/heads/{branch}"
    try:
        api_request(url, token, method="DELETE")
        return True
    except SystemExit:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up merged branches from GitHub")
    parser.add_argument("--owner", default=os.getenv("GITHUB_OWNER", ""), help="Repository owner")
    parser.add_argument("--repo", default=os.getenv("GITHUB_REPO", ""), help="Repository name")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted")
    args = parser.parse_args()

    if not args.owner or not args.repo:
        print("ERROR: --owner and --repo are required (or set GITHUB_OWNER/GITHUB_REPO)")
        sys.exit(1)

    token = get_token()

    print(f"Scanning {args.owner}/{args.repo} for merged branches...")

    all_branches = get_all_branches(args.owner, args.repo, token)
    merged_prs = get_merged_prs(args.owner, args.repo, token)

    to_delete = [b for b in all_branches if b in merged_prs]

    if not to_delete:
        print("No merged branches to clean up.")
        return

    print(f"\nFound {len(to_delete)} branch(es) to delete:")
    for branch in sorted(to_delete):
        print(f"  - {branch}")

    if args.dry_run:
        print("\n[DRY RUN] No branches were actually deleted.")
        return

    print("\nDeleting branches...")
    deleted = 0
    for branch in to_delete:
        if delete_branch(args.owner, args.repo, branch, token):
            print(f"  Deleted: {branch}")
            deleted += 1
        else:
            print(f"  FAILED: {branch}")

    print(f"\nCleanup complete. Deleted {deleted}/{len(to_delete)} branches.")


if __name__ == "__main__":
    main()
