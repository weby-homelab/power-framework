#!/usr/bin/env python3
"""Fail-closed validation for the human-facing M2-v2 annotation packet."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

PACKET_SCHEMA_VERSION = "2.0"
LANGUAGE = "uk"
RESPONSE_FIELDS = (
    "document_id",
    "relevance",
    "acceptable_citation",
    "temporal_status",
)
PACKET_FIELDS = {
    "packet_schema_version",
    "language",
    "split",
    "query_id",
    "question",
    "candidates",
    "response_fields",
}
FORBIDDEN_PACKET_FIELDS = {
    "journey",
    "answerability",
    "expected_abstention",
    "mode",
    "source",
    "source_path",
    "family",
    "hostname",
}
SENSITIVE_PATTERNS = (
    r"https?://",
    r"\b(?:[a-z0-9-]+\.)+(?:com|net|org|io|ua|dev|local)\b",
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b",
    r"\bsk-[A-Za-z0-9]{20,}\b",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\b\d{1,3}(?:\.\d{1,3}){3}\b",
)
UKRAINIAN_LETTERS = re.compile(r"[А-ЩЬЮЯІЇЄҐа-щьюяіїєґ]")  # noqa: RUF001


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number}: JSONL row must be an object")
            rows.append(value)
    return rows


def _contains_sensitive(value: object) -> bool:
    serialized = json.dumps(value, ensure_ascii=False)
    return any(re.search(pattern, serialized, re.IGNORECASE) for pattern in SENSITIVE_PATTERNS)


def validate_packet(
    packet_rows: list[dict[str, Any]],
    query_rows: list[dict[str, Any]],
    corpus_rows: list[dict[str, Any]],
    *,
    expected_split: str,
) -> list[str]:
    """Return all packet violations without exposing packet text in errors."""
    errors: list[str] = []
    queries = {str(row.get("query_id", "")): row for row in query_rows}
    documents = {str(row.get("document_id", "")): row for row in corpus_rows}
    if len(queries) != len(query_rows) or "" in queries:
        errors.append("queries must have unique non-empty query_id values")
    if len(documents) != len(corpus_rows) or "" in documents:
        errors.append("corpus must have unique non-empty document_id values")
    if len(documents) != 4:
        errors.append("M2-v2 packet must contain exactly four candidates")
    seen_queries: set[str] = set()
    candidate_order: tuple[str, ...] | None = None
    for index, packet in enumerate(packet_rows, 1):
        if set(packet) != PACKET_FIELDS:
            errors.append(f"packet row {index}: top-level fields do not match v2 contract")
        query_id = str(packet.get("query_id", ""))
        if not isinstance(packet.get("query_id"), str) or not query_id:
            errors.append(f"packet row {index}: query_id must be a non-empty string")
        if query_id in seen_queries:
            errors.append(f"packet row {index}: duplicate query_id")
        seen_queries.add(query_id)
        packet_version = packet.get("packet_schema_version")
        if packet_version != PACKET_SCHEMA_VERSION:
            errors.append(f"packet row {index}: packet_schema_version must be 2.0")
        if packet.get("language") != LANGUAGE:
            errors.append(f"packet row {index}: language must be uk")
        if packet.get("split") != expected_split:
            errors.append(f"packet row {index}: split does not match expected split")
        if FORBIDDEN_PACKET_FIELDS.intersection(packet):
            errors.append(f"packet row {index}: hidden evaluation field exposed")
        if tuple(packet.get("response_fields", ())) != RESPONSE_FIELDS:
            errors.append(f"packet row {index}: response_fields do not match v2 contract")
        if query_id not in queries:
            errors.append(f"packet row {index}: query_id is not in query artifact")
            continue
        question = packet.get("question")
        if not isinstance(question, str) or not question.strip() or len(question) > 160:
            errors.append(f"packet row {index}: question must be short and non-empty")
        elif not UKRAINIAN_LETTERS.search(question):
            errors.append(f"packet row {index}: question is not Ukrainian-language")
        if question != queries[query_id].get("question"):
            errors.append(f"packet row {index}: question does not match query artifact")
        candidates = packet.get("candidates")
        if not isinstance(candidates, list) or len(candidates) != 4:
            errors.append(f"packet row {index}: exactly four candidates are required")
        ids: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                errors.append(f"packet row {index}: candidate must be an object")
                continue
            if set(candidate) != {"document_id", "title", "text"}:
                errors.append(f"packet row {index}: candidate exposes non-human fields")
                continue
            document_id_value = candidate.get("document_id")
            document_id = str(document_id_value)
            if not isinstance(document_id_value, str) or not document_id:
                errors.append(
                    f"packet row {index}: candidate document_id must be a non-empty string"
                )
            ids.append(document_id)
            if document_id not in documents:
                errors.append(f"packet row {index}: candidate is not in corpus artifact")
                continue
            if candidate.get("title") != documents[document_id].get("title"):
                errors.append(f"packet row {index}: candidate title is not corpus-bound")
            if candidate.get("text") != documents[document_id].get("text"):
                errors.append(f"packet row {index}: candidate text is not corpus-bound")
            text = candidate.get("text")
            if not isinstance(text, str) or not text.strip() or len(text) > 500:
                errors.append(f"packet row {index}: candidate text is too long or empty")
            elif not UKRAINIAN_LETTERS.search(text):
                errors.append(f"packet row {index}: candidate text is not Ukrainian-language")
        if len(set(ids)) != len(ids):
            errors.append(f"packet row {index}: candidate document IDs are not unique")
        if candidate_order is None:
            candidate_order = tuple(ids)
        elif tuple(ids) != candidate_order:
            errors.append(f"packet row {index}: candidate order differs between queries")
        if _contains_sensitive(packet):
            errors.append(f"packet row {index}: sensitive or external material detected")
    if seen_queries != set(queries):
        errors.append("packet and query artifacts have different query IDs")
    return sorted(set(errors))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--queries", required=True, type=Path)
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument("--split", default="development", choices=("development", "calibration"))
    args = parser.parse_args()
    errors = validate_packet(
        load_jsonl(args.packet),
        load_jsonl(args.queries),
        load_jsonl(args.corpus),
        expected_split=args.split,
    )
    if errors:
        sys.stderr.write("M2-v2 annotation packet invalid:\n")
        for error in errors:
            sys.stderr.write(f"- {error}\n")
        return 1
    sys.stdout.write(
        json.dumps(
            {
                "status": "valid",
                "packet": str(args.packet),
                "queries": len(load_jsonl(args.queries)),
                "candidates_per_query": 4,
                "language": LANGUAGE,
                "split": args.split,
            },
            ensure_ascii=False,
        )
        + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
