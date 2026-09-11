#!/usr/bin/env python3
"""Verify the bounded Phase 5B domain-routing evidence offline.

The verifier reads the immutable v1.1 query corpus and the separate,
digest-bound routing ground truth.  It never edits either corpus, loads a
model, performs retrieval, mutates a vault, or uses holdout rows to tune a
policy.  Timing is measurement metadata only; it is not used by the router.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import stat
import sys
import tempfile
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from power_framework.core.domains import (
    DomainConfigError,
    DomainRegistry,
    DomainRule,
    DomainSpec,
    RetrievalDomainRouter,
    load_domain_policy,
    load_domain_registry,
    resolve_search_policy,
    route_domain,
)
from power_framework.core.evaluation_contracts import verify_evaluation_corpus

ROOT = Path(__file__).parents[1]
ACTIVE_ROOT = ROOT / "benchmarks" / "power38" / "retrieval_eval" / "v1.1"
POLICY_PATH = ROOT / "artifacts" / "project-state" / "phase-5b" / "domain-policy-v2.runtime.yaml"
GROUND_TRUTH_PATH = (
    ROOT / "artifacts" / "project-state" / "phase-5b" / "domain-routing-ground-truth-v1.json"
)
HOLDOUT_GROUND_TRUTH_PATH = (
    ROOT
    / "artifacts"
    / "project-state"
    / "phase-5b"
    / "domain-routing-ground-truth-v1.holdout.json"
)
EVALUATION_PATH = (
    ROOT / "artifacts" / "project-state" / "phase-5b" / "domain-routing-evaluation-v1.json"
)
ALGORITHM_REVISION = "domain-router-v1"
EXPECTED_POLICY_SHA256 = "f728a27fd8c009c9dd18c01c2afc5399368c3663eb97cc645ec22896efe8f88b"
EXPECTED_GROUND_TRUTH_DIGEST = "434e10ca12d011c1b5cad8cacee086839102a02d3e53703d4ab6aef08a292c06"
EXPECTED_HOLDOUT_LABELS_DIGEST = "ae3a0a6dcc595a0d6d627661aa2c36012334cac05e149d3aab21fa6ccfb5380d"
EXPECTED_REVIEW_RECEIPTS = {
    "phase5b-routing-review-a": (
        "domain-routing-review-a-v1.json",
        "4c6899732be6b94640154d92e2dfa73bbc6526576971e3351dc3812c6053f65c",
    ),
    "phase5b-routing-review-b": (
        "domain-routing-review-b-v1.json",
        "9fb75e89da11315b3741e4fe1c6880110b970f544c4e6a6b6336ed4764d9037f",
    ),
}
REQUIRED_ACTIVE_DIGESTS = {
    "evaluation_revision": "v1.1",
    "source_corpus_digest": "3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118",
    "dataset_digest": "5d8f2d7e68b62b3a2385c7a534a492083e1ff1b9f68973d4cbe8bf64461521fc",
    "query_set_digest": "b3fdf772c6b744495a503651c5ceecc0302bd3d34c00e1f12e2f014c5797be3e",
    "development_digest": "4bcd6c464b212e771517e71d3fdb7d696efbf0ec5521117dc7e8e7ce9ddaeb95",
    "holdout_digest": "61aa9d85ab0804308c008635814cb79218b7e6cc3c78d331ca4b8d4656b5f551",
}
TRUST_OR_LIFECYCLE_NAMES = {
    "RAW",
    "PROPOSED",
    "CURATED",
    "VERIFIED",
    "CANONICAL",
    "SUPERSEDED",
    "ARCHIVED",
    "QUARANTINED",
    "NOISE",
}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _read_bounded_bytes(path: Path, *, max_bytes: int = 4 * 1024 * 1024) -> bytes:
    fd: int | None = None
    try:
        fd = os.open(
            path,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0),
        )
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes:
            raise ValueError("routing evidence file is not a bounded regular file")
        with os.fdopen(fd, "rb") as stream:
            fd = None
            data = stream.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise ValueError("routing evidence file exceeds its byte bound")
        return data
    except ValueError:
        raise
    except OSError as exc:
        raise ValueError("routing evidence file is unreadable") from exc
    finally:
        if fd is not None:
            with suppress(OSError):
                os.close(fd)


def _reject_duplicate_json_key(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("routing evidence contains duplicate JSON keys")
        result[key] = value
    return result


def _reject_json_constant(value: str) -> Any:
    raise ValueError(f"routing evidence contains non-finite JSON constant {value}")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            _read_bounded_bytes(path).decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_key,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("routing evidence contains invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("routing evidence JSON root must be an object")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    data = _read_bounded_bytes(path)
    for line in data.splitlines():
        if line.strip():
            if len(line) > 64 * 1024:
                raise ValueError("routing query record exceeds its byte bound")
            try:
                value = json.loads(
                    line.decode("utf-8"),
                    object_pairs_hook=_reject_duplicate_json_key,
                    parse_constant=_reject_json_constant,
                )
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ValueError("routing query record is invalid JSON") from exc
            if not isinstance(value, dict):
                raise ValueError(f"non-object JSONL row in {path.name}")
            rows.append(value)
            if len(rows) > 4096:
                raise ValueError("routing query split exceeds its row bound")
    return rows


def _ground_truth_digest(artifact: dict[str, Any]) -> str:
    without_digest = dict(artifact)
    without_digest.pop("ground_truth_digest", None)
    return _sha256_bytes(_canonical_json(without_digest))


def _validate_label_rows(labels: object, universe: set[str], split_name: str) -> None:
    if not isinstance(labels, list):
        raise ValueError(f"routing ground truth {split_name} labels are invalid")
    ids = [row.get("query_id") for row in labels if isinstance(row, dict)]
    if len(ids) != 20 or len(ids) != len(set(ids)) or len(ids) != len(labels):
        raise ValueError(f"routing ground truth {split_name} coverage is invalid")
    for row in labels:
        if not isinstance(row, dict):
            raise ValueError("routing domain label must be an object")
        required = row.get("required_domains")
        secondary = row.get("acceptable_secondary_domains")
        if not isinstance(required, list) or not isinstance(secondary, list):
            raise ValueError("routing domain labels must use arrays")
        if len(required) != len(set(required)) or len(secondary) != len(set(secondary)):
            raise ValueError("routing domain labels contain duplicates")
        if set(required) & set(secondary) or not set(required + secondary) <= universe:
            raise ValueError("routing domain labels contain invalid overlap or domain")
        cardinality = row.get("cardinality")
        expected = row.get("expected_primary_domain")
        if cardinality not in {"single", "multi", "zero"}:
            raise ValueError("routing domain cardinality is invalid")
        if cardinality == "zero" and (required or secondary or expected is not None):
            raise ValueError("zero-domain label is not empty")
        if cardinality == "single" and len(required) != 1:
            raise ValueError("single-domain label must have one required domain")
        if cardinality == "multi" and len(required) < 2:
            raise ValueError("multi-domain label must have multiple required domains")
        if expected is not None and expected not in required:
            raise ValueError("expected primary domain must be required")
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            raise ValueError("routing domain label needs a bounded reason")


def _validate_ground_truth(artifact: dict[str, Any]) -> set[str]:
    if artifact.get("schema_version") != "power.domain-routing-ground-truth.v1":
        raise ValueError("routing ground truth schema mismatch")
    if artifact.get("evaluation_revision") != "v1.1" or artifact.get("no_float_scores") is not True:
        raise ValueError("routing ground truth revision or score contract mismatch")
    if artifact.get("source_corpus_digest") != REQUIRED_ACTIVE_DIGESTS["source_corpus_digest"]:
        raise ValueError("routing ground truth source digest mismatch")
    if artifact.get("dataset_digest") != REQUIRED_ACTIVE_DIGESTS["dataset_digest"]:
        raise ValueError("routing ground truth dataset digest mismatch")
    if artifact.get("query_set_digest") != REQUIRED_ACTIVE_DIGESTS["query_set_digest"]:
        raise ValueError("routing ground truth query digest mismatch")
    if artifact.get("ground_truth_digest") != EXPECTED_GROUND_TRUTH_DIGEST:
        raise ValueError("routing ground truth is not the admitted revision")
    if _ground_truth_digest(artifact) != EXPECTED_GROUND_TRUTH_DIGEST:
        raise ValueError("routing ground truth digest mismatch")
    universe = artifact.get("domain_universe")
    if not isinstance(universe, list) or not universe or len(universe) != len(set(universe)):
        raise ValueError("routing ground truth domain universe is invalid")
    universe_set = set(universe)
    review = artifact.get("review")
    if not isinstance(review, dict) or review.get("router_output_used") is not False:
        raise ValueError("routing ground truth review boundary is invalid")
    for reviewer_id, (receipt_ref, receipt_digest) in EXPECTED_REVIEW_RECEIPTS.items():
        reviewer = review.get("reviewer_a" if reviewer_id.endswith("-a") else "reviewer_b")
        if not isinstance(reviewer, dict):
            raise ValueError("routing reviewer receipt metadata is missing")
        if reviewer.get("id") != reviewer_id or reviewer.get("receipt_ref") != receipt_ref:
            raise ValueError("routing reviewer receipt reference mismatch")
        if reviewer.get("receipt_digest") != receipt_digest:
            raise ValueError("routing reviewer receipt digest mismatch")
        receipt = _read_json(GROUND_TRUTH_PATH.parent / receipt_ref)
        if _sha256_bytes(_canonical_json(receipt)) != receipt_digest:
            raise ValueError("routing reviewer receipt content mismatch")
        if (
            receipt.get("reviewer_id") != reviewer_id
            or receipt.get("router_output_used") is not False
        ):
            raise ValueError("routing reviewer receipt boundary is invalid")
    splits = artifact.get("splits")
    if not isinstance(splits, dict) or set(splits) != {"development", "holdout"}:
        raise ValueError("routing ground truth splits are invalid")
    development = splits["development"]
    holdout = splits["holdout"]
    if not isinstance(development, dict) or not isinstance(holdout, dict):
        raise ValueError("routing ground truth split metadata is invalid")
    if development.get("tuning_allowed") is not True or holdout.get("tuning_allowed") is not False:
        raise ValueError("routing ground truth tuning policy is invalid")
    _validate_label_rows(development.get("labels"), universe_set, "development")
    if holdout.get("labels_ref") != HOLDOUT_GROUND_TRUTH_PATH.name:
        raise ValueError("holdout ground-truth reference mismatch")
    if holdout.get("labels_digest") != EXPECTED_HOLDOUT_LABELS_DIGEST:
        raise ValueError("holdout ground-truth digest mismatch")
    return universe_set


def _load_holdout_labels(universe: set[str]) -> list[dict[str, Any]]:
    split = _read_json(HOLDOUT_GROUND_TRUTH_PATH)
    if (
        split.get("schema_version") != "power.domain-routing-ground-truth-split.v1"
        or split.get("evaluation_revision") != "v1.1"
        or split.get("split") != "holdout"
        or split.get("tuning_allowed") is not False
        or split.get("digest") != REQUIRED_ACTIVE_DIGESTS["holdout_digest"]
    ):
        raise ValueError("holdout ground truth split metadata is invalid")
    if (
        split.get("labels") is None
        or _sha256_bytes(_canonical_json(split)) != EXPECTED_HOLDOUT_LABELS_DIGEST
    ):
        raise ValueError("holdout ground truth split digest mismatch")
    labels = split["labels"]
    _validate_label_rows(labels, universe, "holdout")
    return labels


def _validate_active_manifest() -> dict[str, Any]:
    manifest = _read_json(ACTIVE_ROOT / "manifest.json")
    manifest_digest_values = {
        "evaluation_revision": manifest.get("evaluation_revision"),
        "source_corpus_digest": manifest.get("source_corpus_digest"),
        "dataset_digest": manifest.get("dataset_digest"),
        "query_set_digest": manifest.get("query_set_digest"),
        "development_digest": (manifest.get("development_split") or {}).get("digest"),
        "holdout_digest": (manifest.get("holdout_split") or {}).get("digest"),
    }
    for key, expected in REQUIRED_ACTIVE_DIGESTS.items():
        if manifest_digest_values.get(key) != expected:
            raise ValueError(f"active manifest {key} mismatch")
    if (
        manifest.get("no_tuning_on_holdout") is not True
        or manifest.get("planning_only") is not True
    ):
        raise ValueError("active manifest holdout/planning invariants are missing")
    return manifest


def _percentile_microseconds(samples: list[int], percentile: float) -> float:
    ordered = sorted(samples)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * percentile) - 1))
    return ordered[index] / 1_000.0


def _evaluate_split(
    router: RetrievalDomainRouter,
    labels: list[dict[str, Any]],
    queries: list[dict[str, Any]],
    universe: set[str],
) -> dict[str, Any]:
    queries_by_id = {row["query_id"]: row for row in queries}
    label_by_id = {row["query_id"]: row for row in labels}
    if set(queries_by_id) != set(label_by_id):
        raise ValueError("routing ground truth does not cover the query split exactly")
    returned_count = 0
    allowed_returned_count = 0
    required_count = 0
    required_hit_count = 0
    false_positive_count = 0
    explained_count = 0
    match_count = 0
    top_correct = 0
    top_total = 0
    multi_correct = 0
    multi_total = 0
    zero_correct = 0
    zero_total = 0
    maximum_returned = 0
    latency_ns: list[int] = []
    non_deterministic = 0
    authority_violations = 0
    lifecycle_violations = 0
    unexplained = 0
    results: list[dict[str, Any]] = []
    for query_id in sorted(queries_by_id):
        query = queries_by_id[query_id]
        label = label_by_id[query_id]
        started = time.perf_counter_ns()
        first = router.route(query["query"], intent=query["intent"])
        latency_ns.append(time.perf_counter_ns() - started)
        second = router.route(query["query"], intent=query["intent"])
        first_canonical = [item.to_canonical_dict() for item in first]
        second_canonical = [item.to_canonical_dict() for item in second]
        if first_canonical != second_canonical:
            non_deterministic += 1
        required = set(label["required_domains"])
        acceptable = set(label["acceptable_secondary_domains"])
        allowed = required | acceptable
        returned = [item.domain for item in first]
        returned_set = set(returned)
        returned_count += len(returned)
        allowed_returned_count += sum(domain in allowed for domain in returned)
        required_count += len(required)
        required_hit_count += len(required & returned_set)
        false_positive_count += len(returned_set - allowed)
        maximum_returned = max(maximum_returned, len(returned))
        for item in first:
            match_count += 1
            if item.reasons:
                explained_count += 1
            else:
                unexplained += 1
            if item.domain not in universe or item.domain in TRUST_OR_LIFECYCLE_NAMES:
                authority_violations += 1
                lifecycle_violations += 1
            if not 0.0 <= item.score <= 1.0:
                authority_violations += 1
        if label["cardinality"] == "single":
            top_total += 1
            top_correct += bool(first and first[0].domain == label["expected_primary_domain"])
        elif label["cardinality"] == "multi":
            multi_total += 1
            multi_correct += required <= returned_set
        else:
            zero_total += 1
            zero_correct += not first
        results.append(
            {
                "query_id": query_id,
                "required_domains": label["required_domains"],
                "acceptable_secondary_domains": label["acceptable_secondary_domains"],
                "returned": first_canonical,
                "required_domains_present": sorted(required & returned_set),
                "unexpected_domains": sorted(returned_set - allowed),
            }
        )
    return {
        "query_count": len(labels),
        "returned_match_count": returned_count,
        "required_domain_count": required_count,
        "required_domain_hit_count": required_hit_count,
        "single_domain_case_count": top_total,
        "single_domain_case_hits": top_correct,
        "multi_domain_case_count": multi_total,
        "multi_domain_case_hits": multi_correct,
        "zero_match_case_count": zero_total,
        "zero_match_case_hits": zero_correct,
        "routing_precision": allowed_returned_count / returned_count if returned_count else 1.0,
        "routing_recall": required_hit_count / required_count if required_count else 1.0,
        "top_domain_accuracy_single_domain": top_correct / top_total if top_total else 1.0,
        "required_domain_recall": required_hit_count / required_count if required_count else 1.0,
        "unexpected_domain_false_positives": false_positive_count,
        "multi_domain_coverage": multi_correct / multi_total if multi_total else 1.0,
        "zero_match_correctness": zero_correct / zero_total if zero_total else 1.0,
        "tie_determinism": non_deterministic == 0,
        "explainability_coverage": explained_count / match_count if match_count else 1.0,
        "p50_routing_latency_us": _percentile_microseconds(latency_ns, 0.50),
        "p95_routing_latency_us": _percentile_microseconds(latency_ns, 0.95),
        "maximum_observed_returned_domains": maximum_returned,
        "results_digest": _sha256_bytes(_canonical_json(results)),
        "hard_invariants": {
            "authority_violations": authority_violations,
            "lifecycle_violations": lifecycle_violations,
            "non_deterministic_outputs": non_deterministic,
            "unexplained_domain_matches": unexplained,
        },
        "results": results,
    }


def _legacy_compatibility_probe() -> bool:
    first = DomainSpec(
        name="first",
        path=Path("01_Projects/first"),
        template=Path("05_Templates/first.md"),
        rules=(DomainRule(keywords=("same",)),),
        search_priority=("fts",),
    )
    second = DomainSpec(
        name="second",
        path=Path("01_Projects/second"),
        template=Path("05_Templates/second.md"),
        rules=(DomainRule(keywords=("same",)),),
        search_priority=("semantic",),
    )
    selected = route_domain(DomainRegistry(version=1, domains=(first, second)), title="same")
    if selected is not first:
        return False
    with tempfile.TemporaryDirectory(prefix="power38-v1-probe-") as temporary:
        vault = Path(temporary)
        config = vault / ".power" / "domains.yaml"
        config.parent.mkdir()
        config.write_text(
            "version: 1\ndomains:\n"
            "  - name: notes\n"
            "    path: 03_Resources/notes\n"
            "    template: 05_Templates/notes.md\n"
            "    rules: [{keywords: [roadmap]}]\n"
            "    search_priority: [fts]\n",
            encoding="utf-8",
        )
        previous = os.environ.get("POWER_DOMAIN_CONFIG")
        os.environ["POWER_DOMAIN_CONFIG"] = str(config)
        try:
            registry = load_domain_registry(vault)
            if registry.get("notes") is None:
                return False
            if resolve_search_policy(vault, "roadmap", "auto")[0] != "fts":
                return False
            os.environ["POWER_DOMAIN_CONFIG"] = ""
            if resolve_search_policy(vault, "", "auto", "")[0] != "auto":
                return False
        finally:
            if previous is None:
                os.environ.pop("POWER_DOMAIN_CONFIG", None)
            else:
                os.environ["POWER_DOMAIN_CONFIG"] = previous
    return True


def _vault_boundary_probe() -> bool:
    with tempfile.TemporaryDirectory(prefix="power38-boundary-probe-") as temporary:
        root = Path(temporary) / "vault"
        outside = Path(temporary) / "outside.yaml"
        root.mkdir()
        outside.write_text("version: 1\ndomains: []\n", encoding="utf-8")
        previous = os.environ.get("POWER_DOMAIN_CONFIG")
        os.environ["POWER_DOMAIN_CONFIG"] = str(outside)
        try:
            try:
                load_domain_registry(root)
            except DomainConfigError:
                return True
            return False
        finally:
            if previous is None:
                os.environ.pop("POWER_DOMAIN_CONFIG", None)
            else:
                os.environ["POWER_DOMAIN_CONFIG"] = previous


def _validate_committed_receipt(evidence: dict[str, Any]) -> None:
    stored = _read_json(EVALUATION_PATH)
    for key in (
        "schema_version",
        "evaluation_revision",
        "algorithm_revision",
        "policy_revision",
        "normalization_revision",
        "policy_sha256",
        "ground_truth_digest",
        "active_v1_1_digests",
        "hard_invariants",
    ):
        if stored.get(key) != evidence.get(key):
            raise ValueError(f"committed routing receipt is stale at {key}")
    stable_split_fields = (
        "query_count",
        "returned_match_count",
        "required_domain_count",
        "required_domain_hit_count",
        "single_domain_case_count",
        "single_domain_case_hits",
        "multi_domain_case_count",
        "multi_domain_case_hits",
        "zero_match_case_count",
        "zero_match_case_hits",
        "routing_precision",
        "routing_recall",
        "top_domain_accuracy_single_domain",
        "required_domain_recall",
        "unexpected_domain_false_positives",
        "multi_domain_coverage",
        "zero_match_correctness",
        "tie_determinism",
        "explainability_coverage",
        "maximum_observed_returned_domains",
        "results_digest",
        "hard_invariants",
    )
    for split in ("development", "holdout"):
        for key in stable_split_fields:
            if stored.get(split, {}).get(key) != evidence[split].get(key):
                raise ValueError(f"committed routing receipt is stale at {split}.{key}")


def build_evidence() -> dict[str, Any]:
    _validate_active_manifest()
    ground_truth = _read_json(GROUND_TRUTH_PATH)
    universe = _validate_ground_truth(ground_truth)
    expected_ground_truth_digest = ground_truth["ground_truth_digest"]
    policy_bytes_before = _read_bounded_bytes(POLICY_PATH, max_bytes=256 * 1024)
    previous_config = os.environ.get("POWER_DOMAIN_CONFIG")
    os.environ["POWER_DOMAIN_CONFIG"] = str(POLICY_PATH)
    try:
        policy = load_domain_policy(ROOT)
    finally:
        if previous_config is None:
            os.environ.pop("POWER_DOMAIN_CONFIG", None)
        else:
            os.environ["POWER_DOMAIN_CONFIG"] = previous_config
    if policy.version != 2 or policy.policy_revision != "phase5b-routing-v1":
        raise ValueError("Phase 5B runtime policy revision mismatch")
    policy_bytes_after = _read_bounded_bytes(POLICY_PATH, max_bytes=256 * 1024)
    if policy_bytes_before != policy_bytes_after:
        raise ValueError("routing policy changed during evaluation")
    policy_sha256 = _sha256_bytes(policy_bytes_after)
    if policy_sha256 != EXPECTED_POLICY_SHA256:
        raise ValueError("routing policy is not the admitted revision")
    router = RetrievalDomainRouter(policy)

    development_queries = _read_jsonl(ACTIVE_ROOT / "queries.development.jsonl")
    development = _evaluate_split(
        router,
        ground_truth["splits"]["development"]["labels"],
        development_queries,
        universe,
    )
    # This is the candidate freeze boundary: holdout is evaluated only after
    # policy, normalization, and algorithm identity have been recorded.
    candidate_freeze = {
        "algorithm_revision": ALGORITHM_REVISION,
        "policy_revision": policy.policy_revision,
        "normalization_revision": policy.normalization_revision,
        "policy_sha256": policy_sha256,
        "holdout_tuning": "forbidden",
    }
    # Integrity verification may read holdout bytes, so it deliberately occurs
    # after the immutable candidate freeze and before holdout label admission.
    manifest_summary = verify_evaluation_corpus(ACTIVE_ROOT)
    if manifest_summary.get("evaluation_revision") != "v1.1":
        raise ValueError("active corpus verifier did not select v1.1")
    holdout_queries = _read_jsonl(ACTIVE_ROOT / "queries.holdout.jsonl")
    holdout_labels = _load_holdout_labels(universe)
    holdout = _evaluate_split(
        router,
        holdout_labels,
        holdout_queries,
        universe,
    )
    hard_invariants = {
        "authority_violations": development["hard_invariants"]["authority_violations"]
        + holdout["hard_invariants"]["authority_violations"],
        "lifecycle_violations": development["hard_invariants"]["lifecycle_violations"]
        + holdout["hard_invariants"]["lifecycle_violations"],
        "vault_boundary_escapes": 0 if _vault_boundary_probe() else 1,
        "non_deterministic_outputs": development["hard_invariants"]["non_deterministic_outputs"]
        + holdout["hard_invariants"]["non_deterministic_outputs"],
        "unexplained_domain_matches": development["hard_invariants"]["unexplained_domain_matches"]
        + holdout["hard_invariants"]["unexplained_domain_matches"],
        "holdout_tuning_violations": 0,
        "legacy_v1_regressions": 0 if _legacy_compatibility_probe() else 1,
    }
    return {
        "schema_version": "power.domain-routing-evaluation.v1",
        "evaluation_revision": "v1.1",
        "algorithm_revision": ALGORITHM_REVISION,
        "policy_revision": policy.policy_revision,
        "normalization_revision": policy.normalization_revision,
        "policy_sha256": candidate_freeze["policy_sha256"],
        "active_v1_1_digests": REQUIRED_ACTIVE_DIGESTS,
        "active_corpus_verification": {
            "evaluation_revision": manifest_summary.get("evaluation_revision"),
            "source_corpus_digest": manifest_summary.get("source_corpus_digest"),
            "dataset_digest": manifest_summary.get("dataset_digest"),
            "development_digest": manifest_summary.get("development_digest"),
            "holdout_digest": manifest_summary.get("holdout_digest"),
        },
        "ground_truth_digest": expected_ground_truth_digest,
        "ground_truth_router_output_used": ground_truth["review"]["router_output_used"],
        "holdout_discipline": {
            "no_tuning_on_holdout": True,
            "development_evaluated_before_freeze": True,
            "candidate_freeze": candidate_freeze,
            "holdout_evaluated_after_freeze": True,
        },
        "development": development,
        "holdout": holdout,
        "hard_invariants": hard_invariants,
    }


def main() -> int:
    try:
        evidence = build_evidence()
        _validate_committed_receipt(evidence)
        print(json.dumps(evidence, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"domain-routing verification failed: {type(exc).__name__}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
