"""Shared application-boundary contracts for direct callers and transports."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from power_framework.core.application import ApplicationService, RequestContext

if TYPE_CHECKING:
    from pathlib import Path


def test_retrieve_envelope_is_bounded_and_content_free_receipt(sample_vault: Path) -> None:
    audit = []
    service = ApplicationService(sample_vault, audit_hook=audit.append)

    envelope = service.retrieve("Test", max_results=3, context=RequestContext(actor="test"))
    payload = envelope.as_dict()

    assert payload["schema_version"] == "power.application.v2"
    assert payload["operation"] == "retrieve"
    assert payload["request_id"] == payload["receipt"]["request_id"]
    assert payload["actual_capability"]
    assert "source_revision" in payload
    assert payload["data"]["trust"] == "untrusted"
    assert payload["data"]["data_only"] is True
    assert payload["receipt"]["data_sha256"]
    assert len(audit) == 1
    assert "Test" not in json.dumps(audit[0].as_dict())


def test_propose_apply_share_idempotent_application_contract(sample_vault: Path) -> None:
    service = ApplicationService(sample_vault)
    content = (
        '---\ntype: Project\ntitle: "Application boundary"\n'
        'description: "shared use case"\ntimestamp: 2026-08-11T00:00:00Z\n---\n'
    )
    proposal = service.propose(
        "01_Projects/ApplicationBoundary.md",
        content,
        context=RequestContext(actor="test", authority="propose", idempotency_key="proposal-1"),
    )
    assert proposal.status == "ok"
    receipt = service.apply(
        proposal.data,
        approved=True,
        context=RequestContext(actor="test", authority="apply", idempotency_key="proposal-1"),
    )
    assert receipt.data["search_mode"] == "fts"
    replay = service.apply(
        proposal.data,
        approved=True,
        context=RequestContext(actor="test", authority="apply", idempotency_key="proposal-1"),
    )
    assert replay.data == receipt.data


def test_optional_fleet_is_explicitly_unavailable(sample_vault: Path) -> None:
    result = ApplicationService(sample_vault).fleet_status()

    assert result.status == "unavailable"
    assert result.data["safe_fallback"] == "local_fts"


def test_apply_requires_authority_and_approval(sample_vault: Path) -> None:
    with pytest.raises(PermissionError):
        ApplicationService(sample_vault).apply(
            {}, approved=True, context=RequestContext(authority="propose")
        )


def test_application_task_facade_uses_canonical_task_store(sample_vault: Path) -> None:
    """The generic application task use case no longer creates legacy work packets."""
    service = ApplicationService(sample_vault)
    created = service.task(
        action="create",
        task_id="application-task",
        values={"title": "Application task", "objective": "Canonical task truth"},
        context=RequestContext(actor="test", authority="propose"),
    )

    transitioned = service.task(
        action="advance",
        task_id="application-task",
        values={"new_state": "ready", "expected_revision": 1},
        context=RequestContext(actor="test", authority="apply"),
    )

    assert created.data["revision"] == 1
    assert transitioned.data["state"] == "ready"
    assert (sample_vault / ".power" / "tasks" / "application-task.json").is_file()
    assert not (sample_vault / ".power" / "work-packets").exists()
