"""Phase H/J acceptance: read-only kill switch + hermetic GUI/core e2e contracts."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from power_framework.core.application import ApplicationService, RequestContext
from power_framework.web.app import create_app
from power_framework.web.config import Settings


def _extract_csrf(response) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text)
    return match.group(1) if match else ""


def _extract_proposal_id(html: str) -> str:
    match = re.search(r'name="proposal_id"\s+value="([0-9a-f]{64})"', html)
    assert match, "proposal_id hidden field missing from proposal review HTML"
    return match.group(1)


@pytest.fixture
def hermetic_vault(tmp_path: Path) -> Path:
    vault = tmp_path / "gui_e2e_vault"
    vault.mkdir()
    (vault / ".power").mkdir()
    (vault / "01_Projects").mkdir()
    (vault / "01_Projects" / "Project_Alpha.md").write_text(
        """---
type: Project
title: "Project Alpha"
description: "Core test project"
tags: [alpha, power]
timestamp: 2026-08-13T12:00:00+00:00
---

# Project Alpha
Baseline body.
""",
        encoding="utf-8",
    )
    return vault


def _client(vault: Path, *, read_only: bool = False) -> TestClient:
    settings = Settings(
        vault_path=vault,
        auth_enabled=False,
        cookie_secure=False,
        read_only_mode=read_only,
    )
    return TestClient(create_app(settings))


def test_read_only_mode_rejects_mutations_with_405(hermetic_vault: Path) -> None:
    """Phase H: direct POST cannot bypass read-only kill switch."""
    # Seed a task so transition path is meaningful under read-only.
    svc = ApplicationService(hermetic_vault)
    svc.task_create(
        "ro_task",
        "RO task",
        state="working",
        context=RequestContext(actor="seed", authority="propose"),
    )
    svc.decision_create(
        decision_id="dec_ro_01",
        task_id="ro_task",
        title="RO decision",
        requested_by="seed",
        context=RequestContext(actor="seed", authority="propose"),
    )

    client = _client(hermetic_vault, read_only=True)

    # Read surfaces remain available.
    for path in ("/dashboard", "/notes", "/search?q=Alpha&mode=fts", "/receipts", "/decisions"):
        assert client.get(path).status_code == 200, path

    csrf = _extract_csrf(client.get("/notes/edit?path=01_Projects/Project_Alpha.md"))
    mutations = [
        (
            "/notes/propose",
            {
                "csrf_token": csrf,
                "path": "01_Projects/Project_Alpha.md",
                "content": "---\ntype: Project\ntitle: X\ndescription: d\n"
                "timestamp: 2026-08-13T12:00:00+00:00\n---\n# X\n",
            },
        ),
        (
            "/notes/apply",
            {"csrf_token": csrf, "proposal_id": "0" * 64, "approved": "true"},
        ),
        (
            "/tasks/new",
            {
                "csrf_token": csrf,
                "task_id": "should_fail",
                "title": "Nope",
                "objective": "blocked",
                "owner": "tester",
                "priority": "normal",
                "authority": "propose",
            },
        ),
        (
            "/tasks/ro_task/transition",
            {
                "csrf_token": csrf,
                "new_state": "ready",
                "expected_revision": "1",
            },
        ),
        (
            "/decisions/dec_ro_01/resolve",
            {"csrf_token": csrf, "action": "reject"},
        ),
    ]
    for path, data in mutations:
        resp = client.post(path, data=data, follow_redirects=False)
        assert resp.status_code == 405, f"{path} expected 405 got {resp.status_code}"
        assert "read-only" in resp.text.lower() or "read-only" in (
            resp.json().get("detail", "").lower()
            if resp.headers.get("content-type", "").startswith("application/json")
            else resp.text.lower()
        )


def test_notes_propose_apply_by_id_receipt_and_readback(hermetic_vault: Path) -> None:
    """Phase E/J: browser passes only proposal_id; core applies durable record."""
    client = _client(hermetic_vault)
    path = "01_Projects/Project_Alpha.md"
    new_content = """---
