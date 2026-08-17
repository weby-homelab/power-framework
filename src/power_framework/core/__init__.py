"""
P.O.W.E.R. Core Library.

Shared functionality for the P.O.W.E.R. Knowledge Management Framework:
- OKF metadata validation (Pydantic models)
- Safe YAML frontmatter parsing
- Vault indexing and catalog generation
- Health linting (broken links, orphans, metadata)
- Path traversal protection and atomic writes

Usage:
    from power_core import OKFMetadata, run_generate_index, run_lint_report
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

from .application import ApplicationEnvelope, ApplicationService, AuditReceipt, RequestContext
from .chunker import SemanticChunker
from .connect import ConnectPlan, apply_connect_plan, build_connect_plan
from .control_plane import (
    build_control_plane,
    build_obsidian_base,
    remove_obsidian_base,
    write_control_plane,
    write_obsidian_base,
)
from .handoff import (
    WorkPacket,
    WorkPacketState,
    advance_work_packet,
    create_work_packet,
    list_work_packets,
    read_work_packet,
)
from .healer import HealFailure, HealReport, heal_frontmatter, heal_vault, heal_vault_report
from .health_loop import HealthCycle, HealthLoop, HealthNotification
from .indexer import (
    generate_index_content,
    generate_log_initial,
    generate_main_index_content,
    generate_sub_index_content,
    run_generate_hierarchical_index,
    run_generate_index,
    run_generate_sub_index,
    scan_folder_notes,
    scan_vault_notes,
)
from .lifecycle import LifecycleAdapter, LifecycleCapability, LifecycleEnvelope, capability_matrix
from .linter import (
    LintResult,
    ROTResult,
    archive_stale_notes,
    run_lint_report,
    run_lint_vault,
    run_rot_audit,
    run_rot_report,
    run_status_report,
)
from .maintenance import (
    MaintenanceAction,
    MaintenancePlan,
    MaintenanceReceipt,
    apply_maintenance_plan,
    build_maintenance_plan,
)
from .markdown_checks import (
    check_all,
    check_code_block_language,
    check_header_jumps,
    check_list_markers,
    check_trailing_whitespace,
    fix_all,
    fix_list_markers,
    fix_trailing_whitespace,
)
from .memory_api import (
    apply_change,
    commit_note_change,
    get_context,
    propose_change,
    read_history,
    validate_state,
)
from .models import (
    MAX_DESCRIPTION_LENGTH,
    MAX_TITLE_LENGTH,
    NOTE_TYPE_ORDER,
    PARA_FOLDERS,
    VAULT_STRUCTURE,
    MemoryKind,
    MemoryMetadata,
    NoteFile,
    NoteStatus,
    NoteType,
    OKFMetadata,
    Sensitivity,
    TypedRelation,
    WritePolicy,
)
from .mutation import run_blocking, run_vault_mutation
from .parser import (
    build_frontmatter,
    extract_frontmatter_raw,
    has_frontmatter,
    has_type_field,
    parse_frontmatter,
    read_file_content,
    validate_metadata,
)
from .provenance import (
    PROVENANCE_SCHEMA_VERSION,
    EvidenceCapture,
    ProvenanceError,
    ProvenanceRecord,
    capture_bytes,
    capture_file,
    capture_file_to_store,
    is_stale,
    read_captured_evidence,
    same_content,
    verify_bytes,
)
from .searcher import (
    CANONICAL_SEARCH_MODES,
    DEFAULT_SEARCH_MODE,
    SEARCH_MODE_ALIASES,
    SearchResult,
    format_search_results,
    format_untrusted_search_envelope,
    normalize_search_mode,
    search_vault,
)
from .state_migration import (
    STATE_MIGRATION_SCHEMA,
    StateEntry,
    StateMigrationPlan,
    apply_state_migration_plan,
    build_state_migration_plan,
)
from .temporal import TemporalStatus, TemporalView, normalize_as_of, normalize_temporal_view
from .utils import (
    RateLimiter,
    __version__,
    atomic_write,
    atomic_write_in_vault,
    clean_note_name,
    create_backup,
    enforce_cpu_throttling_env,
    get_cache_dir,
    get_cpu_worker_limit,
    prune_backups,
    resolve_path_in_vault,
    resolve_vault_path,
    restore_backup,
    validate_path_in_vault,
    validate_vault_path,
)
from .write_queue import enqueue_write

if TYPE_CHECKING:
    from power_framework.experimental.embeddings import (  # noqa: N812
        get_embedding_manager as EmbeddingManager,
    )
    from power_framework.experimental.query_expansion import QueryExpander
    from power_framework.experimental.relations import (
        KnowledgeGraph,
        RelationSuggestion,
        format_relation_suggestions,
        suggest_related,
        suggest_related_semantic,
    )
    from power_framework.experimental.reranker import RerankerManager
    from power_framework.experimental.rot_scoring import (
        TYPE_HALF_LIFE_DAYS,
        ContentDedupDetector,
        ContradictionDetector,
        FreshnessScorer,
        LinkRotChecker,
        UsageTracker,
    )

    from .cli import main as cli_main

_OPTIONAL_EXPORTS = {
    "cli_main": ("power_framework.core.cli", "main"),
    "EmbeddingManager": ("power_framework.experimental.embeddings", "get_embedding_manager"),
    "QueryExpander": ("power_framework.experimental.query_expansion", "QueryExpander"),
    "KnowledgeGraph": ("power_framework.experimental.relations", "KnowledgeGraph"),
    "RelationSuggestion": ("power_framework.experimental.relations", "RelationSuggestion"),
    "format_relation_suggestions": (
        "power_framework.experimental.relations",
        "format_relation_suggestions",
    ),
    "suggest_related": ("power_framework.experimental.relations", "suggest_related"),
    "suggest_related_semantic": (
        "power_framework.experimental.relations",
        "suggest_related_semantic",
    ),
    "RerankerManager": ("power_framework.experimental.reranker", "RerankerManager"),
    "TYPE_HALF_LIFE_DAYS": ("power_framework.experimental.rot_scoring", "TYPE_HALF_LIFE_DAYS"),
    "ContentDedupDetector": (
        "power_framework.experimental.rot_scoring",
        "ContentDedupDetector",
    ),
    "ContradictionDetector": (
        "power_framework.experimental.rot_scoring",
        "ContradictionDetector",
    ),
    "FreshnessScorer": ("power_framework.experimental.rot_scoring", "FreshnessScorer"),
    "LinkRotChecker": ("power_framework.experimental.rot_scoring", "LinkRotChecker"),
    "UsageTracker": ("power_framework.experimental.rot_scoring", "UsageTracker"),
}


def __getattr__(name: str) -> object:
    """Load experimental and CLI compatibility exports only when requested."""
    target = _OPTIONAL_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value


__all__ = [
    "CANONICAL_SEARCH_MODES",
    "DEFAULT_SEARCH_MODE",
    "MAX_DESCRIPTION_LENGTH",
    "MAX_TITLE_LENGTH",
    "NOTE_TYPE_ORDER",
    "PARA_FOLDERS",
    "PROVENANCE_SCHEMA_VERSION",
    "SEARCH_MODE_ALIASES",
    "STATE_MIGRATION_SCHEMA",
    "TYPE_HALF_LIFE_DAYS",
    "VAULT_STRUCTURE",
    "ApplicationEnvelope",
    "ApplicationService",
    "AuditReceipt",
    "ConnectPlan",
    "ContentDedupDetector",
    "ContradictionDetector",
    "EmbeddingManager",
    "EvidenceCapture",
    "FreshnessScorer",
    "HealFailure",
    "HealReport",
    "HealthCycle",
    "HealthLoop",
    "HealthNotification",
    "KnowledgeGraph",
    "LifecycleAdapter",
    "LifecycleCapability",
    "LifecycleEnvelope",
    "LinkRotChecker",
    "LintResult",
    "MaintenanceAction",
    "MaintenancePlan",
    "MaintenanceReceipt",
    "MemoryKind",
    "MemoryMetadata",
    "NoteFile",
    "NoteStatus",
    "NoteType",
    "OKFMetadata",
    "ProvenanceError",
    "ProvenanceRecord",
    "QueryExpander",
    "ROTResult",
    "RateLimiter",
    "RelationSuggestion",
    "RequestContext",
    "RerankerManager",
    "SearchResult",
    "SemanticChunker",
    "Sensitivity",
    "StateEntry",
    "StateMigrationPlan",
    "TemporalStatus",
    "TemporalView",
    "TypedRelation",
    "UsageTracker",
    "WorkPacket",
    "WorkPacketState",
    "WritePolicy",
    "__version__",
    "advance_work_packet",
    "apply_change",
    "apply_connect_plan",
    "apply_maintenance_plan",
    "apply_state_migration_plan",
    "archive_stale_notes",
    "atomic_write",
    "atomic_write_in_vault",
    "build_connect_plan",
    "build_control_plane",
    "build_frontmatter",
    "build_maintenance_plan",
    "build_obsidian_base",
    "build_state_migration_plan",
    "capability_matrix",
    "capture_bytes",
    "capture_file",
    "capture_file_to_store",
    "check_all",
    "check_code_block_language",
    "check_header_jumps",
    "check_list_markers",
    "check_trailing_whitespace",
    "clean_note_name",
    "cli_main",
    "commit_note_change",
    "create_backup",
    "create_work_packet",
    "enforce_cpu_throttling_env",
    "enqueue_write",
    "extract_frontmatter_raw",
    "fix_all",
    "fix_list_markers",
    "fix_trailing_whitespace",
    "format_relation_suggestions",
    "format_search_results",
    "format_untrusted_search_envelope",
    "generate_index_content",
    "generate_log_initial",
    "generate_main_index_content",
    "generate_sub_index_content",
    "get_cache_dir",
    "get_context",
    "get_cpu_worker_limit",
    "has_frontmatter",
    "has_type_field",
    "heal_frontmatter",
    "heal_vault",
    "heal_vault_report",
    "is_stale",
    "list_work_packets",
    "normalize_as_of",
    "normalize_search_mode",
    "normalize_temporal_view",
    "parse_frontmatter",
    "propose_change",
    "prune_backups",
    "read_captured_evidence",
    "read_file_content",
    "read_history",
    "read_work_packet",
    "remove_obsidian_base",
    "resolve_path_in_vault",
    "resolve_vault_path",
    "restore_backup",
    "run_blocking",
    "run_generate_hierarchical_index",
    "run_generate_index",
    "run_generate_sub_index",
    "run_lint_report",
    "run_lint_vault",
    "run_rot_audit",
    "run_rot_report",
    "run_status_report",
    "run_vault_mutation",
    "same_content",
    "scan_folder_notes",
    "scan_vault_notes",
    "search_vault",
    "suggest_related",
    "suggest_related_semantic",
    "validate_metadata",
    "validate_path_in_vault",
    "validate_state",
    "validate_vault_path",
    "verify_bytes",
    "write_control_plane",
    "write_obsidian_base",
]
