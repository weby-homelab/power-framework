"""SearchScope Pushdown compilation, SQL condition generation, and gating.

POWER 3.8 Phase 5C (P38-WP01):
Enforces SCOPE BEFORE CANDIDATES across all retrieval pipelines (FTS, vector,
dense, hybrid, reranker, graph-assisted, and fallback scan).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .domain_errors import DomainConfigError
from .domains import load_domain_registry
from .temporal import (
    includes_temporal_status,
    load_temporal_records,
    normalize_as_of,
    normalize_temporal_view,
    resolve_temporal_statuses,
    scan_temporal_records,
)

if TYPE_CHECKING:
    from .context_contracts import AccessPolicy, SearchScope
    from .searcher import _ResolvedDb


class SearchScopeError(Exception):
    """Base exception for search scope compilation and pushdown enforcement."""


class UnsupportedSearchScopeError(SearchScopeError):
    """Raised when an unsupported search scope dimension (trust_states, project_ids) is non-empty."""


class SearchScopeAccessDeniedError(SearchScopeError, PermissionError):
    """Raised when privileged search scope access is requested without server-issued authorization."""


class UnknownDomainError(SearchScopeError, DomainConfigError):
    """Raised when an unknown domain ID is specified in SearchScope."""


def escape_like_wildcards(val: str) -> str:
    """Escape LIKE pattern special characters (% and _ and \\) for SQLite ESCAPE '\\'."""
    return val.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True)
class ResolvedSearchScope:
    """Compiled and validated search scope ready for SQL pushdown and candidate gating."""

    domain_ids: tuple[str, ...] = ()
    path_prefixes: tuple[str, ...] = ()
    source_types: tuple[str, ...] = ()
    temporal_view: str = "current"
    as_of: date = field(default_factory=date.today)
    include_archived: bool = False
    include_quarantine: bool = False
    excluded_temporal_paths: frozenset[str] = field(default_factory=frozenset)
    scope_digest: str | None = None

    def is_empty(self) -> bool:
        """Return True if this scope imposes no filtering constraints."""
        return (
            not self.domain_ids
            and not self.path_prefixes
            and not self.source_types
            and self.include_archived
            and self.include_quarantine
            and not self.excluded_temporal_paths
        )

    def is_path_in_scope(self, rel_path: str, note_type: str | None = None) -> bool:
        """Check whether a relative path and optional note type satisfy this scope."""
        clean = rel_path.strip().strip("/")

        # 1. Archive check
        if not self.include_archived:
            if clean == "04_Archive" or clean.startswith("04_Archive/"):
                return False
            if note_type is not None and note_type.casefold() == "archive":
                return False

        # 2. Quarantine check
        if not self.include_quarantine and (
            clean.startswith(".quarantine/")
            or clean.startswith("quarantine/")
            or "/.quarantine/" in clean
            or "/quarantine/" in clean
        ):
            return False

        # 3. Path prefixes check
        if self.path_prefixes:
            matched = False
            for prefix in self.path_prefixes:
                if clean == prefix or clean.startswith(f"{prefix}/"):
                    matched = True
                    break
            if not matched:
                return False

        # 4. Source types check
        if self.source_types and note_type is not None:
            normalized_types = {t.casefold() for t in self.source_types}
            if note_type.casefold() not in normalized_types:
                return False

        # 5. Temporal excluded paths check
        return not (self.excluded_temporal_paths and clean in self.excluded_temporal_paths)

    def build_sql_conditions(
        self,
        *,
        rel_path_col: str = "rel_path",
        note_type_col: str | None = "note_type",
    ) -> tuple[str, list[Any]]:
        """Generate SQL WHERE clauses and parameters for pushdown filtering."""
        clauses: list[str] = []
        params: list[Any] = []

        # 1. Path prefixes
        if self.path_prefixes:
            prefix_clauses: list[str] = []
            for prefix in self.path_prefixes:
                clean_p = prefix.strip("/")
                if clean_p.endswith(".md"):
                    prefix_clauses.append(f"{rel_path_col} = ?")
                    params.append(clean_p)
                else:
                    escaped_p = escape_like_wildcards(clean_p)
                    prefix_clauses.append(
                        f"({rel_path_col} = ? OR {rel_path_col} LIKE ? ESCAPE '\\')"
                    )
                    params.extend([clean_p, f"{escaped_p}/%"])
            if prefix_clauses:
                clauses.append("(" + " OR ".join(prefix_clauses) + ")")

        # 2. Archive exclusion
        if not self.include_archived:
            clauses.append(
                f"({rel_path_col} != '04_Archive' AND {rel_path_col} NOT LIKE '04_Archive/%' ESCAPE '\\')"
            )
            if note_type_col is not None:
                clauses.append(f"({note_type_col} IS NULL OR {note_type_col} != 'Archive')")

        # 3. Quarantine exclusion
        if not self.include_quarantine:
            clauses.append(
                f"({rel_path_col} NOT LIKE '.quarantine/%' ESCAPE '\\' "
                f"AND {rel_path_col} NOT LIKE 'quarantine/%' ESCAPE '\\' "
                f"AND {rel_path_col} NOT LIKE '%/.quarantine/%' ESCAPE '\\' "
                f"AND {rel_path_col} NOT LIKE '%/quarantine/%' ESCAPE '\\')"
            )

        # 4. Source types
        if self.source_types and note_type_col is not None:
            placeholders = ", ".join("?" for _ in self.source_types)
            clauses.append(f"{note_type_col} IN ({placeholders})")
            params.extend(self.source_types)

        # 5. Temporal exclusions
        if self.excluded_temporal_paths:
            excluded = sorted(self.excluded_temporal_paths)
            if len(excluded) <= 900:
                placeholders = ", ".join("?" for _ in excluded)
                clauses.append(f"{rel_path_col} NOT IN ({placeholders})")
                params.extend(excluded)

        if not clauses:
            return "", []
        return " AND ".join(clauses), params

    def build_fts_condition(self) -> tuple[str, list[Any]]:
        """Generate SQL condition for fts_notes (columns: rel_path, note_type)."""
        return self.build_sql_conditions(rel_path_col="rel_path", note_type_col="note_type")

    def build_vector_condition(
        self, tf_alias: str = "t", fts_alias: str = "f"
    ) -> tuple[str, list[Any]]:
        """Generate SQL condition for tf_vectors JOIN fts_notes."""
        return self.build_sql_conditions(
            rel_path_col=f"{tf_alias}.rel_path",
            note_type_col=f"{fts_alias}.note_type",
        )

    def build_chunk_condition(self, chunk_alias: str = "c") -> tuple[str, list[Any]]:
        """Generate SQL condition for chunk_embeddings."""
        col = f"{chunk_alias}.rel_path" if chunk_alias else "rel_path"
        clauses: list[str] = []
        params: list[Any] = []

        # 1. Path prefixes
        if self.path_prefixes:
            prefix_clauses: list[str] = []
            for prefix in self.path_prefixes:
                clean_p = prefix.strip("/")
                if clean_p.endswith(".md"):
                    prefix_clauses.append(f"{col} = ?")
                    params.append(clean_p)
                else:
                    escaped_p = escape_like_wildcards(clean_p)
                    prefix_clauses.append(f"({col} = ? OR {col} LIKE ? ESCAPE '\\')")
                    params.extend([clean_p, f"{escaped_p}/%"])
            if prefix_clauses:
                clauses.append("(" + " OR ".join(prefix_clauses) + ")")

        # 2. Archive exclusion
        if not self.include_archived:
            clauses.append(
                f"({col} != '04_Archive' AND {col} NOT LIKE '04_Archive/%' ESCAPE '\\')"
            )
            # Subquery to exclude Archive note_type
            clauses.append(
                f"{col} NOT IN (SELECT rel_path FROM fts_notes WHERE note_type = 'Archive')"  # noqa: S608
            )

        # 3. Quarantine exclusion
        if not self.include_quarantine:
            clauses.append(
                f"({col} NOT LIKE '.quarantine/%' ESCAPE '\\' "
                f"AND {col} NOT LIKE 'quarantine/%' ESCAPE '\\' "
                f"AND {col} NOT LIKE '%/.quarantine/%' ESCAPE '\\' "
                f"AND {col} NOT LIKE '%/quarantine/%' ESCAPE '\\')"
            )

        # 4. Source types subquery
        if self.source_types:
            placeholders = ", ".join("?" for _ in self.source_types)
            clauses.append(
                f"{col} IN (SELECT rel_path FROM fts_notes WHERE note_type IN ({placeholders}))"  # noqa: S608
            )
            params.extend(self.source_types)

        # 5. Temporal exclusions
        if self.excluded_temporal_paths:
            excluded = sorted(self.excluded_temporal_paths)
            if len(excluded) <= 900:
                placeholders = ", ".join("?" for _ in excluded)
                clauses.append(f"{col} NOT IN ({placeholders})")
                params.extend(excluded)

        if not clauses:
            return "", []
        return " AND ".join(clauses), params


def canonical_scope_digest(resolved: ResolvedSearchScope | None) -> str | None:
    """Compute a deterministic digest of effective scope for cache keys."""
    if resolved is None or resolved.is_empty():
        return None
    data = {
        "domain_ids": sorted(resolved.domain_ids),
        "path_prefixes": sorted(resolved.path_prefixes),
        "source_types": sorted(resolved.source_types),
        "temporal_view": resolved.temporal_view,
        "as_of": str(resolved.as_of),
        "include_archived": resolved.include_archived,
        "include_quarantine": resolved.include_quarantine,
        "excluded_temporal_paths": sorted(resolved.excluded_temporal_paths),
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


def compile_search_scope(
    vault_dir: Path,
    scope: SearchScope | None = None,
    domain: str | None = None,
    temporal_view: str = "current",
    as_of: date | str | None = None,
    access_policy: AccessPolicy | None = None,
    resolved_db: _ResolvedDb | None = None,
) -> ResolvedSearchScope:
    """Validate and compile raw search inputs into a canonical ResolvedSearchScope.

    Fails closed on unsupported dimensions (trust_states, project_ids) or unauthorized
    requests for privileged boundaries (include_archived, include_quarantine).
    """
    vault_dir = Path(vault_dir).expanduser().resolve()

    # 1. Fail closed on unsupported dimensions
    if scope is not None:
        if scope.trust_states:
            raise UnsupportedSearchScopeError(
                "trust_states dimension is not supported in SQLite index schema (must fail closed)"
            )
        if scope.project_ids:
            raise UnsupportedSearchScopeError(
                "project_ids dimension is not supported in SQLite index schema (must fail closed)"
            )

    # 2. Enforce authorization boundary for privileged scope dimensions
    if scope is not None:
        if scope.include_archived and (
            access_policy is None
            or getattr(access_policy, "raw_access", None) != "privileged"
            or getattr(access_policy, "approval_ref", None) is None
        ):
            raise SearchScopeAccessDeniedError(
                "include_archived=True requires server-issued AccessPolicy with privileged raw_access and approval_ref"
            )
        if scope.include_quarantine and (
            access_policy is None
            or getattr(access_policy, "quarantine_access", None) != "privileged"
            or getattr(access_policy, "approval_ref", None) is None
        ):
            raise SearchScopeAccessDeniedError(
                "include_quarantine=True requires server-issued AccessPolicy with privileged quarantine_access and approval_ref"
            )

    # 3. Resolve domains
    domain_names: list[str] = []
    if scope and scope.domain_ids:
        domain_names.extend(scope.domain_ids)
    if domain and domain not in domain_names:
        domain_names.append(domain)

    registry = load_domain_registry(vault_dir)
    domain_prefixes: list[str] = []
    for d in domain_names:
        spec = registry.get(d)
        if spec is None:
            raise UnknownDomainError(f"unknown domain: {d}")
        domain_prefixes.append(spec.path.as_posix().strip("/"))

    # 4. Resolve path prefixes
    prefixes: list[str] = []
    if scope and scope.path_prefixes:
        for p in scope.path_prefixes:
            cleaned = str(p).strip().strip("/")
            if cleaned:
                prefixes.append(cleaned)
    prefixes.extend(domain_prefixes)

    dedup_prefixes: list[str] = []
    seen_prefixes: set[str] = set()
    for p in prefixes:
        if p not in seen_prefixes:
            seen_prefixes.add(p)
            dedup_prefixes.append(p)

    # 5. Resolve source types
    source_types = tuple(scope.source_types) if (scope and scope.source_types) else ()

    # 6. Resolve temporal boundary
    normalized_temporal_view = normalize_temporal_view(temporal_view).value
    normalized_as_of = normalize_as_of(as_of)
    if scope and getattr(scope, "temporal_boundary", None):
        if scope.temporal_boundary.as_of:
            normalized_as_of = scope.temporal_boundary.as_of
        if not scope.temporal_boundary.include_historical:
            normalized_temporal_view = "current"

    excluded_temporal_paths: set[str] = set()
    if normalized_temporal_view != "all":
        db_path = None
        if resolved_db is not None and getattr(resolved_db, "path", None):
            db_path = resolved_db.path
        else:
            from .generation_index import resolve_active_generation
            from .vault_storage import existing_vault_db_path

            active = resolve_active_generation(vault_dir)
            db_path = active.path if active is not None else existing_vault_db_path(vault_dir)

        records = load_temporal_records(db_path) if db_path else None
        if records is None:
            records = scan_temporal_records(vault_dir)
        statuses = resolve_temporal_statuses(records, normalized_as_of)
        for p, status in statuses.items():
            if not includes_temporal_status(status, normalized_temporal_view):
                excluded_temporal_paths.add(p)

    # 7. Archived & Quarantine flags
    if scope is not None:
        include_archived = bool(scope.include_archived)
        include_quarantine = bool(scope.include_quarantine)
    else:
        if domain is not None:
            include_archived = False
            include_quarantine = False
        else:
            include_archived = True
            include_quarantine = False

    resolved_scope = ResolvedSearchScope(
        domain_ids=tuple(domain_names),
        path_prefixes=tuple(dedup_prefixes),
        source_types=source_types,
        temporal_view=normalized_temporal_view,
        as_of=normalized_as_of,
        include_archived=include_archived,
        include_quarantine=include_quarantine,
        excluded_temporal_paths=frozenset(excluded_temporal_paths),
    )
    digest = canonical_scope_digest(resolved_scope)
    if digest is not None:
        object.__setattr__(resolved_scope, "scope_digest", digest)
    return resolved_scope
