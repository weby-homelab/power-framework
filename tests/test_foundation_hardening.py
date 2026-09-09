"""Focused F1--F5 foundation hardening contracts."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import pytest

from power_framework.core.application import (
    ApplicationService,
    CompletedAfterBudgetError,
    CompletedAfterDeadlineError,
    DeadlineExceededError,
    RequestContext,
    ResultBudgetExceededError,
)
from power_framework.core.errors import ConflictError
from power_framework.core.principal import Principal

if TYPE_CHECKING:
    from pathlib import Path


def test_principal_factories_keep_binding_separate_from_actor() -> None:
    """Principal references are issued by a binding, never copied from actor text."""
    local = Principal.local_cli()
    web = Principal.web_signed_session("admin")

    assert local.binding == "LOCAL_CLI"
    assert local.ref == "local-cli"
    assert web.binding == "WEB_SIGNED_SESSION"
    assert web.ref.startswith("web-")
    assert "admin" not in web.ref
    assert local.is_valid()
    assert web.is_valid()

    with pytest.raises(ValueError, match="trusted binding"):
        Principal(ref="forged", binding="WEB_SIGNED_SESSION")  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="principal binding"):
        RequestContext(authority="apply", principal=None)


def test_mutation_requires_context_and_emits_bounded_failure_receipt(
    sample_vault: Path,
) -> None:
    """Missing mutation context cannot reach a writer and is safely receipted."""
    audit = []
    service = ApplicationService(sample_vault, audit_hook=audit.append)
    content = (
        '---\ntype: Project\ntitle: "Rejected"\n'
        'description: "must not write"\ntimestamp: 2026-09-09T00:00:00Z\n---\n'
    )

    with pytest.raises(PermissionError, match="explicit RequestContext"):
        service.propose("01_Projects/Rejected.md", content)

    assert not (sample_vault / ".power" / "proposals").exists()
    assert audit
    failure = audit[-1].as_dict()
    assert failure["status"] != "ok"
    assert failure["outcome"] == "failed"
    assert failure["error_code"] == "permission_denied"
    assert failure["principal_ref"] is None
    assert len(json.dumps(failure)) < 2048


def test_generic_mutation_runner_does_not_default_missing_context(sample_vault: Path) -> None:
    """The shared execution boundary also fails closed for direct mutation calls."""
    called = False

    def sentinel() -> None:
        nonlocal called
        called = True

    with pytest.raises(PermissionError, match="explicit RequestContext"):
        ApplicationService(sample_vault)._run("test.mutation", None, sentinel, mutation=True)

    assert called is False


def test_generic_mutation_runner_rejects_read_only_context(sample_vault: Path) -> None:
    """A read-only context cannot be relabeled as a mutation by the runner."""
    called = False

    def sentinel() -> None:
        nonlocal called
        called = True

    with pytest.raises(PermissionError, match="propose or apply"):
        ApplicationService(sample_vault)._run(
            "test.mutation",
            RequestContext(principal=Principal.local_cli()),
            sentinel,
            mutation=True,
        )

    assert called is False


def test_proposal_idempotency_key_cannot_bind_two_different_payloads(sample_vault: Path) -> None:
    """A repeated proposal key is replay-safe and cannot create a second claim."""
    service = ApplicationService(sample_vault)
    first = (
        '---\ntype: Project\ntitle: "First"\ndescription: "one"\n'
        "timestamp: 2026-09-09T00:00:00Z\n---\n"
    )
    second = first.replace('title: "First"', 'title: "Second"')
    context = RequestContext(
        authority="propose",
        idempotency_key="same-proposal-key",
        principal=Principal.local_cli(),
    )

    service.propose("01_Projects/First.md", first, context=context)
    with pytest.raises(ConflictError, match="idempotency key"):
        service.propose("01_Projects/Second.md", second, context=context)

    proposals = list((sample_vault / ".power" / "proposals").glob("*.json"))
    assert len(proposals) == 1


@pytest.mark.skipif(os.name == "nt", reason="symlink policy test requires POSIX")
def test_proposal_control_directory_symlink_is_rejected(sample_vault: Path, tmp_path: Path) -> None:
    """A control-subdirectory symlink cannot redirect proposal writes."""
    external = tmp_path / "external-proposals"
    external.mkdir()
    (sample_vault / ".power").mkdir()
    (sample_vault / ".power" / "proposals").symlink_to(external, target_is_directory=True)
    content = (
        '---\ntype: Project\ntitle: "Symlink"\ndescription: "reject"\n'
        "timestamp: 2026-09-09T00:00:00Z\n---\n"
    )

    with pytest.raises(ValueError, match="must not be a symlink"):
        ApplicationService(sample_vault).propose(
            "01_Projects/Symlink.md",
            content,
            context=RequestContext(authority="propose", principal=Principal.local_cli()),
        )

    assert list(external.iterdir()) == []


def test_ingest_replays_same_idempotency_key_without_duplicate_write(sample_vault: Path) -> None:
    """A lost response can be replayed without treating the existing note as new work."""
    service = ApplicationService(sample_vault)
    context = RequestContext(
        authority="apply",
        idempotency_key="ingest-replay",
        principal=Principal.local_cli(),
    )
    values = {
        "name": "01_Projects/Replay.md",
        "note_type": "Project",
        "title": "Replay",
        "description": "Idempotent ingest",
        "content": "body",
        "context": context,
    }

    first = service.ingest_note(**values)
    replay = service.ingest_note(**values)

    assert first.data["receipt"] == replay.data["receipt"]


def test_expired_principal_cannot_mutate(sample_vault: Path) -> None:
    """A verified binding with an expired lifetime is rejected at the core boundary."""
    expired = Principal.web_signed_session(
        "admin",
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
    )

    with pytest.raises(PermissionError, match="expired"):
        ApplicationService(sample_vault).task_create(
            "expired-task",
            "Expired task",
            context=RequestContext(
                actor="forged-attribution",
                authority="propose",
                principal=expired,
            ),
        )

    assert not (sample_vault / ".power" / "tasks").exists()


@pytest.mark.parametrize(
    "override",
    [
        "absolute-external.db",
        "../relative-traversal.db",
        "file:///tmp/uri-looking.db",
        "http://127.0.0.1:9/network-looking.db",
    ],
)
def test_application_retrieval_ignores_external_search_db_overrides(
    sample_vault: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    override: str,
) -> None:
    """Agent-facing ApplicationService retrieval cannot select POWER_SEARCH_DB."""
    external = tmp_path / "external-search.db"
    external.write_text("not a database", encoding="utf-8")
    monkeypatch.setenv(
        "POWER_SEARCH_DB",
        str(external) if override == "absolute-external.db" else override,
    )

    result = ApplicationService(sample_vault).retrieve("not-present", mode="fts")

    assert result.data["result_count"] == 0
    assert external.read_text(encoding="utf-8") == "not a database"


def test_application_retrieval_cannot_use_a_valid_external_index(
    sample_vault: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid attacker-selected SQLite index is not the ApplicationService authority."""
    from power_framework.core.db import _init_db

    external = tmp_path / "valid-external.db"
    with closing(sqlite3.connect(external)) as connection:
        _init_db(connection)
        connection.execute(
            "INSERT INTO fts_notes(title, tags, description, content, rel_path, note_type) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("External", "", "", "external-only-marker", "external.md", "Resource"),
        )
        connection.commit()
    monkeypatch.setenv("POWER_SEARCH_DB", str(external))

    result = ApplicationService(sample_vault).retrieve("external-only-marker", mode="fts")

    assert result.data["result_count"] == 0