type: Project
title: "Alpha Applied"
description: "Applied via GUI by proposal_id"
tags: [alpha, power]
timestamp: 2026-08-13T12:00:00+00:00
---

# Alpha Applied
Canonical body after apply.
"""
    csrf = _extract_csrf(client.get(f"/notes/edit?path={path}"))
    prop = client.post(
        "/notes/propose",
        data={"csrf_token": csrf, "path": path, "content": new_content},
    )
    assert prop.status_code == 200
    proposal_id = _extract_proposal_id(prop.text)
    assert "before_sha256" not in prop.text or 'name="before_sha256"' not in prop.text
    assert 'name="content"' not in prop.text or 'name="proposal_id"' in prop.text

    csrf2 = _extract_csrf(prop)
    apply_resp = client.post(
        "/notes/apply",
        data={"csrf_token": csrf2, "proposal_id": proposal_id, "approved": "true"},
        follow_redirects=False,
    )
    assert apply_resp.status_code == 303
    assert "notes/read" in apply_resp.headers.get("location", "")

    on_disk = (hermetic_vault / path).read_text(encoding="utf-8")
    assert "Alpha Applied" in on_disk
    assert (
        hashlib.sha256(on_disk.encode()).hexdigest()
        == hashlib.sha256(new_content.encode()).hexdigest()
    )

    # Idempotent re-apply of same durable proposal returns without corruption.
    reapply = client.post(
        "/notes/apply",
        data={"csrf_token": csrf2, "proposal_id": proposal_id, "approved": "true"},
        follow_redirects=False,
    )
    assert reapply.status_code in {303, 400}
    assert (hermetic_vault / path).read_text(encoding="utf-8") == on_disk

    readback = client.get(f"/notes/read?path={path}")
    assert readback.status_code == 200
    assert "Alpha Applied" in readback.text

    # Missing / malformed proposal_id fail closed.
    bad = client.post(
        "/notes/apply",
        data={"csrf_token": csrf2, "proposal_id": "0" * 64, "approved": "true"},
        follow_redirects=False,
    )
    assert bad.status_code == 400


def test_task_completion_evidence_creates_canonical_tcr_receipt(hermetic_vault: Path) -> None:
    """Phase G/J: GUI passes evidence only; core builds tcr_* receipt."""
    client = _client(hermetic_vault)
    csrf = _extract_csrf(client.get("/tasks/new"))
    create = client.post(
        "/tasks/new",
        data={
            "csrf_token": csrf,
            "task_id": "complete_gui_01",
            "title": "Complete via GUI",
            "objective": "evidence-bound completion",
            "owner": "tester",
            "priority": "normal",
            "authority": "apply",
        },
        follow_redirects=True,
    )
    assert create.status_code == 200

    detail = client.get("/tasks/complete_gui_01")
    csrf_d = _extract_csrf(detail)
    # backlog -> working
    client.post(
        "/tasks/complete_gui_01/transition",
        data={
            "csrf_token": csrf_d,
            "new_state": "working",
            "expected_revision": "1",
        },
        follow_redirects=True,
    )

    artifact_rel = "01_Projects/completion_artifact.md"
    (hermetic_vault / artifact_rel).write_text(
        "---\ntype: Project\ntitle: Done\ndescription: d\n"
        "timestamp: 2026-08-13T12:00:00+00:00\n---\n# done\n",
        encoding="utf-8",
    )
    detail2 = client.get("/tasks/complete_gui_01")
    csrf2 = _extract_csrf(detail2)
    done = client.post(
        "/tasks/complete_gui_01/transition",
        data={
            "csrf_token": csrf2,
            "new_state": "completed",
            "expected_revision": "2",
            "completion_postcondition": "Completion artifact exists and is readable.",
            "completion_artifact_refs": artifact_rel,
        },
        follow_redirects=True,
    )
    assert done.status_code == 200

    svc = ApplicationService(hermetic_vault)
    task = svc.task_service.get_task("complete_gui_01")
    assert task is not None
    assert task.state == "completed"
    assert task.receipt_ids
    assert all(rid.startswith("tcr_") for rid in task.receipt_ids)
    assert not any(rid.startswith("rec_") for rid in task.receipt_ids)
    receipt = svc.task_service.store.get_completion_receipt(task.receipt_ids[0])
    assert receipt is not None
    assert receipt.task_id == "complete_gui_01"
    assert artifact_rel in receipt.artifact_digests


def test_task_sse_resume_cursor_starts_after_requested_sequence(
    hermetic_vault: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SSE resumes from the caller cursor instead of replaying the full journal."""
    svc = ApplicationService(hermetic_vault)
    svc.task_create(
        "sse_cursor_01",
        "SSE cursor task",
        context=RequestContext(actor="seed", authority="propose"),
    )
    svc.task_transition(
        "sse_cursor_01",
        new_state="ready",
        expected_revision=1,
        context=RequestContext(actor="seed", authority="apply"),
    )

    async def _run_power_call(request, settings, function, *args, **kwargs):
        del request, settings
        kwargs.pop("timeout_seconds", None)
        return function(*args, **kwargs)

    from power_framework.web.routes import tasks as task_routes

    monkeypatch.setattr(task_routes, "run_power_call", _run_power_call)

    settings = Settings(
        vault_path=hermetic_vault,
        auth_enabled=False,
        cookie_secure=False,
        sse_max_lifetime_seconds=60,
    ).model_copy(update={"sse_max_lifetime_seconds": 0.01})
    client = TestClient(create_app(settings))
    response = client.get("/tasks/api/events/stream?task_id=sse_cursor_01&since_sequence=1")

    assert response.status_code == 200
    assert '"sequence": 1' not in response.text
    assert '"sequence": 2' in response.text


