#!/usr/bin/env python3
"""
P.O.W.E.R. Hierarchical Index Generator Script.

Standalone CLI wrapper around power_core.indexer for generating the vault catalog.
Generates a navigation map (index.md) plus per-folder _index.md files.

Usage:
    python generate_index.py [vault_path]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from power_framework.core import (
    run_generate_hierarchical_index,
    generate_log_initial,
    scan_folder_notes,
)

script_dir = os.path.dirname(os.path.abspath(__file__))


def resolve_vault_dir() -> Path:
    """Determine vault directory from script location or command-line argument."""
    vault_dir = Path(os.getcwd()).resolve()

    if ".agents" in script_dir:
        idx = script_dir.find(".agents")
        workspace_root = script_dir[:idx].rstrip("/")
        brain_path = Path(workspace_root) / "brain"
        if brain_path.is_dir():
            vault_dir = brain_path.resolve()
        else:
            vault_dir = Path(workspace_root).resolve()
    elif "03_Resources" in script_dir:
        idx = script_dir.find("03_Resources")
        vault_dir = Path(script_dir[:idx].rstrip("/")).resolve()

    if len(sys.argv) > 1 and os.path.isdir(sys.argv[1]):
        vault_dir = Path(sys.argv[1]).resolve()

    return vault_dir


def main() -> None:
    """Generate hierarchical index (index.md + _index.md files) and optionally initialize log.md."""
    vault_dir = resolve_vault_dir()

    if not vault_dir.exists():
        print(f"Error: Vault directory does not exist: {vault_dir}")
        sys.exit(1)

    result = run_generate_hierarchical_index(vault_dir)
    print(result)

    folder_notes = scan_folder_notes(vault_dir)
    total = sum(len(notes) for notes in folder_notes.values())
    generate_log_initial(vault_dir, total)


if __name__ == "__main__":
    main()
