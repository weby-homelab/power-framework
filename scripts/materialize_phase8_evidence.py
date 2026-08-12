#!/usr/bin/env python3
"""Materialize maintainer-approved, content-free Phase 8 evidence safely."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

REAL_VAULT_RECEIPT_ENV = "POWER35_REAL_VAULT_RECEIPT_JSON"
HUMAN_MANIFEST_ENV = "POWER35_HUMAN_MANIFEST_JSON"


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


def materialize_phase8_evidence(
    output_dir: Path, *, environ: Mapping[str, str] | None = None
) -> tuple[Path, Path]:
    """Materialize both approved evidence documents and return their paths."""
    source = os.environ if environ is None else environ
    real_vault = _read_json_object(source, REAL_VAULT_RECEIPT_ENV)
    human_manifest = _read_json_object(source, HUMAN_MANIFEST_ENV)

    output_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(output_dir, 0o700)
    real_vault_path = output_dir / "real-vault-receipt.json"
    human_manifest_path = output_dir / "human-manifest.json"
    _atomic_private_write(real_vault_path, real_vault)
    _atomic_private_write(human_manifest_path, human_manifest)
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
