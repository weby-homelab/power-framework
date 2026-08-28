"""
P.O.W.E.R. Centralized Constants.

Single source of truth for exclusion lists, folder definitions,
and other shared configuration. Import from here instead of
duplicating across modules.
"""

from __future__ import annotations

EXCLUDED_DIRS: frozenset[str] = frozenset(
    {
        # System / framework managed directories
        ".git",
        ".backups",
        "05_Templates",
        "scratch",
        ".system_generated",
        ".agents",
        # Third-party / vendored dependency trees (never OKF notes)
        "node_modules",
        ".venv",
        "venv",
        "vendor",
        "site-packages",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        # Foreign tool / agent configuration of other projects
        ".claude",
        ".github",
    }
)

EXCLUDED_ORPHAN_FILES: frozenset[str] = frozenset(
    {
        "README.md",
        "Home.md",
        "index.md",
        "_index.md",
        "log.md",
        "Successor-Hub.md",
        "PARA-OKF-LLM_Wiki.md",
        "Weby_PARA-OKF-LLM_Wiki.md",
    }
)

PARA_FOLDERS_: tuple[str, ...] = (
    "00_Inbox",
    "01_Projects",
    "02_Areas",
    "03_Resources",
    "04_Archive",
    "06_Daily_Logs",
)

# Folders that belong to the navigable knowledge catalog. ``PROTOCOLS`` is
# intentionally separate from PARA because it is a system-guide namespace,
# but it must still be indexed when it is part of the vault scope.
INDEX_FOLDERS: tuple[str, ...] = (*PARA_FOLDERS_, "PROTOCOLS")

# Generated catalog pages are deliberately bounded so the navigation map stays
# useful to agents even when a vault contains thousands of notes.
INDEX_MAX_BYTES = 32 * 1024

SKIP_FILES: frozenset[str] = frozenset({"index.md", "log.md", "_index.md", "POWER_STATUS.md"})

SYSTEM_SKIP_PARTS: tuple[str, ...] = (".git", "05_Templates", ".system_generated")

# Dense chunk IDs include their ordinal so repeated identical sections cannot
# overwrite one another in the globally keyed chunk_embeddings table.
DENSE_INDEX_SCHEMA_VERSION = "3"


def is_catalog_filename(filename: str) -> bool:
    """Return whether *filename* is a generated hierarchical catalog page."""
    if filename == "_index.md":
        return True
    if not (filename.startswith("_index-") and filename.endswith(".md")):
        return False
    return filename[len("_index-") : -len(".md")].isdigit()
