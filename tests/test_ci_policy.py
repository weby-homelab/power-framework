"""Regression checks for blocking GitHub Actions policy."""

from __future__ import annotations

import re
from pathlib import Path

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


def test_ci_has_windows_runtime_smoke_for_documented_lifecycle() -> None:
    ci_text = (WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8")

    assert "  windows-runtime-smoke:" in ci_text
    assert "runs-on: windows-latest" in ci_text
    assert "uv sync --locked" in ci_text
    assert "uv run power index $vault --strict" in ci_text
    assert "uv run power sync $vault --fts-only" in ci_text
    assert 'uv run power search $vault "Windows smoke" --mode fts' in ci_text


def test_current_python_support_starts_at_3_11() -> None:
    ci_text = (WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8")
    pyproject_text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'requires-python = ">=3.11"' in pyproject_text
    assert '"Programming Language :: Python :: 3.10"' not in pyproject_text
    assert 'python-version: ["3.11", "3.12", "3.13", "3.14"]' in ci_text
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
    assert "attestations: write" in release_text
    assert "id-token: write" in release_text


def test_ci_uses_locked_dependencies_and_clean_package_smoke() -> None:
    ci_text = (WORKFLOWS_DIR / "ci.yml").read_text(encoding="utf-8")
    release_text = (WORKFLOWS_DIR / "release.yml").read_text(encoding="utf-8")

    assert (REPO_ROOT / "uv.lock").is_file()
    assert ci_text.count("uv sync --locked --group dev") >= 4
    assert "package-smoke:" in ci_text
    assert "scripts/smoke_package.py" in ci_text
    assert "scripts/smoke_package.py" in release_text
    assert "scripts/generate_release_receipt.py" in release_text
