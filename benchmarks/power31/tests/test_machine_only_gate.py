"""Regression tests for the machine-only M2-M5 technical gate."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

EVALUATION_DIR = Path(__file__).resolve().parent.parent / "scripts" / "evaluation"
if str(EVALUATION_DIR) not in sys.path:
    sys.path.insert(0, str(EVALUATION_DIR))

import run_machine_only_gate as gate  # noqa: E402


def _contract() -> dict:
    return json.loads(gate.CONTRACT_DEFAULT.read_text(encoding="utf-8"))


def test_machine_only_contract_is_fail_closed() -> None:
    contract = _contract()
    gate._validate_contract(contract)
    assert contract["human_evidence_used"] is False
    assert contract["sealed_accessed"] is False
    assert contract["m5"]["human_quality_certification"] is False
    assert contract["m5"]["production_quality_claim"] is False


def test_contract_rejects_human_evidence() -> None:
    contract = _contract()
    contract["human_evidence_used"] = True
    with pytest.raises(ValueError, match="human evidence"):
        gate._validate_contract(contract)


def test_m4_machine_only_transaction_scenario_passes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    result = gate._run_m4(_contract())
    assert result["quality_gate"] == "PASS"
    assert result["approval_boundary_enforced"] is True
    assert result["stale_proposal_rejected"] is True
    assert result["validated_state"] is True
    assert result["history_entries"] == 2


def test_contract_copy_cannot_enable_sealed_or_human_scope() -> None:
    contract = _contract()
    changed = copy.deepcopy(contract)
    changed["sealed_accessed"] = True
    with pytest.raises(ValueError, match="sealed access"):
        gate._validate_contract(changed)
