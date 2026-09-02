"""Deterministic source metadata and link projection primitives."""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .constants import is_catalog_filename
from .ignore import should_skip
from .parser import read_file_content, validate_metadata
from .utils import iter_vault_markdown_files

if TYPE_CHECKING:
    from .models import OKFMetadata

WIKILINK_PATTERN = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]+)?(?:\|[^\]]+)?\]\]")
MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)#]+\.md)(?:#[^)]+)?\)")


@dataclass(frozen=True)
class SourceRecord:
    """One valid source note captured for a generation or bounded fallback."""

    rel_path: str
    title: str
    description: str
    note_type: str
    category: str
    tags: tuple[str, ...]
    size_bytes: int
    modified_at: str
    content_sha256: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class SourceLink:
    """One deterministic, resolved directed source link."""

    source: str
    target: str
    relation_type: str
    weight: float = 1.0
    is_candidate: bool = False


@dataclass(frozen=True)
class SourceAmbiguity:
    """One unresolved target whose stem maps to multiple source paths."""

    source: str
    raw_target: str
    relation_type: str
    candidates: tuple[str, ...]


@dataclass(frozen=True)
class ScannedProjection:
    """Pure in-memory projection output, safe to write or return as fallback."""

    sources: tuple[SourceRecord, ...]
    links: tuple[SourceLink, ...]
    ambiguities: tuple[SourceAmbiguity, ...]
    source_revision: str


