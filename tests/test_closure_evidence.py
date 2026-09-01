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
    assert "8ab5314613f104c4aea8aa578bc602ae274ac910" in blocker_log
    assert "169c90f4a3239b89ef7f82bc6143b4e5b54219d3" not in blocker_log
    assert "256b61200af1a0bf6060d78107b9dc5fa885aabb" not in blocker_log


def test_prxmx_readonly_audit_reports_verified_runtime_and_skill_drift() -> None:
    audit = _read_json("phase-10-prxmx-readonly-audit.json")
    assert audit["mode"] == "read-only"
    assert audit["mutation_performed"] is False
    assert audit["remote_access_attempted"] is True
    assert audit["status"] == "DRIFT"
    assert audit["release_resolved"] is True
    assert audit["manifest_verified"] is True
    assert audit["wheel_verified"] is True

    transport = audit["transport"]
    assert transport["target_alias"] == "PRXMX-01"
    assert transport["batch_mode"] is True
    assert transport["identities_only"] is True
    assert transport["strict_host_key_checking"] is True
    assert transport["clear_all_forwardings"] is True
    assert transport["forward_agent"] is False
    assert transport["permit_local_command"] is False
    assert transport["request_tty"] is False
    assert transport["temporary_permission_removed_after_audit"] is True
    assert transport["credentials_or_authorization_material_persisted"] is False
    assert not {"address", "port", "user", "authentication"} & transport.keys()

    release = audit["release_resolution"]
    public_assets = _read_json("phase-03-public-assets.json")
    asset_digests = {
        asset["name"]: asset["api_digest"].removeprefix("sha256:")
        for asset in public_assets["assets"]
    }
    assert release["manifest_sha256"] == asset_digests["power-release-manifest.json"]
    assert release["wheel_sha256"] == asset_digests[release["wheel_filename"]]

    runtime = audit["runtime_inventory_summary"]
    assert runtime["runtime_count"] == 6
    assert runtime["versions"] == ["3.7.10"]
    assert runtime["all_target_versions_match"] is True
    assert runtime["host_paths_persisted"] is False
    assert "locations" not in runtime

    mcp = audit["mcp_summary"]
    assert mcp["config_count"] == 4
    assert mcp["canonical_count"] == 4
    assert mcp["private_configuration_values_persisted"] is False

    skill = audit["skill_summary"]
    assert skill["target_count"] == 5
    assert skill["up_to_date_count"] == 4
    assert skill["manual_review_count"] == 1
    assert skill["private_skill_content_persisted"] is False
    assert not skill["drift_target"].startswith("/")

    drift = audit["drift"]
    assert drift["runtime"] is False
    assert drift["mcp"] is False
    assert drift["skills"] is True
    assert drift["source_worktree"] is True
    assert drift["remote_immutability"] == "unchanged"

    source = audit["source_audit"]
    assert source["public_revision_and_blob_verified"] is True
    assert source["working_copy_dirty"] is True
    assert source["working_copy_executed"] is False

    immutability = audit["immutability"]
    assert set(immutability) == {
        "before_after_equal",
        "script_revision_unchanged",
        "script_blob_unchanged",
        "script_index_unchanged",
        "script_hash_unchanged",
        "script_status_unchanged",
        "source_worktree_dirty_unchanged",
        "mcp_metadata_hashes_unchanged",
        "skill_metadata_hashes_unchanged",
    }
    assert immutability["before_after_equal"] is True
    assert all(value is True for value in immutability.values())

    mutation = audit["mutation_evidence"]
    assert mutation["mutation_command_invoked"] is False
    assert mutation["bounded_target_metadata_unchanged"] is True
    assert mutation["universal_transient_write_absence_claim"] == "not_made"

    final = _read_json("final-public-repository-closure.json")
    assert final["verdicts"]["prxmx"] == "DRIFT_REMEDIATION_REQUIRED"
    assert final["verdicts"]["actions_security"] == "PASS_WITH_ACTIONLINT_UNAVAILABLE"
    assert (
        final["release_invariants"]["release_signing_fingerprint"]
        == "7AF1EDA195FE29FF093FB1CA2D49E810C7F2527E"
    )
    assert final["blockers"]["found"] == 6
    assert final["blockers"]["resolved"] == 4
    assert final["blockers"]["remaining"] == 2
    assert final["blockers"]["remaining_ids"] == ["BLK-0005", "BLK-0006"]

    expected_pr_snapshot = "8ab5314613f104c4aea8aa578bc602ae274ac910"
    assert final["closure_pr"]["head_at_latest_public_readback"] == expected_pr_snapshot

    report = (EVIDENCE / "POWER_3.7.10_PUBLIC_REPOSITORY_CLOSURE_REPORT.md").read_text(
        encoding="utf-8"
    )
    assert expected_pr_snapshot in report
    assert "blocked only by external authorization gates" not in report
    assert "absolute PRXMX path inventory" in report
