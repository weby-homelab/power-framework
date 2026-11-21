# Searcher

Full-text search with relevance scoring using SQLite FTS5 (with memory fallback).

| Function                                            | Returns              | Description                                                                                                                                                                                                                                                                                                                                                          |
| --------------------------------------------------- | -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `search_vault(vault_dir, query, max_results, mode)` | `list[SearchResult]` | Search the vault with `auto` (default; verified dense when ready, otherwise labelled FTS), `fts` (BM25 FTS5), `vector` (TF-vector cosine), `hybrid` (RRF of FTS + TF-vector), `semantic` (explicit BGE-M3 dense cosine), `reranked` (explicit opt-in: RRF of FTS + TF-vector + dense candidates, then BGE ONNX cross-encoder), or `graph_assisted` (sparse RRF expanded through validated OKF relations). Explicit dense-required modes fail closed unless the caller explicitly allows the labelled FTS fallback. |
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
| `actual_mode` | `str or None` | Mode actually used after profile resolution |
| `fallback_reason` | `str or None` | Stable reason when a profile falls back |
| `index_age_seconds` | `float or None` | Request-time age of the verified index path |
| `index_kind` | `str or None` | Verified request index: `immutable_generation` or `legacy_db` |
| `index_generation_id` | `str or None` | Immutable generation identifier when `index_kind` is `immutable_generation` |
| `index_source_snapshot_hash` | `str or None` | Content-free source snapshot hash for the verified immutable generation |

## Retrieval contract

The executable registry is `SEARCH_MODE_REGISTRY` in `core/searcher.py` and
the generated reference table is in [Architecture](../architecture.md). The
deprecated `hybrid_reranked` input alias normalizes to `reranked`; it is not a
canonical mode. The current default is `auto`, not `reranked`.

## Index freshness

The retrieval envelope and server discovery report the age of the selected
index file at request time. `index_freshness` uses seconds since its last
modification:

| Age | `index_freshness` |
| --- | --- |
| Less than 1 hour | `fresh` |
| At least 1 hour and less than 24 hours | `stale` |
| At least 24 hours | `critical` |
| No available age (e.g. an unindexed scan) | `unknown` |

On `critical`, the retrieval envelope sets `index_freshness_warning` to
`index_critically_stale`, even when the query returned no hits. Otherwise the
warning is `null`. Agents should flag critically stale evidence to the user
and verify the current source before relying on it. Do not run a sync
implicitly; request authorization if a rebuild is needed. Age is not proof
that sources have or have not changed, does not change result ranking, and
does not override the index integrity checks.

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
