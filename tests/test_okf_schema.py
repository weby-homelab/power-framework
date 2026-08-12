"""Generated OKF schema remains identical to the typed runtime contract."""

from __future__ import annotations

import json
from pathlib import Path

from power_framework.core.capabilities import manifest
from power_framework.core.models import OKFMetadata
from scripts.generate_okf_schema import build_schema

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO_ROOT / "docs" / "schemas" / "okf-metadata-v1.json"


def test_public_okf_schema_matches_runtime_model() -> None:
    generated = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert generated == build_schema()
    assert generated["required"] == ["type", "title", "description", "timestamp"]
    assert generated["x-power-schema-version"] == "power.okf-metadata.v1"
    assert OKFMetadata.model_json_schema()["required"] == generated["required"]

    public_contract = manifest()["okf"]
    assert public_contract == {
        "schema_version": "power.okf-metadata.v1",
        "artifact": "docs/schemas/okf-metadata-v1.json",
        "required_fields": ["type", "title", "description", "timestamp"],
    }
