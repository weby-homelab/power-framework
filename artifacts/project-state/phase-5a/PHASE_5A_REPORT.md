# POWER 3.8
# PHASE 5A — RUNTIME CONTRACTS V2
# & FROZEN RETRIEVAL EVALUATION CORPUS
# ADMISSION REPORT

## Executive result

```text
PHASE_5A = ADMISSION CANDIDATE / IMPLEMENTED / LOCALLY VERIFIED
PROTECTED_MERGE = PENDING
PHASE_5B = BLOCKED / NOT STARTED
```

This report is candidate evidence. Live GitHub, protected checks, exact-head
review, normal merge, and post-merge readback remain authoritative for closure.

## Base and candidate

```text
REPOSITORY: https://github.com/weby-homelab/power-framework
BRANCH: feat/power-3.8-phase5a-runtime-contracts
BASE_SHA: 9f732b1160f58e7ced88ebaa2fd52dd7c82da428
BASE_TREE: 52aa98950b4c2f371b8f63f906deec16d31c2e48
BASE_PARENTS: 95f8cadd7e90ef4b16773b3c45bbc9ab40569e7a 96f0b1cc0e1fc85e0921c9518761683266e3f9ae
FINAL_CANDIDATE_HEAD: RESOLVE_FROM_GITHUB
FINAL_CANDIDATE_TREE: RESOLVE_FROM_GITHUB
FINAL_CANDIDATE_PARENTS: RESOLVE_FROM_GITHUB
FINAL_CANDIDATE_GPG: RESOLVE_FROM_GITHUB
```

The protected Foundation closure was independently revalidated before work:
PR #414 is closed/merged, final head `96f0b1cc0e1fc85e0921c9518761683266e3f9ae`,
merge/main `9f732b1160f58e7ced88ebaa2fd52dd7c82da428`, tree
`52aa98950b4c2f371b8f63f906deec16d31c2e48`, GitHub verification
`verified=true / reason=valid`, and post-merge CI/Docs/CodeQL passed.

## Runtime contract matrix

| Planning contract | Runtime type | Validation | Deferred behavior |
|---|---|---|---|
| `QueryIntent` | `QueryIntent` | strict bounded text, closed intent/budget, explicit omission policy | 5B intent/routing |
| `RetrievalBudget` | `RetrievalBudget` | structural caps, class flags, closed stages | 5B–5E policy |
| `SearchScope` | `SearchScope` | bounded domains/paths/types/trust/temporal/project fields | 5C pushdown |
| `DomainMatch` | `DomainMatch` | finite confidence and bounded reasons | 5B router |
| `RetrievalStage` | `RetrievalStage` | closed enum/scalar discriminator | 5B–5D |
| `RetrievalPlan` | `RetrievalPlan` | complete attempted/skipped partition and stage/flag compatibility | 5D planner |
| `NoiseAssessment` | `NoiseAssessment` | quarantine/source-preserved invariant | 5D noise gate |
| `ContextItem` | `ContextItem` | trust↔authority matrix, domain orthogonality, provenance/redaction/cost | 5D pack |
| `ContextPack` | `ContextPack` | server-issued access, aggregate token/byte/candidate bounds, read-only index flag | 5D compiler |
| `IndexWorkItem` | `IndexWorkItem` | DTO-only queue state/lease/retry bounds | Phase 6 queue |
| `IndexCostEstimate` | `IndexCostEstimate` | non-negative bounded cost evidence | 5F/6 |
| `MemoryDisposition` | `MemoryDisposition` | closed disposition enum | Phase 6 policy |
| `MemoryAction` | `MemoryActionDecision` | private server issuer, no caller/bearer authority | governed future policy |
| v2 retention/sensitivity | `RetentionClass`, `SensitivityClass`, policy DTOs | closed enums and non-destructive retention rules | Phase 6 |
| v2 tombstone | `TombstoneReceipt` | explicit tombstone/deletion semantics, digests, aware timestamps | Phase 6 |
| v2 bitemporal | `BitemporalEvidence` | UTC-aware timestamps and ordered validity interval | 5C/6 |
| v2 ordering | `EvidenceOrderingPolicy` | exact explainable stage/rank order; no score collapse | 5D/5E |
| v2 resources | `ResourceProfile`, `HostCapabilityProfile` | abstract host-neutral classes and bounded refs | 5E deployment evidence |
| v2 budget | `RetrievalBudgetPolicy` + pure resolver | structural/resource/domain/caller-lower-only min composition | 5E calibration |
| v2 retries | `RetryPolicy` | bounded retry/backoff/dead-letter/review semantics; no worker | Phase 6 |
| evaluation manifest | `EvaluationCorpusManifest` | frozen digests, coverage, provenance, split and no-tuning policy | 5E quality gate |

