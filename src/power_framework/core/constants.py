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

SKIP_FILES: frozenset[str] = frozenset({"index.md", "log.md", "_index.md"})

SYSTEM_SKIP_PARTS: tuple[str, ...] = (".git", "05_Templates", ".system_generated")
