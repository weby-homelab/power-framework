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
| `match_count` | `int`       | Match count fallback                  |
| `tags`        | `list[str]` | List of tags associated with the note |
| `retrieval_contract` | `str` | Applied retrieval contract, including an explicit fallback when enabled |

## Retrieval contract

The executable registry is `SEARCH_MODE_REGISTRY` in `core/searcher.py` and
the generated reference table is in [Architecture](../architecture.md). The
deprecated `hybrid_reranked` input alias normalizes to `reranked`; it is not a
canonical mode. The current default is `semantic`, not `reranked`.