def test_failure_receipt_redacts_exception_text_and_preserves_correlation(
    sample_vault: Path,
) -> None:
    """Failure evidence contains categories and IDs, never exception content."""
    audit = []
    service = ApplicationService(sample_vault, audit_hook=audit.append)
    context = RequestContext(actor="cli-label", principal=Principal.local_cli())

    def fail() -> None:
        raise RuntimeError("password=super-secret request body with note content")

    with pytest.raises(RuntimeError):
        service._run("test.failure", context, fail)

    receipt = audit[-1]
    payload = receipt.as_dict()
    assert payload["status"] == "failed"
    assert payload["error_code"] == "internal_error"
    assert payload["request_id"] == context.request_id
    assert payload["principal_ref"] == "local-cli"
    assert "super-secret" not in json.dumps(payload)
    assert "request body" not in json.dumps(payload)
    assert len(json.dumps(payload)) < 2048


def test_invalid_retrieval_request_emits_failure_receipt(sample_vault: Path) -> None:
    """Boundary validation failures are correlated without echoing the query."""
    audit = []
    service = ApplicationService(sample_vault, audit_hook=audit.append)

    with pytest.raises(ValueError, match="empty"):
        service.retrieve("   ")

    assert audit[-1].as_dict()["operation"] == "retrieve"
    assert audit[-1].as_dict()["error_code"] == "invalid_request"


