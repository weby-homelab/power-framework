"""One human-governed transactional memory workflow for all POWER surfaces."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .linter import run_lint_vault
from .mutation import execute_vault_mutation
from .searcher import SearchResult, search_vault
from .utils import atomic_write_in_vault, resolve_path_in_vault

if TYPE_CHECKING:
    from pathlib import Path


def get_context(vault_dir: Path, query: str, max_results: int = 5) -> list[SearchResult]:
    """Read context without creating a mutation or hidden proposal."""
    return search_vault(vault_dir, query, max_results=max_results, mode="fts")


def propose_change(vault_dir: Path, rel_path: str, content: str) -> dict[str, str]:
    """Create a content-addressed proposal; proposal alone never writes a note."""
    target = resolve_path_in_vault(vault_dir, rel_path)
    before = target.read_text(encoding="utf-8") if target.exists() else ""
    return {
        "path": rel_path,
        "before_sha256": hashlib.sha256(before.encode()).hexdigest(),
        "after_sha256": hashlib.sha256(content.encode()).hexdigest(),
        "content": content,
    }


def apply_change(vault_dir: Path, proposal: dict[str, str], approved: bool) -> dict[str, str]:
    """Apply only an explicit approval through POWER's shared mutation boundary."""
    if not approved:
        raise PermissionError("proposal requires explicit approved=True")
    rel_path = proposal["path"]
    content = proposal["content"]
    if hashlib.sha256(content.encode()).hexdigest() != proposal["after_sha256"]:
        raise ValueError("proposal content hash does not match")

    def mutate() -> dict[str, str]:
        target = resolve_path_in_vault(vault_dir, rel_path)
        before = target.read_text(encoding="utf-8") if target.exists() else ""
        if hashlib.sha256(before.encode()).hexdigest() != proposal["before_sha256"]:
            raise RuntimeError("proposal is stale; note changed after proposal")
        atomic_write_in_vault(vault_dir, rel_path, content)
        receipt = {
            "path": rel_path,
            "after_sha256": proposal["after_sha256"],
            "at": datetime.now(UTC).isoformat(),
        }
        history = vault_dir / ".power" / "memory-history.jsonl"
        history.parent.mkdir(parents=True, exist_ok=True)
        with history.open("a", encoding="utf-8") as file:
            file.write(json.dumps(receipt, sort_keys=True) + "\n")
        return receipt

    return execute_vault_mutation(vault_dir, mutate)


def validate_state(vault_dir: Path) -> bool:
    """Return the actual vault health result after a transaction."""
    return not run_lint_vault(vault_dir).has_issues


def read_history(vault_dir: Path) -> list[dict[str, str]]:
    """Read append-only transaction receipts without exposing content."""
    history = vault_dir / ".power" / "memory-history.jsonl"
    if not history.exists():
        return []
    return [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines() if line]
