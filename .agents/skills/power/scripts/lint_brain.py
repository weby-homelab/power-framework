#!/usr/bin/env python3
"""
P.O.W.E.R. Vault Linter Script.

Standalone CLI wrapper around power_core.linter for health checking the vault.
Checks for broken links, missing metadata, and orphan notes.

Usage:
    python lint_brain.py [vault_path]
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from power_framework.core import run_lint_vault

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
    """Run lint and print health report."""
    vault_dir = resolve_vault_dir()

    if not vault_dir.exists():
        print(f"Error: Vault directory does not exist: {vault_dir}")
        sys.exit(1)

    result = run_lint_vault(vault_dir)
    print(result.format_report(vault_dir))
    sys.exit(1 if result.has_blocking_issues else 0)


if __name__ == "__main__":
    main()
