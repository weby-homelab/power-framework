"""Read-only index discovery without scanning vector payloads or loading a model."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING, Literal

from .constants import DENSE_INDEX_SCHEMA_VERSION

if TYPE_CHECKING:
    from pathlib import Path


def read_index_status(
    database: Path,
) -> tuple[int, int, Literal["manifest_compatible", "missing", "incompatible"]]:
    """Inspect the selected index; actual dense retrieval validates the vectors."""
    with closing(sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True, timeout=30)) as conn:
        conn.execute("SELECT rel_path FROM fts_notes LIMIT 1").fetchone()
        notes = int(conn.execute("SELECT COUNT(*) FROM file_metadata").fetchone()[0])
        chunks = int(conn.execute("SELECT COUNT(*) FROM chunk_embeddings").fetchone()[0])
        if chunks == 0:
            return notes, chunks, "missing"
        try:
            manifest = dict(
                conn.execute("SELECT manifest_key, manifest_value FROM dense_index_manifest")
            )
        except sqlite3.Error:
            return notes, chunks, "incompatible"

    from power_framework.experimental.embeddings import configured_embedding_identity

    provider, model = configured_embedding_identity()
    try:
        dimension = int(manifest.get("embedding_dimension", ""))
    except (TypeError, ValueError):
        dimension = 0
    compatible = (
        dimension > 0
        and manifest.get("schema_version") == DENSE_INDEX_SCHEMA_VERSION
        and manifest.get("chunk_count") == str(chunks)
        and manifest.get("embedding_provider") == provider
        and manifest.get("embedding_model") == model
    )
    return notes, chunks, "manifest_compatible" if compatible else "incompatible"
