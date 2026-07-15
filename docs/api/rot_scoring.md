# ROT Scoring

Track A2 scoring: content deduplication (via dense embeddings), semantic contradiction detection, freshness monitoring, link rot detection, and usage tracking.

| Class / Function | Description |
|------------------|-------------|
| `ContentDedupDetector` | Dense embedding cosine similarity for body content |
| `ContradictionDetector` | Semantic contradiction check for similar notes (LLM/Metadata) |
| `FreshnessScorer` | Type-based exponential decay freshness scoring |
| `LinkRotChecker` | HTTP HEAD checks for external URL health |
| `UsageTracker` | SQLite-based access counter (thread-safe) |

## `ContentDedupDetector`

```python
detector = ContentDedupDetector(threshold=0.75)
pairs: list[tuple[str, str, float]] = detector.detect(vault_dir)
```

- Uses dense embedding cosine similarity (via `EmbeddingManager` with `BAAI/bge-m3`)
- Threshold defaults to `0.75` — pairs below threshold are not reported
- Skips notes with body length less than 50 characters
- Returns sorted list of `(path_a, path_b, similarity_score)`

## `ContradictionDetector`

```python
detector = ContradictionDetector(similarity_threshold=0.7, api_key=None)
contradicting: list[tuple[str, str, str]] = detector.detect(vault_dir)
```

- Find semantically similar note pairs that may contain contradictory facts, instructions, or statements
- Identifies similar notes using dense embedding similarity (threshold: `0.7`)
- Checks for factual contradictions using a Local LLM (OpenCode) or OpenRouter API. If no API key or local model is configured, falls back to comparing metadata fields (`status`, `owner`, `expiry`, `priority`)
- Returns a list of tuples: `(path_a, path_b, reason_for_contradiction)`

## `FreshnessScorer`

```python
scorer = FreshnessScorer()
scores: dict[str, float] = scorer.score_all(vault_dir)
```

- Scores each note `0.0` (stale) to `1.0` (fresh)
- Uses exponential decay: `score = 2^(-age_days / half_life_days)`
- Half-life depends on note type:

| Type | Half-life |
|------|-----------|
| Daily Log | 30 days |
| Project | 180 days |
| Area | 365 days |
| Resource | 365 days |
| System Guide | 365 days |
| Archive | 730 days |

## `LinkRotChecker`

```python
checker = LinkRotChecker(timeout=5)
broken: dict[str, list[tuple[str, int]]] = checker.check_all(vault_dir)
```

- Performs HTTP HEAD requests on external markdown links
- Returns dict mapping `rel_path` → `[(url, status_code)]` for broken links only (status >= 400 or connection error)
- Connection error returns status `-1`

## `UsageTracker`

```python
tracker = UsageTracker(vault_dir)
tracker.track_access("01_Projects/note.md")
count = tracker.get_count("01_Projects/note.md")
all_counts: dict[str, int] = tracker.get_all_counts()
```

- Thread-safe SQLite storage (`.power_usage.db` in vault root)
- `track_access()` upserts with increment
- `get_all_counts()` returns dict of `rel_path → access_count`