Full mapping evidence: `artifacts/project-state/phase-5a/runtime-contract-mapping.md`.

Runtime identity: `power.context-runtime.v2`. Planning fields
`planning_only`, `implementation_status`, and `phase_status` are not mandatory
runtime request fields. Planning JSON/Markdown files are not imported or read
for production behavior.

## Serialization and digest

```text
format: compact UTF-8 JSON, sorted object keys, no NaN/Infinity
datetime: aware only; UTC normalization; canonical Z form; fixed microseconds
optional fields: omitted when None; explicit null rejected
enums: stable enum values
digest: SHA-256(canonical serialized bytes), lowercase 64-hex
```

Runtime contract tests prove dictionary-order and timezone equivalence,
cross-process deterministic bytes, finite-float rejection, and no model/network
import or filesystem side effect.

## Frozen corpus

```text
LOCATION: benchmarks/power38/retrieval_eval/v1/
SOURCE_FIXTURES: 20 synthetic Markdown files
DEVELOPMENT_QUERIES: 20
HOLDOUT_QUERIES: 20
LANGUAGES: UA / EN / MIXED_UA_EN in both splits
GROUND_TRUTH: separate development and holdout JSONL files
```

```text
DATASET_DIGEST: 179ac7ee8d2e8ec0d5e0924cb322d32783da8ae1fdff379ecb0bfa7e0afc53b0
SOURCE_CORPUS_DIGEST: 3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118
QUERY_SET_DIGEST: 7e2c0aaf8e0b3940bfa97c949781ade43fc4d67709634f2fcf3f08016fe1b086
DEVELOPMENT_DIGEST: 29b4ff596a2a125cfb2a3be54a17570cc10a88051bf5b379d5e2472c481e9289
HOLDOUT_DIGEST: ef6f122eefe9f4482d016a05a35422e11f0b120be2a64ad08d7ce661bad6721a
DISJOINTNESS_DIGEST: 554ca3a962beb09c2f7e9afe0bebea19ca79b62d77378959082ab1cfc5ad4275
```

The verifier pins the admitted digest identity in versioned code, checks the
exact Markdown inventory, UTF-8/frontmatter shape, sidecar bytes, split IDs,
scenario families, normalized query text, category/language coverage, semantic
ground truth, and holdout receipt. It is offline, model-free, network-free,
and fails closed.

## Holdout integrity

```text
SEALED: YES — immutable/content-addressed/governed after admission
CONFIDENTIAL: NO — public repository readers can inspect it
TUNING_ON_HOLDOUT: REJECTED
INTEGRITY_READ: ALLOWED ONLY AS SEPARATE RECEIPTED OPERATION
SHARED_SOURCE_CORPUS: ALLOWED / READ-ONLY
QUERY_ID_INTERSECTION: 0
SCENARIO_FAMILY_INTERSECTION: 0
NORMALIZED_EXACT_QUERY_OVERLAP: 0
```

The official integrity command can emit a bounded receipt outside the frozen
directory:

```bash
uv run --offline python scripts/verify_retrieval_eval.py \
  benchmarks/power38/retrieval_eval/v1 \
  --receipt-out /tmp/power38-holdout-integrity-receipt.json
```

No raw query/source text is written to the receipt. No claim of cryptographic
confidentiality or arbitrary manual-read auditing is made.

## Verification results

