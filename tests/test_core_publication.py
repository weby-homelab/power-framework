"""A signed native publication must never depend on a container registry."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_core_release_route() -> None:
    jobs = yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())["jobs"]
    marker = (ROOT / "release/publication-profile").read_text()
    assert marker == "core-cli-mcp-v1\n"
    core = jobs["publish_core"]
    assert "core-cli-mcp-v1" in core["if"]
    assert "legacy-unified" in jobs["release"]["if"]
    assert set(core["needs"]) == {
        "release_input",
        "signed_tag_admission",
        "validate",
        "upgrade-matrix-aggregate",
    }
    assert "packages" not in core["permissions"]
    commands = "\n".join(step.get("run", "") for step in core["steps"])
    for forbidden in ("docker ", "ghcr.io", "buildx", "recover_staged"):
        assert forbidden not in commands
    for required in (
        "scripts/smoke_package.py",
        "gh attestation verify",
        "scripts/build_release_manifest.py",
        "sha256sum --check",
        "--verify-tag",
    ):
        assert required in commands
