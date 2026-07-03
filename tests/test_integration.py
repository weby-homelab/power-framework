"""
Integration tests for P.O.W.E.R. full cycle: init → ingest → lint → index.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from power_framework.core.cli import main
from power_framework.core.indexer import run_generate_hierarchical_index
from power_framework.core.linter import run_lint_report

if TYPE_CHECKING:
    from pathlib import Path


def test_full_cycle_init_ingest_lint_index(tmp_path: Path) -> None:
    vault = tmp_path / "integration_vault"

    # Step 1: init
    with patch.object(sys, "argv", ["power", "init", str(vault)]), pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert vault.exists()
    assert (vault / "01_Projects").is_dir()

    # Step 2: ingest a note
    with (
        patch.object(
            sys,
            "argv",
            [
                "power",
                "ingest",
                str(vault),
                "--type",
                "Project",
                "--title",
                "Integration Test",
                "--description",
                "A project created during integration test",
            ],
        ),
        pytest.raises(SystemExit) as exc,
    ):
        main()
    assert exc.value.code == 0
    note = vault / "01_Projects" / "integration_test.md"
    assert note.exists()

    # Step 3: update the first note to link to a resource, then create it
    note.write_text(
        """---
type: Project
title: "Integration Test"
description: "A project created during integration test"
timestamp: 2026-07-03T00:00:00
---

# Integration Test

Main project note. Links to [[linked_resource]].
"""
    )

    linked_note = vault / "03_Resources" / "linked_resource.md"
    linked_note.write_text(
        """---
type: Resource
title: "Linked Resource"
description: "A resource linked to the project"
timestamp: 2026-07-03T00:00:00
---

# Linked Resource

Linked from [[integration_test]].
"""
    )

    # Step 4: run index to generate proper index.md with frontmatter
    index_result = run_generate_hierarchical_index(vault)
    assert "index.md" in index_result
    assert (vault / "index.md").exists()
    assert (vault / "01_Projects" / "_index.md").exists()

    # Step 5: lint — index.md now has frontmatter after generation
    lint_report = run_lint_report(vault)
    assert "OK: Vault is completely healthy" in lint_report

    # Step 6: verify sub-index has our notes
    projects_index = (vault / "01_Projects" / "_index.md").read_text(encoding="utf-8")
    assert "Integration Test" in projects_index
    resources_index = (vault / "03_Resources" / "_index.md").read_text(encoding="utf-8")
    assert "Linked Resource" in resources_index


def test_init_then_lint_broken_vault(tmp_path: Path) -> None:
    vault = tmp_path / "broken_integration"

    # init
    with patch.object(sys, "argv", ["power", "init", str(vault)]), pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0

    # Run index first to generate index.md with frontmatter
    run_generate_hierarchical_index(vault)

    # Add a note without frontmatter
    broken = vault / "01_Projects" / "Broken.md"
    broken.write_text("# Broken Note\n\nNo frontmatter here.\n")

    # lint should find the issue
    lint_report = run_lint_report(vault)
    assert "Missing/Invalid" in lint_report or "WARNING" in lint_report
