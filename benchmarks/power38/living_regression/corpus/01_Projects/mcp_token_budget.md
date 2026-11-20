---
type: Project
title: "MCP Lean Surface and Token Budget"
description: "Paginated read_note, compact get_server_info, and bounded MCP context tools"
tags: [mcp, phase5g, tokens, pagination]
timestamp: 2026-10-03T10:00:00
---

# Lean MCP Token Economy

Issue #474 and Phase 5G introduce compact `get_server_info`, cursor-paginated `read_note`, and typed `compile_context` / `explain_context` endpoints.
Bounded excerpts reduce redundant context tokens for autonomous coding agents while enforcing strict `query_side_writes == 0`.
