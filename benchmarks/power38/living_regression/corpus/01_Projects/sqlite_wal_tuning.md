---
type: Project
title: "SQLite WAL and FTS5 Tuning"
description: "Read-only URI connections, WAL journaling, busy_timeout, and unicode61 BM25 search"
tags: [sqlite, wal, fts5, bm25, performance]
timestamp: 2026-10-05T10:00:00
---

# SQLite WAL and FTS5 Tuning

The generation index opens SQLite with `PRAGMA journal_mode=WAL`, `PRAGMA busy_timeout=30000`, `mmap_size`, and an FTS5 virtual table using the `unicode61` tokenizer.
Query-side callers open `file:<db>?mode=ro` read-only URIs so concurrent readers never block or write to disk.
