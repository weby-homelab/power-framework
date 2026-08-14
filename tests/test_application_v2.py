"""Unit and contract tests for POWER Application API v2 and SourceService."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from power_framework.core.application import ApplicationService
from power_framework.core.application_models import (
    SourceListRequest,
)
from power_framework.core.source_service import (
    normalize_rel_path,
    resolve_safe_vault_path,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def temp_vault(tmp_path: Path) -> Path:
    """Create a hermetic temporary vault structure."""
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / ".power").mkdir()
    (vault / "01_Projects").mkdir()
    (vault / "02_Areas").mkdir()
    (vault / "03_Resources").mkdir()

    # Create test notes with OKF metadata
    note1 = vault / "01_Projects" / "Project_Alpha.md"
    note1.write_text(
        """---
type: Project
title: "Project Alpha"
description: "Core test project"
tags: [alpha, power]
timestamp: 2026-08-13T12:00:00+00:00
---

# Project Alpha
This links to [[Resource_Beta]].
""",
        encoding="utf-8",
    )

    note2 = vault / "03_Resources" / "Resource_Beta.md"
    note2.write_text(
        """---
type: Resource
title: "Resource Beta"
description: "Reference material"
tags: [beta, reference]
timestamp: 2026-08-13T12:00:00+00:00
---

# Resource Beta
Reference content.
""",
        encoding="utf-8",
    )

    return vault


def test_path_normalization_and_containment(temp_vault: Path) -> None:
    """Ensure path normalization and traversal prevention work fail-closed."""
    assert normalize_rel_path("01_Projects/Note.md") == "01_Projects/Note.md"
    assert normalize_rel_path("/01_Projects/Note.md") == "01_Projects/Note.md"
    assert normalize_rel_path("01_Projects\\Note.md") == "01_Projects/Note.md"

    with pytest.raises(PermissionError, match="Path traversal"):
        normalize_rel_path("../secrets.env")

    with pytest.raises(PermissionError, match="Path traversal"):
        normalize_rel_path("01_Projects/../../etc/passwd")

    with pytest.raises(PermissionError, match="Path traversal detected"):
        resolve_safe_vault_path(temp_vault, "../outside.md")


def test_source_list_and_pagination(temp_vault: Path) -> None:
    """Test listing sources with filters and pagination."""
    service = ApplicationService(temp_vault)

    # List all
    env = service.source_list()
    assert env.status == "ok"
    assert env.data["total_count"] == 2
    assert len(env.data["items"]) == 2

    # Filter by category
    env_cat = service.source_list(SourceListRequest(category="01_Projects"))
    assert len(env_cat.data["items"]) == 1
    assert env_cat.data["items"][0]["rel_path"] == "01_Projects/Project_Alpha.md"

    # Filter by tag
    env_tag = service.source_list(SourceListRequest(tag="beta"))
    assert len(env_tag.data["items"]) == 1
    assert env_tag.data["items"][0]["title"] == "Resource Beta"


def test_source_read_and_etag(temp_vault: Path) -> None:
    """Test reading source content with ETag and hash verification."""
    service = ApplicationService(temp_vault)
    env = service.source_read("01_Projects/Project_Alpha.md")
    assert env.status == "ok"
    assert env.data["rel_path"] == "01_Projects/Project_Alpha.md"
    assert "Project Alpha" in env.data["content"]
    assert env.data["etag"]
    assert env.data["sha256"]
    assert env.data["metadata"]["type"] == "Project"

    # Non-existent file
    with pytest.raises(FileNotFoundError):
        service.source_read("01_Projects/NonExistent.md")


def test_source_stats(temp_vault: Path) -> None:
    """Test aggregated vault statistics."""
    service = ApplicationService(temp_vault)
    env = service.source_stats()
    assert env.status == "ok"
    assert env.data["total_notes"] == 2
    assert env.data["category_counts"]["01_Projects"] == 1
    assert env.data["category_counts"]["03_Resources"] == 1


def test_graph_projection(temp_vault: Path) -> None:
    """Test graph projection extracts nodes and edges."""
    service = ApplicationService(temp_vault)
    env = service.source_graph()
    assert env.status == "ok"
    assert env.data["total_nodes"] == 2
    assert env.data["total_edges"] == 1
    edge = env.data["edges"][0]
    assert edge["source"] == "01_Projects/Project_Alpha.md"
    assert edge["target"] == "03_Resources/Resource_Beta.md"
