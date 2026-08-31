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
    assert summary["package_verification_output_scope"].startswith("combined wheel-and-sdist")
    assert summary["package_verification_output_is_not_artifact_digest"] is True

    for name in (
        "phase-07-wheel-attestation.json",
        "phase-07-sdist-attestation.json",
    ):
        evidence = _read_json(name)
        assert evidence["verification_output_is_not_artifact_digest"] is True
        assert "byte-identical" in evidence["verification_output_scope"]


def test_security_and_permissions_evidence_are_precisely_classified() -> None:
    permissions = _read_json("phase-21-actions-security.json")
    assert permissions["release_permissions_scope"] == "job"
    assert permissions["release_write_permissions_isolated_to_release_job"] is True
    assert "release_write_permissions_step_scoped" not in permissions

    security = _read_json("phase-22-repository-security.json")
    assert security["code_scanning_alerts_at_baseline"]["severity"].startswith("unknown")
    assert security["authenticated_default_branch_alert_readback"]["status"] == "available"
    assert security["p0_p1_absence_claim"] == "not_made"

    attestation_policy = permissions["attestation_policy"]
    assert attestation_policy["repository_scope_flag"] == "--repo"
    assert attestation_policy["signer_workflow_scope_flag"] == "--signer-workflow"
    assert attestation_policy["signer_workflow_identity_includes_repository"] is True
    assert attestation_policy["predicate_type_scope_flag"] == "--predicate-type"
    assert attestation_policy["raw_attestation_outputs_uploaded"] is False


def test_historical_untracked_inventory_is_complete_and_snapshot_scoped() -> None:
    baseline = _read_json("phase-00-baseline.json")
    assert baseline["preserved_untracked_count"] == 17
    preserved = baseline["preserved_untracked"]
    assert isinstance(preserved, list)
    assert len(preserved) == 17
    assert any(
        isinstance(item, dict)
        and item["path"]
        == "release/evidence/3.7.9/sbom/power-framework-3.7.9.prepublication.spdx.json"
        for item in preserved
    )

    hygiene = _read_json("phase-16-18-repository-hygiene.json")
    assert hygiene["preserved_untracked_historical_artifacts_count"] == 17
    assert hygiene["untracked_inventory_includes_ignored_files"] is True
    assert hygiene["snapshot_timing"]["open_count_fields_are_baseline_snapshot"] is True
    inventory = hygiene["preserved_untracked_historical_artifacts_inventory"]
    assert isinstance(inventory, list)
    assert len(inventory) == 17


def test_current_release_wording_marks_snapshots_and_local_only_history() -> None:
    release_doc = (ROOT / "docs" / "release-3.7.10.md").read_text(encoding="utf-8")
    assert "requires required CI" not in release_doc
    assert "It records the observed published release snapshot" in release_doc
    assert "WS-local-only" in release_doc
    assert "global" in release_doc.lower()

    final = _read_json("final-public-repository-closure.json")
    next_cycle = final["next_development_cycle"]
    assert "OWNER-ACTION-001" in next_cycle
    assert "OWNER-ACTION-002" in next_cycle

    blocker_log = (EVIDENCE / "blocker-log.md").read_text(encoding="utf-8")
    assert "1bca7ff5471095bdf9461e0d1a477c0f0087e78e" in blocker_log
    assert "256b61200af1a0bf6060d78107b9dc5fa885aabb" not in blocker_log
