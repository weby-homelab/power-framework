#!/usr/bin/env python3
"""Create a provenance receipt for a tagged POWER release and its artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _git(repo: Path, *args: str) -> str:
    """Return one successful read-only Git query."""
    result = subprocess.run(  # noqa: S603 -- fixed executable and read-only release queries.
        ["git", "-C", str(repo), *args],  # noqa: S607 -- fixed executable name.
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    """Hash one release asset in bounded memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset_receipt(path: Path) -> dict[str, Any]:
    """Return stable, path-safe metadata for one uploaded asset."""
    return {
        "name": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": _sha256(path),
    }


def build_receipt(
    *,
    repo: Path,
    tag: str,
    assets_dir: Path,
    repository: str,
    workflow_run_id: str,
) -> dict[str, Any]:
    """Build a receipt tied to the exact tag commit, tree and local artifacts."""
    commit = _git(repo, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
    tree = _git(repo, "show", "-s", "--format=%T", commit)
    assets = sorted(
        path
        for path in assets_dir.iterdir()
        if path.is_file()
        and path.name != "power-framework.release-receipt.json"
        and path.suffix in {".whl", ".gz", ".json"}
    )
    if not assets:
        raise ValueError(f"no release assets found in {assets_dir}")

    run_url = (
        f"https://github.com/{repository}/actions/runs/{workflow_run_id}"
        if repository and workflow_run_id
        else None
    )
    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "release": {
            "repository": repository,
            "tag": tag,
            "commit": commit,
            "tree": tree,
        },
        "workflow_run": {
            "id": workflow_run_id or None,
            "name": os.environ.get("GITHUB_WORKFLOW"),
            "attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
            "url": run_url,
        },
        "assets": [_asset_receipt(path) for path in assets],
    }


def main() -> int:
    """Parse release context and write one immutable JSON receipt."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--git-repo", type=Path, default=Path.cwd())
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--workflow-run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    args = parser.parse_args()

    receipt = build_receipt(
        repo=args.git_repo.resolve(),
        tag=args.tag,
        assets_dir=args.assets_dir.resolve(),
        repository=args.repository,
        workflow_run_id=args.workflow_run_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Release receipt written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
