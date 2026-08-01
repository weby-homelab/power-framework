"""Build local-only, de-identified M2-v2 corpus and Ukrainian packets.

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

# Ukrainian corpus fixtures intentionally contain Cyrillic text.
# ruff: noqa: RUF001

PROTOCOL_VERSION = "2.0"
PACKET_LANGUAGE = "uk"
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
        "schema_version": PROTOCOL_VERSION,
        "status": "pending_calibration",
        "split": split,
        "corpus_sha256": digests["corpus"],
        "queries_sha256": digests["queries"],
        "raw_judgments_sha256": digests["raw_judgments"],
        "adjudicated_qrels_sha256": digests["adjudicated_qrels"],
        "artifacts": artifacts,
        "annotation_protocol": "annotation_protocol_v2.md",
        "language": PACKET_LANGUAGE,
        "calibration": {
            "status": "pending",
            "agreement_receipt_sha256": None,
        },
        "journeys": list(JOURNEYS),
        "thresholds": None,
        "corpus_status": "deidentified_reviewed_pending_calibration_and_annotation",
    }


def _packet_rows(
    queries: list[dict[str, Any]], documents: list[dict[str, Any]], split: str
) -> list[dict[str, Any]]:
    """Render only the human-facing fields; never expose journey or source data."""
    visible_documents = [
        {
            "document_id": str(document["document_id"]),
            "title": str(document["title"]),
            "text": str(document["text"]),
        }
        for document in documents
    ]
    return [
        {
            "packet_schema_version": PROTOCOL_VERSION,
            "language": PACKET_LANGUAGE,
            "split": split,
            "query_id": str(query["query_id"]),
            "question": str(query["question"]),
            "candidates": visible_documents,
            "response_fields": [
                "document_id",
                "relevance",
                "acceptable_citation",
                "temporal_status",
            ],
        }
        for query in queries
    ]


def build(output_root: Path, vault: Path) -> None:
    """Create split-isolated corpus, calibration material and Ukrainian packets."""
    documents = [
        {
            "document_id": "doc-001",
            "family": "roadmap-authority",
            "split": "development",
            "title": "Поточне правило: головний план",
            "text": "Статус документа: поточний. Головним планом проєкту є Markdown у системі версій. Похідні індекси та embeddings можна побудувати знову. Називати роботу завершеною можна лише за наявності виконуваного доказу.",
        },
        {
            "document_id": "doc-002",
            "family": "roadmap-quality-gap",
            "split": "development",
            "title": "Історичний запис: межа синтетичного тесту",
            "text": "Статус документа: історичний. Синтетичний benchmark корисний для регресійної перевірки, але сам не доводить користь для реальних запитань. Для такого висновку потрібні людські qrels, adjudication і sealed holdout.",
        },
        {
            "document_id": "doc-003",
            "family": "m2-foundation",
            "split": "development",
            "title": "Поточне правило: доказ M2",
            "text": "Статус документа: поточний. M2 потребує незалежних людських оцінок і sealed holdout. Контракт доказів відділяє development від holdout та зв'язує corpus, queries і judgments контрольними сумами.",
        },
        {
            "document_id": "doc-004",
            "family": "release-boundary",
            "split": "development",
            "title": "Поточне правило: межі release-доказу",
            "text": "Статус документа: поточний. Release-перевірки можуть довести походження пакета й автоматичні gate. Вони не доводять людську якість пошуку, sealed evaluation або production performance на цільовому обладнанні.",
        },
        {
            "document_id": "doc-005",
            "family": "security-model",
            "split": "sealed_holdout",
            "title": "Поточне правило: controls threat model",
            "text": "Статус документа: поточний. Формальна модель загроз описує активи, межі довіри, входи під контролем атакувальника, припущення та захист. Серед controls є containment шляхів, атомарні записи й явно дозволені зміни.",
        },
        {
            "document_id": "doc-006",
            "family": "m2-adjudication",
            "split": "sealed_holdout",
            "title": "Історичний запис: правило adjudication",
            "text": "Статус документа: історичний. Двоє оцінювачів незалежно оцінюють кожну пару «запит—документ». Третій adjudicator вирішує розбіжності, зберігаючи обидві початкові оцінки та причину.",
        },
    ]
    queries = [
        {
            "query_id": "dev-q-001",
            "split": "development",
            "journey": "current_fact",
            "question": "Що є головним джерелом поточного плану проєкту?",
        },
        {
            "query_id": "dev-q-002",
            "split": "development",
            "journey": "historical_fact",
            "question": "Чи доводить успішна release-перевірка якість пошуку для людей?",
        },
        {
            "query_id": "dev-q-003",
            "split": "development",
            "journey": "provenance_trace",
            "question": "Що потрібно мати, перш ніж назвати перевірку пошуку завершеною?",
        },
        {
            "query_id": "dev-q-004",
            "split": "development",
            "journey": "abstention",
            "question": "У якому документі вказано число для p95 затримки цільового обладнання?",
        },
        {
            "query_id": "dev-q-005",
            "split": "development",
            "journey": "candidate_boundary",
            "question": "Чи може синтетичний CI-тест сам довести production-якість?",
        },
        {
            "query_id": "holdout-q-001",
            "split": "sealed_holdout",
            "journey": "current_fact",
            "question": "Які controls називає формальна модель загроз?",
        },
        {
            "query_id": "holdout-q-002",
            "split": "sealed_holdout",
            "journey": "historical_fact",
            "question": "Що треба зберегти після вирішення розбіжностей?",
        },
        {
            "query_id": "holdout-q-003",
            "split": "sealed_holdout",
            "journey": "provenance_trace",
            "question": "Як зробити corpus і оцінки відтворюваними?",
        },
        {
            "query_id": "holdout-q-004",
            "split": "sealed_holdout",
            "journey": "abstention",
            "question": "У якому документі вказано затверджене ім'я віддаленого хоста?",
        },
        {
            "query_id": "holdout-q-005",
            "split": "sealed_holdout",
            "journey": "candidate_boundary",
            "question": "Чи можна вважати heuristic inference доказом без додаткової перевірки?",
        },
    ]
    calibration_documents = [
        {
            "document_id": "cal-doc-001",
            "title": "Поточний запис: час зустрічі",
            "text": "Статус документа: поточний. Командна зустріч починається о 10:00.",
        },
        {
            "document_id": "cal-doc-002",
            "title": "Історичний запис: стара назва",
            "text": "Статус документа: історичний. Раніше проєкт мав назву «Старий план».",
        },
        {
            "document_id": "cal-doc-003",
            "title": "Поточний запис: формат звіту",
            "text": "Статус документа: поточний. Щотижневий звіт зберігають у форматі Markdown.",
        },
        {
            "document_id": "cal-doc-004",
            "title": "Довідковий запис: колір",
            "text": "Статус документа: поточний. Для заголовка дозволено синій колір.",
        },
    ]
    calibration_queries = [
        {
            "query_id": "cal-q-001",
            "question": "О котрій починається командна зустріч?",
        },
        {
            "query_id": "cal-q-002",
            "question": "Яку стару назву мав проєкт?",
        },
        {
            "query_id": "cal-q-003",
            "question": "Який номер телефону вказано для команди?",
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
    _assert_deidentified(documents + queries + calibration_documents + calibration_queries)
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
                "status": "pre_registered_before_human_calibration",
                "protocol_version": PROTOCOL_VERSION,
                "language": PACKET_LANGUAGE,
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
    calibration_root = output_root / "calibration"
    _write_jsonl(calibration_root / "corpus.jsonl", calibration_documents)
    _write_jsonl(calibration_root / "queries.jsonl", calibration_queries)
    calibration_packets = _packet_rows(calibration_queries, calibration_documents, "calibration")
    for annotator in ("a", "b"):
        _write_jsonl(
            output_root / "annotation-packets" / f"annotator-{annotator}-calibration.jsonl",
            calibration_packets,
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
        if split == "development":
            candidates = _packet_rows(split_queries, split_docs, split)
            for annotator in ("a", "b"):
                _write_jsonl(
                    output_root / "annotation-packets" / f"annotator-{annotator}-{split}.jsonl",
                    candidates,
                )
        else:
            (output_root / "annotation-packets" / "SEALED_NOT_PACKAGED").write_text(
                "Sealed holdout packet intentionally not generated.\n", encoding="utf-8"
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
