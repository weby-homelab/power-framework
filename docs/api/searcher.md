# Searcher

Full-text search with relevance scoring using SQLite FTS5 (with memory fallback).

| Function                                            | Returns              | Description                                                                                                                                                                                                                                                                                                                                                          |
| --------------------------------------------------- | -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `search_vault(vault_dir, query, max_results, mode)` | `list[SearchResult]` | Search the vault with a canonical mode: `semantic` (default; BGE-M3 dense cosine), `fts` (BM25 FTS5), `vector` (TF-vector cosine), `hybrid` (RRF of FTS + TF-vector), `reranked` (explicit opt-in: RRF of FTS + TF-vector + dense candidates, then BGE ONNX cross-encoder), or `graph_assisted` (sparse RRF expanded through validated OKF relations). Dense-required modes fail closed unless the caller explicitly allows the labelled FTS fallback. |
| `format_search_results(results, query, mode)`       | `str`                | Format search results into a human-readable report string                                                                                                                                                                                                                                                                                                            |

## `SearchResult`

Class representing a single search result with relevance details.

| Attribute     | Type        | Description                           |
| ------------- | ----------- | ------------------------------------- |
| `rel_path`    | `str`       | Note relative path                    |
| `title`       | `str`       | Note title                            |
| `description` | `str`       | Note description                      |
| `note_type`   | `str`       | Note OKF type                         |
| `score`       | `float`     | Weighted relevance score              |
| `snippet`     | `str`       | Context window around match           |
| `matched_text` | `str`      | Bounded body-only passage for agent context; excludes YAML frontmatter and synthetic chunk headers |
| `match_count` | `int`       | Match count fallback                  |
| `tags`        | `list[str]` | List of tags associated with the note |
| `retrieval_contract` | `str` | Applied retrieval contract, including an explicit fallback when enabled |
| `index_kind` | `str or None` | Verified request index: `immutable_generation` or `legacy_db` |
| `index_generation_id` | `str or None` | Immutable generation identifier when `index_kind` is `immutable_generation` |
| `index_source_snapshot_hash` | `str or None` | Content-free source snapshot hash for the verified immutable generation |

## Retrieval contract

The executable registry is `SEARCH_MODE_REGISTRY` in `core/searcher.py` and
the generated reference table is in [Architecture](../architecture.md). The
deprecated `hybrid_reranked` input alias normalizes to `reranked`; it is not a
canonical mode. The current default is `semantic`, not `reranked`.

## Active-generation resolution

When a vault has an immutable generation, POWER verifies the active state and
database identity before serving retrieval. The verified identity may be
reused by later requests only while the generation-state database (including
its SQLite WAL/SHM files) and the immutable database fingerprint are unchanged.
Publication explicitly invalidates this cache, and an identity or integrity
mismatch fails closed instead of falling back to a stale generation.

For dense retrieval, the exact vector matrix is also cached in process memory
after that identity verification. The cache key is the vault plus the verified
generation ID and database SHA-256; it is bounded, contains no note content, and
is never used for a legacy writable database. A new generation creates a new
matrix and evicts the superseded entry for that vault. This is an exact-read
optimization, not an ANN index or a new persistence layer; cache misses and
hits use the same SQLite vector bytes and cosine oracle.
