from __future__ import annotations

import pytest

from power_framework.core.memory_api import (
    apply_change,
    propose_change,
    read_history,
    validate_state,
)


def test_memory_transaction_requires_approval_and_records_history(sample_vault):
    proposal = propose_change(
        sample_vault,
        "01_Projects/Transaction.md",
        '---\ntype: Project\ntitle: "Transaction"\ndescription: "A transaction"\ntimestamp: 2026-07-29T00:00:00Z\n---\n\n# Transaction\n',
    )
    with pytest.raises(PermissionError):
        apply_change(sample_vault, proposal, approved=False)
    receipt = apply_change(sample_vault, proposal, approved=True)
    assert receipt["path"] == "01_Projects/Transaction.md"
    assert read_history(sample_vault)[0]["after_sha256"] == receipt["after_sha256"]
    assert isinstance(validate_state(sample_vault), bool)


def test_memory_transaction_rejects_stale_proposal(sample_vault):
    target = sample_vault / "01_Projects" / "TestProject.md"
    proposal = propose_change(sample_vault, "01_Projects/TestProject.md", "replacement")
    target.write_text("changed", encoding="utf-8")
    with pytest.raises(RuntimeError, match="stale"):
        apply_change(sample_vault, proposal, approved=True)
