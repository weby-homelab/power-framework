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
from .indexer import (
    generate_index_content,
    generate_main_index_content,
    generate_sub_index_content,
    run_generate_hierarchical_index,
    run_generate_index,
    run_generate_sub_index,
    scan_folder_notes,
    scan_vault_notes,
)
from .linter import LintResult, run_lint_report, run_lint_vault
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
from .searcher import SearchResult, format_search_results, search_vault
from .utils import (
    __version__,
    atomic_write,
    clean_note_name,
    create_backup,
    resolve_vault_path,
    validate_vault_path,
)

__all__ = [
    "MAX_DESCRIPTION_LENGTH",
    "MAX_TITLE_LENGTH",
    "NOTE_TYPE_ORDER",
    "PARA_FOLDERS",
    "VAULT_STRUCTURE",
    "LintResult",
    "NoteFile",
    "NoteStatus",
    "NoteType",
    "OKFMetadata",
    "SearchResult",
    "__version__",
    "atomic_write",
    "build_frontmatter",
    "clean_note_name",
    "cli_main",
    "create_backup",
    "extract_frontmatter_raw",
    "format_search_results",
    "generate_index_content",
    "generate_main_index_content",
    "generate_sub_index_content",
    "has_frontmatter",
    "has_type_field",
    "parse_frontmatter",
    "read_file_content",
    "resolve_vault_path",
    "run_generate_hierarchical_index",
    "run_generate_index",
    "run_generate_sub_index",
    "run_lint_report",
    "run_lint_vault",
    "scan_folder_notes",
    "scan_vault_notes",
    "search_vault",
    "validate_metadata",
    "validate_vault_path",
]
