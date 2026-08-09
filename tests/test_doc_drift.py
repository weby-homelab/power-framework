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

    assert len(facts["cli_commands"]) == 17
    assert len(facts["mcp_tools"]) == 18
    assert gate["check_interfaces"](documents, facts) == []
    assert gate["check_onboarding"](documents, facts) == []
    assert gate["check_links"](documents, facts) == []


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
