# POWER 3.8 Stale Dependabot PR Cleanup & Dependency Refresh Ledger

Baseline Main Commit: `d14a851e459eb5166d25df5764c3304bcd8c30e2`
Recorded: 2026-09-04T23:22:00+03:00

| PR | Package | Version | Classification | Merge Base | Disposition |
|:---|:---|:---|:---|:---|:---|
| #389 | `filelock` | 3.32.5 | Ordinary Maintenance | `af2e302` | Close stale PR; re-evaluate in controlled dependency refresh on current main. |
| #390 | `pygments` | 2.21.0 | Ordinary Maintenance | `af2e302` | Close stale PR; re-evaluate in controlled dependency refresh on current main. |
| #391 | `mcp` | 2.1.1 | Compatibility Relevant | `af2e302` | Re-evaluate against the final Phase-5 Context/MCP implementation. Must pass full stdio/client compatibility suite. |
| #392 | `numpy` | 2.5.2 | Compatibility Relevant | `af2e302` | Do not automatically widen upper boundary. Requires semantic, rerank, ONNX runtime, Profile B, lock reproducibility, and performance tests. |
| #393 | `huggingface-hub` | 1.29.0 | **SECURITY RELEVANT** | `af2e302` | **MANDATORY SECURITY RE-EVALUATION BEFORE v3.8.0**. Contains security-relevant upstream fixes. |
