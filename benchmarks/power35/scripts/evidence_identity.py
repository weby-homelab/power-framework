"""Build content-free release/source identity for Phase 8 technical receipts."""

from __future__ import annotations

import hashlib
import subprocess
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]


def _git(*args: str) -> str:
    result = subprocess.run(  # noqa: S603 -- fixed local Git query.
        ["git", "-C", str(REPO_ROOT), *args],  # noqa: S607 -- fixed executable name.
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout.strip()


def _worktree_sha256() -> str:
    """Hash tracked and untracked release-source changes without leaking content."""
    digest = hashlib.sha256()
    diff = subprocess.run(  # noqa: S603 -- fixed local Git query.
        ["git", "-C", str(REPO_ROOT), "diff", "--binary", "HEAD", "--"],  # noqa: S607
        capture_output=True,
        check=True,
    ).stdout
    digest.update(diff)
    names = subprocess.run(  # noqa: S603 -- fixed local Git query.
        ["git", "-C", str(REPO_ROOT), "ls-files", "--others", "--exclude-standard", "-z"],  # noqa: S607
        capture_output=True,
        check=True,
    ).stdout.split(b"\0")
    for raw_name in sorted(name for name in names if name):
        name = raw_name.decode("utf-8")
        path = REPO_ROOT / name
        if not path.is_file() or path.is_symlink():
            continue
        digest.update(raw_name)
        digest.update(b"\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def technical_evidence_identity() -> dict[str, Any]:
    """Return the release and exact content-free checkout identity."""
    commit = _git("rev-parse", "--verify", "HEAD")
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        release = str(tomllib.load(handle)["project"]["version"])
    return {
        "release": release,
        "source": {
            "commit": commit,
            "tree": _git("show", "-s", "--format=%T", commit),
            "clean": not bool(_git("status", "--porcelain")),
            "worktree_sha256": _worktree_sha256(),
        },
    }


__all__ = ["technical_evidence_identity"]