def _snapshot_hash(source_hashes: dict[str, str]) -> str:
    digest = hashlib.blake2b(digest_size=32)
    for rel_path, content_hash in sorted(source_hashes.items()):
        digest.update(rel_path.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content_hash.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _source_path_candidates(source_path: str, raw_target: str) -> tuple[str, ...]:
    """Return exact and source-relative path candidates in deterministic order."""
    target = raw_target.strip().replace("\\", "/")
    if not target:
        return ()
    candidates: list[str] = [target]
    if not target.endswith(".md"):
        candidates.append(f"{target}.md")
    parent = posixpath.dirname(source_path)
    relative = posixpath.normpath(posixpath.join(parent, target))
    if relative not in {".", ""} and not relative.startswith("../"):
        candidates.append(relative)
        if not relative.endswith(".md"):
            candidates.append(f"{relative}.md")
    return tuple(dict.fromkeys(candidates))


def _resolve_target(
    source_path: str,
    raw_target: str,
    source_paths: set[str],
    stems: dict[str, tuple[str, ...]],
) -> tuple[str | None, tuple[str, ...]]:
    """Resolve a link, returning a target or sorted ambiguous candidates."""
    for candidate in _source_path_candidates(source_path, raw_target):
        if candidate in source_paths and candidate != source_path:
            return candidate, ()

    target_stem = Path(raw_target.strip()).stem.casefold()
    candidates = tuple(path for path in stems.get(target_stem, ()) if path != source_path)
    if len(candidates) == 1:
        return candidates[0], ()
    if len(candidates) > 1:
        return None, tuple(sorted(candidates))
    return None, ()


def scan_projection(
    vault_dir: Path,
    *,
    max_sources: int | None = None,
    max_source_bytes: int | None = None,
) -> ScannedProjection:
    """Read a deterministic bounded source projection without writing any state."""
    root = Path(vault_dir).expanduser().resolve()
    records: list[SourceRecord] = []
    internal: dict[str, tuple[SourceRecord, str, OKFMetadata]] = {}
    source_hashes: dict[str, str] = {}
    scanned_candidates = 0

    for filepath in sorted(iter_vault_markdown_files(root)):
        rel_path = filepath.relative_to(root).as_posix()
        if filepath.name in {"index.md", "log.md"} or is_catalog_filename(filepath.name):
            continue
        if should_skip(root, rel_path):
            continue
        scanned_candidates += 1
        if max_sources is not None and scanned_candidates > max_sources:
            break
        try:
            if max_source_bytes is not None and filepath.stat().st_size > max_source_bytes:
                continue
            content = read_file_content(filepath)
            metadata = validate_metadata(content)
            if metadata is None:
                continue
            stat = filepath.stat()
        except (OSError, UnicodeError, ValueError):
            continue

        content_sha256 = hashlib.sha256(filepath.read_bytes()).hexdigest()
        record = SourceRecord(
            rel_path=rel_path,
            title=metadata.title,
            description=metadata.description,
            note_type=str(metadata.type),
            category=rel_path.split("/", 1)[0] if "/" in rel_path else "root",
            tags=tuple(metadata.tags),
            size_bytes=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat(),
            content_sha256=content_sha256,
            metadata=metadata.model_dump(mode="json"),
        )
        records.append(record)
        internal[rel_path] = (record, content, metadata)
        source_hashes[rel_path] = hashlib.blake2b(
            content.encode("utf-8"), digest_size=32
        ).hexdigest()

    records.sort(key=lambda item: item.rel_path)
    source_paths = {record.rel_path for record in records}
    stems: dict[str, tuple[str, ...]] = {}
    stem_values: dict[str, list[str]] = {}
    for record in records:
        stem_values.setdefault(Path(record.rel_path).stem.casefold(), []).append(record.rel_path)
    stems = {stem: tuple(sorted(paths)) for stem, paths in stem_values.items()}

    links_by_key: dict[tuple[str, str, str], SourceLink] = {}
    ambiguities: set[SourceAmbiguity] = set()
    for source_path in sorted(internal):
        _, content, metadata = internal[source_path]
        targets: list[tuple[str, str, float]] = [
            (raw_target, "wikilink", 1.0) for raw_target in WIKILINK_PATTERN.findall(content)
        ]
        targets.extend(
            (raw_target, "markdown_link", 1.0)
            for raw_target in MARKDOWN_LINK_PATTERN.findall(content)
        )
        targets.extend(
            (
                relation.path,
                relation.relation,
                relation.confidence,
            )
            for relation in metadata.related
        )
        for raw_target, relation_type, weight in targets:
            target, ambiguous = _resolve_target(source_path, raw_target, source_paths, stems)
            if ambiguous:
                ambiguities.add(
                    SourceAmbiguity(
                        source=source_path,
                        raw_target=raw_target.strip(),
                        relation_type=relation_type,
                        candidates=ambiguous,
                    )
                )
            elif target is not None:
                key = (source_path, target, relation_type)
                candidate = SourceLink(source_path, target, relation_type, weight)
                previous = links_by_key.get(key)
                if previous is None or candidate.weight > previous.weight:
                    links_by_key[key] = candidate

    return ScannedProjection(
        sources=tuple(records),
        links=tuple(
            sorted(
                links_by_key.values(),
                key=lambda item: (item.source, item.target, item.relation_type),
            )
        ),
        ambiguities=tuple(
            sorted(
                ambiguities,
                key=lambda item: (item.source, item.raw_target, item.relation_type),
            )
        ),
        source_revision=_snapshot_hash(source_hashes),
    )


def write_projection(conn: Any, projection: ScannedProjection) -> None:
    """Replace source projection rows in an already-staged SQLite database."""
    conn.execute("DELETE FROM source_links")
    conn.execute("DELETE FROM source_link_ambiguities")
    conn.execute("DELETE FROM source_projection_meta")
    conn.execute("DELETE FROM source_metadata")
    conn.executemany(
        """
        INSERT INTO source_metadata (
            rel_path, title, description, note_type, category, stem, tags_json,
            size_bytes, modified_at, content_sha256, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                source.rel_path,
                source.title,
                source.description,
                source.note_type,
                source.category,
                Path(source.rel_path).stem.casefold(),
                json.dumps(list(source.tags), ensure_ascii=False, sort_keys=True),
                source.size_bytes,
                source.modified_at,
                source.content_sha256,
                json.dumps(source.metadata, ensure_ascii=False, sort_keys=True),
            )
            for source in projection.sources
        ],
    )
    conn.executemany(
        "INSERT INTO source_links (source_path, target_path, relation_type, weight, is_candidate) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (link.source, link.target, link.relation_type, link.weight, int(link.is_candidate))
            for link in projection.links
        ],
    )
    conn.executemany(
        "INSERT INTO source_link_ambiguities "
        "(source_path, raw_target, relation_type, candidates_json) VALUES (?, ?, ?, ?)",
        [
            (
                item.source,
                item.raw_target,
                item.relation_type,
                json.dumps(list(item.candidates), ensure_ascii=False, sort_keys=True),
            )
            for item in projection.ambiguities
        ],
    )
    conn.executemany(
        "INSERT INTO source_projection_meta (meta_key, meta_value) VALUES (?, ?)",
        [
            ("schema_version", "1"),
            ("source_revision", projection.source_revision),
            ("source_count", str(len(projection.sources))),
            ("link_count", str(len(projection.links))),
            ("ambiguity_count", str(len(projection.ambiguities))),
        ],
    )
    conn.commit()


__all__ = [
    "ScannedProjection",
    "SourceAmbiguity",
    "SourceLink",
    "SourceRecord",
    "scan_projection",
    "write_projection",
]
