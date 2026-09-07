"""Safe, bounded source read service for POWER 3.7.11.

This module provides side-effect-free, realpath-contained access to vault notes,
precomputed summaries, graph projections, and metadata without modifying the vault
or running unauthorized full disk scans on hot paths.
"""

from __future__ import annotations

import hashlib
import json
import os
import posixpath
import sqlite3
import stat as stat_module
from collections import deque
from contextlib import closing
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import BinaryIO

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
from .constants import SKIP_FILES, is_catalog_filename
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
from .utils import is_regular_vault_file, iter_vault_markdown_files
from .vault_storage import read_vault_identity

# Compatibility name retained for integrations that patched the old helper. It
# is intentionally read-only and never creates vault identity state.
ensure_vault_identity = read_vault_identity

ACTIVE_CAPABILITY = "active_source_projection"
DEGRADED_CAPABILITY = "degraded_bounded_source_scan"
DEGRADED_SCAN_LIMIT = 5000
DEGRADED_SOURCE_BYTES = 2_000_000
CANONICAL_SOURCE_NOT_FOUND = "source not found in canonical source projection"


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


@dataclass(frozen=True)
class SourceReadContext:
    """Request-scoped canonical projection used by retrieval materialization."""

    root: Path
    projection: _ProjectionData
    generation_path: Path | None


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
            for filepath in sorted(iter_vault_markdown_files(root)):
                rel_path = filepath.relative_to(root).as_posix()
                if (
                    filepath.name in SKIP_FILES
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


def _validate_source_request_path(requested: str) -> str:
    """Reject absolute source requests before normalizing their relative form."""
    raw_path = requested.strip()
    windows_path = PureWindowsPath(raw_path)
    if raw_path.startswith(("/", "\\")) or windows_path.is_absolute() or bool(windows_path.drive):
        raise ValueError("Absolute paths are not allowed")
    return normalize_rel_path(raw_path)


def _reject_ineligible_source_path(root: Path, rel_path: str) -> None:
    """Reject paths that cannot be canonical sources without touching projection state."""
    path = Path(rel_path)
    explicit_file = bool(path.suffix)
    if (
        (explicit_file and path.suffix.casefold() != ".md")
        or path.name in SKIP_FILES
        or is_catalog_filename(path.name)
        or (explicit_file and should_skip(root, rel_path))
    ):
        raise SourceNotFoundError(CANONICAL_SOURCE_NOT_FOUND)


def create_source_read_context(vault_dir: Path) -> SourceReadContext:
    """Load one canonical projection for a bounded group of source reads."""
    root = vault_dir.expanduser().resolve()
    active = resolve_active_generation(root)
    return SourceReadContext(
        root=root,
        projection=_read_projection(root),
        generation_path=active.path if active is not None else None,
    )


def _resolve_canonical_source(
    vault_dir: Path, requested: str, projection: _ProjectionData | None = None
) -> tuple[Path, str, _ProjectionData, SourceRecord]:
    """Resolve one request to a projected, regular, non-symlink source note."""
    root = vault_dir.expanduser().resolve()
    normalized = _validate_source_request_path(requested)
    if not normalized:
        raise ValueError("Relative path cannot be empty")
    _reject_ineligible_source_path(root, normalized)

    projection = projection or _read_projection(root)
    try:
        rel_norm = _resolve_projection_path(projection, normalized)
    except SourceNotFoundError as exc:
        raise SourceNotFoundError(CANONICAL_SOURCE_NOT_FOUND) from exc
    record = next((source for source in projection.sources if source.rel_path == rel_norm), None)
    if record is None:
        raise SourceNotFoundError(CANONICAL_SOURCE_NOT_FOUND)

    raw_target = root / rel_norm
    if not is_regular_vault_file(root, raw_target):
        raise SourceNotFoundError(CANONICAL_SOURCE_NOT_FOUND)
    try:
        target = resolve_safe_vault_path(root, rel_norm)
    except (PermissionError, ValueError) as exc:
        raise SourceNotFoundError(CANONICAL_SOURCE_NOT_FOUND) from exc
    if not target.is_file():
        raise SourceNotFoundError(CANONICAL_SOURCE_NOT_FOUND)
    return target, rel_norm, projection, record


def _open_source_file(root: Path, rel_path: str, fallback: Path) -> BinaryIO:
    """Open a projected source with descriptor-relative no-follow semantics."""
    if os.name == "nt":  # pragma: no cover - Linux is the supported release platform
        return fallback.open("rb")

    components = tuple(rel_path.split("/"))
    if not components or any(not component for component in components):
        raise OSError("source path has no components")
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    root_fd: int | None = None
    current_fd: int | None = None
    file_fd: int | None = None
    try:
        root_fd = os.open(root, directory_flags)
        current_fd = root_fd
        for component in components[:-1]:
            assert current_fd is not None
            next_fd = os.open(component, directory_flags, dir_fd=current_fd)
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = next_fd
        assert current_fd is not None
        file_fd = os.open(components[-1], file_flags, dir_fd=current_fd)
        if not stat_module.S_ISREG(os.fstat(file_fd).st_mode):
            raise OSError("source target is not a regular file")
        handle = os.fdopen(file_fd, "rb", closefd=True)
        file_fd = None
        return handle
    finally:
        if file_fd is not None:
            os.close(file_fd)
        if current_fd is not None and current_fd != root_fd:
            os.close(current_fd)
        if root_fd is not None:
            os.close(root_fd)


def authorize_current_source(vault_dir: Path, requested: str) -> str:
    """Authorize a current source path without requiring projection freshness.

    A last-known-good immutable generation may remain searchable while a caller's
    current edit is being repaired. The path itself must nevertheless still be a
    safe, eligible Markdown source with valid metadata; this prevents an old
    generation from re-exposing a newly excluded control file or invalid note.
    """
    root = vault_dir.expanduser().resolve()
    normalized = _validate_source_request_path(requested)
    if not normalized:
        raise SourceNotFoundError(CANONICAL_SOURCE_NOT_FOUND)
    _reject_ineligible_source_path(root, normalized)
    raw_target = root / normalized
    if not is_regular_vault_file(root, raw_target):
        raise SourceNotFoundError(CANONICAL_SOURCE_NOT_FOUND)
    try:
        target = resolve_safe_vault_path(root, normalized)
        if not target.is_file():
            raise SourceNotFoundError(CANONICAL_SOURCE_NOT_FOUND)
        handle = _open_source_file(root, normalized, target)
    except (OSError, ValueError) as exc:
        raise SourceNotFoundError(CANONICAL_SOURCE_NOT_FOUND) from exc
    with handle:
        content = handle.read(10_000_001).decode("utf-8", errors="ignore")
    try:
        metadata = validate_metadata(content)
    except Exception as exc:
        raise SourceNotFoundError(CANONICAL_SOURCE_NOT_FOUND) from exc
    if metadata is None:
        raise SourceNotFoundError(CANONICAL_SOURCE_NOT_FOUND)
    return normalized


def resolve_note_file(vault_dir: Path, rel_path: str) -> tuple[Path, str]:
    """Resolve only a canonical projected source, never an arbitrary file."""
    target, resolved, _projection, _record = _resolve_canonical_source(vault_dir, rel_path)
    return target, resolved


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


def read_source(
    vault_dir: Path,
    request: SourceReadRequest,
    *,
    context: SourceReadContext | None = None,
) -> SourceReadResponse:
    """Read a bounded note only after canonical projection and file-policy checks."""
    root = vault_dir.expanduser().resolve()
    if context is not None and context.root != root:
        raise ValueError("source read context does not match the vault")
    target_file, rel_norm, projection, record = _resolve_canonical_source(
        root, request.rel_path, context.projection if context is not None else None
    )

    try:
        handle = _open_source_file(root, rel_norm, target_file)
    except OSError as exc:
        raise SourceNotFoundError(CANONICAL_SOURCE_NOT_FOUND) from exc
    with handle:
        stat = os.fstat(handle.fileno())
        if stat.st_size > request.max_bytes:
            raise ValueError(
                f"File size {stat.st_size} exceeds requested max_bytes {request.max_bytes}"
            )
        raw_content = handle.read(request.max_bytes + 1)
    if len(raw_content) > request.max_bytes:
        raise ValueError(f"File size exceeds requested max_bytes {request.max_bytes}")
    content = raw_content.decode("utf-8", errors="ignore")
    meta = validate_metadata(content)
    sha256_digest = hashlib.sha256(raw_content).hexdigest()
    current_modified_at = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat()
    if (
        meta is None
        or stat.st_size != record.size_bytes
        or current_modified_at != record.modified_at
        or sha256_digest != record.content_sha256
    ):
        raise SourceProjectionStaleError("source projection is stale; run power sync")
    meta_dict = meta.model_dump(mode="json") if meta else {}
    return SourceReadResponse(
        rel_path=rel_norm,
        content=content,
        sha256=sha256_digest,
        etag=f'"{sha256_digest[:16]}-{int(stat.st_mtime)}"',
        size_bytes=stat.st_size,
        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
        metadata=meta_dict,
        trust_label="local",
        source_revision=projection.source_revision,
        actual_capability=projection.actual_capability,
        degraded_reason=projection.degraded_reason,
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
    "SourceReadContext",
    "create_source_read_context",
    "get_graph_projection",
    "get_source_stats",
    "list_sources",
    "normalize_rel_path",
    "read_source",
    "resolve_safe_vault_path",
]
