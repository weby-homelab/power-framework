"""Deterministic temporal and supersession semantics for governed memory."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from .ignore import should_skip
from .parser import read_file_content, validate_metadata

if TYPE_CHECKING:
    from pathlib import Path

    from .models import MemoryMetadata


class TemporalStatus(StrEnum):
    """Resolved lifecycle state exposed to every retrieval surface."""

    CURRENT = "current"
    HISTORICAL = "historical"
    CONFLICTED = "conflicted"


class TemporalView(StrEnum):
    """Selectable retrieval projection over resolved temporal states."""

    CURRENT = "current"
    HISTORICAL = "historical"
    ALL = "all"


@dataclass(frozen=True)
class TemporalRecord:
    """The lifecycle metadata for one Markdown note, keyed by vault-relative path."""

    rel_path: str
    memory: MemoryMetadata | None


def normalize_temporal_view(view: str) -> TemporalView:
    """Validate one shared library/CLI/MCP temporal-view value."""
    try:
        return TemporalView(view.lower())
    except (AttributeError, ValueError) as exc:
        supported = ", ".join(member.value for member in TemporalView)
        raise ValueError(
            f"Unsupported temporal view '{view}'. Supported views: {supported}"
        ) from exc


def normalize_as_of(as_of: date | str | None) -> date:
    """Return an ISO-date boundary, defaulting explicitly to today's UTC date."""
    if as_of is None:
        return datetime.now(UTC).date()
    if isinstance(as_of, date):
        return as_of
    try:
        return date.fromisoformat(as_of)
    except ValueError as exc:
        raise ValueError("as_of must be an ISO-8601 date (YYYY-MM-DD)") from exc


def scan_temporal_records(vault_dir: Path) -> dict[str, TemporalRecord]:
    """Read valid note metadata without trusting derived index state."""
    records: dict[str, TemporalRecord] = {}
    for filepath in vault_dir.rglob("*.md"):
        rel_path = filepath.relative_to(vault_dir).as_posix()
        if should_skip(vault_dir, rel_path):
            continue
        try:
            metadata = validate_metadata(read_file_content(filepath))
        except OSError:
            continue
        if metadata is not None:
            records[rel_path] = TemporalRecord(rel_path, metadata.memory)
    return records


def resolve_temporal_statuses(
    records: dict[str, TemporalRecord], as_of: date | str | None = None
) -> dict[str, TemporalStatus]:
    """Resolve validity and supersession without silently overwriting conflicts.

    Validity bounds are inclusive. A valid successor makes its ancestors historical.
    When independent current heads supersede the same ancestor, all affected heads
    and their shared ancestry are marked ``conflicted`` rather than choosing one.
    """
    boundary = normalize_as_of(as_of)
    active: set[str] = {
        path
        for path, record in records.items()
        if record.memory is None
        or (
            (record.memory.valid_from is None or record.memory.valid_from <= boundary)
            and (record.memory.valid_until is None or boundary <= record.memory.valid_until)
        )
    }
    statuses = {
        path: TemporalStatus.CURRENT if path in active else TemporalStatus.HISTORICAL
        for path in records
    }

    edges: dict[str, set[str]] = defaultdict(set)
    incoming: set[str] = set()
    for path in active:
        memory = records[path].memory
        if memory is None:
            continue
        for target in memory.supersedes:
            if target in records:
                edges[path].add(target)
                incoming.add(target)

    heads = active - incoming
    reached_by: dict[str, set[str]] = defaultdict(set)
    for head in heads:
        queue = deque(edges.get(head, set()))
        seen: set[str] = set()
        while queue:
            target = queue.popleft()
            if target in seen:
                continue
            seen.add(target)
            reached_by[target].add(head)
            queue.extend(edges.get(target, set()))

    conflicted: set[str] = set()
    for target, competing_heads in reached_by.items():
        if len(competing_heads) > 1:
            conflicted.add(target)
            conflicted.update(competing_heads)

    # Detect actual cycles; a non-head is normal in a linear supersession chain.
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(path: str, trail: list[str]) -> None:
        if path in visiting:
            conflicted.update(trail[trail.index(path) :])
            return
        if path in visited:
            return
        visiting.add(path)
        for target in edges.get(path, set()):
            visit(target, [*trail, target])
        visiting.remove(path)
        visited.add(path)

    for path in active:
        visit(path, [path])

    for target, source_heads in reached_by.items():
        if len(source_heads) == 1 and target not in conflicted:
            statuses[target] = TemporalStatus.HISTORICAL
    for path in conflicted:
        statuses[path] = TemporalStatus.CONFLICTED
    return statuses


def includes_temporal_status(status: TemporalStatus, view: str) -> bool:
    """Apply the same projection contract used by library, CLI, and MCP."""
    normalized = normalize_temporal_view(view)
    return normalized is TemporalView.ALL or status.value == normalized.value
