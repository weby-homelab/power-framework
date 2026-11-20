---
type: Project
title: "CI Quality and Security Gates"
description: "Required checks: ruff lint and format, mypy strict, pytest coverage >= 70, CodeQL"
tags: [ci, quality, ruff, mypy, pytest, codeql]
timestamp: 2026-10-04T10:00:00
---

# CI Quality Gates

Every PR targeting `main` must pass `ruff check`, `ruff format --check`, `mypy src/power_framework/` in strict mode, `pytest` with at least 70 percent coverage, `complexity_dashboard.py`, `mkdocs build --strict`, and `CodeQL` scanning.
