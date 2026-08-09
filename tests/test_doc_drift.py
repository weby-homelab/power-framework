"""Regression tests for the executable documentation contract."""

from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DOC_DRIFT_SCRIPT = REPO_ROOT / "scripts" / "check_doc_drift.py"


def _load_gate() -> dict[str, Any]:
    return runpy.run_path(str(DOC_DRIFT_SCRIPT))


def test_current_docs_match_the_executable_retrieval_contract() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()

    assert gate["check_retrieval_registry"](documents, facts) == []


def test_retrieval_gate_rejects_a_missing_canonical_row() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()
    expected_row = "| `semantic` | `dense` | — | no | yes |"
    assert expected_row in documents["Architecture"]
    documents["Architecture"] = documents["Architecture"].replace(expected_row, "", 1)

    errors = gate["check_retrieval_registry"](documents, facts)

    assert any("semantic" in error and "does not match" in error for error in errors)


def test_current_docs_match_executable_interfaces_and_safe_onboarding() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()

    assert facts["source"] == "power_framework.core.capabilities"
    assert len(facts["interfaces"]["cli_commands"]) == 19
    assert len(facts["interfaces"]["mcp_tools"]) == 18
    assert gate["check_interfaces"](documents, facts) == []
    assert gate["check_onboarding"](documents, facts) == []
    assert gate["check_links"](documents, facts) == []


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
        "default search mode is `semantic`", "default search mode is `reranked`", 1
    )
    documents["Migration UA"] = documents["Migration UA"].replace(
        "режим пошуку за замовчуванням — `semantic`",
        "режим пошуку за замовчуванням — `reranked`",
        1,
    )

    errors = gate["check_migration_guide"](documents, facts)

    assert any("Migration" in error and "semantic" in error for error in errors)
    assert any("Migration UA" in error and "semantic" in error for error in errors)


def test_interface_gate_rejects_stale_architecture_count() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()
    documents["Architecture"] = documents["Architecture"].replace("19 commands", "15 commands", 1)

    errors = gate["check_interfaces"](documents, facts)

    assert any("Architecture" in error and "19 CLI commands" in error for error in errors)


def test_interface_gate_rejects_stale_getting_started_count() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()
    documents["Getting Started"] = documents["Getting Started"].replace(
        "18-tool contract", "17-tool contract", 1
    )

    errors = gate["check_interfaces"](documents, facts)

    assert any("Getting Started" in error and "18 MCP tools" in error for error in errors)


def test_interface_gate_rejects_incomplete_mcp_risk_contract() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()
    facts["interfaces"]["mcp_tool_contracts"][0]["risk"].pop("approval")

    errors = gate["check_interfaces"](documents, facts)

    assert any("missing risk field `approval`" in error for error in errors)


def test_agent_skill_gate_rejects_wrong_index_workflow() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()
    marker = "```bash\npower index <path>\n```"
    assert marker in documents["Agent skill"]
    documents["Agent skill"] = documents["Agent skill"].replace(
        marker, "```bash\npower lint <path>\n```", 1
    )

    errors = gate["check_interfaces"](documents, facts)

    assert any("Agent skill" in error and "index command" in error for error in errors)


def test_agent_skill_gate_covers_workspace_copy_and_readme_ua() -> None:
    gate = _load_gate()
    facts = gate["_load_code_facts"]()
    documents = gate["_read_current_documents"]()
    documents["Workspace agent skill"] = documents["Workspace agent skill"].replace(
        "`sync_vault`", "`missing_tool`", 1
    )
    documents["README.ua"] = documents["README.ua"].replace("18 інструментів", "17 інструментів", 1)

    errors = gate["check_interfaces"](documents, facts)

    assert any("Workspace agent skill" in error and "sync_vault" in error for error in errors)
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
