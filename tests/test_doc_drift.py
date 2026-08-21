"""Regression tests for the executable documentation contract."""

from __future__ import annotations

import runpy
import shutil
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_DRIFT_SCRIPT = REPO_ROOT / "scripts" / "check_doc_drift.py"
REPO_SKILL_ROOT = REPO_ROOT / "skills" / "power"


def _load_gate() -> dict[str, Any]:
    return runpy.run_path(str(DOC_DRIFT_SCRIPT))


def _copy_repo_skill(dest: Path) -> Path:
    """Copy the canonical repository skill tree into a temp skill root."""
    root = dest / "power"
    (root / "references").mkdir(parents=True)
    shutil.copy(REPO_SKILL_ROOT / "SKILL.md", root / "SKILL.md")
    for name in ("agent-workflow.md", "runtime-contract.md"):
        shutil.copy(REPO_SKILL_ROOT / "references" / name, root / "references" / name)
    return root


def test_current_docs_match_the_executable_retrieval_contract() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()

    assert gate["check_retrieval_registry"](documents, facts) == []


def test_global_skill_discovery_includes_agent_and_opencode_roots(
    monkeypatch, tmp_path: Path
) -> None:
    gate = _load_gate()
    monkeypatch.delenv("POWER_GLOBAL_SKILL_PATH", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda _cls: tmp_path))

    expected = (
        tmp_path / ".agents" / "skills" / "power",
        tmp_path / ".opencode" / "skills" / "power",
        tmp_path / ".config" / "opencode" / "skills" / "power",
    )
    for root in expected:
        root.mkdir(parents=True)

    assert gate["_discover_global_skill_roots"]() == list(expected)


def test_retrieval_gate_rejects_a_missing_canonical_row() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()
    expected_row = "| `semantic` | `dense` | — | no | yes |"
    assert expected_row in documents["Architecture"]
    documents["Architecture"] = documents["Architecture"].replace(expected_row, "", 1)

    errors = gate["check_retrieval_registry"](documents, facts)

    assert any("semantic" in error and "does not match" in error for error in errors)


def test_retrieval_gate_rejects_unscoped_historical_token_claim() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()
    documents["README"] += "\nThe index provides ~75% token savings.\n"

    errors = gate["check_retrieval_registry"](documents, facts)

    assert any("unscoped historical token-saving claim" in error for error in errors)


def test_current_docs_match_executable_interfaces_and_safe_onboarding(
    monkeypatch, tmp_path: Path
) -> None:
    gate = _load_gate()
    monkeypatch.setenv("POWER_GLOBAL_SKILL_PATH", str(tmp_path / "no-global-copy"))
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()

    assert facts["source"] == "power_framework.core.capabilities"
    assert len(facts["interfaces"]["cli_commands"]) == 26
    assert len(facts["interfaces"]["mcp_tools"]) == 20
    assert gate["check_interfaces"](documents, facts) == []
    assert gate["check_onboarding"](documents, facts) == []
    assert gate["check_links"](documents, facts) == []


def test_current_client_onboarding_matches_native_mcp_shapes() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()

    assert gate["check_client_onboarding"](documents, facts) == []


def test_client_onboarding_gate_rejects_legacy_wrapper() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()
    documents["Client onboarding"] += "\n/root/geminicli/.agents/mcp_servers/power_server.py\n"

    errors = gate["check_client_onboarding"](documents, facts)

    assert any("repository-specific MCP wrapper" in error for error in errors)


def test_current_migration_guides_match_versioned_runtime_facts() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()

    assert gate["check_migration_guide"](documents, facts) == []


def test_migration_gate_rejects_stale_runtime_claims() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()
    documents["Migration"] = documents["Migration"].replace(
        "default search mode is `auto`", "default search mode is `reranked`", 1
    )
    documents["Migration UA"] = documents["Migration UA"].replace(
        "режим пошуку за замовчуванням — `auto`",
        "режим пошуку за замовчуванням — `reranked`",
        1,
    )

    errors = gate["check_migration_guide"](documents, facts)

    assert any("Migration" in error and "auto" in error for error in errors)
    assert any("Migration UA" in error and "auto" in error for error in errors)


def test_interface_gate_rejects_stale_architecture_count() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()
    documents["Architecture"] = documents["Architecture"].replace("26 commands", "15 commands", 1)

    errors = gate["check_interfaces"](documents, facts)

    assert any("Architecture" in error and "26 CLI commands" in error for error in errors)


def test_interface_gate_rejects_stale_readme_mcp_count() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()
    documents["README"] = documents["README"].replace("20 Async MCP Tools", "19 Async MCP Tools", 1)

    errors = gate["check_interfaces"](documents, facts)

    assert any("README" in error and "stale MCP tools count" in error for error in errors)


def test_interface_gate_rejects_stale_getting_started_count() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()
    documents["Getting Started"] = documents["Getting Started"].replace(
        "20-tool contract", "19-tool contract", 1
    )

    errors = gate["check_interfaces"](documents, facts)

    assert any("Getting Started" in error and "20 MCP tools" in error for error in errors)


def test_interface_gate_rejects_incomplete_mcp_risk_contract() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()
    facts["interfaces"]["mcp_tool_contracts"][0]["risk"].pop("approval")

    errors = gate["check_interfaces"](documents, facts)

    assert any("missing risk field `approval`" in error for error in errors)


