# Searcher

Full-text search with relevance scoring.

| Function | Returns | Description |
|----------|---------|-------------|
| `search_vault(path, query, max_results)` | `list[SearchResult]` | Search vault notes |
| `tokenize(text)` | `list[str]` | Lowercase, strip punctuation |
| `score_note(note_path, tokens)` | `float` | Score note by title/body/tag matches |
| `format_search_results(results)` | `str` | Pretty-print search results |

## `SearchResult`

| Attribute | Type | Description |
|-----------|------|-------------|
| `path` | `Path` | Note file path |
| `title` | `str` | Note title |
| `score` | `float` | Relevance score |
| `snippet` | `str` | Context window around match |
