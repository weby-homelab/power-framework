---
type: Resource
title: "Python Worktree PYTHONPATH Pitfalls"
description: "Isolated editable installs, PYTHONPATH overrides across git worktrees, and offline HF testing"
tags: [python, worktree, venv, pythonpath, testing]
timestamp: 2026-10-14T10:00:00
---

# Python Worktree Pitfalls

When running tests in secondary git worktrees, shared editable virtualenvs (`docs-venv`) point back to the primary checkout.
Export `PYTHONPATH="$PWD/src:$PWD"` with `HF_HUB_OFFLINE=1` so pytest exercises the worktree code in complete isolation.
