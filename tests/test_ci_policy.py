"""Regression checks for blocking GitHub Actions policy."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / ".github" / "workflows"
REPO_ROOT = WORKFLOWS_DIR.parent.parent
FORBIDDEN_WORKFLOW_PATTERNS = ("continue-on-error", "|| true", "/root/gemma/brain")


def test_pr_workflows_do_not_suppress_or_depend_on_private_vaults() -> None:
    workflow_text = "\n".join(
        path.read_text(encoding="utf-8") for path in WORKFLOWS_DIR.glob("*.yml")
    )

    for pattern in FORBIDDEN_WORKFLOW_PATTERNS:
        assert pattern not in workflow_text, f"workflow policy forbids {pattern!r}"


def test_ci_keeps_blocking_test_and_security_jobs() -> None:
    ci_text = (WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8")

    assert "  test:" in ci_text
    assert "  security:" in ci_text


def test_ci_defers_non_linux_runtime_smoke_for_3_6_2() -> None:
    ci_text = (WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8")

    assert "windows-latest" not in ci_text
    assert "macos-latest" not in ci_text
    assert "runs-on: ubuntu-latest" in ci_text


def test_ci_aggregates_all_supported_ubuntu_reports() -> None:
    ci_text = (WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8")

    assert "  upgrade-matrix-aggregate:" in ci_text
    assert "actions/upload-artifact@" in ci_text
    assert "actions/download-artifact@" in ci_text
    assert "merge-multiple: true" in ci_text
    assert "scripts/aggregate_upgrade_matrix.py" in ci_text
    assert "os: [ubuntu-latest]" in ci_text
    assert "--require-supported-platforms" in ci_text
    assert "name: power-release-upgrade-aggregate" in ci_text
    assert "power-release-upgrade-aggregate.json" in ci_text


def test_current_python_support_starts_at_3_11() -> None:
    ci_text = (WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8")
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'requires-python = ">=3.13,<3.15"' in pyproject_text
    assert '"Programming Language :: Python :: 3.10"' not in pyproject_text
    assert 'python-version: ["3.13", "3.14"]' in ci_text
    assert '"3.10"' not in ci_text


def test_workflow_actions_are_pinned_to_immutable_commits() -> None:
    for workflow_path in WORKFLOWS_DIR.glob("*.yml"):
        for line in workflow_path.read_text(encoding="utf-8").splitlines():
            if "uses:" not in line:
                continue
            assert re.search(r"uses:\s+[^@\s]+@[0-9a-f]{40}(?:\s+#.*)?$", line), (
                f"{workflow_path.name} contains an unpinned action: {line.strip()}"
            )


def test_release_workflow_publishes_sbom_and_attestation() -> None:
    release_text = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")

    assert "anchore/sbom-action@" in release_text
    assert "actions/attest-build-provenance@" in release_text
    assert "dist/*.spdx.json" in release_text
    assert "Generate package SPDX SBOM bound to the exact wheel" in release_text
    assert "Generate Web SPDX SBOM bound to the exact image" in release_text
    assert release_text.count("upload-release-assets: false") == 2
    assert (
        "image: ${{ steps.web_image.outputs.reference }}@${{ steps.web_image.outputs.digest }}"
        in release_text
    )
    assert "subject-name: ghcr.io/weby-homelab/power-framework-web" in release_text
    assert "subject-digest:" in release_text
    assert "scripts/profile_acceptance.py" in release_text
    assert "Prefetch locked model snapshots for real Web acceptance" in release_text
    assert "ACCEPTANCE_HARNESS_ROOT" in release_text
    assert "Verify acceptance harness revision" in release_text
    assert "ACCEPTANCE_HARNESS_REVISION" in release_text
    assert "ACCEPTANCE_HARNESS_ROOT: ." in release_text
    assert "Checkout current acceptance harness for tag recovery" not in release_text
    assert "Remove tag recovery harness checkout" not in release_text
    assert "rm -rf -- .release-acceptance-harness" not in release_text
    assert "--profile-evidence" in release_text
    assert "attestations: write" in release_text
    assert "id-token: write" in release_text
    assert "gh release view" in release_text
    assert "GitHub release readback verified" in release_text
    assert "scripts/verify_public_release_bindings.py" in release_text
    assert release_text.count("$RELEASE_CONTROL_ROOT/verify_public_release_bindings.py") == 2
    assert "--expected-tag-target" in release_text
    assert "--attestation-subject" in release_text
    assert 'header = "Authorization: Bearer ' in release_text
    assert "Re-read immutable tag objects immediately before publication" in release_text
    assert "gh release create" in release_text
    assert "--verify-tag" in release_text
    assert "softprops/action-gh-release" not in release_text
    assert release_text.index("Generate release receipt from frozen assets") < release_text.index(
        "Create GitHub Release"
    )


def test_release_package_sbom_scans_the_wheel_as_a_file() -> None:
    release_text = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")

    assert "file: ${{ runner.temp }}/power-framework-package.whl" in release_text
    assert "path: ${{ runner.temp }}/power-framework-package.whl" not in release_text


def test_release_publish_is_blocked_by_a_tag_validation_job() -> None:
    release_text = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")
    workflow = yaml.safe_load(release_text)
    jobs = workflow["jobs"]

    assert "  validate:" in release_text
    assert "signed_tag_admission" in jobs
    admission = jobs["signed_tag_admission"]
    assert admission["needs"] == "release_input"
    assert admission["outputs"] == {
        "tag_object": "${{ steps.admit.outputs.tag_object }}",
        "tag_target": "${{ steps.admit.outputs.tag_target }}",
    }
    admission_run = next(
        step["run"]
        for step in admission["steps"]
        if step.get("name") == "Admit exact signed annotated tag"
    )
    assert 'git verify-tag --raw "$RELEASE_TAG"' in admission_run
    assert 'git verify-commit --raw "$local_tag_target"' in admission_run
    assert 'git cat-file -t "$local_tag_object"' in admission_run
    assert "uv run" not in admission_run
    assert "pytest" not in admission_run
    assert "scripts/" not in admission_run
    assert (
        admission["steps"][0]["with"]["ref"]
        == "${{ format('refs/tags/{0}', needs.release_input.outputs.release_tag) }}"
    )
    assert admission["steps"][0]["with"]["persist-credentials"] is False
    assert workflow["concurrency"]["group"] == (
        "power-release-${{ github.event_name == 'workflow_dispatch' && inputs.release_tag || github.ref_name }}"
    )
    for job_id in ("validate", "upgrade-matrix", "upgrade-matrix-aggregate", "release"):
        needs = jobs[job_id]["needs"]
        needs_set = {needs} if isinstance(needs, str) else set(needs)
        assert "signed_tag_admission" in needs_set
    control_fetch = next(
        step
        for step in jobs["release"]["steps"]
        if step.get("name") == "Fetch exact release control verifier"
    )
    assert control_fetch["env"]["RELEASE_CONTROL_REF"] == "${{ github.sha }}"
    assert control_fetch["env"]["RELEASE_CONTROL_ROOT"] == (
        "${{ runner.temp }}/power-release-control"
    )
    assert "base64 --decode" in control_fetch["run"]
    assert (
        "uv sync --locked --group dev --extra web --extra semantic --extra rerank" in release_text
    )
    assert "uv run pytest tests/" in release_text
    assert "uv run mkdocs build --strict" in release_text
    assert "complexity_dashboard.py --baseline-revision v3.4.5 --require-budget" in release_text
    assert "  upgrade-matrix:" in release_text
    assert "os: [ubuntu-latest]" in release_text
    assert "--require-supported-platforms" in release_text
    assert "macos-latest" not in release_text
    assert "windows-latest" not in release_text
    assert "  upgrade-matrix-aggregate:" in release_text
    assert "needs: [release_input, signed_tag_admission, validate]" in release_text
    assert "needs: [release_input, signed_tag_admission, upgrade-matrix]" in release_text
    assert (
        "needs: [release_input, signed_tag_admission, validate, upgrade-matrix-aggregate]"
        in release_text
    )
    assert "--require-signed-tag" in release_text
    assert "Verify signed release tag and maintainer fingerprint" in release_text
    assert "Install the pinned maintainer release signing key" not in release_text
    assert "GNUPGHOME" in release_text
    assert "VALIDSIG" in release_text
    assert "gh api users/weby-homelab/gpg_keys" in release_text
    assert 'select(.key_id == "2D49E810C7F2527E")' in release_text
    assert "7AF1EDA195FE29FF093FB1CA2D49E810C7F2527E" in release_text
    assert 'gpg --batch --import "$key_file"' in release_text
    assert "Reject an existing GitHub release for this tag" in release_text
    assert "api.github.com/repos/${GITHUB_REPOSITORY}/releases/tags/${RELEASE_TAG}" in release_text
    assert "Unable to prove release absence" in release_text
    assert "Validate immutable manual release recovery" in release_text
    assert "Manual recovery is immutable; tag mutation is forbidden" in release_text
    assert (
        "Recovery may publish only the existing signed tag when no Release exists" in release_text
    )
    assert release_text.count('header = "Authorization: Bearer ') == 3
    assert '"Authorization: Bearer ${GH_TOKEN}"' not in release_text
    assert "workflow_dispatch" in release_text
    assert "inputs.release_tag" in release_text
    assert "Validate the exact release tag checkout" in release_text
    assert '[[ "$RELEASE_TAG" =~ ^v[0-9]+\\.[0-9]+\\.[0-9]+$ ]]' in release_text
    assert 'git ls-remote origin "refs/tags/${RELEASE_TAG}^{}"' in release_text
    assert 'git ls-remote origin "refs/tags/${RELEASE_TAG}"' in release_text
    assert "REMOTE_TAG_TARGET" in release_text
    assert "REMOTE_TAG_OBJECT" in release_text
    assert "permissions: {}" in release_text
    assert (
        "RELEASE_TAG: ${{ github.event_name == 'workflow_dispatch' && needs.release_input.outputs.release_tag || github.ref_name }}"
        in release_text
    )
    assert "--pending-mandatory profile-a-mcp-stdio" in release_text
    assert "--pending-mandatory profile-b-web-acceptance" in release_text
    assert "--pending-mandatory web-semantic-acceptance" in release_text
    assert "--pending-mandatory web-rerank-acceptance" in release_text
    assert "--pending-mandatory public-release-readback" in release_text


def test_release_harness_and_publication_guards_are_tag_bound() -> None:
    workflow = yaml.safe_load((WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8"))
    release_job = workflow["jobs"]["release"]
    steps = release_job["steps"]

    harness_revision = next(
        step for step in steps if step.get("name") == "Verify acceptance harness revision"
    )
    assert (
        harness_revision["env"]["EXPECTED_HARNESS_REVISION"]
        == "${{ needs.signed_tag_admission.outputs.tag_target }}"
    )
    profile_acceptance = next(
        step
        for step in steps
        if step.get("name") == "Prove Profile A/B against the exact Web image"
    )
    assert (
        profile_acceptance["env"]["ACCEPTANCE_HARNESS_REVISION"]
        == "${{ needs.signed_tag_admission.outputs.tag_target }}"
    )
    assert profile_acceptance["env"]["ACCEPTANCE_HARNESS_ROOT"] == "."

    registry_step = next(
        step for step in steps if step.get("name") == "Authenticate and publish Web-only image"
    )
    assert registry_step["env"]["DOCKER_CONFIG"] == (
        "${{ runner.temp }}/power-release-docker-config"
    )
    assert "GH_TOKEN" in registry_step["env"]
    assert "docker login ghcr.io" in registry_step["run"]
    assert "docker buildx build" in registry_step["run"]
    assert "trap 'docker logout ghcr.io' EXIT" in registry_step["run"]
    assert "docker logout ghcr.io" in registry_step["run"]
    assert "STAGING_IMAGE_REF" in registry_step["env"]
    promote_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Promote exact Web image digest to release tag"
    )
    promote_step = steps[promote_index]
    assert promote_step["env"]["SOURCE_IMAGE_REF"] == "${{ steps.web_image.outputs.reference }}"
    assert promote_step["env"]["FINAL_IMAGE_REF"] == (
        "${{ steps.web_image.outputs.final_reference }}"
    )
    assert "ghcr.io/token?service=ghcr.io" in promote_step["run"]
    assert "Unable to establish GHCR release tag state" in promote_step["run"]
    assert "docker buildx imagetools create" in promote_step["run"]
    assert "--prefer-index=false" in promote_step["run"]
    assert '"${SOURCE_IMAGE_REF}@${WEB_IMAGE_DIGEST}"' in promote_step["run"]
    assert "docker logout ghcr.io" in promote_step["run"]
    assert "DOCKER_CONFIG" not in release_job.get("env", {})
    assert "POWER_RELEASE_GHCR_TOKEN" not in "\n".join(
        str(step.get("run", "")) for step in steps[promote_index + 1 :]
    )

    final_absence_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Reconfirm authenticated release absence before publication"
    )
    final_tag_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Re-read immutable tag objects immediately before publication"
    )
    create_index = next(
        index for index, step in enumerate(steps) if step.get("name") == "Create GitHub Release"
    )
    assert final_absence_index + 1 == final_tag_index
    assert final_tag_index + 1 == create_index

    post_create_tag_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Verify public tag binding after release creation"
    )
    assert create_index + 1 == post_create_tag_index
    assert post_create_tag_index + 1 == next(
        index
        for index, step in enumerate(steps)
        if step.get("name") == "Read back GitHub release metadata and assets"
    )

    public_binding_step = next(
        step
        for step in steps
        if step.get("name") == "Verify public asset checksums, manifest bindings, and OCI readback"
    )
    assert '"$RELEASE_CONTROL_ROOT/verify_public_release_bindings.py"' in public_binding_step["run"]
    assert 'verified_image_digest"' in public_binding_step["run"]
    assert 'registry_digest" = "$verified_image_digest"' in public_binding_step["run"]

    attestation_step = next(
        step for step in steps if step.get("name") == "Verify public artifact and Web attestations"
    )
    assert "gh attestation verify" in attestation_step["run"]
    assert "--bundle-from-oci" in attestation_step["run"]
    assert "docker login ghcr.io" in attestation_step["run"]
    assert "docker logout ghcr.io" in attestation_step["run"]

    evidence_step = next(
        step
        for step in steps
        if step.get("name") == "Upload release evidence on success or failure"
    )
    assert evidence_step["if"] == "always()"
    assert evidence_step["with"]["if-no-files-found"] == "ignore"
    assert "dist/" in evidence_step["with"]["path"]

    final_tag_run = steps[final_tag_index]["run"]
    for required in (
        'git ls-remote origin "$tag_ref"',
        'git ls-remote origin "${tag_ref}^{}"',
        'git rev-parse --verify "${tag_ref}^{tag}"',
        'git rev-parse --verify "${tag_ref}^{commit}"',
        'git cat-file -t "$remote_tag_object"',
        '"$remote_tag_object" = "$EXPECTED_TAG_OBJECT"',
        '"$remote_tag_target" = "$EXPECTED_TAG_TARGET"',
    ):
        assert required in final_tag_run

    create_step = steps[create_index]
    token_key = "GH" + "_TOKEN"
    github_token_expression = "${{" + " github.token }}"
    assert create_step["env"][token_key] == github_token_expression
    assert 'gh release create "$RELEASE_TAG"' in create_step["run"]
    assert "--verify-tag" in create_step["run"]
    for forbidden in ("git push", "gh release edit", "gh release delete", "git tag "):
        assert forbidden not in create_step["run"]


def test_every_checkout_disables_persisted_credentials() -> None:
    for workflow_path in WORKFLOWS_DIR.glob("*.yml"):
        workflow = yaml.safe_load(workflow_path.read_text(encoding="utf-8"))
        for job in workflow.get("jobs", {}).values():
            for step in job.get("steps", []):
                if str(step.get("uses", "")).startswith("actions/checkout@"):
                    assert step.get("with", {}).get("persist-credentials") is False, (
                        f"{workflow_path.name} checkout must not persist credentials"
                    )


def test_release_runner_context_is_scoped_to_steps() -> None:
    """Job-level expressions cannot access runner.temp during workflow validation."""

    workflow = yaml.safe_load((WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8"))
    release_job = workflow["jobs"]["release"]
    job_environment = release_job["env"]
    signed_step = next(
        step
        for step in release_job["steps"]
        if step.get("name") == "Verify signed release tag and maintainer fingerprint"
    )
    baseline_step = next(
        step
        for step in release_job["steps"]
        if step.get("name") == "Generate and verify tag-bound release baseline"
    )

    assert "GNUPGHOME" not in job_environment
    assert signed_step["env"]["GNUPGHOME"] == "${{ runner.temp }}/power-release-gnupg"
    assert baseline_step["env"]["GNUPGHOME"] == "${{ runner.temp }}/power-release-gnupg"


def test_release_does_not_require_private_phase8_secrets() -> None:
    release_text = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")

    assert "name: power374-stable-release" not in release_text
    assert "POWER365_REAL_VAULT_RECEIPT_JSON" not in release_text
    assert "POWER365_HUMAN_MANIFEST_JSON" not in release_text
    assert "scripts/materialize_phase8_evidence.py" not in release_text
    assert "--phase8-real-vault-receipt" not in release_text
    assert "--phase8-human-manifest" not in release_text


def test_ci_uses_locked_dependencies_and_clean_package_smoke() -> None:
    ci_text = (WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8")
    docs_text = (WORKFLOWS_DIR / "docs.yml").read_text(encoding="utf-8")
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    release_text = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")

    assert (REPO_ROOT / "uv.lock").is_file()
    assert ci_text.count("uv sync --locked --group dev") >= 4
    assert "uv sync --locked --group dev --extra semantic --extra rerank" in ci_text
    assert '"mkdocs>=' in pyproject_text
    assert '"mkdocs-material>=' in pyproject_text
    assert "uv sync --locked --group dev" in docs_text
    assert "uv run mkdocs build --strict" in docs_text
    assert "package-smoke:" in ci_text
    assert "scripts/smoke_package.py" in ci_text
    assert "scripts/smoke_package.py" in release_text
    assert "scripts/generate_release_receipt.py" in release_text
    assert "--skipped-optional real-vault-quality" in release_text
    assert "run_outcome_benchmark.py" in release_text
    assert "run_continuity_benchmark.py" in release_text
    assert (
        "from scripts.generate_release_validation import build_validation_receipt" in release_text
    )
    assert "scripts/generate_release_gate_manifest.py" in release_text
    assert "scripts/build_release_manifest.py" in release_text
    assert '--commit "$commit"' in release_text
    assert "power-release-gates.json" in release_text
    assert "power-release-validation.json" in release_text
    assert "gate_manifest" in release_text
    assert '--junitxml="$RUNNER_TEMP/power-release-junit.xml"' in release_text
    assert '--cov-report=json:"$RUNNER_TEMP/power-release-coverage.json"' in release_text
    assert "power-release-phase8-technical-receipts" in release_text
    assert 'assert outcome["raw_content_in_report"] is False' in release_text
    assert 'assert outcome["comparison"]["practical_improvement"] is True' in release_text
    assert 'assert continuity["gate"]["power_beats_plain_handoff"] is True' in release_text
    assert "--phase8-outcome-receipt" in release_text
    assert "--phase8-continuity-receipt" in release_text
    assert "--validation-report" in release_text
    assert "--sbom" in release_text
    assert "--upgrade-matrix-aggregate" in release_text
    assert "power-release-upgrade-aggregate" in release_text
    assert '"hatchling>=' in pyproject_text
    assert "uv sync --locked --group dev" in release_text
    assert "uv run python -m build --no-isolation" in release_text
    assert "pip install build ." not in release_text
    assert "PYTHONPATH: src:." not in release_text
    assert "--system-site-packages" not in release_text
    assert "GH_TOKEN: ${{ secrets.POWER_RELEASE_GHCR_TOKEN || github.token }}" in release_text
    assert "BUILD_DATE" not in release_text
    assert "SOURCE_DATE_EPOCH" in release_text
    assert "OCI_CREATED" in release_text


def test_quarantined_fleet_docs_and_helper_forbid_live_cache_transfer() -> None:
    guide_paths = [
        REPO_ROOT / "docs" / "guides" / "hybrid-fleet-gpu-offloading-guide.md",
        REPO_ROOT / "docs" / "guides" / "hybrid-fleet-gpu-offloading-guide.ua.md",
    ]
    forbidden = re.compile(r"(?:rsync\b|generation-state\.db|[-_]wal\b|[-_]shm\b)", re.IGNORECASE)

    for guide_path in guide_paths:
        guide_text = guide_path.read_text(encoding="utf-8")
        assert "quarantined" in guide_text.lower()
        assert "3.5.0" in guide_text
        assert "not" in guide_text.lower() or "не" in guide_text.lower()
        assert not forbidden.search(guide_text), guide_path

    helper_path = REPO_ROOT.parent.parent / "scripts" / "sync_brain_db_from_ws.sh"
    if helper_path.is_file():
        helper_text = helper_path.read_text(encoding="utf-8")
        assert "no-op" in helper_text.lower()
        assert "disabled until manifest/quarantine/rollback support exists" in helper_text.lower()
        assert not forbidden.search(helper_text), (
            "legacy helper must not reintroduce live-cache copy"
        )


def test_mandatory_neural_contract_is_explicit_and_zero_skip() -> None:
    """CI must execute hermetic neural paths even when no HF snapshot exists."""

    contract = (REPO_ROOT / "tests" / "test_neural_hermetic_contract.py").read_text(
        encoding="utf-8"
    )
    assert "pytestmark = pytest.mark.neural_hermetic" in contract
    assert "pytest.skip" not in contract
    assert "skipif" not in contract
    for required in (
        "test_embedding_manager_contract_uses_fake_tokenizer_and_session",
        "test_dedup_contract_accepts_injected_embedder",
        "test_contradiction_contract_accepts_injected_embedder",
        "test_rot_report_contract_executes_dedup_and_contradiction_paths",
    ):
        assert f"def {required}" in contract

    verify_script = (REPO_ROOT / "scripts" / "verify_neural_contract.py").read_text(
        encoding="utf-8"
    )
    assert "skipped" in verify_script
    assert "mandatory neural contract skipped" in verify_script
    for workflow_name in ("ci.yml", "release.yml"):
        workflow = (WORKFLOWS_DIR / workflow_name).read_text(encoding="utf-8")
        assert "tests/test_neural_hermetic_contract.py" in workflow
        assert "scripts/verify_neural_contract.py" in workflow
        assert '-m "not real_neural and not bench"' in workflow
