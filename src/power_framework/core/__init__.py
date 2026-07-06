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

from .cli import main as cli_main
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
from .relations import RelationSuggestion, format_relation_suggestions, suggest_related
from .rot_scoring import (
    TYPE_HALF_LIFE_DAYS,
    ContentDedupDetector,
    FreshnessScorer,
    LinkRotChecker,
    UsageTracker,
)
from .searcher import SearchResult, format_search_results, search_vault
from .utils import (
    RateLimiter,
    __version__,
    atomic_write,
    clean_note_name,
    create_backup,
    get_cache_dir,
    resolve_vault_path,
    validate_path_in_vault,
    validate_vault_path,
)

__all__ = [
    "MAX_DESCRIPTION_LENGTH",
    "MAX_TITLE_LENGTH",
    "NOTE_TYPE_ORDER",
    "PARA_FOLDERS",
    "TYPE_HALF_LIFE_DAYS",
    "VAULT_STRUCTURE",
    "ContentDedupDetector",
    "FreshnessScorer",
    "LinkRotChecker",
    "LintResult",
    "NoteFile",
    "NoteStatus",
    "NoteType",
    "OKFMetadata",
    "ROTResult",
    "RateLimiter",
    "RelationSuggestion",
    "SearchResult",
    "UsageTracker",
    "__version__",
    "archive_stale_notes",
    "atomic_write",
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
    "generate_index_content",
    "generate_log_initial",
    "generate_main_index_content",
    "generate_sub_index_content",
    "get_cache_dir",
    "has_frontmatter",
    "has_type_field",
    "heal_frontmatter",
    "heal_vault",
    "parse_frontmatter",
    "read_file_content",
    "resolve_vault_path",
    "run_generate_hierarchical_index",
    "run_generate_index",
    "run_generate_sub_index",
    "run_lint_report",
    "run_lint_vault",
    "run_rot_audit",
    "run_rot_report",
    "scan_folder_notes",
    "scan_vault_notes",
    "search_vault",
    "suggest_related",
    "validate_metadata",
    "validate_path_in_vault",
    "validate_vault_path",
]
