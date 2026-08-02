#!/usr/bin/env python3
"""Generate a release baseline bound to the exact annotated tag commit."""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path
from typing import Any

from verify_release_contract import (
    DEFAULT_DATASET_MANIFEST,
    DEFAULT_MODELS_LOCK,
    REPO_ROOT,
    _git,
    _load_json,
    _load_package_version,
    _sha256,
)

TAG_PATTERN = re.compile(r"^v\d+\.\d+\.\d+$")
DEFAULT_TEMPLATE = REPO_ROOT / "release" / "evidence" / "baselines" / "v3.3.0.json"


def _default_template() -> Path:
    candidates = sorted((REPO_ROOT / "release" / "evidence" / "baselines").glob("v*.json"))
    return candidates[-1] if candidates else DEFAULT_TEMPLATE


def _manifest_hash(manifest: dict[str, Any], section: str) -> str:
    value = manifest.get(section, {}).get("hash_sha256")
    if not isinstance(value, str) or not value:
        raise ValueError(f"dataset manifest has no {section}.hash_sha256")
    return value


def _git_output(repo: Path, *args: str) -> str:
    status, stdout, stderr = _git(repo, *args)
    if status != 0:
        raise ValueError(f"git query failed: {' '.join(args)}: {stderr}")
    return stdout


def build_baseline(
    *,
    repo: Path,
    tag: str,
    template_path: Path,
    models_lock_path: Path,
    dataset_manifest_path: Path,
) -> dict[str, Any]:
    """Return a baseline whose source fields describe ``tag`` exactly."""
    if not TAG_PATTERN.fullmatch(tag):
        raise ValueError(f"invalid release tag: {tag}")

    package_version = _load_package_version(repo / "pyproject.toml")
    expected_tag = f"v{package_version}"
    if tag != expected_tag:
        raise ValueError(f"tag {tag} does not match package version {package_version}")

    commit = _git_output(repo, "rev-parse", "--verify", f"refs/tags/{tag}^{{commit}}")
    tree = _git_output(repo, "show", "-s", "--format=%T", commit)
    baseline = copy.deepcopy(_load_json(template_path))
    manifest = _load_json(dataset_manifest_path)

    baseline["release"] = package_version
    baseline["source"] = {
        "commit": commit,
        "tree": tree,
        "tag": tag,
        "clean": True,
    }
    benchmark = baseline.setdefault("benchmark", {})
    benchmark["synthetic"] = True
    benchmark["corpus_sha256"] = _manifest_hash(manifest, "corpus")
    benchmark["queries_sha256"] = _manifest_hash(manifest, "queries")
    benchmark["qrels_sha256"] = _manifest_hash(manifest, "qrels")
    benchmark["expected_answers_sha256"] = _manifest_hash(manifest, "expected_answers")
    baseline["models_lock_sha256"] = _sha256(models_lock_path)
    return baseline


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--template", type=Path, default=_default_template())
    parser.add_argument("--models-lock", type=Path, default=DEFAULT_MODELS_LOCK)
    parser.add_argument("--dataset-manifest", type=Path, default=DEFAULT_DATASET_MANIFEST)
    args = parser.parse_args(argv)
    try:
        baseline = build_baseline(
            repo=REPO_ROOT,
            tag=args.tag,
            template_path=args.template,
            models_lock_path=args.models_lock,
            dataset_manifest_path=args.dataset_manifest,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Release baseline written to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
