"""Regression checks for blocking GitHub Actions policy."""

from __future__ import annotations

import re
from pathlib import Path

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / ".github" / "workflows"
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
    assert "attestations: write" in release_text
    assert "id-token: write" in release_text