def test_skill_body_gate_rejects_wrong_index_workflow() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    body = (REPO_SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    assert "power index <path>" in body
    body = body.replace("power index", "power lint")

    errors = gate["_check_skill_body"]("Agent skill", body, facts)

    assert any("Agent skill" in error and "index command" in error for error in errors)


def test_skill_gate_covers_workspace_references_and_readme_ua(monkeypatch, tmp_path: Path) -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()

    root = _copy_repo_skill(tmp_path)
    runtime = root / "references" / "runtime-contract.md"
    runtime.write_text(
        runtime.read_text(encoding="utf-8").replace("`sync_vault`", "`missing_tool`"),
        encoding="utf-8",
    )
    errors = gate["_check_skill_copy"]("Workspace agent skill", root / "SKILL.md", facts)
    assert any("Workspace agent skill" in error and "sync_vault" in error for error in errors)

    monkeypatch.setenv("POWER_GLOBAL_SKILL_PATH", str(tmp_path / "no-global-copy"))
    documents["README.ua"] = documents["README.ua"].replace("20 інструментів", "19 інструментів", 1)
    errors = gate["check_interfaces"](documents, facts)

    assert any("README.ua" in error and "MCP tools" in error for error in errors)


def test_onboarding_gate_rejects_unsafe_windows_launcher() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()
    documents["Windows"] += '\n"command": "py"\n'

    errors = gate["check_onboarding"](documents, facts)

    assert any("unscoped MCP Python launcher" in error for error in errors)


def test_link_gate_rejects_missing_local_target() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()
    documents["README"] += "\n[missing](docs/does-not-exist.md)\n"

    errors = gate["check_links"](documents, facts)

    assert any("does-not-exist.md" in error for error in errors)


def test_skill_gate_rejects_missing_references(tmp_path: Path) -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    root = _copy_repo_skill(tmp_path)
    shutil.rmtree(root / "references")

    errors = gate["_check_skill_copy"]("Test skill", root / "SKILL.md", facts)

    assert any(
        "missing referenced file `references/agent-workflow.md`" in error for error in errors
    )
    assert any(
        "missing referenced file `references/runtime-contract.md`" in error for error in errors
    )


def test_skill_body_gate_rejects_missing_workflow_markers() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    body = "---\nname: power\nversion: 3.4.0\n---\n\nOnly lint here: `power lint <path>`\n"

    errors = gate["_check_skill_body"]("Broken skill", body, facts)

    assert any("Broken skill" in error and "complete agent workflow" in error for error in errors)
    assert any("Broken skill" in error and "index command" in error for error in errors)
    assert any("Broken skill" in error and "doctor discovery" in error for error in errors)
    assert any(
        "progressive-disclosure reference `references/runtime-contract.md`" in error
        for error in errors
    )


def test_skill_body_gate_rejects_incomplete_okf_required_fields() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    body = (REPO_SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    body = body.replace("`description`, `timestamp`", "`description`", 1)

    errors = gate["_check_skill_body"]("Incomplete OKF skill", body, facts)

    assert any("executable OKF required fields" in error for error in errors)


def test_skill_gate_rejects_stale_reference_facts(tmp_path: Path) -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    root = _copy_repo_skill(tmp_path)
    runtime = root / "references" / "runtime-contract.md"
    runtime.write_text(
        runtime.read_text(encoding="utf-8")
        .replace("20 MCP tools", "19 MCP tools", 1)
        .replace("`sync_vault`", "`missing_tool`"),
        encoding="utf-8",
    )

    errors = gate["_check_skill_copy"]("Stale skill", root / "SKILL.md", facts)

    assert any(
        "Stale skill" in error and "does not declare all 20 MCP tools" in error for error in errors
    )
    assert any(
        "Stale skill" in error and "missing executable MCP tool `sync_vault`" in error
        for error in errors
    )


def test_fresh_agent_contract_exposes_safe_full_workflow() -> None:
    skill = (REPO_SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
    workflow = (REPO_SKILL_ROOT / "references" / "agent-workflow.md").read_text(encoding="utf-8")
    runtime = (REPO_SKILL_ROOT / "references" / "runtime-contract.md").read_text(encoding="utf-8")
    contract = "\n".join((skill, workflow, runtime))

    for marker in (
        "discover → inspect → retrieve → propose → apply → verify → handoff",
        "power doctor",
        "power ingest",
        "power memory",
        "power sync <path> --strict",
        "power index <path> --strict",
        "power lint <path>",
        "power markdown-check <path>",
        "log.md",
        "untrusted content",
    ):
        assert marker in contract


def test_global_skill_discovery_checks_both_opencode_paths(monkeypatch, tmp_path: Path) -> None:
    gate = _load_gate()
    home = tmp_path / "fake-home"
    for relative in (".opencode/skills/power", ".config/opencode/skills/power"):
        (home / relative).mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("POWER_GLOBAL_SKILL_PATH", raising=False)

    roots = gate["_discover_global_skill_roots"]()

    expected = {
        home / ".opencode" / "skills" / "power",
        home / ".config" / "opencode" / "skills" / "power",
    }
    assert {Path(r) for r in roots} == expected


def test_global_skill_discovery_respects_explicit_env_override(monkeypatch, tmp_path: Path) -> None:
    gate = _load_gate()
    explicit = tmp_path / "explicit-skill"
    explicit.mkdir(parents=True)
    monkeypatch.setenv("POWER_GLOBAL_SKILL_PATH", str(explicit))

    roots = gate["_discover_global_skill_roots"]()

    assert [Path(r) for r in roots] == [explicit]


def test_global_skill_discovery_accepts_explicit_skill_file(monkeypatch, tmp_path: Path) -> None:
    gate = _load_gate()
    skill_file = tmp_path / "power" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("POWER_GLOBAL_SKILL_PATH", str(skill_file))

    roots = gate["_discover_global_skill_roots"]()

    assert [Path(r) for r in roots] == [skill_file.parent]
