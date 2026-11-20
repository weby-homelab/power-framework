---
type: Project
title: "Incremental Dense Dirty-Set Design"
description: "Phase 5F design for dirty-set chunk re-embedding and generation reconciliation"
tags: [phase5f, incremental, dense, chunks, hot-warm-cold]
timestamp: 2026-10-02T10:00:00
---

# Incremental Dense Validity

Instead of triggering a full rebuild when one note changes, `generation_reconcile.py` and `index_write.py` compute the dirty-set of modified chunks.
Only altered chunk hashes are re-embedded (`reembed_amplification` near 1.0), preserving unchanged `HOT`, `WARM`, and `COLD` vectors cleanly without silent fallback.
