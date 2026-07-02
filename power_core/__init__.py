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
    NoteFile,
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
from .utils import (
    __version__,
    atomic_write,
    clean_note_name,
    create_backup,
    resolve_vault_path,
    validate_vault_path,
)

__all__ = [
    "__version__",
    "OKFMetadata",
    "NoteType",
    "NoteFile",
    "NOTE_TYPE_ORDER",
    "MAX_TITLE_LENGTH",
    "MAX_DESCRIPTION_LENGTH",
    "LintResult",
    "run_generate_index",
    "run_generate_hierarchical_index",
    "run_generate_sub_index",
    "run_lint_vault",
    "run_lint_report",
    "scan_vault_notes",
    "scan_folder_notes",
    "generate_index_content",
    "generate_main_index_content",
    "generate_sub_index_content",
    "validate_metadata",
    "parse_frontmatter",
    "extract_frontmatter_raw",
    "build_frontmatter",
    "has_frontmatter",
    "has_type_field",
    "read_file_content",
    "validate_vault_path",
    "resolve_vault_path",
    "atomic_write",
    "create_backup",
    "clean_note_name",
    "cli_main",
]
