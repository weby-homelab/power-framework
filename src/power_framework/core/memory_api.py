"""One human-governed transactional memory workflow for all POWER surfaces."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from .constants import INDEX_FOLDERS, is_catalog_filename
from .indexer import run_generate_hierarchical_index
from .linter import run_lint_vault
from .models import PARA_FOLDERS
from .mutation import execute_vault_mutation
from .parser import validate_metadata
from .searcher import SearchResult, search_vault
from .utils import atomic_write, atomic_write_in_vault, resolve_path_in_vault
from .vault_storage import existing_vault_cache_dir

if TYPE_CHECKING:
    from pathlib import Path


@dataclass(frozen=True)
class _FileSnapshot:
    """Exact text pre-image for one file touched by the closed transaction."""

    path: Path
    existed: bool
    content: str = ""


def get_context(vault_dir: Path, query: str, max_results: int = 5) -> list[SearchResult]:
    """Read context without creating a mutation or hidden proposal."""
    return search_vault(vault_dir, query, max_results=max_results, mode="fts")


def propose_change(vault_dir: Path, rel_path: str, content: str) -> dict[str, str]:
    """Persist a content-addressed proposal without writing the target note."""
    if not isinstance(rel_path, str) or not isinstance(content, str):
        raise ValueError("proposal path and content must be strings")
    target = resolve_path_in_vault(vault_dir, rel_path, allowed_directories=PARA_FOLDERS)
    if validate_metadata(content) is None:
        raise ValueError("proposal content has invalid or missing OKF metadata")

    def persist() -> dict[str, str]:
        before = target.read_text(encoding="utf-8") if target.exists() else ""
        payload = {
            "path": rel_path,
            "before_sha256": hashlib.sha256(before.encode("utf-8")).hexdigest(),
            "after_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "content": content,
        }
        proposal_id = _proposal_id(payload)
        proposal_path = _proposal_path(vault_dir, proposal_id)
        if proposal_path.exists():
            existing = _read_proposal_file(proposal_path)
            if _proposal_payload(existing) != payload:
                raise RuntimeError("content-addressed proposal collision detected")
            return _public_proposal(existing)

        record = {
            **payload,
            "proposal_id": proposal_id,
            "schema_version": 1,
            "created_at": datetime.now(UTC).isoformat(),
        }
        proposal_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(proposal_path, json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return _public_proposal(record)

    return execute_vault_mutation(vault_dir, persist)


def commit_note_change(
    vault_dir: Path,
    rel_path: str,
    content: str,
    *,
    expected_before_sha256: str | None = None,
    require_absent: bool = False,
    allowed_directories: tuple[str, ...] | None = None,
    operation: str = "memory.apply",
    log_entry: str | None = None,
    proposal_id: str | None = None,
) -> dict[str, str]:
    """Commit one note through the shared write → verify → publish workflow."""

    def mutate() -> dict[str, str]:
        target = resolve_path_in_vault(vault_dir, rel_path, allowed_directories)
        target_snapshot = _capture_file(target)
        before = target_snapshot.content if target_snapshot.existed else ""
        before_sha256 = hashlib.sha256(before.encode()).hexdigest()
        if require_absent and target_snapshot.existed:
            raise FileExistsError(f"Note already exists at {rel_path}")
        if expected_before_sha256 is not None and before_sha256 != expected_before_sha256:
            raise RuntimeError("proposal is stale; note changed after proposal")

        # Validate before the first write.  This prevents an approved but
        # malformed proposal from entering the vault and disappearing from the
        # next index/sync pass.
        if validate_metadata(content) is None:
            raise ValueError("proposal content has invalid or missing OKF metadata")

        snapshots = _capture_projection_snapshot(vault_dir)
        history = vault_dir / ".power" / "memory-history.jsonl"
        history_snapshot = _capture_file(history)
        log_file = vault_dir / "log.md"
        log_snapshot = _capture_file(log_file)
        published_search = False
        has_dense = False
        receipt = {
            "operation": operation,
            "path": rel_path,
            "before_sha256": before_sha256,
            "after_sha256": hashlib.sha256(content.encode()).hexdigest(),
            "at": datetime.now(UTC).isoformat(),
        }
        if proposal_id is not None:
            receipt["proposal_id"] = proposal_id

        try:
            atomic_write_in_vault(
                vault_dir,
                rel_path,
                content,
                allowed_directories=allowed_directories,
            )
            if log_entry is not None and log_file.exists():
                _append_text(log_file, log_entry)
            index_summary = run_generate_hierarchical_index(vault_dir)
            lint_result = run_lint_vault(vault_dir)
            if lint_result.has_blocking_issues:
                raise RuntimeError(
                    "post-mutation lint failed: "
                    f"metadata={len(lint_result.untyped_files)}, "
                    f"broken_links={len(lint_result.broken_links)}, "
                    f"ambiguous_links={len(lint_result.ambiguous_links)}, "
                    f"stale={len(lint_result.stale_notes)}"
                )

            # Keep a dense projection usable when one already exists.  A new
            # vault without dense state gets a cheap FTS publication and can
            # later opt into the full embedding sync explicitly.
            from .generation_index import active_dense_chunk_count, sync_vault_atomically

            has_dense = active_dense_chunk_count(vault_dir) > 0
            report = sync_vault_atomically(
                vault_dir,
                sync_embeddings=has_dense,
                allow_partial=False,
            )
            published_search = True
            receipt.update(
                {
                    "index_summary": index_summary,
                    "search_mode": "semantic" if has_dense else "fts",
                    "search_generation": report.generation_id,
                    "notes_scanned": str(report.total_scanned),
                    "notes_indexed": str(report.actual_files),
                    "notes_excluded": str(report.invalid_sources),
                    "lint_orphans": str(len(lint_result.orphans)),
                }
            )
            _append_receipt(history, receipt)
            return receipt
        except Exception:
            source_restore_error: Exception | None = None
            projection_restore_error: Exception | None = None
            try:
                _restore_file_snapshot(target, target_snapshot)
            except Exception as rollback_error:
                source_restore_error = rollback_error
            try:
                _restore_projection_snapshot(vault_dir, snapshots)
                _restore_file_snapshot(history, history_snapshot)
                _restore_file_snapshot(log_file, log_snapshot)
            except Exception as rollback_error:
                projection_restore_error = rollback_error
            search_restore_error: Exception | None = None
            if published_search and source_restore_error is None:
                try:
                    # Search generations are immutable.  If a later receipt
                    # write fails after publication, rebuild against the
                    # restored source so the active generation cannot retain
                    # a note that the transaction rolled back.
                    sync_vault_atomically(
                        vault_dir,
                        sync_embeddings=has_dense,
                        allow_partial=False,
                    )
                except Exception as rollback_error:
                    search_restore_error = rollback_error
            if source_restore_error is not None:
                raise RuntimeError("memory mutation rollback failed for the note") from (
                    source_restore_error
                )
            if projection_restore_error is not None:
                raise RuntimeError("memory mutation rollback failed for projections") from (
                    projection_restore_error
                )
            if search_restore_error is not None:
                raise RuntimeError(
                    "memory mutation rollback failed to restore search projection"
                ) from search_restore_error
            raise

    return execute_vault_mutation(vault_dir, mutate)


def apply_change(vault_dir: Path, proposal: dict[str, str], approved: bool) -> dict[str, str]:
    """Apply an approved proposal through the shared mutation boundary."""
    if not approved:
        raise PermissionError("proposal requires explicit approved=True")
    if not isinstance(proposal, dict):
        raise ValueError("proposal must be an object")
    values: dict[str, str] = {}
    for field in ("path", "content", "before_sha256", "after_sha256", "proposal_id"):
        value = proposal.get(field)
        if not isinstance(value, str):
            raise ValueError(f"proposal field '{field}' must be a string")
        values[field] = value
    rel_path = values["path"]
    content = values["content"]
    before_sha256 = values["before_sha256"]
    after_sha256 = values["after_sha256"]
    proposal_id = values["proposal_id"]
    for field, digest in (("before_sha256", before_sha256), ("after_sha256", after_sha256)):
        if not _is_sha256(digest):
            raise ValueError(f"proposal field '{field}' must be a SHA-256 hex digest")
    if not _is_sha256(proposal_id):
        raise ValueError("proposal field 'proposal_id' must be a SHA-256 hex digest")
    if hashlib.sha256(content.encode()).hexdigest() != after_sha256:
        raise ValueError("proposal content hash does not match")
    payload = {
        "path": rel_path,
        "before_sha256": before_sha256,
        "after_sha256": after_sha256,
        "content": content,
    }
    if _proposal_id(payload) != proposal_id:
        raise ValueError("proposal id does not match its content-addressed payload")
    stored = _read_proposal_file(_proposal_path(vault_dir, proposal_id))
    if _proposal_payload(stored) != payload:
        raise ValueError("proposal does not match its durable record")
    return commit_note_change(
        vault_dir,
        rel_path,
        content,
        expected_before_sha256=before_sha256,
        allowed_directories=PARA_FOLDERS,
        operation="memory.apply",
        proposal_id=proposal_id,
    )


def _is_sha256(value: str) -> bool:
    """Return whether a value is a lowercase SHA-256 hex digest."""
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _proposal_payload(proposal: dict[str, object]) -> dict[str, str]:
    """Extract and type-check the content-addressed proposal payload."""
    payload: dict[str, str] = {}
    for field in ("path", "content", "before_sha256", "after_sha256"):
        value = proposal.get(field)
        if not isinstance(value, str):
            raise ValueError(f"durable proposal field '{field}' must be a string")
        payload[field] = value
    return payload


def _proposal_id(payload: dict[str, str]) -> str:
    """Derive a stable ID from the complete proposal payload."""
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _proposal_path(vault_dir: Path, proposal_id: str) -> Path:
    """Return the safe durable path for a validated proposal ID."""
    return vault_dir / ".power" / "proposals" / f"{proposal_id}.json"


def _read_proposal_file(path: Path) -> dict[str, object]:
    """Read one durable proposal and reject malformed state."""
    if not path.is_file():
        raise ValueError("proposal is not durable; call propose_memory_change first")
    try:
        proposal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("durable proposal is unreadable") from exc
    if not isinstance(proposal, dict):
        raise ValueError("durable proposal must be an object")
    payload = _proposal_payload(proposal)
    stored_id = proposal.get("proposal_id")
    if not isinstance(stored_id, str) or not _is_sha256(stored_id):
        raise ValueError("durable proposal has an invalid proposal_id")
    if _proposal_id(payload) != stored_id:
        raise ValueError("durable proposal content address does not match")
    return proposal


def _public_proposal(proposal: dict[str, object]) -> dict[str, str]:
    """Return the proposal fields accepted by CLI and MCP clients."""
    payload = _proposal_payload(proposal)
    proposal_id = proposal.get("proposal_id")
    created_at = proposal.get("created_at")
    if not isinstance(proposal_id, str) or not _is_sha256(proposal_id):
        raise ValueError("proposal has an invalid proposal_id")
    if not isinstance(created_at, str):
        raise ValueError("proposal has an invalid created_at")
    return {**payload, "proposal_id": proposal_id, "created_at": created_at}


def _capture_file(path: Path) -> _FileSnapshot:
    """Capture a UTF-8 file without creating a missing path."""
    if not path.exists():
        return _FileSnapshot(path, False)
    return _FileSnapshot(path, True, path.read_text(encoding="utf-8"))


def _projection_paths(vault_dir: Path) -> set[Path]:
    """Return the Markdown projection files the hierarchical index may touch."""
    paths: set[Path] = {vault_dir / "index.md"}
    for path in vault_dir.rglob("*.md"):
        relative = path.relative_to(vault_dir)
        if is_catalog_filename(path.name) and relative.parts and relative.parts[0] in INDEX_FOLDERS:
            paths.add(path)
    cache_dir = existing_vault_cache_dir(vault_dir)
    if cache_dir is not None:
        paths.add(cache_dir / "hierarchical-index-cache.json")
    return paths


def _capture_projection_snapshot(vault_dir: Path) -> list[_FileSnapshot]:
    """Capture all existing catalog pages before an index render."""
    return [_capture_file(path) for path in sorted(_projection_paths(vault_dir))]


def _restore_file_snapshot(path: Path, snapshot: _FileSnapshot) -> None:
    """Restore one file pre-image, removing files created by the failed run."""
    if snapshot.existed:
        atomic_write(path, snapshot.content)
    else:
        path.unlink(missing_ok=True)


def _restore_projection_snapshot(vault_dir: Path, snapshots: list[_FileSnapshot]) -> None:
    """Restore catalogs and invalidate the incremental renderer cache."""
    before = {snapshot.path: snapshot for snapshot in snapshots}
    for path in _projection_paths(vault_dir) | set(before):
        snapshot = before.get(path)
        if snapshot is None:
            path.unlink(missing_ok=True)
        else:
            _restore_file_snapshot(path, snapshot)

    cache_path = next(
        (
            snapshot.path
            for snapshot in snapshots
            if snapshot.path.name == "hierarchical-index-cache.json"
        ),
        None,
    )
    if cache_path is None:
        cache_dir = existing_vault_cache_dir(vault_dir)
        if cache_dir is not None:
            (cache_dir / "hierarchical-index-cache.json").unlink(missing_ok=True)


def _append_receipt(history: Path, receipt: dict[str, str]) -> None:
    """Atomically append a content-free receipt after search publication."""
    history.parent.mkdir(parents=True, exist_ok=True)
    previous = history.read_text(encoding="utf-8") if history.exists() else ""
    atomic_write(history, previous + json.dumps(receipt, sort_keys=True) + "\n")


def _append_text(path: Path, entry: str) -> None:
    """Atomically append one operational log entry."""
    previous = path.read_text(encoding="utf-8") if path.exists() else ""
    atomic_write(path, previous + entry)


def validate_state(vault_dir: Path) -> bool:
    """Return whether the transaction state has no blocking health issues.

    Orphan notes remain actionable lint warnings, but they are not evidence
    that the approved note failed to persist or enter the search projection.
    """
    return not run_lint_vault(vault_dir).has_blocking_issues


def read_history(vault_dir: Path) -> list[dict[str, str]]:
    """Read append-only transaction receipts without exposing content."""
    history = vault_dir / ".power" / "memory-history.jsonl"
    if not history.exists():
        return []
    return [json.loads(line) for line in history.read_text(encoding="utf-8").splitlines() if line]
