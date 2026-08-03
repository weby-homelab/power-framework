#!/usr/bin/env python3
"""Build a restricted, deterministic M2-v2.1 candidate pool."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import random
import sys
from pathlib import Path
from typing import Any

POLICY_SCHEMA_VERSION = "power.m2.retrieval-preregistration.v1"
POOL_SCHEMA_VERSION = "power.m2.candidate-pool.v1"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON object from {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return payload


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        stream = path.open(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read JSONL from {path}") from exc
    with stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at {path}:{line_number}") from exc
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row at {path}:{line_number} is not an object")
            rows.append(row)
    return rows


def _validate_policy(policy: dict[str, Any]) -> list[str]:
    validator_path = Path(__file__).with_name("validate_preregistration.py")
    spec = importlib.util.spec_from_file_location("m2_preregistration_validator", validator_path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot load M2-v2.1 policy validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return list(module.validate_policy(policy))


def load_approved_policy(path: Path) -> tuple[dict[str, Any], str]:
    policy = load_json(path)
    errors = _validate_policy(policy)
    if errors:
        raise ValueError("invalid M2-v2.1 policy: " + "; ".join(errors))
    if policy.get("schema_version") != POLICY_SCHEMA_VERSION:
        raise ValueError("unsupported M2-v2.1 policy schema")
    if policy.get("status") != "pre_registered_before_human_calibration":
        raise ValueError("candidate pool requires curator-approved policy status")
    return policy, sha256_file(path)


def _receipt_runs(
    receipt: dict[str, Any], modes: list[str], query_ids: list[str], top_k: int
) -> dict[str, dict[str, list[str]]]:
    receipt_modes = receipt.get("modes")
    if not isinstance(receipt_modes, dict):
        raise ValueError("evaluation receipt must contain modes")
    query_set = set(query_ids)
    runs: dict[str, dict[str, list[str]]] = {}
    for mode in modes:
        entry = receipt_modes.get(mode)
        if not isinstance(entry, dict) or entry.get("status") != "completed":
            raise ValueError(f"comparator {mode} is missing or not completed")
        rows = entry.get("per_query")
        if not isinstance(rows, list):
            raise ValueError(f"comparator {mode} has no per_query results")
        run: dict[str, list[str]] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"comparator {mode} has a malformed per_query row")
            query_id = str(row.get("query_id", ""))
            result_ids = row.get("result_doc_ids")
            if query_id in run or query_id not in query_set or not isinstance(result_ids, list):
                raise ValueError(f"comparator {mode} has invalid query results")
            ids = [str(document_id) for document_id in result_ids[:top_k]]
            if len(ids) != len(set(ids)) or any(not document_id for document_id in ids):
                raise ValueError(f"comparator {mode} has duplicate or empty document IDs")
            run[query_id] = ids
        if set(run) != query_set:
            raise ValueError(f"comparator {mode} does not cover every query")
        runs[mode] = run
    return runs


def build_pool(
    policy_path: Path,
    corpus_path: Path,
    queries_path: Path,
    receipt_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Freeze all policy comparator candidates plus deterministic negatives."""
    policy, policy_sha256 = load_approved_policy(policy_path)
    corpus = load_jsonl(corpus_path)
    queries = load_jsonl(queries_path)
    receipt = load_json(receipt_path)
    pool_policy = policy["candidate_pool"]
    modes = [*policy["gated_comparators"], *policy["diagnostic_comparators"]]
    top_k = int(pool_policy["top_k_per_comparator"])
    negative_count = int(pool_policy["random_negative_count_per_query"])
    random_seed = int(pool_policy["random_seed"])

    corpus_ids = [str(row.get("document_id", "")) for row in corpus]
    if len(corpus_ids) != len(set(corpus_ids)) or any(
        not document_id for document_id in corpus_ids
    ):
        raise ValueError("corpus document IDs must be unique and non-empty")
    if any(str(row.get("split", "")) == "sealed_holdout" for row in corpus):
        raise ValueError("candidate pool input must not contain sealed_holdout documents")
    query_ids = [str(row.get("query_id", "")) for row in queries]
    if len(query_ids) != len(set(query_ids)) or any(not query_id for query_id in query_ids):
        raise ValueError("query IDs must be unique and non-empty")
    runs = _receipt_runs(receipt, modes, query_ids, top_k)
    corpus_id_set = set(corpus_ids)

    pool_rows: list[dict[str, Any]] = []
    for query_index, query_id in enumerate(query_ids):
        ordered_ids: list[str] = []
        source_modes: dict[str, list[str]] = {}
        for mode in modes:
            for document_id in runs[mode][query_id]:
                if document_id not in corpus_id_set:
                    raise ValueError(f"{mode}/{query_id} references unknown document {document_id}")
                if document_id not in source_modes:
                    ordered_ids.append(document_id)
                    source_modes[document_id] = []
                source_modes[document_id].append(mode)

        available_negatives = sorted(corpus_id_set - set(ordered_ids))
        if len(available_negatives) < negative_count:
            raise ValueError(f"not enough random negatives for query {query_id}")
        rng = random.Random(f"{random_seed}:{query_index}:{query_id}")  # noqa: S311
        random_negative_ids = rng.sample(available_negatives, negative_count)
        ordered_ids.extend(random_negative_ids)
        pool_rows.append(
            {
                "query_id": query_id,
                "candidate_document_ids": ordered_ids,
                "source_modes": source_modes,
                "random_negative_ids": random_negative_ids,
            }
        )

    output = {
        "schema_version": POOL_SCHEMA_VERSION,
        "policy_sha256": policy_sha256,
        "corpus_sha256": sha256_file(corpus_path),
        "queries_sha256": sha256_file(queries_path),
        "source_receipt_sha256": sha256_file(receipt_path),
        "top_k_per_comparator": top_k,
        "random_negative_count_per_query": negative_count,
        "random_seed": random_seed,
        "queries": pool_rows,
    }
    if output_path.exists():
        raise ValueError("candidate pool output already exists; choose a new immutable path")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    output_path.chmod(0o600)
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--queries", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = build_pool(args.policy, args.corpus, args.queries, args.receipt, args.output)
    except (OSError, ValueError) as exc:
        sys.stderr.write(f"candidate pool rejected: {exc}\n")
        return 1
    sys.stdout.write(f"candidate pool frozen: {len(result['queries'])} queries\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
