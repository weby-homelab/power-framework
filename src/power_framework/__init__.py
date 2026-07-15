"""
P.O.W.E.R. Framework — AI-native toolkit for Second Brain knowledge bases.

Modules:
    power_framework.core — Core library (models, parser, linter, searcher, indexer, CLI)
    power_framework.mcp  — MCP server for AI agent integration
"""

from __future__ import annotations

from .core import cli_main
from .core.healer import heal_frontmatter, heal_vault
from .core.indexer import (
    generate_log_initial,
    run_generate_hierarchical_index,
    run_generate_sub_index,
    scan_folder_notes,
)
from .core.linter import archive_stale_notes, run_lint_report, run_rot_report, run_status_report
from .core.markdown_checks import check_all, fix_all
from .core.models import (
    MAX_DESCRIPTION_LENGTH,
    MAX_TITLE_LENGTH,
    NOTE_TYPE_ORDER,
    PARA_FOLDERS,
    VAULT_STRUCTURE,
    NoteFile,
    NoteType,
    OKFMetadata,
)
from .core.parser import build_frontmatter, read_file_content
from .core.relations import format_relation_suggestions, suggest_related
from .core.searcher import SearchResult, format_search_results, search_vault
from .core.utils import (
    RateLimiter,
    __version__,
    atomic_write,
    get_cache_dir,
    resolve_vault_path,
    validate_path_in_vault,
)

__all__ = [
    "MAX_DESCRIPTION_LENGTH",
    "MAX_TITLE_LENGTH",
    "NOTE_TYPE_ORDER",
    "PARA_FOLDERS",
    "VAULT_STRUCTURE",
    "NoteFile",
    "NoteType",
    "OKFMetadata",
    "RateLimiter",
    "SearchResult",
    "__version__",
    "archive_stale_notes",
    "atomic_write",
    "build_frontmatter",
    "check_all",
    "cli_main",
    "fix_all",
    "format_relation_suggestions",
    "format_search_results",
    "generate_log_initial",
    "get_cache_dir",
    "heal_frontmatter",
    "heal_vault",
    "read_file_content",
    "resolve_vault_path",
    "run_generate_hierarchical_index",
    "run_generate_sub_index",
    "run_lint_report",
    "run_rot_report",
    "run_status_report",
    "scan_folder_notes",
    "search_vault",
    "suggest_related",
    "validate_path_in_vault",
]
