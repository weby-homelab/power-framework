"""Keep SECURITY.md aligned with the current runtime security contract."""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_security_policy_is_current_and_covers_runtime_boundaries() -> None:
    document = (REPO_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version = str(project["project"]["version"])
    major_minor = ".".join(version.split(".")[:2])

    assert f"`{major_minor}.x`" in document
    assert "1.8.x" not in document

    for section in (
        "## Purpose and scope",
        "## Supported versions",
        "## Security objectives and boundaries",
        "## Implemented controls",
        "## Report a vulnerability",
        "## Severity calibration",
        "## Out of scope and known limitations",
        "## Security-related development rules",
    ):
        assert section in document

    for control in (
        "`resolve_path_in_vault`",
        "`atomic_write_in_vault`",
        "`POWER_EGRESS_POLICY`",
        "`POWER_VAULT_DIR`",
        "loopback",
        "not an authorization mechanism",
        "YAML frontmatter",
        "CodeQL",
    ):
        assert control in document
