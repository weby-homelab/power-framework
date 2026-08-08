# Windows 11 25H2 validation

Validation date: 2026-08-08  
Validation target: physical Windows 11 Home 25H2, OS build `26200.8973`, x64  
Python: CPython `3.13.14`  
P.O.W.E.R. version: `3.3.2`  
Source revision: `4e5b2b9`

This report records the Windows portability validation for the follow-up source
revision. It is intentionally limited to reproducible results and contains no
machine-specific paths, addresses, credentials, or private configuration.

## Results

| Gate | Result |
| --- | --- |
| Full test suite with coverage and warnings-as-errors | `739 passed, 21 skipped`; coverage `78.21%` |
| Ruff format and lint | Passed |
| MyPy | Passed; 39 source files checked |
| Documentation drift | Passed |
| Release contract | Passed |
| Markdown checks | Passed; 0 issues |
| Wheel and sdist package smoke | Passed; 16 queries |
| Clean vault: init, ingest, strict index, lint, Markdown, FTS, status | Passed |
| Dense semantic search | Passed |
| Reranked search | Passed |
| MCP preflight | Passed |

## Reproduction record

The following gates were executed on the validation host; each command returned
exit code `0`:

```text
uv run ruff check src tests scripts
uv run ruff format --check src tests scripts
uv run mypy src/power_framework
uv run python scripts/check_doc_drift.py
uv run python scripts/verify_release_contract.py
uv run power markdown-check docs
uv run pytest tests/ -v --tb=short --cov=src/power_framework/ --cov-report=term-missing --cov-fail-under=70 -W error
uv run python -m build --sdist --wheel
uv run python scripts/smoke_package.py --wheel <wheel> --sdist <sdist>
```

The full test suite elapsed time was `79.20s`; its exit code was `0`. The
clean-vault, FTS, dense, reranked, and MCP acceptance commands also returned
exit code `0`.

## Warning classification

- No warning was accepted as a product failure or left unclassified.
- The 21 skipped tests were classified as: 5 optional neural-benchmark cases
  requiring an explicit benchmark flag or real brain vault; 11 optional
  reranker-cache cases; 1 real-brain-vault quality case; and 4 Windows symlink
  cases requiring `SeCreateSymbolicLinkPrivilege`.
- Windows symlink-privilege and model-cache symlink messages were classified as
  host capability/cache warnings; model-backed acceptance completed with the
  pinned CPU runtime.
- MkDocs reported existing historical pages outside `nav`; this was a
  non-blocking documentation warning and the strict build still returned exit
  code `0`.

The dense and reranked checks used the pinned model contract and CPU runtime.
The FTS checks were also run independently of model-backed retrieval.

## Scope boundary

This is a source and build validation record for revision `4e5b2b9`. The
immutable public `v3.3.2` release tag and artifacts are not moved, replaced, or
reissued by this change. The report does not claim certification for an
unchanged artifact that was not rebuilt from this revision.

The Microsoft Visual C++ runtime was present on the validation host. CUDA was
not required because the acceptance run used the CPU ONNX Runtime backend.

## Post-merge read-back

- PR #231 merged by squash as `11e2248`.
- `main` and `origin/main` matched at the read-back.
- Post-merge CI, Docs, and CodeQL runs for `11e2248` completed successfully.
- Public GitHub Pages returned HTTP `200` and exposed the Windows 11 25H2
  validation navigation.
- Issue #232 was closed automatically by `Closes #232`.
