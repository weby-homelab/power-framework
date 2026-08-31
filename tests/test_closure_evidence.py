"""Regression checks for truthful public closure evidence wording and shape."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "release" / "evidence" / "3.7.10-postrelease"


def _read_json(name: str) -> dict[str, object]:
    return json.loads((EVIDENCE / name).read_text(encoding="utf-8"))


def test_observed_attestation_ids_are_not_invented() -> None:
    expected_status = "AMBIGUOUS_NOT_EXPOSED_BY_GH_ATTESTATION_VERIFY_OUTPUT"
    for name in (
        "phase-07-wheel-attestation.json",
        "phase-07-sdist-attestation.json",
        "phase-07-web-attestation.json",
    ):
        evidence = _read_json(name)
        assert evidence["raw_output_attestation_id_field_present"] is False
        observed = evidence["observed_attestations"]
        assert isinstance(observed, list)
        assert observed
        for entry in observed:
            assert isinstance(entry, dict)
            assert entry["attestation_id"] is None
            assert entry["attestation_id_status"] == expected_status
        assert evidence["observed_attestation_id_mapping"] == "ambiguous"

    summary = _read_json("phase-07-attestation-summary.json")
    mapping = summary["observed_attestation_id_mapping"]
    assert isinstance(mapping, dict)
    assert mapping["status"] == "AMBIGUOUS"
    assert mapping["observed_entries_carry_null_ids"] is True


def test_security_and_permissions_evidence_are_precisely_classified() -> None:
    permissions = _read_json("phase-21-actions-security.json")
    assert permissions["release_permissions_scope"] == "job"
    assert permissions["release_write_permissions_isolated_to_release_job"] is True
    assert "release_write_permissions_step_scoped" not in permissions

    security = _read_json("phase-22-repository-security.json")
    assert security["code_scanning_alerts_at_baseline"]["severity"].startswith("unknown")
    assert security["authenticated_default_branch_alert_readback"]["status"] == "available"
    assert security["p0_p1_absence_claim"] == "not_made"


def test_current_release_wording_marks_snapshots_and_local_only_history() -> None:
    release_doc = (ROOT / "docs" / "release-3.7.10.md").read_text(encoding="utf-8")
    assert "requires required CI" not in release_doc
    assert "It records the observed published release snapshot" in release_doc
    assert "WS-local-only" in release_doc
    assert "global" in release_doc.lower()
