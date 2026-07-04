# Searcher

Full-text search with relevance scoring using SQLite FTS5 (with memory fallback).

| Function | Returns | Description |
|----------|---------|-------------|
| `search_vault(vault_dir, query, max_results)` | `list[SearchResult]` | Search the vault for notes matching the query |
| `format_search_results(results, query)` | `str` | Format search results into a human-readable report string |

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

