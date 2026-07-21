"""Hermetic blocking retrieval-quality fixture for PR CI."""

from __future__ import annotations

from pathlib import Path

import pytest

from power_framework.core.searcher import search_vault


@pytest.mark.parametrize(
    ("query", "expected_path"),
    [
        ("test project", "01_Projects/TestProject.md"),
        ("sample resource", "03_Resources/TestResource.md"),
        ("Weby QRank architecture", "01_Projects/Weby-QRank/Architecture.md"),
    ],
)
def test_fts_retrieval_fixture_returns_expected_document(
    sample_vault: Path, query: str, expected_path: str
) -> None:
    results = search_vault(sample_vault, query, mode="fts", max_results=3)

    assert results, f"fixture query executed but returned no results: {query!r}"
    assert expected_path in {result.rel_path for result in results}
