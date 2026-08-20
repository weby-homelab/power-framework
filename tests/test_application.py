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


def test_request_context_rejects_invalid_authority_actor_and_request_id() -> None:
    """Invalid transport context metadata fails closed before a use case runs."""
    with pytest.raises(ValueError, match="actor"):
        RequestContext(actor="")
    with pytest.raises(ValueError, match="authority"):
        RequestContext(authority="execute")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="request_id"):
        RequestContext(request_id="/unsafe/request-id")


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


def test_apply_proposal_by_id_uses_durable_canonical_record(sample_vault: Path) -> None:
    """Application boundary applies a stored proposal without a browser payload."""
    service = ApplicationService(sample_vault)
    proposal = service.propose(
        "01_Projects/ApplyById.md",
        '---\ntype: Project\ntitle: "Apply by ID"\ndescription: "test"\n'
        "timestamp: 2026-08-11T00:00:00Z\n---\n",
        context=RequestContext(actor="test", authority="propose"),
    )
    proposal_id = proposal.data["proposal_id"]
    applied = service.apply_proposal(
        proposal_id,
        approved=True,
        context=RequestContext(actor="gui", authority="apply"),
    )
    assert applied.status == "ok"
    assert (sample_vault / "01_Projects" / "ApplyById.md").is_file()

    with pytest.raises((FileNotFoundError, ValueError)):
        service.apply_proposal(
            "0" * 64,
            approved=True,
            context=RequestContext(actor="gui", authority="apply"),
        )


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
