"""
P.O.W.E.R. Centralized Constants.

Single source of truth for exclusion lists, folder definitions,
and other shared configuration. Import from here instead of
duplicating across modules.
"""

from __future__ import annotations

EXCLUDED_DIRS: frozenset[str] = frozenset(
    {".git", "05_Templates", "scratch", ".system_generated", ".agents"}
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

SKIP_FILES: frozenset[str] = frozenset({"index.md", "log.md", "_index.md"})

SYSTEM_SKIP_PARTS: tuple[str, ...] = (".git", "05_Templates", ".system_generated")
