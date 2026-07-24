# P.O.W.E.R. Framework — Agent Instructions

Python 3.10+, hatchling, Pydantic v2, FastMCP 3.x, ONNX Runtime, BGE-M3.

## Commands

```bash
pip install -e ".[dev]"    # editable install
pytest tests/ -v           # run all tests
ruff check src/ tests/     # lint (no --fix unless reviewed)
ruff format src/ tests/    # format
mypy src/power_framework/  # type check
```

## Code Style

- ruff rules: E/F/W/I/N/UP/B/A/SIM/TCH/S/C4/DTZ/T20/PT/RUF/PERF/RET/LOG/FIX
- line-length: 100. Ignore: E501, S101.
- 4 spaces, no tabs. snake_case for functions/vars, PascalCase for classes.
- Type hints on all public signatures. Use `from __future__ import annotations` in new files.
- `async def` for all I/O-bound public APIs. Precept `async` over `ThreadPoolExecutor` thread-pool calls.
- Named exports only. No `from module import *`.
- // CORRECT
  async def fetch_vault(path: str, timeout: int = 30) -> dict[str, Any]:
      ...
  // WRONG
  def fetch_vault(path, timeout=30):
      ...
- Error handling: use Pydantic v2 validation at all public boundaries. Fail closed on missing credentials — raise early, not silently.
- Imports: stdlib → third-party → local. One blank line between groups.

## Architecture

```
src/power_framework/
├── core/          # CLI, models, parser, indexer, linter, searcher, embeddings, reranker
├── mcp/           # FastMCP 3.x server — 12 async tools
tests/             # pytest, asyncio_mode=auto, coverage >= 70%
scripts/           # utility scripts (excluded from ruff T20/S310)
```

Rules:
- `core/` must NOT import from `mcp/`. Data flows one direction: CLI/MCP → core.
- Never add `I/O` in hot paths (search, lint, index). Batch reads.
- Keep MCP tools stateless — vault state lives in the filesystem, not in memory.

## Testing

- Co-locate tests as `test_*.py` in `tests/`. Mirror `src/` structure.
- pytest addopts: `-v --tb=short --cov=power_framework --cov-report=term-missing --cov-fail-under=70`.
- Every new CLI command needs a test. Every new core function needs a unit test.
- Mark real-vault benchmarks with `@pytest.mark.bench` — never run in CI.

## Git

- GPG-sign all commits (key `2D49E810C7F2527E`, user `weby-homelab`).
- Conventional commits: `feat:`, `fix:`, `refactor:`, `test:`, `chore:`, `docs:`.
- Branch → PR → Merge (squash). No direct pushes to `main`.
- Clean up merged branches locally and on remote.

## Boundaries

- NEVER commit `.env`, secrets, tokens, private keys, result JSON, or deployment credentials.
- NEVER modify `CHANGELOG.md` manually — it is auto-generated during release.
- NEVER `glob **/*.md` on vault directories. Use `power index` + `read_sub_index` instead.
- NEVER add new dependencies without a review. If you must, update `pyproject.toml` and this file.
- DO NOT convert sync internal helpers to async unless they perform I/O. Keep pure computation synchronous.
- DO NOT use bare `except:`. Always catch specific exceptions.