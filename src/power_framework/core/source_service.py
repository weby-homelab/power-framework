"""Safe, bounded source read service for POWER 3.7.

This module provides side-effect-free, realpath-contained access to vault notes,
precomputed summaries, graph projections, and metadata without modifying the vault
or running unauthorized full disk scans on hot paths.
"""

from __future__ import annotations

import contextlib
import hashlib
import posixpath
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .application_models import (
    GraphEdgeDTO,
    GraphNodeDTO,
    GraphProjectionResponse,
    SourceItemDTO,
    SourceListRequest,
    SourceListResponse,
    SourceReadRequest,
    SourceReadResponse,
    SourceStatsResponse,
)
from .ignore import should_skip
from .parser import read_file_content, validate_metadata
from .vault_storage import ensure_vault_identity


def normalize_rel_path(path: str) -> str:
    """Normalize and validate relative path to prevent directory traversal."""
    cleaned = path.strip().replace("\\", "/").lstrip("/")
    norm = posixpath.normpath(cleaned)
    if norm in {".", ""}:
        return ""
    if norm.startswith("..") or "/../" in f"/{norm}/":
        raise PermissionError(f"Path traversal detected: {path}")
    return norm


def resolve_safe_vault_path(vault_dir: Path, rel_path: str) -> Path:
    """Resolve and verify that the target path strictly resides inside vault_dir."""
    normalized = normalize_rel_path(rel_path)
    if not normalized:
        raise ValueError("Relative path cannot be empty")
    root = vault_dir.expanduser().resolve()
    target = (root / normalized).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise PermissionError(f"Path escapes vault boundary: {rel_path}") from exc
    return target


def resolve_note_file(vault_dir: Path, rel_path: str) -> tuple[Path, str]:
    """Resolve note path or wikilink stem to an actual note file inside vault_dir."""
    normalized = normalize_rel_path(rel_path)
    if not normalized:
        raise ValueError("Relative path cannot be empty")
    root = vault_dir.expanduser().resolve()
    target = (root / normalized).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise PermissionError(f"Path escapes vault boundary: {rel_path}") from exc

    # 1. Exact file match
    if target.is_file():
        return target, target.relative_to(root).as_posix()

    # 2. Match with .md suffix
    if not normalized.endswith(".md"):
        with_md = target.with_suffix(".md")
        if with_md.is_file():
            return with_md, with_md.relative_to(root).as_posix()

    # 3. Directory index or same-named note inside directory
    if target.is_dir():
        same_named = target / f"{target.name}.md"
        if same_named.is_file():
            return same_named, same_named.relative_to(root).as_posix()
        idx = target / "index.md"
        if idx.is_file():
            return idx, idx.relative_to(root).as_posix()
        und_idx = target / "_index.md"
        if und_idx.is_file():
            return und_idx, und_idx.relative_to(root).as_posix()

    # 4. Vault-wide stem matching (Obsidian wikilink target resolution)
    clean_target = normalized.split("/")[-1]
    if clean_target.endswith(".md"):
        clean_target = clean_target[:-3]
    clean_target_lower = clean_target.lower()

    candidates: list[tuple[int, int, Path]] = []
    for file_path in root.rglob("*.md"):
        rel = file_path.relative_to(root).as_posix()
        if should_skip(root, rel):
            continue
        is_archive = rel.startswith("04_Archive/")
        stem = file_path.stem
        stem_lower = stem.lower()

        if stem == clean_target:
            priority = 3 if is_archive else 1
            candidates.append((priority, len(file_path.parts), file_path))
        elif stem_lower == clean_target_lower:
            priority = 4 if is_archive else 2
            candidates.append((priority, len(file_path.parts), file_path))

    if candidates:
        candidates.sort(key=lambda x: (x[0], x[1]))
        best = candidates[0][2]
        return best, best.relative_to(root).as_posix()

    raise FileNotFoundError(f"Source note not found: {rel_path}")


def list_sources(vault_dir: Path, request: SourceListRequest | None = None) -> SourceListResponse:
    """List notes in the vault with bounded pagination and filtering."""
    req = request or SourceListRequest()
    root = vault_dir.expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Vault path is not a directory: {root}")

    # Gather matching files
    items: list[SourceItemDTO] = []
    prefix_norm = normalize_rel_path(req.prefix) if req.prefix else ""

    for file_path in root.rglob("*.md"):
        rel_posix = file_path.relative_to(root).as_posix()
        if should_skip(root, rel_posix):
            continue
        if file_path.name in {"index.md", "log.md", "_index.md"}:
            continue
        if prefix_norm and not rel_posix.startswith(prefix_norm):
            continue

        parts = rel_posix.split("/")
        top_cat = parts[0] if len(parts) > 1 else "root"
        if req.category and top_cat.lower() != req.category.lower():
            continue

        try:
            stat = file_path.stat()
            content = read_file_content(file_path)
            meta = validate_metadata(content)
            title = meta.title if meta else file_path.stem
            tags = meta.tags if meta else []
            if req.tag and req.tag.lower() not in [t.lower() for t in tags]:
                continue
            mtime_iso = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
            file_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

            items.append(
                SourceItemDTO(
                    rel_path=rel_posix,
                    title=title,
                    category=top_cat,
                    size_bytes=stat.st_size,
                    modified_at=mtime_iso,
                    tags=tags,
                    trust_label="local",
                    sha256=file_hash,
                )
            )
        except Exception:  # noqa: S112
            continue

    # Sort deterministically by rel_path
    items.sort(key=lambda x: x.rel_path)
    total_count = len(items)

    # Apply cursor offset pagination
    offset = 0
    if req.cursor:
        try:
            offset = int(req.cursor)
        except ValueError:
            offset = 0

    page_items = items[offset : offset + req.limit]
    next_cursor = str(offset + req.limit) if (offset + req.limit) < total_count else None

    # Get vault revision if possible
    vault_rev = ""
    identity_file = root / ".power" / "vault.json"
    if identity_file.exists():
        with contextlib.suppress(Exception):
            vault_rev = hashlib.sha256(identity_file.read_bytes()).hexdigest()[:12]

    return SourceListResponse(
        items=page_items,
        total_count=total_count,
        next_cursor=next_cursor,
        source_revision=vault_rev,
    )


