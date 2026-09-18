"""Tests for P38-WP03-R4: production-faithful runtime correction.

Covers the eligible-set admission, canonical owner matrix, and
intent-dependent ordering of RetrievalPlanner with production-shaped
fixtures only. No benchmark, holdout, or fixture identifiers are used;
every identifier below is synthetic and local to its test.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from power_framework.core.context_contracts import (
    AccessPolicy,
    Authority,
    AuthorityBasis,
    BudgetClass,
    QueryIntent,
    QueryIntentKind,
    TemporalBoundary,
    TrustState,
)
from power_framework.core.decision_service import DecisionService
from power_framework.core.project_models import AppendCommand
from power_framework.core.project_store import ProjectEventStore
from power_framework.core.retrieval_planner import RetrievalPlanner
from power_framework.core.state_service import ProjectStateService
from power_framework.core.task_service import TaskService


def _make_policy(
    *,
    raw: str = "privileged",
    quarantine: str = "privileged",
) -> AccessPolicy:
    now = datetime.now(UTC)
    data: dict[str, Any] = {
        "origin": "authorization_boundary",
        "actor": "test_actor",
        "raw_access": raw,
        "quarantine_access": quarantine,
        "redaction": "mandatory",
        "capability_id": "retrieval_planner",
        "expires_at": now + timedelta(hours=1),
    }
    if raw == "privileged" or quarantine == "privileged":
        data["approval_ref"] = "approvals/appr-001.json"
    return AccessPolicy._from_authorization_boundary(**data)


def _vault_skeleton(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    for folder in ["01_Projects", "02_Areas", "03_Resources", "06_Daily_Logs", ".power"]:
        (vault / folder).mkdir(parents=True, exist_ok=True)
    return vault


def _write_note(vault: Path, rel: str, frontmatter: str, body: str) -> Path:
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"{frontmatter}\n\n{body}\n", encoding="utf-8")
    return p


class _FakeHit:
    def __init__(self, rel_path: str, content: str, score: float = 0.5) -> None:
        self.rel_path = rel_path
        self.content = content
        self.snippet = content
        self.score = score


class _CountingTaskService(TaskService):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.list_calls = 0

    def list_tasks(self, limit: int = 100, **kwargs: Any) -> list[Any]:
        self.list_calls += 1
        return super().list_tasks(limit=limit, **kwargs)


class _CountingDecisionService(DecisionService):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.list_calls = 0

    def list_decisions(self, limit: int = 100, **kwargs: Any) -> list[Any]:
        self.list_calls += 1
        return super().list_decisions(limit=limit, **kwargs)


def _create_project(vault: Path, project_id: str, name: str) -> ProjectStateService:
    ProjectEventStore(project_id, vault)._append_governed(
        AppendCommand(
            project_id=project_id,
            event_type="project.created",
            payload={"name": name},
            actor="user:lead",
            source="pse_governance",
        )
    )
    return ProjectStateService(vault)


# ---------------------------------------------------------------------------
# Test A: unrelated canonical vs relevant note (eligibility admission).
# ---------------------------------------------------------------------------
def test_a_unrelated_canonical_not_admitted(tmp_path: Path) -> None:
    vault = _vault_skeleton(tmp_path)
    _write_note(
        vault,
        "02_Areas/south.md",
        "---\ntype: Area\ntitle: South river hydrology\ntags: [survey]\n---",
        "South river hydrology survey results and gauge readings.",
    )
    pid = "prj_north_ridge"
    pss = _create_project(vault, pid, "North Ridge telemetry rollout")
    planner = RetrievalPlanner(
        vault,
        project_state_service=pss,
        search_fn=lambda *a, **k: [
            _FakeHit(
                "02_Areas/south.md",
                "South river hydrology survey results and gauge readings.",
                0.9,
            )
        ],
    )
    intent = QueryIntent(
        query="South river hydrology survey results",
        intent=QueryIntentKind.PROJECT_STATE,
        budget_class=BudgetClass.FAST,
    )
    result = planner.plan_and_retrieve(intent, access_policy=_make_policy())
    ids = [c.source_id for c in result.candidates]
    assert f"project:{pid}" not in ids
    assert ids[0] == "02_Areas/south.md"


# ---------------------------------------------------------------------------
# Test B: genuine authority conflict, same subject (canonical wins).
# ---------------------------------------------------------------------------
def test_b_canonical_current_outranks_raw_same_subject(tmp_path: Path) -> None:
    vault = _vault_skeleton(tmp_path)
    pid = "prj_harbor_dredging"
    pss = _create_project(vault, pid, "Harbor dredging current plan")
    _write_note(
        vault,
        "06_Daily_Logs/harbor.md",
        "---\ntype: Project\ntitle: Harbor memo\ntags: [harbor]\n---",
        "Harbor dredging informal memo with an older draft plan.",
    )
    planner = RetrievalPlanner(
        vault,
        project_state_service=pss,
        search_fn=lambda *a, **k: [
            _FakeHit(
                "06_Daily_Logs/harbor.md",
                "Harbor dredging informal memo with an older draft plan.",
                0.95,
            )
        ],
    )
    intent = QueryIntent(
        query="Harbor dredging current plan",
        intent=QueryIntentKind.PROJECT_STATE,
        budget_class=BudgetClass.FAST,
    )
    result = planner.plan_and_retrieve(intent, access_policy=_make_policy())
    assert len(result.candidates) == 2
    first, second = result.candidates[0], result.candidates[1]
    assert first.source_id == f"project:{pid}"
    assert first.authority is Authority.CANONICAL
    assert first.provenance.authority_basis is AuthorityBasis.CANONICAL_LEDGER
    assert second.source_id == "06_Daily_Logs/harbor.md"
    assert second.authority is Authority.UNVERIFIED


# ---------------------------------------------------------------------------
# Test C: task A vs task B (per-object eligibility + explicit scope).
# ---------------------------------------------------------------------------
def test_c_task_scope_admits_only_matching_task(tmp_path: Path) -> None:
    vault = _vault_skeleton(tmp_path)
    ts = TaskService(vault)
    ts.create_task(
        task_id="tsk-alpine-audit",
        title="Alpine meadow audit",
        objective="Survey alpine plots each spring",
    )
    ts.create_task(
        task_id="tsk-bog-sampling",
        title="Bog water sampling",
        objective="Collect peatland water monthly",
    )
    planner = RetrievalPlanner(vault, task_service=ts, search_fn=lambda *a, **k: [])
    intent = QueryIntent(
        query="Alpine meadow audit status",
        intent=QueryIntentKind.TASK,
        budget_class=BudgetClass.FAST,
    )
    result = planner.plan_and_retrieve(intent, access_policy=_make_policy())
    ids = [c.source_id for c in result.candidates]
    assert "task:tsk-alpine-audit" in ids
    assert "task:tsk-bog-sampling" not in ids

    scoped = QueryIntent(
        query="tsk-bog-sampling status",
        intent=QueryIntentKind.TASK,
        budget_class=BudgetClass.FAST,
    )
    scoped_result = planner.plan_and_retrieve(scoped, access_policy=_make_policy())
    scoped_ids = [c.source_id for c in scoped_result.candidates]
    assert scoped_ids == ["task:tsk-bog-sampling"]
    assert scoped_result.candidates[0].authority is Authority.CANONICAL
    assert scoped_result.candidates[0].score == 0.95


# ---------------------------------------------------------------------------
# Test D: project A vs project B (explicit project_id scope restriction).
# ---------------------------------------------------------------------------
def test_d_project_scope_restriction(tmp_path: Path) -> None:
    vault = _vault_skeleton(tmp_path)
    pid_a = "prj_alpha_ledger"
    pid_b = "prj_beta_ledger"
    _create_project(vault, pid_a, "Alpha ledger consolidation")
    pss = _create_project(vault, pid_b, "Beta archive migration")
    planner = RetrievalPlanner(vault, project_state_service=pss, search_fn=lambda *a, **k: [])
    intent = QueryIntent(
        query="prj_alpha_ledger current phase",
        intent=QueryIntentKind.PROJECT_STATE,
        budget_class=BudgetClass.FAST,
    )
    result = planner.plan_and_retrieve(intent, access_policy=_make_policy())
    ids = [c.source_id for c in result.candidates]
    assert ids == [f"project:{pid_a}"]
    assert result.candidates[0].authority is Authority.CANONICAL
    assert result.candidates[0].score == 0.95

    weak = QueryIntent(
        query="Beta archive migration phase",
        intent=QueryIntentKind.PROJECT_STATE,
        budget_class=BudgetClass.FAST,
    )
    weak_result = planner.plan_and_retrieve(weak, access_policy=_make_policy())
    weak_ids = [c.source_id for c in weak_result.candidates]
    assert f"project:{pid_b}" in weak_ids
    assert f"project:{pid_a}" not in weak_ids


# ---------------------------------------------------------------------------
# Test E: non-authority intents never inject canonicals; relevance rules.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "intent",
    [
        QueryIntentKind.CODE,
        QueryIntentKind.RESEARCH,
        QueryIntentKind.INFRASTRUCTURE,
        QueryIntentKind.LOOKUP,
        QueryIntentKind.CROSS_DOMAIN,
        QueryIntentKind.UNKNOWN,
    ],
)
def test_e_non_authority_intent_has_no_canonical_injection(
    tmp_path: Path, intent: QueryIntentKind
) -> None:
    vault = _vault_skeleton(tmp_path)
    ts = _CountingTaskService(vault)
    ts.create_task(
        task_id="tsk-cipher-rotation",
        title="Cipher rotation procedure",
        objective="Rotate service ciphers quarterly",
    )
    ds = _CountingDecisionService(vault, task_service=ts)
    ds.create_decision(
        decision_id="dec_cipher_approval",
        task_id="tsk-cipher-rotation",
        title="Cipher rotation approval",
        description="Approve cipher rotation procedure",
        requested_by="local",
    )
    _create_project(vault, "prj_cipher_fleet", "Cipher fleet rotation")
    _write_note(
        vault,
        "03_Resources/runbook.md",
        "---\ntype: Resource\ntitle: Cipher runbook\ntags: [runbook]\n---",
        "Cipher rotation procedure steps for operators.",
    )
    _write_note(
        vault,
        "03_Resources/memo.md",
        "---\ntype: Resource\ntitle: Canteen memo\ntags: [memo]\n---",
        "Unrelated canteen memo.",
    )
    planner = RetrievalPlanner(
        vault,
        task_service=ts,
        decision_service=ds,
        search_fn=lambda *a, **k: [
            _FakeHit(
                "03_Resources/runbook.md",
                "Cipher rotation procedure steps for operators.",
                0.9,
            ),
            _FakeHit("03_Resources/memo.md", "Unrelated canteen memo.", 0.7),
        ],
    )
    query = QueryIntent(
        query="Cipher rotation procedure steps",
        intent=intent,
        budget_class=BudgetClass.FAST,
    )
    result = planner.plan_and_retrieve(query, access_policy=_make_policy())
    ids = [c.source_id for c in result.candidates]
    assert ids == ["03_Resources/runbook.md", "03_Resources/memo.md"]
    assert ts.list_calls == 0
    assert ds.list_calls == 0


# ---------------------------------------------------------------------------
# Test F: stale / superseded / raw / unverified diagnostics retrievable.
# ---------------------------------------------------------------------------
def _diagnostic_hits() -> list[_FakeHit]:
    return [
        _FakeHit("02_Areas/stale.md", "Stale bridge maintenance roster.", 0.8),
        _FakeHit("02_Areas/sup.md", "Superseded bridge roster wording.", 0.7),
        _FakeHit("02_Areas/raw.md", "Raw bridge inspection capture.", 0.6),
        _FakeHit("02_Areas/plain.md", "Bridge survey note.", 0.5),
    ]


def _diagnostic_vault(tmp_path: Path) -> Path:
    vault = _vault_skeleton(tmp_path)
    _write_note(
        vault,
        "02_Areas/stale.md",
        "---\ntype: Area\ntitle: Stale roster\ntags: [stale]\n---",
        "Stale bridge maintenance roster.",
    )
    _write_note(
        vault,
        "02_Areas/sup.md",
        "---\ntype: Area\ntitle: Old roster\ntags: [superseded]\n---",
        "Superseded bridge roster wording.",
    )
    _write_note(
        vault,
        "02_Areas/raw.md",
        "---\ntype: Area\ntitle: Raw capture\ntags: [raw-capture]\n---",
        "Raw bridge inspection capture.",
    )
    _write_note(
        vault,
        "02_Areas/plain.md",
        "---\ntype: Area\ntitle: Survey note\ntags: [survey]\n---",
        "Bridge survey note.",
    )
    return vault


def test_f_diagnostics_excluded_by_default(tmp_path: Path) -> None:
    vault = _diagnostic_vault(tmp_path)
    planner = RetrievalPlanner(vault, search_fn=lambda *a, **k: _diagnostic_hits())
    intent = QueryIntent(
        query="bridge roster",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.FAST,
    )
    result = planner.plan_and_retrieve(
        intent, access_policy=_make_policy(raw="none", quarantine="none")
    )
    ids = [c.source_id for c in result.candidates]
    assert ids == ["02_Areas/plain.md"]
    reasons = {e.source_id: e.reason for e in result.excluded}
    assert reasons["02_Areas/raw.md"] == "raw_access_denied"
    assert reasons["02_Areas/sup.md"] == "superseded_evidence_excluded"
    assert reasons["02_Areas/stale.md"] == "archived_evidence_excluded"


def test_f_diagnostics_retrievable_with_policy(tmp_path: Path) -> None:
    vault = _diagnostic_vault(tmp_path)
    planner = RetrievalPlanner(vault, search_fn=lambda *a, **k: _diagnostic_hits())
    intent = QueryIntent(
        query="bridge roster",
        intent=QueryIntentKind.LOOKUP,
        budget_class=BudgetClass.FAST,
        include_archived=True,
        temporal_boundary=TemporalBoundary(as_of=date(2026, 9, 18), include_historical=True),
    )
    result = planner.plan_and_retrieve(intent, access_policy=_make_policy())
    ids = [c.source_id for c in result.candidates]
    assert "02_Areas/plain.md" in ids
    assert "02_Areas/stale.md" in ids
    assert "02_Areas/sup.md" in ids
    assert "02_Areas/raw.md" in ids
    by_id = {c.source_id: c for c in result.candidates}
    assert by_id["02_Areas/raw.md"].trust_state is TrustState.RAW
    assert by_id["02_Areas/sup.md"].trust_state is TrustState.SUPERSEDED
    assert by_id["02_Areas/stale.md"].trust_state is TrustState.ARCHIVED
    assert by_id["02_Areas/plain.md"].trust_state is TrustState.PROPOSED
