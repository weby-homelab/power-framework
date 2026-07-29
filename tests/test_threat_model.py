"""Keep the published M1 security gate tied to its executable controls."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_threat_model_covers_m1_security_boundaries() -> None:
    document = (REPO_ROOT / "docs" / "threat-model.md").read_text(encoding="utf-8")

    for section in (
        "## Overview",
        "## Threat Model, Trust Boundaries, and Assumptions",
        "## Attack Surface, Mitigations, and Attacker Stories",
        "## Severity Calibration",
        "Repository: weby-homelab/power-framework",
        "Version: 20a9ee9aecc5e5d11edee284e6670a4fe91d8162",
    ):
        assert section in document

    for control in (
        "`core/egress.py`",
        "`core/memory_api.py`",
        "`atomic_write_in_vault`",
        "`mcp/power_server.py`",
        "`POWER_EGRESS_POLICY`",
    ):
        assert control in document
