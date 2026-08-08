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

The dense and reranked checks used the pinned model contract and CPU runtime.
The FTS checks were also run independently of model-backed retrieval.

## Scope boundary

This is a source and build validation record for revision `4e5b2b9`. The
immutable public `v3.3.2` release tag and artifacts are not moved, replaced, or
reissued by this change. The report does not claim certification for an
unchanged artifact that was not rebuilt from this revision.

The Microsoft Visual C++ runtime was present on the validation host. CUDA was
not required because the acceptance run used the CPU ONNX Runtime backend.
