"""
P.O.W.E.R. Framework — AI-native toolkit for Second Brain knowledge bases.

Modules:
    power_framework.core — Core library (models, parser, linter, searcher, indexer, CLI)
    power_framework.mcp  — MCP server for AI agent integration
"""

from __future__ import annotations

from importlib import import_module

from .core import ApplicationService, RequestContext
from .core.healer import HealFailure, HealReport, heal_frontmatter, heal_vault, heal_vault_report
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
    "ApplicationService",
    "HealFailure",
    "HealReport",
    "NoteFile",
    "NoteType",
    "OKFMetadata",
    "RateLimiter",
    "RequestContext",
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
    "heal_vault_report",
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

_LAZY_EXPORTS = {
    "cli_main": ("power_framework.core.cli", "main"),
    "format_relation_suggestions": (
        "power_framework.experimental.relations",
        "format_relation_suggestions",
    ),
    "suggest_related": ("power_framework.experimental.relations", "suggest_related"),
}


def __getattr__(name: str) -> object:
    """Load optional compatibility exports only when requested."""
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute_name = target
    value = getattr(import_module(module_name), attribute_name)
    globals()[name] = value
    return value