def read_source(vault_dir: Path, request: SourceReadRequest) -> SourceReadResponse:
    """Read a specific note from the vault with ETag and strict containment."""
    target_file, rel_norm = resolve_note_file(vault_dir, request.rel_path)

    stat = target_file.stat()
    if stat.st_size > request.max_bytes:
        raise ValueError(
            f"File size {stat.st_size} exceeds requested max_bytes {request.max_bytes}"
        )

    content = read_file_content(target_file)
    meta = validate_metadata(content)
    meta_dict: dict[str, Any] = {}
    if meta:
        meta_dict = meta.model_dump()

    sha256_digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    etag = f'"{sha256_digest[:16]}-{int(stat.st_mtime)}"'
    mtime_iso = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()

    return SourceReadResponse(
        rel_path=rel_norm,
        content=content,
        sha256=sha256_digest,
        etag=etag,
        size_bytes=stat.st_size,
        modified_at=mtime_iso,
        metadata=meta_dict,
        trust_label="local",
    )


def get_source_stats(vault_dir: Path) -> SourceStatsResponse:
    """Compute aggregate vault statistics."""
    root = vault_dir.expanduser().resolve()
    vault_id = "default"
    with contextlib.suppress(Exception):
        ident = ensure_vault_identity(root)
        vault_id = ident.vault_id

    cat_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    total_notes = 0
    total_bytes = 0

    for file_path in root.rglob("*.md"):
        rel_posix = file_path.relative_to(root).as_posix()
        if should_skip(root, rel_posix):
            continue
        if file_path.name in {"index.md", "log.md", "_index.md"}:
            continue

        parts = rel_posix.split("/")
        cat = parts[0] if len(parts) > 1 else "root"
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
        total_notes += 1

        try:
            stat = file_path.stat()
            total_bytes += stat.st_size
            content = read_file_content(file_path)
            meta = validate_metadata(content)
            if meta:
                for tag in meta.tags:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        except Exception:  # noqa: S112
            continue

    return SourceStatsResponse(
        vault_id=vault_id,
        total_notes=total_notes,
        category_counts=cat_counts,
        tag_counts=tag_counts,
        total_links=0,
        storage_bytes=total_bytes,
        last_indexed_at=datetime.now(UTC).isoformat(),
        healthy=True,
    )


def get_graph_projection(
    vault_dir: Path,
    max_nodes: int = 500,
    focus_path: str | None = None,
    max_depth: int = 2,
) -> GraphProjectionResponse:
    """Extract a safe, bounded graph projection for visualization."""
    root = vault_dir.expanduser().resolve()
    nodes_map: dict[str, GraphNodeDTO] = {}
    edges: list[GraphEdgeDTO] = []

    # First collect nodes
    for file_path in root.rglob("*.md"):
        rel_posix = file_path.relative_to(root).as_posix()
        if should_skip(root, rel_posix):
            continue
        if file_path.name in {"index.md", "log.md", "_index.md"}:
            continue

        parts = rel_posix.split("/")
        cat = parts[0] if len(parts) > 1 else "root"
        try:
            content = read_file_content(file_path)
            meta = validate_metadata(content)
            title = meta.title if meta else file_path.stem
            nodes_map[rel_posix] = GraphNodeDTO(
                id=rel_posix,
                label=title,
                category=cat,
                degree=0,
                metadata={"tags": meta.tags if meta else []},
            )
        except Exception:  # noqa: S112
            continue

        if len(nodes_map) >= max_nodes:
            break

    # Next collect links (wikilinks format [[Target Note]] or [[Target|Alias]])
    import re

    link_pattern = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")

    for source_path, node in list(nodes_map.items()):
        source_file = root / source_path
        if not source_file.is_file():
            continue
        try:
            content = read_file_content(source_file)
            matches = link_pattern.findall(content)
            for target_raw in matches:
                target_clean = target_raw.strip()
                # Find matching target in nodes_map (by path or by stem/title)
                matched_target: str | None = None
                for candidate_path, cand_node in nodes_map.items():
                    if (
                        candidate_path == target_clean
                        or Path(candidate_path).stem.lower() == target_clean.lower()
                        or cand_node.label.lower() == target_clean.lower()
                    ):
                        matched_target = candidate_path
                        break

                if matched_target and matched_target != source_path:
                    edges.append(
                        GraphEdgeDTO(
                            source=source_path,
                            target=matched_target,
                            relation_type="wikilink",
                            is_candidate=False,
                            weight=1.0,
                        )
                    )
                    node.degree += 1
                    nodes_map[matched_target].degree += 1
        except Exception:  # noqa: S112
            continue

    return GraphProjectionResponse(
        nodes=list(nodes_map.values()),
        edges=edges,
        total_nodes=len(nodes_map),
        total_edges=len(edges),
        max_depth=max_depth,
        is_truncated=len(nodes_map) >= max_nodes,
    )


__all__ = [
    "get_graph_projection",
    "get_source_stats",
    "list_sources",
    "normalize_rel_path",
    "read_source",
    "resolve_safe_vault_path",
]
