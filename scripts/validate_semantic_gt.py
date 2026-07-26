#!/usr/bin/env python3
"""Validate the frozen semantic holdout before running TEST-2 quality metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def validate_holdout(data: dict[str, Any], vault: Path) -> list[str]:
    """Return all fixture validation errors for a specific benchmark vault."""
    errors: list[str] = []
    queries = data.get("queries")
    metadata = data.get("metadata")
    groups = data.get("language_groups")
    if not isinstance(queries, list):
        return ["queries must be a list"]
    if not isinstance(metadata, dict):
        errors.append("metadata must be an object")
        metadata = {}
    if metadata.get("query_count") != len(queries):
        errors.append(
            f"metadata.query_count={metadata.get('query_count')!r} does not match {len(queries)}"
        )

    query_texts = [entry.get("query") for entry in queries if isinstance(entry, dict)]
    if len(query_texts) != len(queries) or any(
        not isinstance(query, str) or not query for query in query_texts
    ):
        errors.append("every query entry must contain a non-empty query string")
    elif len(set(query_texts)) != len(query_texts):
        errors.append("queries must be unique")

    for index, entry in enumerate(queries):
        if not isinstance(entry, dict):
            errors.append(f"query[{index}] must be an object")
            continue
        relevant = entry.get("relevant")
        if not isinstance(relevant, dict) or not relevant:
            errors.append(f"query[{index}] must define non-empty relevant mappings")
            continue
        for rel_path, grade in relevant.items():
            if grade not in {1, 2, 3}:
                errors.append(
                    f"query[{index}] has invalid relevance grade for {rel_path!r}: {grade!r}"
                )
            candidate = vault / str(rel_path)
            if not candidate.is_file():
                errors.append(f"query[{index}] relevant path is absent from vault: {rel_path}")

    if not isinstance(groups, dict) or not groups:
        errors.append("language_groups must be a non-empty object")
        groups = {}
    group_indexes: list[int] = []
    distribution: dict[str, int] = {}
    for name, group in groups.items():
        if (
            not isinstance(group, dict)
            or not isinstance(group.get("label"), str)
            or not group["label"].strip()
        ):
            errors.append(f"language group {name!r} requires a non-empty label")
            continue
        indexes = group.get("query_indexes")
        if not isinstance(indexes, list) or not all(isinstance(item, int) for item in indexes):
            errors.append(f"language group {name!r} requires integer query_indexes")
            continue
        distribution[name] = len(indexes)
        group_indexes.extend(indexes)
    if sorted(group_indexes) != list(range(len(queries))):
        errors.append("language-group query_indexes must label every query exactly once")
    if metadata.get("language_group_distribution") != distribution:
        errors.append("metadata.language_group_distribution does not match language_groups")

    description = data.get("description")
    distribution_terms = [
        f"{count} {group['label'].removesuffix(' queries')}"
        for name, count in distribution.items()
        if (group := groups.get(name)) and isinstance(group.get("label"), str)
    ]
    expected_description = f"{len(queries)} queries: " + ", ".join(distribution_terms)
    if not isinstance(description, str) or expected_description not in description:
        errors.append(f"description must state actual group distribution: {expected_description}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fixture", type=Path, default=Path("tests/fixtures/semantic_gt_holdout_v1.json")
    )
    parser.add_argument("--vault", type=Path, required=True)
    args = parser.parse_args()

    try:
        data = json.loads(args.fixture.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: unable to load fixture: {exc}")
        return 2
    errors = validate_holdout(data, args.vault)
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print(f"PASS: {args.fixture} ({data['metadata']['query_count']} queries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
