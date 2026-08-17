# P.O.W.E.R. 3.6.1 release notes

P.O.W.E.R. 3.6.1 introduces the **Strict 50% CPU Throttling Mandate & Concurrency Guard**, ensuring that P.O.W.E.R. operations (indexing, embeddings, FastMCP, rot scoring, and native inference) never exceed 50% of available host CPU capacity.

## What changed

- **Strict 50% CPU Throttling Helper (`power_framework.core.utils`)**:
  - Implemented `get_cpu_worker_limit()` and `enforce_cpu_throttling_env()`.
  - Math formula: `max(1, (os.cpu_count() or 4) // 2)`.
- **Automatic Environment Throttling**:
  - Sets and clamps `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, `MKL_NUM_THREADS`, `VECLIB_MAXIMUM_THREADS`, `NUMEXPR_NUM_THREADS`, and `POWER_EMBED_NUM_THREADS` on package import, CLI startup, and FastMCP server initialization.
- **Inference & Concurrency Guards**:
  - Clamped ONNX Runtime `intra_op_num_threads` in `BGEM3OnnxManager` and `BGERerankerOnnxManager` to `get_cpu_worker_limit()`.
  - Updated `LinkRotChecker` to use `get_cpu_worker_limit()` in its `ThreadPoolExecutor`.
  - Bounded `fastembed` parallel worker counts to `get_cpu_worker_limit()`.
- **Test Suite**:
  - Added dedicated unit tests in `tests/test_cpu_throttling.py` verifying CPU scaling, thread clamping, environment variable enforcement, and worker bounds.

## Platform boundary

Linux remains the primary release platform for `v3.6.1`. The public inventory of 24 CLI commands and 20 MCP tools remains fully stable and unchanged.

## Release gates

```bash
uv sync --locked --group dev --extra semantic --extra rerank
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src/power_framework
pytest tests/ -v
```
