"""Safe, bounded source read service for POWER 3.6.5.

This module provides side-effect-free, realpath-contained access to vault notes,
precomputed summaries, graph projections, and metadata without modifying the vault
or running unauthorized full disk scans on hot paths.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import sqlite3
from collections import deque
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

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
from .constants import is_catalog_filename
from .generation_index import resolve_active_generation
from .ignore import should_skip
from .parser import validate_metadata
from .source_projection import (
    ScannedProjection,
    SourceAmbiguity,
    SourceLink,
    SourceRecord,
    scan_projection,
)
from .vault_storage import read_vault_identity

# Compatibility name retained for integrations that patched the old helper. It
# is intentionally read-only and never creates vault identity state.
ensure_vault_identity = read_vault_identity

ACTIVE_CAPABILITY = "active_source_projection"
DEGRADED_CAPABILITY = "degraded_bounded_source_scan"
DIRECT_CAPABILITY = "direct_file_read"
DEGRADED_SCAN_LIMIT = 5000
DEGRADED_SOURCE_BYTES = 2_000_000


class SourceProjectionError(RuntimeError):
    """The active source projection is missing, malformed, or inconsistent."""

    code = "source_projection_error"
    status_code = 503


class SourceProjectionStaleError(SourceProjectionError):
    """The active projection no longer describes the current Markdown set."""

    code = "source_projection_stale"


class SourceNotFoundError(FileNotFoundError):
    """A source path or stem has no deterministic projection match."""

    code = "source_not_found"
    status_code = 404


class SourceAmbiguousError(ValueError):
    """A source stem maps to more than one deterministic source path."""

    code = "source_ambiguous"
    status_code = 409


@dataclass(frozen=True)
class _ProjectionData:
    sources: tuple[SourceRecord, ...]
    links: tuple[SourceLink, ...]
    ambiguities: tuple[SourceAmbiguity, ...]
    source_revision: str
    actual_capability: str
    degraded_reason: str | None
    last_indexed_at: str | None
    healthy: bool
    vault_id: str


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


def _projection_from_scan(projection: ScannedProjection, reason: str) -> _ProjectionData:
    """Convert a bounded source scan to the read projection contract."""
    return _ProjectionData(
        sources=projection.sources,
        links=projection.links,
        ambiguities=projection.ambiguities,
        source_revision=projection.source_revision,
        actual_capability=DEGRADED_CAPABILITY,
        degraded_reason=reason,
        last_indexed_at=None,
        healthy=False,
        vault_id="default",
    )


def _load_active_projection(root: Path) -> _ProjectionData | None:
    """Load and verify the projection from the verified active generation."""
    active = resolve_active_generation(root)
    if active is None:
        return None
    try:
        with closing(sqlite3.connect(f"file:{active.path}?mode=ro", uri=True, timeout=30)) as conn:
            conn.execute("PRAGMA query_only=ON")
            tables = {
                str(row[0])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            required = {
                "file_metadata",
                "source_metadata",
                "source_links",
                "source_link_ambiguities",
                "source_projection_meta",
            }
            if not required <= tables:
                missing = ", ".join(sorted(required - tables))
                raise SourceProjectionError(
                    f"active source projection is missing tables: {missing}"
                )
            meta = dict(conn.execute("SELECT meta_key, meta_value FROM source_projection_meta"))
            if meta.get("schema_version") != "1":
                raise SourceProjectionError("active source projection schema is unsupported")
            source_rows = conn.execute(
                "SELECT rel_path, title, description, note_type, category, tags_json, "
                "size_bytes, modified_at, content_sha256, metadata_json "
                "FROM source_metadata ORDER BY rel_path"
            ).fetchall()
            sources = tuple(
                SourceRecord(
                    rel_path=str(row[0]),
                    title=str(row[1]),
                    description=str(row[2]),
                    note_type=str(row[3]),
                    category=str(row[4]),
                    tags=tuple(json.loads(str(row[5]))),
                    size_bytes=int(row[6]),
                    modified_at=str(row[7]),
                    content_sha256=str(row[8]),
                    metadata=dict(json.loads(str(row[9]))),
                )
                for row in source_rows
            )
            links = tuple(
                SourceLink(str(row[0]), str(row[1]), str(row[2]), float(row[3]), bool(row[4]))
                for row in conn.execute(
                    "SELECT source_path, target_path, relation_type, weight, is_candidate "
                    "FROM source_links ORDER BY source_path, target_path, relation_type"
                )
            )
            ambiguities = tuple(
                SourceAmbiguity(
                    source=str(row[0]),
                    raw_target=str(row[1]),
                    relation_type=str(row[2]),
                    candidates=tuple(sorted(json.loads(str(row[3])))),
                )
                for row in conn.execute(
                    "SELECT source_path, raw_target, relation_type, candidates_json "
                    "FROM source_link_ambiguities ORDER BY source_path, raw_target, relation_type"
                )
            )
            projected_paths = {source.rel_path for source in sources}
            indexed_paths = {
                str(row[0]) for row in conn.execute("SELECT rel_path FROM file_metadata")
            }
            if projected_paths != indexed_paths:
                raise SourceProjectionError("active source projection coverage mismatch")
            if meta.get("source_count") != str(len(sources)):
                raise SourceProjectionError("active source projection source count mismatch")
            if meta.get("link_count") != str(len(links)):
                raise SourceProjectionError("active source projection link count mismatch")
            if meta.get("ambiguity_count") != str(len(ambiguities)):
                raise SourceProjectionError("active source projection ambiguity count mismatch")
            source_revision = meta.get("source_revision", "")
            if source_revision != active.source_snapshot_hash:
                raise SourceProjectionError("active source projection revision mismatch")
            projected_stats = {
                source.rel_path: (source.size_bytes, source.modified_at) for source in sources
            }
            current_paths: set[str] = set()
            for filepath in sorted(root.rglob("*.md")):
                rel_path = filepath.relative_to(root).as_posix()
                if (
                    filepath.name in {"index.md", "log.md"}
                    or is_catalog_filename(filepath.name)
                    or should_skip(root, rel_path)
                ):
                    continue
                current_paths.add(rel_path)
                try:
                    stat = filepath.stat()
                except OSError as exc:
                    raise SourceProjectionStaleError(
                        "active source projection cannot verify current source files"
                    ) from exc
                projected = projected_stats.get(rel_path)
                current_modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
                if projected is None or projected != (stat.st_size, current_modified):
                    raise SourceProjectionStaleError(
                        "active source projection is stale; run power sync"
                    )
            if current_paths != set(projected_stats):
                raise SourceProjectionStaleError(
                    "active source projection is stale; run power sync"
                )
    except SourceProjectionError:
        raise
    except (sqlite3.Error, OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise SourceProjectionError("active source projection is unreadable") from exc

    try:
        identity = read_vault_identity(root)
    except (OSError, ValueError):
        identity = None
    return _ProjectionData(
        sources=sources,
        links=links,
        ambiguities=ambiguities,
        source_revision=source_revision,
        actual_capability=ACTIVE_CAPABILITY,
        degraded_reason=None,
        last_indexed_at=active.completed_at,
        healthy=True,
        vault_id=identity.vault_id if identity is not None else "default",
    )


def _read_projection(root: Path) -> _ProjectionData:
    """Return active projection, or an explicit bounded degraded projection."""
    active = _load_active_projection(root)
    if active is not None:
        return active
    degraded = _projection_from_scan(
        scan_projection(
            root,
            max_sources=DEGRADED_SCAN_LIMIT,
            max_source_bytes=DEGRADED_SOURCE_BYTES,
        ),
        "no_active_generation",
    )
    # A degraded read is still a pure read.  Do not create vault identity or
    # cache state merely to populate an optional identifier in the response.
    return replace(degraded, vault_id="default")


def _resolve_projection_path(projection: _ProjectionData, requested: str) -> str:
    """Resolve an exact projection path or a unique case-insensitive stem."""
    normalized = normalize_rel_path(requested)
    exact = {source.rel_path for source in projection.sources}
    if normalized in exact:
        return normalized
    if not normalized.endswith(".md") and f"{normalized}.md" in exact:
        return f"{normalized}.md"
    stem = Path(normalized).stem.casefold()
    candidates = sorted(
        source.rel_path
        for source in projection.sources
        if Path(source.rel_path).stem.casefold() == stem
    )
    if not candidates:
        raise SourceNotFoundError(f"source not found in projection: {requested}")
    if len(candidates) > 1:
        raise SourceAmbiguousError(
            f"source stem is ambiguous: {requested}; candidates={','.join(candidates)}"
        )
    return candidates[0]


def resolve_note_file(vault_dir: Path, rel_path: str) -> tuple[Path, str]:
    """Resolve an exact path directly or a stem through the source projection."""
    normalized = normalize_rel_path(rel_path)
    if not normalized:
        raise ValueError("Relative path cannot be empty")
    root = vault_dir.expanduser().resolve()
    target = resolve_safe_vault_path(root, normalized)
    if target.is_file():
        return target, target.relative_to(root).as_posix()
    if target.is_dir():
        for candidate in (
            target / f"{target.name}.md",
            target / "index.md",
            target / "_index.md",
        ):
            if candidate.is_file():
                return candidate, candidate.relative_to(root).as_posix()
    if "/" in normalized or normalized.endswith(".md"):
        raise SourceNotFoundError(f"source file is missing: {normalized}")
    projection = _read_projection(root)
    resolved = _resolve_projection_path(projection, normalized)
    return resolve_safe_vault_path(root, resolved), resolved


def list_sources(vault_dir: Path, request: SourceListRequest | None = None) -> SourceListResponse:
    """List notes from the active projection or an explicit bounded fallback."""
    req = request or SourceListRequest()
    root = vault_dir.expanduser().resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Vault path is not a directory: {root}")
    projection = _read_projection(root)
    prefix_norm = normalize_rel_path(req.prefix) if req.prefix else ""
    records = [
        source
        for source in projection.sources
        if (
            not prefix_norm
            or source.rel_path == prefix_norm
            or source.rel_path.startswith(prefix_norm.rstrip("/") + "/")
        )
        and (not req.category or source.category.casefold() == req.category.casefold())
        and (not req.tag or req.tag.casefold() in {tag.casefold() for tag in source.tags})
    ]
    items = [
        SourceItemDTO(
            rel_path=source.rel_path,
            title=source.title,
            category=source.category,
            size_bytes=source.size_bytes,
            modified_at=source.modified_at,
            tags=list(source.tags),
            trust_label="local",
            sha256=source.content_sha256,
        )
        for source in records
    ]
    try:
        offset = max(0, int(req.cursor or "0"))
    except ValueError:
        offset = 0
    next_offset = offset + req.limit
    return SourceListResponse(
        items=items[offset:next_offset],
        total_count=len(items),
        next_cursor=str(next_offset) if next_offset < len(items) else None,
        source_revision=projection.source_revision,
        actual_capability=projection.actual_capability,
        degraded_reason=projection.degraded_reason,
    )


def read_source(vault_dir: Path, request: SourceReadRequest) -> SourceReadResponse:
    """Read a bounded file directly; only stem lookup consults the projection."""
    root = vault_dir.expanduser().resolve()
    normalized = normalize_rel_path(request.rel_path)
    if not normalized:
        raise ValueError("Relative path cannot be empty")
    exact_target = resolve_safe_vault_path(root, normalized)
    actual_capability = DIRECT_CAPABILITY
    degraded_reason: str | None = None
    source_revision = ""
    direct_target = exact_target
    if exact_target.is_dir():
        direct_candidates = (
            exact_target / f"{exact_target.name}.md",
            exact_target / "index.md",
            exact_target / "_index.md",
        )
        direct_target = next(
            (candidate for candidate in direct_candidates if candidate.is_file()), exact_target
        )
    if direct_target.is_file():
        target_file, rel_norm = direct_target, direct_target.relative_to(root).as_posix()
    else:
        if "/" in normalized or normalized.endswith(".md"):
            raise SourceNotFoundError(f"source file is missing: {normalized}")
        projection = _read_projection(root)
        rel_norm = _resolve_projection_path(projection, normalized)
        target_file = resolve_safe_vault_path(root, rel_norm)
        if not target_file.is_file():
            raise SourceNotFoundError(f"source file is missing: {rel_norm}")
        source_revision = projection.source_revision
        actual_capability = projection.actual_capability
        degraded_reason = projection.degraded_reason

    stat = target_file.stat()
    if stat.st_size > request.max_bytes:
        raise ValueError(
            f"File size {stat.st_size} exceeds requested max_bytes {request.max_bytes}"
        )
    with target_file.open("rb") as handle:
        raw_content = handle.read(request.max_bytes + 1)
    if len(raw_content) > request.max_bytes:
        raise ValueError(f"File size exceeds requested max_bytes {request.max_bytes}")
    content = raw_content.decode("utf-8", errors="ignore")
    meta = validate_metadata(content)
    meta_dict = meta.model_dump(mode="json") if meta else {}
    sha256_digest = hashlib.sha256(raw_content).hexdigest()
    return SourceReadResponse(
        rel_path=rel_norm,
        content=content,
        sha256=sha256_digest,
        etag=f'"{sha256_digest[:16]}-{int(stat.st_mtime)}"',
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
        metadata=meta_dict,
        trust_label="local",
        source_revision=source_revision,
        actual_capability=actual_capability,
        degraded_reason=degraded_reason,
    )


def get_source_stats(vault_dir: Path) -> SourceStatsResponse:
    """Return aggregate statistics from the verified source projection."""
    projection = _read_projection(Path(vault_dir).expanduser().resolve())
    category_counts: dict[str, int] = {}
    tag_counts: dict[str, int] = {}
    for source in projection.sources:
        category_counts[source.category] = category_counts.get(source.category, 0) + 1
        for tag in source.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    return SourceStatsResponse(
        vault_id=projection.vault_id,
        total_notes=len(projection.sources),
        category_counts=dict(sorted(category_counts.items())),
        tag_counts=dict(sorted(tag_counts.items())),
        total_links=len(projection.links),
        storage_bytes=sum(source.size_bytes for source in projection.sources),
        last_indexed_at=projection.last_indexed_at,
        healthy=projection.healthy,
        source_revision=projection.source_revision,
        actual_capability=projection.actual_capability,
        degraded_reason=projection.degraded_reason,
    )


def get_graph_projection(
    vault_dir: Path,
    max_nodes: int = 1000,
    focus_path: str | None = None,
    max_depth: int = 2,
) -> GraphProjectionResponse:
    """Return a deterministic bounded BFS slice from the source projection."""
    if not 1 <= max_nodes <= 1000:
        raise ValueError("max_nodes must be between 1 and 1000")
    if not 1 <= max_depth <= 10:
        raise ValueError("max_depth must be between 1 and 10")
    projection = _read_projection(Path(vault_dir).expanduser().resolve())
    source_map = {source.rel_path: source for source in projection.sources}
    if focus_path is None:
        selected = sorted(source_map)[:max_nodes]
        truncated = len(source_map) > len(selected)
    else:
        focus = _resolve_projection_path(projection, focus_path)
        adjacency: dict[str, set[str]] = {path: set() for path in source_map}
        for link in projection.links:
            adjacency[link.source].add(link.target)
            adjacency[link.target].add(link.source)
        distances = {focus: 0}
        queue = deque([focus])
        while queue:
            current = queue.popleft()
            if distances[current] >= max_depth:
                continue
            for neighbor in sorted(adjacency[current]):
                if neighbor not in distances:
                    distances[neighbor] = distances[current] + 1
                    queue.append(neighbor)
        ordered = sorted(distances, key=lambda path: (distances[path], path))
        selected = ordered[:max_nodes]
        truncated = len(ordered) > len(selected)
    selected_set = set(selected)
    edges = [
        GraphEdgeDTO(
            source=link.source,
            target=link.target,
            relation_type=link.relation_type,
            is_candidate=link.is_candidate,
            weight=link.weight,
        )
        for link in projection.links
        if link.source in selected_set and link.target in selected_set
    ]
    degrees = dict.fromkeys(selected, 0)
    for edge in edges:
        degrees[edge.source] += 1
        degrees[edge.target] += 1
    nodes = [
        GraphNodeDTO(
            id=source.rel_path,
            label=source.title,
            category=source.category,
            degree=degrees[source.rel_path],
            metadata={"tags": list(source.tags)},
        )
        for source in (source_map[path] for path in selected)
    ]
    return GraphProjectionResponse(
        nodes=nodes,
        edges=edges,
        total_nodes=len(nodes),
        total_edges=len(edges),
        max_depth=max_depth,
        is_truncated=truncated,
        source_revision=projection.source_revision,
        actual_capability=projection.actual_capability,
        degraded_reason=projection.degraded_reason,
        ambiguities=[
            {
                "source": ambiguity.source,
                "raw_target": ambiguity.raw_target,
                "relation_type": ambiguity.relation_type,
                "candidates": list(ambiguity.candidates),
            }
            for ambiguity in projection.ambiguities
            if ambiguity.source in selected_set
        ],
    )


__all__ = [
    "SourceAmbiguousError",
    "SourceNotFoundError",
    "SourceProjectionError",
    "SourceProjectionStaleError",
    "get_graph_projection",
    "get_source_stats",
    "list_sources",
    "normalize_rel_path",
    "read_source",
    "resolve_safe_vault_path",
]
