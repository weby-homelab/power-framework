# P.O.W.E.R. Framework — Agent Instructions

Python 3.11+ toolkit for AI-native Second Brain management. CLI (`power`, 26 top-level
commands) + local MCP server (20 tools).

## Project Structure

```
src/power_framework/       # Core library
  core/                    #   models, parser, indexer, linter, searcher, application service
  mcp/                     #   official MCP SDK v2 server (20 async tools)
tests/                     # Pytest suite; CI enforces coverage >=70%
scripts/                   # Dev/CI utilities
docs/                      # MkDocs-material documentation site
skills/                    # MCP skill definitions
```

## Development Commands

```bash
pip install -e ".[dev]"   # Editable install with dev deps
pytest tests/ -v           # Run tests (coverage >=70%)
ruff check src tests scripts  # Lint
ruff format --check .      # Format check (line-length 100)
mypy src/power_framework   # Type check (strict mode)
pre-commit run --all-files # Git hooks (ruff + mypy + pip-audit)
```

## Coding Conventions

- **Types**: Strict Pydantic v2 models for all API/data boundaries (`core/models.py`)
- **Style**: Ruff (select E/F/W/I/N/UP/B/A/SIM/TCH/S/C4/DTZ/T20/PT/RUF/PERF/RET/LOG/FIX), line-length 100, 4-space indent, `snake_case`
- **Validation**: `pydantic.Field` with `description` and governance fields (`owner`, `status`, `expiry`, `related`)
- **Concurrency**: `ThreadPoolExecutor` with strict 50% CPU cap: `max_workers = max(1, (os.cpu_count() or 4) // 2)` (never raw threads or unbounded pools)
- **Commits**: GPG-signed (`git commit -S`), conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`)

## Architecture

| Module                | Purpose                                                |
| --------------------- | ------------------------------------------------------ |
| `core/models.py`      | Pydantic v2 OKF schemas + Graph RAG fields             |
| `core/parser.py`      | Safe YAML frontmatter parsing                          |
| `core/indexer.py`     | Recursive bounded catalog generation (index.md + _index*.md) |
| `core/linter.py`      | Health checks: links, metadata, orphans, stale/expired |
| `core/searcher.py`    | FTS5/dense/hybrid/reranked search (`auto` default; labelled FTS fallback) |
| `experimental/embeddings.py` | Optional BGE-M3 ONNX (1024d) + MiniLM fallback       |
| `mcp/power_server.py` | official MCP SDK v2, 20 async tools, stdio/loopback HTTP + /health |

## Workflow

1. Branch from `main`: `feature/name` or `fix/name`
2. Implement with tests (regression coverage required)
3. Run full gate: `ruff check . && mypy src && pytest tests/ -v`
4. GPG-signed commit, push, open PR
5. CI must pass (tests, ruff, mypy, CodeQL, coverage >=70%)
6. Squash-merge after review

## Key Dependencies

- Base: `pydantic>=2.0`, `pyyaml>=6.0`, `pathspec>=0.12`, `defusedxml>=0.7.1` — offline FTS/core path
- `semantic` extra: `onnxruntime`, `tokenizers`, `huggingface-hub`, and `numpy`
- `rerank` extra: `fastembed` and its explicit neural runtime dependencies
- `mcp`/`remote`: `mcp>=2.0,<3.0` — official local MCP server/client SDK

## Skills (on-demand)

- `holistic-analysis` — Codebase analysis + step-by-step verification protocol
- `cleanup-branches` — Remove merged git branches
- `power` — Vault maintenance workflow (lint, index, heal, search, archive)

The canonical search default is `auto`: verified dense only when the local
generation/provider is ready, otherwise an explicit FTS result with fallback
metadata. Detailed dev guide: `CONTRIBUTING.md` | Full docs: `docs/` | CI:
`.github/workflows/`
