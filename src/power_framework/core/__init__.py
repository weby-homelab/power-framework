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

from .chunker import SemanticChunker
from .cli import main as cli_main
from .embeddings import get_embedding_manager
from .healer import heal_frontmatter, heal_vault
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
from .models import (
    MAX_DESCRIPTION_LENGTH,
    MAX_TITLE_LENGTH,
    NOTE_TYPE_ORDER,
    PARA_FOLDERS,
    VAULT_STRUCTURE,
    NoteFile,
    NoteStatus,
    NoteType,
    OKFMetadata,
    TypedRelation,
)
from .parser import (
    build_frontmatter,
    extract_frontmatter_raw,
    has_frontmatter,
    has_type_field,
    parse_frontmatter,
    read_file_content,
    validate_metadata,
)
from .query_expansion import QueryExpander
from .relations import (
    KnowledgeGraph,
    RelationSuggestion,
    format_relation_suggestions,
    suggest_related,
)
from .reranker import RerankerManager
from .rot_scoring import (
    TYPE_HALF_LIFE_DAYS,
    ContentDedupDetector,
    ContradictionDetector,
    FreshnessScorer,
    LinkRotChecker,
    UsageTracker,
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
from .utils import (
    RateLimiter,
    __version__,
    atomic_write,
    atomic_write_in_vault,
    clean_note_name,
    create_backup,
    get_cache_dir,
    resolve_path_in_vault,
    resolve_vault_path,
    validate_path_in_vault,
    validate_vault_path,
)

EmbeddingManager = get_embedding_manager  # backward compat alias

__all__ = [
    "CANONICAL_SEARCH_MODES",
    "DEFAULT_SEARCH_MODE",
    "MAX_DESCRIPTION_LENGTH",
    "MAX_TITLE_LENGTH",
    "NOTE_TYPE_ORDER",
    "PARA_FOLDERS",
    "SEARCH_MODE_ALIASES",
    "TYPE_HALF_LIFE_DAYS",
    "VAULT_STRUCTURE",
    "ContentDedupDetector",
    "ContradictionDetector",
    "EmbeddingManager",
    "FreshnessScorer",
    "KnowledgeGraph",
    "LinkRotChecker",
    "LintResult",
    "NoteFile",
    "NoteStatus",
    "NoteType",
    "OKFMetadata",
    "QueryExpander",
    "ROTResult",
    "RateLimiter",
    "RelationSuggestion",
    "RerankerManager",
    "SearchResult",
    "SemanticChunker",
    "TypedRelation",
    "UsageTracker",
    "__version__",
    "archive_stale_notes",
    "atomic_write",
    "atomic_write_in_vault",
    "build_frontmatter",
    "check_all",
    "check_code_block_language",
    "check_header_jumps",
    "check_list_markers",
    "check_trailing_whitespace",
    "clean_note_name",
    "cli_main",
    "create_backup",
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
    "has_frontmatter",
    "has_type_field",
    "heal_frontmatter",
    "heal_vault",
    "normalize_search_mode",
    "parse_frontmatter",
    "read_file_content",
    "resolve_path_in_vault",
    "resolve_vault_path",
    "run_generate_hierarchical_index",
    "run_generate_index",
    "run_generate_sub_index",
    "run_lint_report",
    "run_lint_vault",
    "run_rot_audit",
    "run_rot_report",
    "run_status_report",
    "scan_folder_notes",
    "scan_vault_notes",
    "search_vault",
    "suggest_related",
    "validate_metadata",
    "validate_path_in_vault",
    "validate_vault_path",
]
