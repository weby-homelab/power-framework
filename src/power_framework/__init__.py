"""
P.O.W.E.R. Framework — AI-native toolkit for Obsidian knowledge bases.

Modules:
    power_framework.core — Core library (models, parser, linter, searcher, indexer, CLI)
    power_framework.mcp  — MCP server for AI agent integration
"""

from __future__ import annotations

from .core import cli_main
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
from .core.searcher import SearchResult
from .core.utils import __version__

__all__ = [
    "MAX_DESCRIPTION_LENGTH",
    "MAX_TITLE_LENGTH",
    "NOTE_TYPE_ORDER",
    "PARA_FOLDERS",
    "VAULT_STRUCTURE",
    "NoteFile",
    "NoteType",
    "OKFMetadata",
    "SearchResult",
    "__version__",
    "cli_main",
]
