"""Runtime safety tests for maintainer-provisioned Phase 8 evidence."""

from __future__ import annotations

import json
import os
from stat import S_IMODE
from typing import TYPE_CHECKING

import pytest

from scripts.materialize_phase8_evidence import (
    HUMAN_MANIFEST_ENV,
    REAL_VAULT_RECEIPT_ENV,
    materialize_phase8_evidence,
)

if TYPE_CHECKING:
    from pathlib import Path


def _environment() -> dict[str, str]:
    return {
        REAL_VAULT_RECEIPT_ENV: '{"schema_version":"power.phase8.real-vault-receipt.v1"}\n',
        HUMAN_MANIFEST_ENV: '{"schema_version":"m2-v2.1","split":"sealed_holdout"}\n',
    }


def test_materializer_preserves_validated_bytes_and_private_modes(tmp_path: Path) -> None:
    output_dir = tmp_path / "phase8"
    environment = _environment()

    real_vault_path, human_manifest_path = materialize_phase8_evidence(
        output_dir, environ=environment
    )

    assert real_vault_path.read_text(encoding="utf-8") == environment[REAL_VAULT_RECEIPT_ENV]
    assert human_manifest_path.read_text(encoding="utf-8") == environment[HUMAN_MANIFEST_ENV]
    assert json.loads(real_vault_path.read_text(encoding="utf-8"))["schema_version"]
    assert json.loads(human_manifest_path.read_text(encoding="utf-8"))["split"] == "sealed_holdout"
    assert not list(output_dir.glob(".*.json.*"))
    if os.name != "nt":
        assert S_IMODE(output_dir.stat().st_mode) == 0o700
        assert S_IMODE(real_vault_path.stat().st_mode) == 0o600
        assert S_IMODE(human_manifest_path.stat().st_mode) == 0o600


def test_materializer_validates_both_secrets_before_creating_output(tmp_path: Path) -> None:
    environment = _environment()
    environment[HUMAN_MANIFEST_ENV] = "not-json"

    with pytest.raises(ValueError, match="not valid JSON"):
        materialize_phase8_evidence(tmp_path / "phase8", environ=environment)

    assert not (tmp_path / "phase8").exists()


@pytest.mark.parametrize(
    "missing",
    [REAL_VAULT_RECEIPT_ENV, HUMAN_MANIFEST_ENV],
)
def test_materializer_fails_closed_when_a_secret_is_missing(tmp_path: Path, missing: str) -> None:
    environment = _environment()
    del environment[missing]

    with pytest.raises(ValueError, match="required environment secret is missing"):
        materialize_phase8_evidence(tmp_path / "phase8", environ=environment)

    assert not (tmp_path / "phase8").exists()
