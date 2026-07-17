"""Tests for POWER v3.0 performance features and optimizations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from power_framework.core.searcher import (
    _init_db,
    _vector_search,
    search_vault,
)
from power_framework.core.utils import get_cache_dir


def test_tf_vectors_caching(sample_vault: Path):
    """Verify that TF vectors are successfully cached in SQLite during search."""
    # Run a search to trigger DB initialization and synchronization
    results = search_vault(sample_vault, "Weby-QRank", mode="vector")
    assert len(results) > 0

    # Connect to the database and verify the tf_vectors table has data
    db_path = get_cache_dir() / "power_search.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    cursor.execute("SELECT count(*) FROM tf_vectors")
    count = cursor.fetchone()[0]
    assert count > 0

    # Ensure details exist for our files
    cursor.execute("SELECT rel_path, tf_data FROM tf_vectors")
    rows = cursor.fetchall()
    assert len(rows) == count
    for rel_path, tf_data in rows:
        assert rel_path.endswith(".md")
        assert "{" in tf_data  # Should be JSON serialized dict
        assert "}" in tf_data

    conn.close()


def test_query_expansion_deduplication(sample_vault: Path):
    """Verify that Query Expansion fusion returns unique results without duplicate paths."""
    # Mode = hybrid which triggers Query Expansion with variants
    results = search_vault(sample_vault, "deploy docker container", mode="hybrid")
    
    # Ensure there are no duplicate rel_paths
    seen_paths = set()
    for r in results:
        assert r.rel_path not in seen_paths
        seen_paths.add(r.rel_path)