def test_deadline_expiry_before_start_skips_action_and_receipts_failure(
    sample_vault: Path,
) -> None:
    """An already expired absolute deadline prevents even sentinel execution."""
    audit = []
    service = ApplicationService(sample_vault, audit_hook=audit.append)
    called = False
    context = RequestContext(
        authority="apply",
        principal=Principal.local_cli(),
        deadline_ms=100,
        deadline_at=time.monotonic() - 1,
    )

    def sentinel() -> None:
        nonlocal called
        called = True

    with pytest.raises(DeadlineExceededError, match="before operation started"):
        service._run("test.prestart", context, sentinel, mutation=True)

    assert called is False
    assert audit[-1].as_dict()["outcome"] == "rejected_before_start"
    assert audit[-1].as_dict()["error_code"] == "deadline_exceeded"


def test_mutation_late_completion_is_not_reported_as_cancellation(sample_vault: Path) -> None:
    """A committed slow action reports completed-after-deadline truthfully."""
    audit = []
    service = ApplicationService(sample_vault, audit_hook=audit.append)
    marker = sample_vault / "late-completion.marker"
    context = RequestContext(
        authority="apply",
        principal=Principal.local_cli(),
        deadline_ms=1,
    )

    def slow_mutation() -> dict[str, object]:
        time.sleep(0.01)
        marker.write_text("committed", encoding="utf-8")
        return {"changed": True}

    with pytest.raises(CompletedAfterDeadlineError, match="completed after deadline"):
        service._run("test.mutation", context, slow_mutation, mutation=True)

    assert marker.read_text(encoding="utf-8") == "committed"
    failure = audit[-1].as_dict()
    assert failure["status"] == "completed_after_deadline"
    assert failure["outcome"] == "completed_after_deadline"
    assert failure["error_code"] == "completed_after_deadline"


def test_result_budget_rejects_oversized_envelope(sample_vault: Path) -> None:
    """Generic application results have a server-selected structural ceiling."""
    audit = []
    service = ApplicationService(sample_vault, audit_hook=audit.append)
    context = RequestContext(
        authority="apply",
        principal=Principal.local_cli(),
        max_result_bytes=128,
    )

    with pytest.raises(ResultBudgetExceededError, match="result budget"):
        service._run("test.result-budget", context, lambda: {"value": "x" * 1024})

    failure = audit[-1].as_dict()
    assert failure["status"] == "failed"
    assert failure["error_code"] == "result_budget_exceeded"
    assert "x" * 128 not in json.dumps(failure)


def test_mutation_result_budget_has_truthful_late_outcome(sample_vault: Path) -> None:
    """A post-action result-bound violation cannot be mistaken for pre-action failure."""
    audit = []
    service = ApplicationService(sample_vault, audit_hook=audit.append)
    context = RequestContext(
        authority="apply",
        principal=Principal.local_cli(),
        max_result_bytes=128,
    )

    with pytest.raises(CompletedAfterBudgetError, match="result budget"):
        service._run(
            "test.mutation-result-budget",
            context,
            lambda: {"value": "x" * 1024},
            mutation=True,
        )

    assert audit[-1].as_dict()["outcome"] == "completed_after_budget"
    assert audit[-1].as_dict()["status"] == "completed_after_budget"


def test_receipt_history_rejects_unbounded_or_content_bearing_records(sample_vault: Path) -> None:
    """The readback surface fails closed on unsafe durable receipt state."""
    history = sample_vault / ".power" / "memory-history.jsonl"
    history.parent.mkdir()
    history.write_text('{"operation":"x","content":"must not be here"}\n', encoding="utf-8")

    with pytest.raises(RuntimeError, match="non-content-free"):
        ApplicationService(sample_vault).receipt()


def test_success_receipt_legacy_shape_is_preserved_with_principal_on_envelope(
    sample_vault: Path,
) -> None:
    """Existing content-free success receipts stay wire-compatible."""
    result = ApplicationService(sample_vault).discover()

    assert set(result.receipt.as_dict()) == {
        "schema_version",
        "operation",
        "status",
        "request_id",
        "idempotency_key",
        "data_sha256",
        "duration_ms",
    }
    assert result.as_dict()["principal_ref"] == "local-cli"


def test_audit_hook_failure_cannot_turn_committed_success_into_operation_failure(
    sample_vault: Path,
) -> None:
    """A broken optional sink is isolated from the application outcome."""

    def broken_hook(_receipt: object) -> None:
        raise RuntimeError("sink unavailable")

    result = ApplicationService(sample_vault, audit_hook=broken_hook).discover()

    assert result.status == "ok"
