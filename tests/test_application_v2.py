"""Unit and contract tests for POWER Application API v2 and SourceService."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from power_framework.core import source_service
from power_framework.core.application import ApplicationService, RequestContext
from power_framework.core.application_models import (
    DecisionDTO,
    SourceListRequest,
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
    assert source_service.normalize_rel_path("01_Projects/Note.md") == "01_Projects/Note.md"
    assert source_service.normalize_rel_path("/01_Projects/Note.md") == "01_Projects/Note.md"
    assert source_service.normalize_rel_path("01_Projects\\Note.md") == "01_Projects/Note.md"

    with pytest.raises(PermissionError, match="Path traversal"):
        source_service.normalize_rel_path("../secrets.env")

    with pytest.raises(PermissionError, match="Path traversal"):
        source_service.normalize_rel_path("01_Projects/../../etc/passwd")

    with pytest.raises(PermissionError, match="Path traversal detected"):
        source_service.resolve_safe_vault_path(temp_vault, "../outside.md")


def test_read_only_application_service_does_not_create_task_namespace(temp_vault: Path) -> None:
    """Constructing and using read APIs must not materialize task storage."""
    tasks_dir = temp_vault / ".power" / "tasks"
    service = ApplicationService(temp_vault)

    service.source_read("01_Projects/Project_Alpha.md")

    assert not tasks_dir.exists()


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
    """Test reading source content with ETag, hash verification, and stem resolution."""
    service = ApplicationService(temp_vault)
    env = service.source_read("01_Projects/Project_Alpha.md")
    assert env.status == "ok"
    assert env.data["rel_path"] == "01_Projects/Project_Alpha.md"
    assert "Project Alpha" in env.data["content"]
    assert env.data["etag"]
    assert env.data["sha256"]
    assert env.data["metadata"]["type"] == "Project"

    # Wikilink / stem resolution without folder and without .md
    env_stem = service.source_read("Project_Alpha")
    assert env_stem.status == "ok"
    assert env_stem.data["rel_path"] == "01_Projects/Project_Alpha.md"

    env_stem2 = service.source_read("Resource_Beta")
    assert env_stem2.status == "ok"
    assert env_stem2.data["rel_path"] == "03_Resources/Resource_Beta.md"

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


def test_source_stats_fallback_vault_id(monkeypatch: pytest.MonkeyPatch, temp_vault: Path) -> None:
    """Test that get_source_stats falls back to 'default' if identity resolution fails."""

    def fail_identity(_root: Path) -> None:
        raise OSError("Permission denied")

    monkeypatch.setattr(source_service, "ensure_vault_identity", fail_identity)
    stats = source_service.get_source_stats(temp_vault)
    assert stats.vault_id == "default"
    assert stats.total_notes == 2


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


def test_decision_api_binds_authority_and_returns_durable_receipt(temp_vault: Path) -> None:
    """Decision API v2 must preserve domain bindings across the application boundary."""
    service = ApplicationService(temp_vault)
    service.task_create(
        "task_application_decision",
        "Application decision",
        state="working",
        context=RequestContext(actor="agent-1", authority="propose"),
    )
    created = service.decision_create(
        decision_id="dec_application",
        task_id="task_application_decision",
        title="Approve exact proposal",
        proposal_id="proposal-application",
        proposal_sha256="a" * 64,
        allowed_actors=["operator-1"],
        context=RequestContext(actor="agent-1", authority="propose"),
    )
    assert created.schema_version == "power.application.v2"
    assert DecisionDTO.model_validate(created.data).status == "pending"

    listed = service.decision_list(status="pending")
    assert [item["decision_id"] for item in listed.data["items"]] == ["dec_application"]
    assert service.decision_read("dec_application").data == created.data

    with pytest.raises(PermissionError, match="insufficient authority"):
        service.decision_resolve(
            "dec_application",
            action="approve",
            proposal_sha256="a" * 64,
            context=RequestContext(actor="operator-1", authority="propose"),
        )

    resolved = service.decision_resolve(
        "dec_application",
        action="approve",
        proposal_sha256="a" * 64,
        context=RequestContext(actor="operator-1", authority="apply"),
    )
    assert resolved.data["decision"]["status"] == "approved"
    assert resolved.data["receipt"]["receipt_id"].startswith("dcr_")
