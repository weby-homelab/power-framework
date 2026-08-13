#!/usr/bin/env python3
"""Materialize maintainer-approved, content-free Phase 8 evidence safely."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

REAL_VAULT_RECEIPT_ENV = "POWER36_REAL_VAULT_RECEIPT_JSON"
HUMAN_MANIFEST_ENV = "POWER36_HUMAN_MANIFEST_JSON"


def _read_json_object(environ: Mapping[str, str], variable: str) -> bytes:
    """Return the exact UTF-8 secret bytes after validating its JSON shape."""
    raw = environ.get(variable, "")
    if not raw:
        raise ValueError(f"required environment secret is missing: {variable}")
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"environment secret is not valid JSON: {variable}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"environment secret must be a JSON object: {variable}")
    try:
        return raw.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"environment secret is not valid UTF-8: {variable}") from exc


def _atomic_private_write(path: Path, content: bytes) -> None:
    """Write private evidence bytes atomically, without exposing content in logs."""
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        os.chmod(temporary_path, 0o600)
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        os.chmod(path, 0o600)
    except BaseException:
        with suppress(OSError):
            os.close(descriptor)
        with suppress(FileNotFoundError):
            temporary_path.unlink()
        raise


def _embedded_artifact_names(manifest: dict[str, object]) -> set[str]:
    """Return every private artifact path referenced by a human manifest."""
    names: set[str] = set()
    artifacts = manifest.get("artifacts")
    if isinstance(artifacts, dict):
        names.update(value for value in artifacts.values() if isinstance(value, str))
    protocol = manifest.get("annotation_protocol")
    if isinstance(protocol, str):
        names.add(protocol)
    for key in ("calibration", "agreement"):
        receipt = manifest.get(key)
        if isinstance(receipt, dict) and isinstance(
            receipt.get("agreement_receipt" if key == "calibration" else "receipt"), str
        ):
            names.add(receipt["agreement_receipt" if key == "calibration" else "receipt"])
    return names


def _prepare_embedded_artifacts(
    output_dir: Path, manifest: dict[str, object]
) -> list[tuple[Path, bytes]]:
    """Validate embedded artifact names/content before writing any evidence."""
    embedded = manifest.get("embedded_artifacts")
    if embedded is None:
        return []
    if not isinstance(embedded, dict):
        raise ValueError("human manifest embedded_artifacts must be an object")

    required = _embedded_artifact_names(manifest)
    names = set(embedded)
    missing = required - names
    if missing:
        raise ValueError("human manifest embedded_artifacts is missing a referenced artifact")
    unknown = names - required
    if unknown:
        raise ValueError("human manifest embedded_artifacts contains an unreferenced artifact")

    prepared: list[tuple[Path, bytes]] = []
    root = output_dir.resolve()
    hash_keys = {
        "corpus": "corpus_sha256",
        "queries": "queries_sha256",
        "raw_judgments": "raw_judgments_sha256",
        "adjudicated_qrels": "adjudicated_qrels_sha256",
    }
    artifacts_mapping = manifest.get("artifacts")
    artifacts_dict = artifacts_mapping if isinstance(artifacts_mapping, dict) else {}

    for relative_name, content in embedded.items():
        if not isinstance(relative_name, str) or not relative_name:
            raise ValueError("human manifest embedded artifact name must be non-empty")
        relative_path = Path(relative_name)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("human manifest embedded artifact path escapes the output directory")
        target = (output_dir / relative_path).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                "human manifest embedded artifact path escapes the output directory"
            ) from exc
        if not isinstance(content, str):
            raise ValueError(f"human manifest embedded artifact is not text: {relative_name}")
        content_bytes = content.encode("utf-8")
        actual_sha256 = hashlib.sha256(content_bytes).hexdigest()

        for art_key, path_in_manifest in artifacts_dict.items():
            if path_in_manifest == relative_name and art_key in hash_keys:
                expected_sha256 = manifest.get(hash_keys[art_key])
                if expected_sha256 and actual_sha256 != expected_sha256:
                    raise ValueError(
                        f"human manifest embedded artifact {relative_name} SHA-256 does not match its manifest declaration"
                    )

        calib = manifest.get("calibration")
        if isinstance(calib, dict) and calib.get("agreement_receipt") == relative_name:
            expected_calib = calib.get("agreement_receipt_sha256")
            if expected_calib and actual_sha256 != expected_calib:
                raise ValueError(
                    f"human manifest embedded calibration receipt {relative_name} SHA-256 does not match its manifest declaration"
                )

        adj = manifest.get("agreement")
        if isinstance(adj, dict) and adj.get("receipt") == relative_name:
            expected_adj = adj.get("receipt_sha256")
            if expected_adj and actual_sha256 != expected_adj:
                raise ValueError(
                    f"human manifest embedded adjudication receipt {relative_name} SHA-256 does not match its manifest declaration"
                )

        prepared.append((target, content_bytes))
    return prepared


def materialize_phase8_evidence(
    output_dir: Path, *, environ: Mapping[str, str] | None = None
) -> tuple[Path, Path]:
    """Materialize both approved evidence documents and return their paths."""
    source = os.environ if environ is None else environ
    real_vault = _read_json_object(source, REAL_VAULT_RECEIPT_ENV)
    human_manifest = _read_json_object(source, HUMAN_MANIFEST_ENV)
    try:
        human_manifest_obj = json.loads(human_manifest.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("human manifest is not valid UTF-8 JSON") from exc
    if not isinstance(human_manifest_obj, dict):
        raise ValueError("human manifest must be a JSON object")
    embedded_artifacts = _prepare_embedded_artifacts(output_dir, human_manifest_obj)

    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    real_vault_path = output_dir / "real-vault-receipt.json"
    human_manifest_path = output_dir / "human-manifest.json"
    _atomic_private_write(real_vault_path, real_vault)
    _atomic_private_write(human_manifest_path, human_manifest)
    for target, content in embedded_artifacts:
        _atomic_private_write(target, content)

    return real_vault_path, human_manifest_path


def main(argv: list[str] | None = None) -> int:
    """Run the content-free Phase 8 evidence materializer."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        real_vault_path, human_manifest_path = materialize_phase8_evidence(args.output_dir)
    except (OSError, ValueError, UnicodeError) as exc:
        parser.error(str(exc))
        return 2
    print(f"Phase 8 evidence materialized: {real_vault_path}, {human_manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
