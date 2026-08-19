"""Decision domain binding and resolution tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from power_framework.core.decision_service import DecisionService
from power_framework.core.task_service import TaskService

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def decision_service(tmp_path: Path) -> DecisionService:
    vault = tmp_path / "vault"
    vault.mkdir()
    service = TaskService(vault)
    service.create_task(task_id="task_decision", title="Decision task", state="working")
    return DecisionService(vault, task_service=service)


def test_decision_resolution_binds_task_revision_actor_authority_and_proposal(
    decision_service: DecisionService,
) -> None:
    decision = decision_service.create_decision(
        decision_id="dec_publish",
        task_id="task_decision",
        title="Publish proposal",
        requested_by="agent-1",
        proposal_id="proposal-1",
        proposal_sha256="a" * 64,
        allowed_actors=["operator-1"],
    )

    with pytest.raises(PermissionError, match="not allowed"):
        decision_service.resolve_decision(
            decision.decision_id,
            action="approve",
            actor="operator-2",
            authority="apply",
            proposal_sha256="a" * 64,
        )
    with pytest.raises(PermissionError, match="insufficient authority"):
        decision_service.resolve_decision(
            decision.decision_id,
            action="approve",
            actor="operator-1",
            authority="propose",
            proposal_sha256="a" * 64,
        )
    with pytest.raises(ValueError, match="proposal hash"):
        decision_service.resolve_decision(
            decision.decision_id,
            action="approve",
            actor="operator-1",
            authority="apply",
            proposal_sha256="b" * 64,
        )

    resolved, receipt = decision_service.resolve_decision(
        decision.decision_id,
        action="approve",
        actor="operator-1",
        authority="apply",
        proposal_sha256="a" * 64,
    )
    assert resolved.status == "approved"
    assert resolved.receipt_id == receipt.receipt_id
    assert receipt.task_revision == decision.task_revision

    replay, replay_receipt = decision_service.resolve_decision(
        decision.decision_id,
        action="approve",
        actor="operator-1",
        authority="apply",
        proposal_sha256="a" * 64,
    )
    assert replay == resolved
    assert replay_receipt == receipt


def test_decision_rejects_stale_task_revision(decision_service: DecisionService) -> None:
    decision = decision_service.create_decision(
        decision_id="dec_stale",
        task_id="task_decision",
        title="Stale decision",
        requested_by="agent-1",
    )
    decision_service.task_service.transition_task(
        decision.task_id,
        "ready",
        expected_revision=decision.task_revision,
    )

    with pytest.raises(ValueError, match="task revision is stale"):
        decision_service.resolve_decision(
            decision.decision_id,
            action="reject",
            actor="operator",
            authority="apply",
        )


def test_structured_input_requires_exact_allowed_schema(decision_service: DecisionService) -> None:
    decision = decision_service.create_decision(
        decision_id="dec_input",
        task_id="task_decision",
        title="Collect input",
        requested_by="agent-1",
        response_schema={"approved_by": "string", "urgent": "boolean"},
    )

    with pytest.raises(ValueError, match="input fields"):
        decision_service.resolve_decision(
            decision.decision_id,
            action="provide_input",
            actor="operator",
            authority="apply",
            input_data={"approved_by": "operator"},
        )
    with pytest.raises(ValueError, match="must be boolean"):
        decision_service.resolve_decision(
            decision.decision_id,
            action="provide_input",
            actor="operator",
            authority="apply",
            input_data={"approved_by": "operator", "urgent": 1},
        )

    resolved, _ = decision_service.resolve_decision(
        decision.decision_id,
        action="provide_input",
        actor="operator",
        authority="apply",
        input_data={"approved_by": "operator", "urgent": True},
    )
    assert resolved.status == "approved"
    assert resolved.resolution_input == {"approved_by": "operator", "urgent": True}


def test_decision_revalidates_persisted_ids_and_bounds_input(
    decision_service: DecisionService,
) -> None:
    with pytest.raises(ValueError, match="safe identifiers"):
        decision_service.create_decision(
            decision_id="dec_bad_schema",
            task_id="task_decision",
            title="Bad schema",
            requested_by="agent-1",
            response_schema={"../../secret": "string"},
        )

    decision = decision_service.create_decision(
        decision_id="dec_bounded_input",
        task_id="task_decision",
        title="Bounded input",
        requested_by="agent-1",
        response_schema={"comment": "string"},
    )
    with pytest.raises(ValueError, match="exceeds 4096"):
        decision_service.resolve_decision(
            decision.decision_id,
            action="provide_input",
            actor="operator",
            authority="apply",
            input_data={"comment": "x" * 4097},
        )


def test_expired_decision_fails_closed(decision_service: DecisionService) -> None:
    expiry = (datetime.now(UTC) + timedelta(seconds=1)).isoformat()
    decision = decision_service.create_decision(
        decision_id="dec_expiry",
        task_id="task_decision",
        title="Expiring decision",
        requested_by="agent-1",
        expires_at=expiry,
    )
    decision_service.get_decision(decision.decision_id)
    decision_file = decision_service._decision_file(decision.decision_id)
    decision_file.write_text(
        decision.model_copy(
            update={"expires_at": (datetime.now(UTC) - timedelta(seconds=1)).isoformat()}
        ).model_dump_json(),
        encoding="utf-8",
    )

    effective = decision_service.get_decision(decision.decision_id)
    assert effective is not None
    assert effective.status == "expired"
    assert effective.receipt_id is None
    assert decision_service.list_decisions(status="expired")[0].decision_id == decision.decision_id
    assert decision_service.list_decisions(status="pending") == []

    with pytest.raises(ValueError, match="expired"):
        decision_service.resolve_decision(
            decision.decision_id,
            action="reject",
            actor="operator",
            authority="apply",
        )
