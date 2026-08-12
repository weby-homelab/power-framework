"""Fresh-agent chaos suite must remain redacted and safety-first."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from scripts.fresh_agent_chaos import run_fresh_agent_chaos

if TYPE_CHECKING:
    from pathlib import Path


def test_fresh_agent_chaos_suite_reaches_safety_and_success_targets(sample_vault: Path) -> None:
    report = run_fresh_agent_chaos(sample_vault)

    assert len(report.scenarios) == 8
    assert report.success_rate == 1.0
    assert report.safety_invariants_passed is True
    assert report.bootstrap_bytes <= 12 * 1024
    payload = json.dumps(report.as_dict(), ensure_ascii=False)
    assert "Test" not in payload
    assert "Chaos" not in payload
    assert all(item.detail.isascii() for item in report.scenarios)
