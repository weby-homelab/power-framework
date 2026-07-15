# Searcher

Full-text search with relevance scoring using SQLite FTS5 (with memory fallback).

| Function | Returns | Description |
|----------|---------|-------------|
| `search_vault(vault_dir, query, max_results, mode)` | `list[SearchResult]` | Search the vault with query expansion and configurable mode: `fts` (BM25 FTS5, default), `vector` (TF cosine similarity), `hybrid` (RRF fusion of FTS + Vector), `semantic` (dense embedding cosine similarity via `BAAI/bge-m3`), and `hybrid_reranked` (RRF merge with Cross-Encoder reranking) |
| `format_search_results(results, query, mode)` | `str` | Format search results into a human-readable report string |

## `SearchResult`

Class representing a single search result with relevance details.

| Attribute | Type | Description |
|-----------|------|-------------|
| `rel_path` | `str` | Note relative path |
| `title` | `str` | Note title |
| `description` | `str` | Note description |
| `note_type` | `str` | Note OKF type |
| `score` | `float` | Weighted relevance score |
| `snippet` | `str` | Context window around match |
| `match_count` | `int` | Match count fallback |
| `tags` | `list[str]` | List of tags associated with the note |

