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
