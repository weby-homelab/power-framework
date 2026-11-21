---
type: Resource
title: "Hybrid RRF and Semantic Guard Notes"
description: "Combining Reciprocal Rank Fusion with dense cosine similarity and BM25 lexical guards"
tags: [hybrid, rrf, semantic, bm25, cosine]
timestamp: 2026-10-13T10:00:00
---

# Hybrid RRF and Lexical Guard

Reciprocal Rank Fusion (RRF) merges BM25 lexical ranks with dense cosine similarity vectors, while a bounded semantic lexical guard resolves ambiguous top-1 ties without degrading exact symbol lookup.
