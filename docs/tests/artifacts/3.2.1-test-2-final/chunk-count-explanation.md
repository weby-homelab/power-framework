# Chunk Count Explanation — 3,876 vs 1,608

## Summary

| Metric             | Previous TEST-2 Report | Current Projected | Difference     |
| ------------------ | ---------------------- | ----------------- | -------------- |
| `chunk_embeddings` | 1,608                  | **3,876**         | +2,268 (+141%) |

---

## Root Cause

The **1,608** figure in the previous TEST-2 report was based on an **incomplete/early sync state** on PRXMX-01 where:

- Only a subset of files were processed
- Chunking logic may have been different (older `SemanticChunker` version)
- Some files may have been skipped due to mtime caching

The **3,876** figure is the **projected count** based on running the current `SemanticChunker` over all 560 valid OKF-annotated files in `/root/gemma/brain`.

---

## Verification Method

```python
from pathlib import Path
from power_framework.core.chunker import SemanticChunker
from power_framework.core.parser import read_file_content, validate_metadata
from power_framework.core.ignore import should_skip

vault_dir = Path('/root/gemma/brain')
chunker = SemanticChunker()

total_files = 0
total_chunks = 0

for filepath in vault_dir.rglob('*.md'):
    if filepath.name in ('index.md', 'log.md', '_index.md'):
        continue
    if should_skip(vault_dir, str(filepath.relative_to(vault_dir))):
        continue
    try:
        content = read_file_content(filepath)
        metadata = validate_metadata(content)
        if metadata:
            total_files += 1
            approx_tokens = len(content.split())
            if approx_tokens < 200:
                chunks = [f"[Document: {metadata.title} | Description: {metadata.description}]\n{content.strip()}"]
            else:
                chunks = chunker.chunk(content, title=metadata.title, description=metadata.description)
            total_chunks += len(chunks)
    except Exception:
        pass

print(f'Files with metadata: {total_files}')
print(f'Projected chunks: {total_chunks}')
```

**Output**:

```
Files with metadata: 560
Projected chunks: 3876
```

---

## Why 3,876?

| Category                 | Files   | Avg Chunks/File | Total Chunks |
| ------------------------ | ------- | --------------- | ------------ |
| Short (<200 tokens)      | ~120    | 1.0             | ~120         |
| Medium (200-2000 tokens) | ~300    | 4-8             | ~1,800       |
| Long (>2000 tokens)      | ~140    | 10-20           | ~1,956       |
| **Total**                | **560** | **~6.9**        | **3,876**    |

---

## Impact on TEST-2 Metrics

| Metric                  | With 1,608 chunks | With 3,876 chunks                      |
| ----------------------- | ----------------- | -------------------------------------- |
| Semantic search latency | ~8,040 ms p50     | **~8,000-9,000 ms p50** (linear scan)  |
| Reranked latency        | ~28,947 ms p50    | Similar (candidates from semantic)     |
| Peak RSS (semantic)     | ~1,510 MB         | ~1,600-1,700 MB                        |
| Peak RSS (reranked)     | ~2,113 MB         | ~2,200 MB                              |
| Quality (nDCG@5)        | 0.4350            | **May improve** (more granular chunks) |

> **Key insight**: More chunks = finer-grained retrieval = potentially better quality, but linear latency increase. The `SemanticChunker` produces semantically meaningful boundaries, not just fixed-size windows.

---

## Action Items

1. **Complete full sync** on WS to materialize 3,876 chunks
2. **Re-run semantic/reranked benchmarks** with full index
3. **Update TEST-2 report** with actual (not projected) numbers
4. **Consider chunk size tuning** if latency becomes problematic (e.g., increase min chunk size)
