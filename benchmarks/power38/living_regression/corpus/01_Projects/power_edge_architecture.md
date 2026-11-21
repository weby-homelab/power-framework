---
type: Project
title: "POWER Edge Architecture Overview"
description: "Overview of POWER 3.8 edge retrieval, SQLite immutable generation index, and ContextPack compilation"
tags: [power, edge, architecture, context-pack]
timestamp: 2026-10-01T10:00:00
---

# POWER Edge Architecture

POWER 3.8 uses an immutable SQLite generation index paired with deterministic `ContextPack` compilation.
Notes stored in PARA folders provide context excerpts, while canonical project state, decisions, and tasks remain owned by server-verified ledgers (`ProjectStateService`, `DecisionService`, `TaskService`).
