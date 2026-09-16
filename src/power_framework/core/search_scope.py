"""SearchScope Pushdown compilation, SQL condition generation, and gating.

POWER 3.8 Phase 5C (P38-WP01):
Enforces SCOPE BEFORE CANDIDATES across all retrieval pipelines (FTS, vector,
dense, hybrid, reranker, graph-assisted, and fallback scan).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .constants import is_catalog_filename
from .domain_errors import DomainConfigError
from .domains import load_domain_registry
from .ignore import should_skip
from .temporal import (
    includes_temporal_status,
    load_temporal_records,
    normalize_as_of,
    normalize_temporal_view,
    resolve_temporal_statuses,
    scan_temporal_records,
)
from .utils import iter_vault_markdown_files

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .context_contracts import AccessPolicy, SearchScope


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


def _matches_any_prefix(clean_path: str, prefixes: tuple[str, ...] | list[str]) -> bool:
    """Return True if clean_path equals or is under any directory prefix."""
    for prefix in prefixes:
        norm = prefix.strip().strip("/")
        if not norm:
            continue
        if clean_path == norm or clean_path.startswith(f"{norm}/"):
            return True
    return False


def _build_prefix_or_clause(
    prefixes: tuple[str, ...] | list[str],
    rel_path_col: str,
    params: list[Any],
) -> str | None:
    """Build an OR clause for one path dimension (union inside dimension)."""
    cleaned = [p.strip().strip("/") for p in prefixes if p.strip().strip("/")]
    if not cleaned:
        return None
    parts: list[str] = []
    for prefix in cleaned:
        if prefix.endswith(".md"):
            parts.append(f"{rel_path_col} = ?")
            params.append(prefix)
        else:
            escaped = escape_like_wildcards(prefix)
            parts.append(f"({rel_path_col} = ? OR {rel_path_col} LIKE ? ESCAPE '\\')")
            params.extend([prefix, f"{escaped}/%"])
    if not parts:
        return None
    return "(" + " OR ".join(parts) + ")"


@dataclass(frozen=True)
class ResolvedSearchScope:
    """Compiled and validated search scope ready for SQL pushdown and candidate gating.

    Scope algebra (P38-WP01-R1): OR within one dimension, AND across
    independent dimensions. ``domain_path_prefixes`` (union of allowed domains)
    and ``explicit_path_prefixes`` (union of caller path restrictions) are
    stored separately so intersection is enforceable. ``path_prefixes`` is
    retained as the legacy combined union for observability only and must not
    be used as the sole enforcement predicate.
    """

    domain_ids: tuple[str, ...] = ()
    path_prefixes: tuple[str, ...] = ()
    explicit_path_prefixes: tuple[str, ...] = ()
    domain_path_prefixes: tuple[str, ...] = ()
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
            and not self.explicit_path_prefixes
            and not self.domain_path_prefixes
            and not self.source_types
            and self.include_archived
            and self.include_quarantine
            and not self.excluded_temporal_paths
        )

    def is_path_in_scope(self, rel_path: str, note_type: str | None = None) -> bool:
        """Check whether a relative path and optional note type satisfy this scope.

        Least-privilege algebra: OR within one dimension, AND across
        independent dimensions. Adding a restriction never broadens eligibility.
        """
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

        # 3a. Domain dimension (union inside dimension)
        domain_prefixes = self.domain_path_prefixes or ()
        if domain_prefixes and not _matches_any_prefix(clean, domain_prefixes):
            return False

        # 3b. Explicit path dimension (union inside dimension, AND across dimensions)
        explicit_prefixes = self.explicit_path_prefixes or ()
        if explicit_prefixes and not _matches_any_prefix(clean, explicit_prefixes):
            return False

        # 3c. Legacy combined list (defense in depth; must also pass if present).
        # When separated dimensions are populated, the combined check is
        # redundant but retained to prevent accidental widening via stale callers.
        # NOTE: combined OR alone would be insufficient when both dimensions are
        # present, so separated checks above are authoritative.
        if (
            not domain_prefixes
            and not explicit_prefixes
            and self.path_prefixes
            and not _matches_any_prefix(clean, self.path_prefixes)
        ):
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
        """Generate SQL WHERE clauses and parameters for pushdown filtering.

        Union inside each path dimension, intersection across dimensions:
        (domain A OR domain B) AND (path X OR path Y).
        """
        clauses: list[str] = []
        params: list[Any] = []

        # 1. Path dimensions (AND across dimensions)
        domain_prefixes = self.domain_path_prefixes or ()
        explicit_prefixes = self.explicit_path_prefixes or ()
        if domain_prefixes or explicit_prefixes:
            if domain_prefixes:
                domain_clause = _build_prefix_or_clause(domain_prefixes, rel_path_col, params)
                if domain_clause:
                    clauses.append(domain_clause)
            if explicit_prefixes:
                explicit_clause = _build_prefix_or_clause(explicit_prefixes, rel_path_col, params)
                if explicit_clause:
                    clauses.append(explicit_clause)
        elif self.path_prefixes:
            # Legacy fallback for scopes compiled before dimension split.
            legacy_clause = _build_prefix_or_clause(self.path_prefixes, rel_path_col, params)
            if legacy_clause:
                clauses.append(legacy_clause)

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
        """Generate SQL condition for chunk_embeddings (AND across path dimensions)."""
        col = f"{chunk_alias}.rel_path" if chunk_alias else "rel_path"
        clauses: list[str] = []
        params: list[Any] = []

        # 1. Path dimensions (AND across dimensions)
        domain_prefixes = self.domain_path_prefixes or ()
        explicit_prefixes = self.explicit_path_prefixes or ()
        if domain_prefixes or explicit_prefixes:
            if domain_prefixes:
                domain_clause = _build_prefix_or_clause(domain_prefixes, col, params)
                if domain_clause:
                    clauses.append(domain_clause)
            if explicit_prefixes:
                explicit_clause = _build_prefix_or_clause(explicit_prefixes, col, params)
                if explicit_clause:
                    clauses.append(explicit_clause)
        elif self.path_prefixes:
            legacy_clause = _build_prefix_or_clause(self.path_prefixes, col, params)
            if legacy_clause:
                clauses.append(legacy_clause)

        # 2. Archive exclusion
        if not self.include_archived:
            clauses.append(f"({col} != '04_Archive' AND {col} NOT LIKE '04_Archive/%' ESCAPE '\\')")
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
    """Compute a deterministic digest of effective scope for cache keys.

    Distinguishes domain dimension, explicit path dimension, source types,
    temporal boundary, and archive/quarantine access. Two semantically
    different scopes must never share a cache key.
    """
    if resolved is None or resolved.is_empty():
        return None
    data = {
        "domain_ids": sorted(resolved.domain_ids),
        "domain_path_prefixes": sorted(resolved.domain_path_prefixes or ()),
        "explicit_path_prefixes": sorted(resolved.explicit_path_prefixes or ()),
        "path_prefixes": sorted(resolved.path_prefixes),
        "source_types": sorted(resolved.source_types),
        "temporal_view": resolved.temporal_view,
        "as_of": str(resolved.as_of),
        "include_archived": resolved.include_archived,
        "include_quarantine": resolved.include_quarantine,
        "excluded_temporal_paths": sorted(resolved.excluded_temporal_paths),
    }
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode("utf-8")).hexdigest()


def scoped_note_type_from_index(vault_dir: Path, rel_path: str) -> str | None:
    """Return indexed note_type without reading source body (R1 fail-closed helper)."""
    try:
        from .generation_index import resolve_active_generation
        from .vault_storage import existing_vault_db_path

        vault_root = Path(vault_dir).expanduser().resolve()
        active = resolve_active_generation(vault_root)
        db_path = active.path if active is not None else existing_vault_db_path(vault_root)
    except Exception:
        logger.debug("scoped type lookup failed to resolve DB", exc_info=True)
        return None
    if db_path is None or not db_path.is_file():
        return None
    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
        conn.execute("PRAGMA query_only=ON")
        cur = conn.cursor()
        with contextlib.suppress(Exception):
            cur.execute("SELECT note_type FROM fts_notes WHERE rel_path = ?", (rel_path,))
            row = cur.fetchone()
            if row is not None and isinstance(row[0], str) and row[0]:
                return str(row[0])
        with contextlib.suppress(Exception):
            cur.execute("SELECT note_type FROM source_metadata WHERE rel_path = ?", (rel_path,))
            row = cur.fetchone()
            if row is not None and isinstance(row[0], str) and row[0]:
                return str(row[0])
    except Exception:
        logger.debug("scoped type lookup query failed", exc_info=True)
        return None
    finally:
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.close()
    return None


def eligible_graph_paths(
    vault_dir: Path, resolved_scope: ResolvedSearchScope | None
) -> set[str] | None:
    """Derive eligible graph sources without reading bodies (scope before build)."""
    if resolved_scope is None:
        return None
    vault_root = Path(vault_dir).expanduser().resolve()
    eligible: set[str] = set()
    for fp in iter_vault_markdown_files(vault_root):
        if fp.name in ("index.md", "log.md", "_index.md") or is_catalog_filename(fp.name):
            continue
        rel = fp.relative_to(vault_root).as_posix()
        if not resolved_scope.is_path_in_scope(rel):
            continue
        if should_skip(vault_root, rel):
            continue
        if resolved_scope.source_types:
            t = scoped_note_type_from_index(vault_root, rel)
            if t is None or not resolved_scope.is_path_in_scope(rel, note_type=t):
                continue
        eligible.add(rel)
    return eligible


def compile_search_scope(
    vault_dir: Path,
    scope: SearchScope | None = None,
    domain: str | None = None,
    temporal_view: str = "current",
    as_of: date | str | None = None,
    access_policy: AccessPolicy | None = None,
    resolved_db: Any = None,
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

    # 4. Resolve explicit path prefixes (caller restriction, union inside dimension).
    # Domain-derived prefixes are stored separately so cross-dimension
    # enforcement is intersection, not union. Adding a restriction never widens.
    explicit_prefixes: list[str] = []
    if scope and scope.path_prefixes:
        for p in scope.path_prefixes:
            cleaned = str(p).strip().strip("/")
            if cleaned:
                explicit_prefixes.append(cleaned)
    dedup_explicit: list[str] = []
    seen_explicit: set[str] = set()
    for p in explicit_prefixes:
        if p not in seen_explicit:
            seen_explicit.add(p)
            dedup_explicit.append(p)

    dedup_domain: list[str] = []
    seen_domain: set[str] = set()
    for p in domain_prefixes:
        if p not in seen_domain:
            seen_domain.add(p)
            dedup_domain.append(p)

    # Legacy combined union retained for observability only.
    combined: list[str] = []
    seen_combined: set[str] = set()
    for p in [*dedup_explicit, *dedup_domain]:
        if p not in seen_combined:
            seen_combined.add(p)
            combined.append(p)

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
        path_prefixes=tuple(combined),
        explicit_path_prefixes=tuple(dedup_explicit),
        domain_path_prefixes=tuple(dedup_domain),
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