def test_decision_resolve_via_gui_updates_canonical_decision(hermetic_vault: Path) -> None:
    """Phase F/J: GUI resolve delegates to DecisionService; no local decision state."""
    svc = ApplicationService(hermetic_vault)
    svc.task_create(
        "dec_task_01",
        "Decision task",
        state="working",
        context=RequestContext(actor="seed", authority="propose"),
    )
    created = svc.decision_create(
        decision_id="dec_gui_01",
        task_id="dec_task_01",
        title="Approve ship",
        requested_by="seed",
        context=RequestContext(actor="seed", authority="propose"),
    )
    assert created.status == "ok"

    client = _client(hermetic_vault)
    page = client.get("/decisions")
    assert page.status_code == 200
    assert "dec_gui_01" in page.text or "Approve ship" in page.text
    csrf = _extract_csrf(page)
    if not csrf:
        # decisions page may not embed csrf if empty template actions only on cards
        csrf = _extract_csrf(client.get("/tasks/new"))

    resp = client.post(
        "/decisions/dec_gui_01/resolve",
        data={"csrf_token": csrf, "action": "reject", "input_value": ""},
        follow_redirects=False,
    )
    assert resp.status_code in {303, 400}
    if resp.status_code == 400:
        # retry with csrf from a mutation-capable page already obtained
        pytest.fail(f"decision resolve failed: {resp.text[:300]}")

    decision = svc.decision_service.get_decision("dec_gui_01")
    assert decision is not None
    assert decision.status == "rejected"
    assert decision.receipt_id


def test_claims_files_do_not_advertise_a2a_agent_ready() -> None:
    """Phase K residual: shipped docs must not claim A2A Agent Ready."""
    root = Path(__file__).resolve().parents[3]
    for rel in ("README.md", "README.ua.md"):
        text = (root / rel).read_text(encoding="utf-8")
        assert "A2A-Agent_Ready" not in text
        assert "A2A/2026.1" not in text
