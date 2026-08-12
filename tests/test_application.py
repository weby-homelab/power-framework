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

    assert payload["schema_version"] == "power.application.v1"
    assert payload["operation"] == "retrieve"
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
