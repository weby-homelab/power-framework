"""Build local-only, de-identified M2 corpus and blinded annotation packets.

This deliberately does not create human judgments or qrels.  It transforms
manually reviewed semantic excerpts from the real vault into opaque document
identifiers, removes source locations and rejects obvious sensitive material.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

JOURNEYS = (
    "current_fact",
    "historical_fact",
    "provenance_trace",
    "abstention",
    "candidate_boundary",
)
SENSITIVE_PATTERNS = (
    r"https?://",
    r"\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|ua|dev|local)\b",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"\bghp_[A-Za-z0-9]{20,}\b",
    r"\bsk-[A-Za-z0-9]{20,}\b",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\b\d{1,3}(?:\.\d{1,3}){3}\b",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records
        ),
        encoding="utf-8",
    )


def _assert_deidentified(records: list[dict[str, Any]]) -> None:
    serialized = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
    for pattern in SENSITIVE_PATTERNS:
        if re.search(pattern, serialized, flags=re.IGNORECASE):
            raise ValueError(f"de-identification guard rejected pattern: {pattern}")


def _manifest(output: Path, split: str) -> dict[str, Any]:
    artifacts = {
        "corpus": "corpus.jsonl",
        "queries": "queries.jsonl",
        "raw_judgments": "raw-judgments.jsonl",
        "adjudicated_qrels": "adjudicated-qrels.jsonl",
    }
    digests = {key: _sha256(output / filename) for key, filename in artifacts.items()}
    return {
        "schema_version": "1.0",
        "status": "pending_human_annotation",
        "split": split,
        "corpus_sha256": digests["corpus"],
        "queries_sha256": digests["queries"],
        "raw_judgments_sha256": digests["raw_judgments"],
        "adjudicated_qrels_sha256": digests["adjudicated_qrels"],
        "artifacts": artifacts,
        "annotation_protocol": "../../annotation_protocol.md",
        "journeys": list(JOURNEYS),
        "thresholds": None,
        "corpus_status": "deidentified_reviewed_pending_independent_annotation",
    }


def build(output_root: Path, vault: Path) -> None:
    """Create split-isolated corpus, queries and two mode-blind packets."""
    documents = [
        {
            "document_id": "doc-001",
            "family": "roadmap-authority",
            "split": "development",
            "title": "Canonical roadmap authority",
            "text": "Markdown in version control is authoritative. Derived indexes and embeddings can be rebuilt. A status may be called done only with executable evidence.",
        },
        {
            "document_id": "doc-002",
            "family": "roadmap-quality-gap",
            "split": "development",
            "title": "Human retrieval quality gap",
            "text": "A synthetic benchmark is useful for regression but does not demonstrate usefulness for real questions. Frozen human qrels, a sealed holdout and adjudication are required.",
        },
        {
            "document_id": "doc-003",
            "family": "m2-foundation",
            "split": "development",
            "title": "M2 evidence boundary",
            "text": "M2 requires independently produced human judgments and a sealed holdout. The evidence contract separates development from holdout and binds corpus, queries and judgments by hashes.",
        },
        {
            "document_id": "doc-004",
            "family": "release-boundary",
            "split": "development",
            "title": "Release evidence limits",
            "text": "Release checks can prove package provenance and automation gates. They do not prove human-adjudicated retrieval quality, sealed evaluation or production performance on target hardware.",
        },
        {
            "document_id": "doc-005",
            "family": "security-model",
            "split": "sealed_holdout",
            "title": "Threat model controls",
            "text": "The formal threat model covers assets, trust boundaries, attacker-controlled inputs, assumptions and mitigations. Controls include path containment, atomic writes and explicit approved mutations.",
        },
        {
            "document_id": "doc-006",
            "family": "m2-adjudication",
            "split": "sealed_holdout",
            "title": "Human adjudication requirement",
            "text": "Two annotators judge each query-document pair independently. A third adjudicator resolves disagreements while retaining both original judgments and a reason code.",
        },
    ]
    queries = [
        {
            "query_id": "dev-q-001",
            "split": "development",
            "journey": "current_fact",
            "question": "What artifact is authoritative for the current project plan?",
        },
        {
            "query_id": "dev-q-002",
            "split": "development",
            "journey": "historical_fact",
            "question": "Does a successful release gate prove human retrieval quality?",
        },
        {
            "query_id": "dev-q-003",
            "split": "development",
            "journey": "provenance_trace",
            "question": "Which evidence is required before a retrieval status may be treated as completed?",
        },
        {
            "query_id": "dev-q-004",
            "split": "development",
            "journey": "abstention",
            "question": "Which document states the target hardware p95 latency threshold?",
        },
        {
            "query_id": "dev-q-005",
            "split": "development",
            "journey": "candidate_boundary",
            "question": "Can a synthetic CI benchmark authorize a production-quality claim?",
        },
        {
            "query_id": "holdout-q-001",
            "split": "sealed_holdout",
            "journey": "current_fact",
            "question": "What controls are named by the formal threat model?",
        },
        {
            "query_id": "holdout-q-002",
            "split": "sealed_holdout",
            "journey": "historical_fact",
            "question": "What must remain after disagreement reconciliation?",
        },
        {
            "query_id": "holdout-q-003",
            "split": "sealed_holdout",
            "journey": "provenance_trace",
            "question": "How are corpus and annotation artifacts made reproducible?",
        },
        {
            "query_id": "holdout-q-004",
            "split": "sealed_holdout",
            "journey": "abstention",
            "question": "Which document gives the currently approved remote hostname?",
        },
        {
            "query_id": "holdout-q-005",
            "split": "sealed_holdout",
            "journey": "candidate_boundary",
            "question": "May heuristic inference be treated as authoritative evidence?",
        },
    ]
    sources = {
        "source-001": vault / "01_Projects/ROADMAP_POWER.md",
        "source-002": vault
        / "06_Daily_Logs/2026-07-29_POWER_M2_Human_Retrieval_Evidence_Foundation.md",
        "source-003": vault / "06_Daily_Logs/2026-07-28_POWER_3.3.0_Phase_3_Release_Truth.md",
        "source-004": vault / "06_Daily_Logs/2026-07-29_POWER_M1_Gate_Threat_Model.md",
    }
    if not all(path.is_file() for path in sources.values()):
        missing = [source_id for source_id, path in sources.items() if not path.is_file()]
        raise FileNotFoundError(f"approved vault sources are missing: {', '.join(missing)}")
    _assert_deidentified(documents + queries)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "source-provenance.json").write_text(
        json.dumps(
            {
                "status": "local_only_deidentified_derivation",
                "sources": [
                    {"source_id": source_id, "sha256": _sha256(path)}
                    for source_id, path in sources.items()
                ],
                "rule": "Source paths and source text stay in the private vault; only reviewed semantic excerpts are exported.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_root / "pre-registration.json").write_text(
        json.dumps(
            {
                "status": "pre_registered_before_sealed_evaluation",
                "thresholds": {
                    "recall_at_10": 0.80,
                    "ndcg_at_10": 0.70,
                    "mrr_at_10": 0.70,
                    "citation_provenance_accuracy": 0.95,
                    "stale_answer_rate_max": 0.02,
                    "abstention_quality": 0.90,
                    "p95_latency_ms": 1500,
                },
                "comparators": ["lexical", "semantic", "hybrid", "reranked", "graph_assisted"],
                "rule": "Thresholds are policy targets, not measured results; change requires a new pre-registration receipt before sealed access.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for split in ("development", "sealed_holdout"):
        output = output_root / split
        split_docs = [record for record in documents if record["split"] == split]
        split_queries = [record for record in queries if record["split"] == split]
        _write_jsonl(output / "corpus.jsonl", split_docs)
        _write_jsonl(output / "queries.jsonl", split_queries)
        _write_jsonl(
            output / "raw-judgments.jsonl",
            [{"status": "pending_independent_human_annotation", "judgments": []}],
        )
        _write_jsonl(
            output / "adjudicated-qrels.jsonl",
            [{"status": "pending_third_party_adjudication", "qrels": []}],
        )
        (output / "manifest.json").write_text(
            json.dumps(_manifest(output, split), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        candidates = [{"query": query, "candidates": split_docs} for query in split_queries]
        for annotator in ("a", "b"):
            _write_jsonl(
                output_root / "annotation-packets" / f"annotator-{annotator}-{split}.jsonl",
                candidates,
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--vault", required=True, type=Path)
    args = parser.parse_args()
    build(args.output, args.vault)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
