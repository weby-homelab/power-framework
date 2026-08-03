"""Tests for the human-facing Ukrainian M2-v2 packet boundary."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = (
    Path(__file__).parents[1]
    / "benchmarks"
    / "human_retrieval"
    / "scripts"
    / "validate_annotation_packet.py"
)
SPEC = importlib.util.spec_from_file_location("m2_packet", SCRIPT)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _packet() -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    corpus = [
        {"document_id": f"doc-{index}", "title": f"Документ {index}", "text": "Поточний факт."}
        for index in range(1, 5)
    ]
    queries = [
        {"query_id": "dev-q-001", "question": "Що є поточним правилом?", "journey": "current_fact"}
    ]
    packet = [
        {
            "packet_schema_version": "2.0",
            "language": "uk",
            "split": "development",
            "query_id": "dev-q-001",
            "question": "Що є поточним правилом?",
            "candidates": corpus,
            "response_fields": list(MODULE.RESPONSE_FIELDS),
        }
    ]
    return packet, queries, corpus


def test_valid_packet_hides_evaluation_contract() -> None:
    packet, queries, corpus = _packet()
    assert MODULE.validate_packet(packet, queries, corpus, expected_split="development") == []


def test_packet_rejects_journey_and_non_uk_text() -> None:
    packet, queries, corpus = _packet()
    packet[0]["journey"] = "current_fact"
    packet[0]["question"] = "What is current?"
    errors = MODULE.validate_packet(packet, queries, corpus, expected_split="development")
    assert "packet row 1: hidden evaluation field exposed" in errors
    assert "packet row 1: question is not Ukrainian-language" in errors


def test_packet_rejects_external_material() -> None:
    packet, queries, corpus = _packet()
    packet[0]["candidates"][0]["text"] = "Поточний факт https://example.com"  # type: ignore[index]
    errors = MODULE.validate_packet(packet, queries, corpus, expected_split="development")
    assert "packet row 1: sensitive or external material detected" in errors


def test_packet_rejects_unknown_top_level_field() -> None:
    packet, queries, corpus = _packet()
    packet[0]["gold_answer"] = "Поточний факт"

    errors = MODULE.validate_packet(packet, queries, corpus, expected_split="development")

    assert "packet row 1: top-level fields do not match v2 contract" in errors