| Gate | Result |
|---|---:|
| Phase 5A targeted contracts + corpus | `55 passed` |
| Evaluation verifier | `PASS` |
| Foundation F1–F5/Web/MCP targeted slice | `91 passed` |
| PSE/Task/Decision/crash targeted slice | `177 passed` |
| Retrieval/security targeted slice | `88 passed` |
| Phase 1/package/release targeted slice | `28 passed` |
| Benchmark integrity | `114 passed, 1 skipped` |
| Upgrade matrix | `PASS` |
| Full hermetic suite | `1868 passed, 4 skipped, 17 deselected` |
| Coverage | `83.34%` (threshold 70%) |
| Ruff / format / MyPy | `PASS` |
| `uv lock --check`, locked sync, pip check | `PASS` |
| Doc drift / strict MkDocs | `PASS` (existing non-fatal nav/deprecation warnings) |
| pip-audit | `PASS` (local package not auditable on PyPI) |
| wheel + sdist package smoke | `PASS` |

Full tests emitted five non-fatal existing warnings: Starlette deprecation,
fastembed warning, and three existing Pydantic serializer warnings. No test,
resource-warning, or unraisable-exception gate failed.

## Candidate epochs

| Epoch | Head | Tree | Parent | Reason | Local result |
|---|---|---|---|---|---|
| 0 | `9f732b1…` | `52aa989…` | Foundation merge parents | fresh protected main base | PASS |
| 1 | `ddd40dc…` | `99e81e8…` | `9f732b1…` | typed runtime contract layer | 31 targeted passed |
| 2 | `744d68b…` | `6ac4b27…` | `ddd40dc…` | frozen synthetic corpus/verifier | 43 targeted passed |
| 3 | `3d6c456…` | `4e487f5…` | `744d68b…` | governance mapping/state reconciliation | docs/lint clean |
| 4 | `b584df0…` | `6a3657d…` | `3d6c456…` | first adversarial repair: split GT/pinning/integrity | targeted/full gates passed |
| 5 | `3d7752e…` | `3ce28e8…` | `b584df0…` | issuer, aggregate bounds, flags, retry/source hardening | 55 targeted passed |
| 6 | `a1823ca…` | `15a947a…` | `3d7752e…` | report/handoff evidence epoch | local gates passed |
| 7 | `fec487d…` | `f4b776a…` | `7ec9403…` | CodeQL-clean registry and review hardening | exact-head remote CodeQL PASS |
| 8 | `RESOLVE_FROM_GITHUB` | `RESOLVE_FROM_GITHUB` | `fec487d…` | final evidence update | pending remote admission |

Every maintainer commit in these epochs is locally GPG-signed with primary
fingerprint `2D49E810C7F2527E`; GitHub verification remains a remote exact-head
gate.

## Review classifications

- CodeQL findings on historical head `a1823ca…` (undefined explicit export and
  static import cycle) were valid and repaired in `7ec9403…`; the new exact-head
  CodeQL run reported no new alerts.
- CodeRabbit comments claiming holdout q06/q11/q16 mismatched their queries
  were checked against exact query text and ground truth: q06 asks for current
  infrastructure policy, q11 asks for the current project rather than the
  distractor, and q16 asks for curated rather than unverified research. These
  three findings are non-actionable false classifications.
- Receipt snapshot accounting, RFC3339 grammar, and mutable ContextPack
  collection findings were valid and repaired in the subsequent candidate
  epoch. Optional bot docstring-coverage warnings are not repository gates.

## Explicit scope proof

```text
Domain router: NO
SearchScope pushdown: NO
RetrievalPlanner behavior: NO
ContextPackCompiler: NO
Dense/index behavior change: NO
MCP context tools: NO
Capture/session ingestion: NO
Vector database/ANN backend: NO
Model download/migration: NO
Network service: NO
Version/tag/release: NO
```

`ContextPack`, `RetrievalPlan`, and `IndexWorkItem` are typed DTOs only. No
retrieval quality claim is made in Phase 5A.

## Current admission state

```text
FOUNDATION_HARDENING: CLOSED / IMPLEMENTED / VERIFIED
PHASE_5A: ADMISSION CANDIDATE / LOCALLY VERIFIED
PHASE_5B: BLOCKED / NOT STARTED
POWER_3_8_0: NO-GO
ADMIN_BYPASS: NO
PROTECTION_BYPASS: NO
FORCE: NO
AUTO_MERGE: NO
```

Open gate: create one PR from the final exact branch head, enumerate live
required contexts/reviews/rulesets, obtain exact-head protected admission, make
one normal merge commit, read back `main`, and publish one bounded closure
comment. Then stop before Phase 5B.
