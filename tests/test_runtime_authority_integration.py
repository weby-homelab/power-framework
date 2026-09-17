"""Tests for P38-WP03-R2: Runtime Authority Integration & Provenance Binding."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from power_framework.core.application import ApplicationService
from power_framework.core.context_contracts import (
    AccessPolicy,
    Authority,
    AuthorityBasis,
    BudgetClass,
    Freshness,
    QueryIntent,
    QueryIntentKind,
    TrustState,
)
from power_framework.core.decision_service import DecisionService
from power_framework.core.retrieval_planner import (
    RetrievalPlanner,
    _inspect_vault_note_authority,
)
from power_framework.core.state_service import ProjectStateService
from power_framework.core.task_service import TaskService


def _make_access_policy(
    *,
    raw: str = "privileged",
    quarantine: str = "privileged",
) -> AccessPolicy:
    now = datetime.now(UTC)
    data = {
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


def test_application_service_wires_project_state_service(tmp_path: Path) -> None:
    """ApplicationService initializes ProjectStateService and wires it."""
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    for folder in [
        "01_Projects",
        "02_Areas",
        "03_Resources",
        "04_Archive",
        "05_Templates",
        "06_Daily_Logs",
        ".power",
    ]:
        (vault / folder).mkdir(parents=True, exist_ok=True)

    app = ApplicationService(vault)
    assert app.project_state_service is not None
    assert isinstance(app.project_state_service, ProjectStateService)
    assert app.decision_service is not None
    assert isinstance(app.decision_service, DecisionService)
    assert app.task_service is not None
    assert isinstance(app.task_service, TaskService)


def test_inspect_vault_note_authority_canonical_project(tmp_path: Path) -> None:
    """P38-WP03-R3: project-state tag alone never grants CANONICAL without service proof."""
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    note = vault / "01_Projects" / "current_proj.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "---\n"
        "type: Project\n"
        "title: Current Project\n"
        "status: active\n"
        "tags: [power38, project-state]\n"
        "---\n"
        "# Project Status\n"
        "Phase 5 is active.\n",
        encoding="utf-8",
    )

    auth, trust, basis, stype, fresh, _contra, _noise = _inspect_vault_note_authority(
        vault, "01_Projects/current_proj.md", "Phase 5 is active."
    )
    assert auth is Authority.UNVERIFIED
    assert trust is TrustState.PROPOSED
    assert basis is AuthorityBasis.PROPOSAL
    assert stype == "vault_note"
    assert fresh is Freshness.UNKNOWN


def test_inspect_vault_note_authority_superseded_project(tmp_path: Path) -> None:
    """P38-WP03-R3: superseded tag lowers trust but never raises to VERIFIED."""
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    note = vault / "01_Projects" / "old_proj.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "---\n"
        "type: Project\n"
        "title: Old Project\n"
        "status: archived\n"
        "tags: [power38, superseded]\n"
        "---\n"
        "# Old Project\n"
        "Historical content.\n",
        encoding="utf-8",
    )

    auth, trust, _basis, _stype, fresh, contra, _noise = _inspect_vault_note_authority(
        vault, "01_Projects/old_proj.md", "Historical content."
    )
    assert auth is Authority.UNVERIFIED
    assert trust is TrustState.SUPERSEDED
    assert _basis is AuthorityBasis.PROPOSAL
    assert fresh is Freshness.STALE
    assert contra.value == "superseded"


def test_inspect_vault_note_authority_raw_chat(tmp_path: Path) -> None:
    """Daily log or raw-capture tag receives UNVERIFIED authority and RAW trust."""
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    note = vault / "06_Daily_Logs" / "chat.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "---\n"
        "type: Daily Log\n"
        "title: Chat log\n"
        "status: active\n"
        "tags: [power38, raw-capture]\n"
        "---\n"
        "# Raw chat\n"
        "Informal chatter.\n",
        encoding="utf-8",
    )

    auth, trust, basis, stype, _fresh, _contra, _noise = _inspect_vault_note_authority(
        vault, "06_Daily_Logs/chat.md", "Informal chatter."
    )
    assert auth is Authority.UNVERIFIED
    assert trust is TrustState.RAW
    assert basis is AuthorityBasis.RAW_CAPTURE
    assert stype == "raw_capture"


def test_canonical_beats_raw_in_retrieval(tmp_path: Path) -> None:
    """P38-WP03-R3: tag alone never grants CANONICAL; both notes stay UNVERIFIED."""
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    p_curr = vault / "01_Projects" / "proj_current.md"
    p_curr.parent.mkdir(parents=True, exist_ok=True)
    p_curr.write_text(
        "---\n"
        "type: Project\n"
        "title: Power 3.8 state\n"
        "status: active\n"
        "tags: [power38, project-state]\n"
        "---\n"
        "# Current State\n"
        "Exact canonical record.\n",
        encoding="utf-8",
    )

    p_raw = vault / "06_Daily_Logs" / "proj_raw.md"
    p_raw.parent.mkdir(parents=True, exist_ok=True)
    p_raw.write_text(
        "---\n"
        "type: Daily Log\n"
        "title: Power 3.8 state chat\n"
        "status: active\n"
        "tags: [power38, raw-capture]\n"
        "---\n"
        "# Chatter\n"
        "Power 3.8 state with high lexical repetition.\n",
        encoding="utf-8",
    )

    class FakeHit:
        def __init__(self, rel_path: str, content: str, score: float) -> None:
            self.rel_path = rel_path
            self.content = content
            self.snippet = content
            self.score = score

    fake_hits = [
        FakeHit("06_Daily_Logs/proj_raw.md", "Power 3.8 state with high lexical repetition", 0.95),
        FakeHit("01_Projects/proj_current.md", "Exact canonical record", 0.40),
    ]

    planner = RetrievalPlanner(
        vault,
        search_fn=lambda *args, **kwargs: fake_hits,
    )
    intent = QueryIntent(
        query="Power 3.8 current state",
        intent=QueryIntentKind.PROJECT_STATE,
        budget_class=BudgetClass.FAST,
    )
    policy = _make_access_policy(raw="privileged")
    result = planner.plan_and_retrieve(intent, access_policy=policy)

    assert len(result.candidates) == 2
    # TEXT != AUTHORITY: without owning-service proof neither tag grants CANONICAL.
    for candidate in result.candidates:
        assert candidate.authority is Authority.UNVERIFIED
        assert candidate.provenance.authority_basis is not AuthorityBasis.CANONICAL_LEDGER
    by_id = {c.source_id: c for c in result.candidates}
    assert by_id["01_Projects/proj_current.md"].trust_state is TrustState.PROPOSED
    assert by_id["06_Daily_Logs/proj_raw.md"].trust_state is TrustState.RAW


def test_superseded_decision_excluded_by_default(tmp_path: Path) -> None:
    """Superseded decision is excluded from candidates when query does not request historical."""
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    d_curr = vault / "01_Projects" / "dec_curr.md"
    d_curr.parent.mkdir(parents=True, exist_ok=True)
    d_curr.write_text(
        "---\n"
        "type: Project\n"
        "title: Decision current\n"
        "status: active\n"
        "tags: [power38, decision]\n"
        "---\n"
        "# Current Decision\n"
        "Approved architecture.\n",
        encoding="utf-8",
    )

    d_old = vault / "01_Projects" / "dec_old.md"
    d_old.write_text(
        "---\n"
        "type: Project\n"
        "title: Decision old\n"
        "status: archived\n"
        "tags: [power38, superseded, decision]\n"
        "---\n"
        "# Old Decision\n"
        "Provisional proposal.\n",
        encoding="utf-8",
    )

    class FakeHit:
        def __init__(self, rel_path: str, content: str, score: float) -> None:
            self.rel_path = rel_path
            self.content = content
            self.snippet = content
            self.score = score

    fake_hits = [
        FakeHit("01_Projects/dec_old.md", "Provisional proposal old decision", 0.99),
        FakeHit("01_Projects/dec_curr.md", "Approved architecture current decision", 0.70),
    ]

    planner = RetrievalPlanner(
        vault,
        search_fn=lambda *args, **kwargs: fake_hits,
    )
    intent = QueryIntent(
        query="architecture decision",
        intent=QueryIntentKind.DECISION,
        budget_class=BudgetClass.FAST,
    )
    policy = _make_access_policy(raw="none")
    result = planner.plan_and_retrieve(intent, access_policy=policy)

    # dec_old must be excluded
    candidate_ids = [c.source_id for c in result.candidates]
    assert "01_Projects/dec_curr.md" in candidate_ids
    assert "01_Projects/dec_old.md" not in candidate_ids
    assert any(e.source_id == "01_Projects/dec_old.md" for e in result.excluded)


def test_archived_infra_excluded_by_default(tmp_path: Path) -> None:
    """Archived infrastructure note is excluded when include_archived is False."""
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    infra_curr = vault / "02_Areas" / "infra_curr.md"
    infra_curr.parent.mkdir(parents=True, exist_ok=True)
    infra_curr.write_text(
        "---\n"
        "type: Area\n"
        "title: Infra current\n"
        "status: active\n"
        "tags: [power38, infrastructure]\n"
        "---\n"
        "# Current Infra\n"
        "Active cluster.\n",
        encoding="utf-8",
    )

    infra_stale = vault / "02_Areas" / "infra_stale.md"
    infra_stale.write_text(
        "---\n"
        "type: Area\n"
        "title: Infra stale\n"
        "status: archived\n"
        "tags: [power38, historical]\n"
        "---\n"
        "# Stale Infra\n"
        "Old machine assumptions.\n",
        encoding="utf-8",
    )

    class FakeHit:
        def __init__(self, rel_path: str, content: str, score: float) -> None:
            self.rel_path = rel_path
            self.content = content
            self.snippet = content
            self.score = score

    fake_hits = [
        FakeHit("02_Areas/infra_stale.md", "Old machine assumptions", 0.99),
        FakeHit("02_Areas/infra_curr.md", "Active cluster current infra", 0.60),
    ]

    planner = RetrievalPlanner(
        vault,
        search_fn=lambda *args, **kwargs: fake_hits,
    )
    intent = QueryIntent(
        query="infrastructure setup",
        intent=QueryIntentKind.INFRASTRUCTURE,
        budget_class=BudgetClass.FAST,
        include_archived=False,
    )
    policy = _make_access_policy(raw="none")
    result = planner.plan_and_retrieve(intent, access_policy=policy)

    candidate_ids = [c.source_id for c in result.candidates]
    assert "02_Areas/infra_curr.md" in candidate_ids
    assert "02_Areas/infra_stale.md" not in candidate_ids
    assert any(e.source_id == "02_Areas/infra_stale.md" for e in result.excluded)


def test_curated_research_beats_unverified(tmp_path: Path) -> None:
    """P38-WP03-R3: research/Resource tags alone never grant CURATED without proof."""
    vault = tmp_path / "vault"
    vault.mkdir(parents=True, exist_ok=True)
    r_cur = vault / "03_Resources" / "res_curated.md"
    r_cur.parent.mkdir(parents=True, exist_ok=True)
    r_cur.write_text(
        "---\n"
        "type: Resource\n"
        "title: Curated Research\n"
        "status: active\n"
        "tags: [power38, research]\n"
        "---\n"
        "# Research\n"
        "Curated findings.\n",
        encoding="utf-8",
    )

    r_prop = vault / "03_Resources" / "res_unverified.md"
    r_prop.write_text(
        "---\n"
        "type: Resource\n"
        "title: Unverified Research\n"
        "status: review\n"
        "tags: [power38, research, proposed]\n"
        "---\n"
        "# Proposed\n"
        "Unverified claim.\n",
        encoding="utf-8",
    )

    class FakeHit:
        def __init__(self, rel_path: str, content: str, score: float) -> None:
            self.rel_path = rel_path
            self.content = content
            self.snippet = content
            self.score = score

    fake_hits = [
        FakeHit("03_Resources/res_unverified.md", "Unverified claim with high lexical match", 0.98),
        FakeHit("03_Resources/res_curated.md", "Curated findings lower match", 0.50),
    ]

    planner = RetrievalPlanner(
        vault,
        search_fn=lambda *args, **kwargs: fake_hits,
    )
    intent = QueryIntent(
        query="evaluation practice research",
        intent=QueryIntentKind.RESEARCH,
        budget_class=BudgetClass.FAST,
    )
    policy = _make_access_policy(raw="none")
    result = planner.plan_and_retrieve(intent, access_policy=policy)

    assert len(result.candidates) == 2
    for candidate in result.candidates:
        assert candidate.authority is Authority.UNVERIFIED
        assert candidate.provenance.authority_basis is not AuthorityBasis.CURATED_NOTE
        assert candidate.provenance.authority_basis is not AuthorityBasis.CANONICAL_LEDGER
        assert candidate.provenance.authority_basis is not AuthorityBasis.VERIFIED_PROJECTION
    by_id = {c.source_id: c for c in result.candidates}
    assert by_id["03_Resources/res_curated.md"].trust_state is TrustState.PROPOSED
    assert by_id["03_Resources/res_unverified.md"].trust_state is TrustState.PROPOSED
