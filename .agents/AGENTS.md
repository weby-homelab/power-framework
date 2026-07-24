# P.O.W.E.R. Framework — Agent Instructions

Python 3.10+ toolkit for AI-native Second Brain management. CLI (`power`) + MCP server (12 tools).

## Project Structure

```
src/power_framework/       # Core library
  core/                    #   models, parser, indexer, linter, searcher, embedder
  mcp/                     #   FastMCP-3.x server (12 async tools)
tests/                     # Pytest suite (270+, 81%+ coverage)
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
- **Concurrency**: `ThreadPoolExecutor` (never raw threads)
- **Commits**: GPG-signed (`git commit -S`), conventional commits (`feat:`, `fix:`, `docs:`, `test:`, `chore:`)

## Architecture

| Module                | Purpose                                                |
| --------------------- | ------------------------------------------------------ |
| `core/models.py`      | Pydantic v2 OKF schemas + Graph RAG fields             |
| `core/parser.py`      | Safe YAML frontmatter parsing                          |
| `core/indexer.py`     | Hierarchical index generation (index.md + _index.md)   |
| `core/linter.py`      | Health checks: links, metadata, orphans, stale/expired |
| `core/searcher.py`    | FTS5/Vector/Hybrid search (3 modes)                    |
| `core/embeddings.py`  | BGE-M3 ONNX (1024d) + MiniLM fallback                  |
| `mcp/power_server.py` | FastMCP 3.x, 12 async tools, HTTP transport + /health  |

## Workflow

1. Branch from `main`: `feature/name` or `fix/name`
2. Implement with tests (regression coverage required)
3. Run full gate: `ruff check . && mypy src && pytest tests/ -v`
4. GPG-signed commit, push, open PR
5. CI must pass (tests, ruff, mypy, CodeQL, coverage >=70%)
6. Squash-merge after review

## Key Dependencies

- `fastmcp>=3.2` — MCP server framework
- `pydantic>=2.0` — Schema validation
- `onnxruntime>=1.17` + `tokenizers>=0.15` — BGE-M3 embeddings
- `fastembed>=0.5` — Cross-encoder reranker
- `pyyaml>=6.0` — Frontmatter parsing
- `pathspec>=0.12` — .gitignore-style exclusion

## Skills (on-demand)

- `holistic-analysis` — Codebase analysis + step-by-step verification protocol
- `cleanup-branches` — Remove merged git branches
- `power` — Vault maintenance workflow (lint, index, heal, search, archive)

Detailed dev guide: `CONTRIBUTING.md` | Full docs: `docs/` | CI: `.github/workflows/`