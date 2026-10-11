# EmbeddingGemma 2 Integration Plan — 2026-10-11

## Status and source identity

| Field | Value |
|---|---|
| Status | `PROPOSED / NOT CANONICAL / NOT IMPLEMENTED` |
| Source main | `aa295a4073ba4c0fff0e45721610a4bcdb5489c8` |
| Source tree | `a25c80d6b5a77c4d36ec8373032d1e91ccdb36ac` |
| Audit evidence path | `artifacts/project-state/evidence/2026-10-11_embeddinggemma2_EG2-00_audit.md` |
| Proposed decision | [ADR-0009](../adr/0009-embeddinggemma2-optional-text-retrieval.md) |

This plan is local preparation only. No code/runtime change, model acquisition,
evaluation-asset creation, official holdout, production vault mutation, default
change, package/lock update, version bump, tag, release, remote branch, or PR is
authorized by this artifact.

## Objective

Prepare a bounded, local, opt-in evaluation of text-only EmbeddingGemma 2 while
preserving BGE-M3 as the default, FTS-only base install, existing search and
generation contracts, canonical authority boundaries, deterministic scope, and
normal release/governance gates.

## Live position and governance boundary

Verified live main is the protected merge commit for PR #485. Public GitHub REST
reports the commit signature as `verified=true / reason=valid`. Phase 5E remains
`OPEN / NOT PASSED`; its fresh evaluation-authoring procedure is a separate
canonical invocation. Phase 5F remains `BLOCKED` behind Phase 5E and its own
admission. POWER 3.8.0 remains `NO-GO`.

The repository planning snapshot still contains pre-final wording that says the
post-#483 reconciliation is pending. Do not create a duplicate PR merely from
that stale wording. The live status and exact #485 evidence are recorded in the
EG2-00 audit. This proposed EmbeddingGemma sequence is not a canonical phase
reorder. Before EG2-02 changes runtime, an operator/governance decision must
resolve how the proposed correctness prerequisite relates to the currently
listed Phase 5E authoring gate.

## Verified facts, proposals, and unknowns

### Verified facts

- The Stage 3 semantic dispatch defect is present in the source tree: the
  planner sends `mode="vector"`, which is TF-vector, and reports
  `dense_used=True` after success.
- Existing positive-looking closure coverage mocks `mode="vector"`; the
  existing dense fallback test has no active generation. Neither proves a
  positive dense scorer call.
- The current default is BGE-M3. The base dependency list is FTS/core only; the
  existing `semantic` extra uses ONNX Runtime, tokenizers, the pinned Hub range,
  and NumPy. The lock has no SentenceTransformers, Transformers, or Ollama
  dependency.
- The current model lock contains no EmbeddingGemma 2 revision/file hashes.
- The current model manager, dense readiness, doctor probe, and capability
  manifest are BGE-focused. Existing dense generations store a short provider
  and model identity plus dimensions; a complete prompt/tokenizer/runtime
  descriptor is not present.
- The existing generation publisher provides immutable staged generations,
  integrity/hash checks, atomic pointer publication, and readback.
- The existing `commit_note_change` receipt already records the published
  search mode and generation. Do not add a second sync after a successful
  canonical mutation receipt.
- S-Book's current POWER policy is CPU-only for embeddings/indexing. The exact
  host snapshot, absent local neural runtime, and unavailable project test
  environment are recorded in the EG2-00 audit.

### Proposed direction

- Keep the initial scope text-only and local.
- Use the Google-published SentenceTransformers route as the reference PoC and
  the sole proposed production candidate. Do not admit an adapter until EG2-03
  proves dependency, artifact, security, text-only loading, numerical, and
  resource contracts. If proof fails, mark the backend `DEFERRED`; do not
  silently substitute Ollama or an unverified export.
- Compare only 768d and 256d in the first bounded development experiment.
- Reuse existing factories, model policy, searcher, SearchScope, SQLite
  generation, doctor/capability, and receipt surfaces. No parallel engine or
  public MCP tool is proposed.

### Unknowns / pending evidence

- Exact model revision, artifact file list/hashes/bytes, tokenizer digest, and
  license-file inventory for the actual pinned snapshot.
- Supported Python 3.13/3.14 dependency resolution against the current Hub pin
  and live dependency PRs #477/#486.
- Exact SentenceTransformers text-only loading constructor and version. The
  Google AI documentation endpoints were unavailable during EG2-00; the
  publisher's model card states that modality-loading details vary by library.
- Runtime session binding, exact CPU RSS/latency, model-fit headroom, and
  measured 768d/256d quality.
- Current protected branch rules, which were not publicly observable without
  authenticated REST.

## Proposed gate sequence

```text
EG2-02 — F-01 semantic dispatch correction
  → EG2-03 — isolated text-only reference PoC and backend admission
  → EG2-04 — one opt-in adapter plus isolated whole-generation migration
  → EG2-05 — preregistered development-only shadow comparison
```

This is a proposed EG2 track, not canonical roadmap authority. The current
canonical next gate remains Phase 5E fresh evaluation authoring. The recommended
next **EG2 experiment gate** is EG2-02 because a trustworthy semantic baseline
requires truthful dense execution. It may start only after an explicit
invocation and a governance decision resolving its ordering relative to Phase
5E. EG2-06 is the existing official Phase 5E procedure and requires its own
authoring/admission/execution gates; this plan does not start it.

## Gate EG2-02 — F-01 semantic dispatch correction

**Preconditions:** Explicitly admitted corrective gate; the exact live-tree
defect is rechecked; a project test environment exists; no production vault or
holdout is used.

**Acceptance checklist:**

- [ ] Stage 3 calls the executable dense mode and retains resolved scope,
  access policy, budget, and deterministic ordering.
- [ ] `dense_used`, attempted/skipped stages, actual mode, and fallback reason
  match execution.
- [ ] `mode="vector"` remains lexical TF-vector and does not load the dense
  manager.
- [ ] Positive path uses a valid non-empty disposable dense generation and a
  query-embed spy; it proves actual dense scoring/materialization.
- [ ] Dense-relevant/no-lexical-overlap fixture cannot pass through TF-only
  results. Mark it a hermetic contract test, not model quality.
- [ ] Missing/corrupt/incompatible generation, explicit fail-closed behavior,
  and permitted labelled fallback are covered.
- [ ] SearchScope SQL pushdown, unprivileged access, authority ordering, stable
  snapshot ordering, and zero query-side vault/index writes are covered.
- [ ] FAST does not import/load optional runtimes or perform model/network work.

**Expected code allowlist:**

- `src/power_framework/core/retrieval_planner.py`
- `tests/test_phase5d_retrieval_planner.py` or one newly named focused test file
- No dependency, model, MCP registration, or release files without a separately
  admitted reason.

## Gate EG2-03 — isolated reference PoC and backend admission

**Preconditions:** Separate authorization for an exact model-acquisition scope;
disposable environment; no production vault; no active or historical sealed
holdout; approved source/artifact license and exact immutable revision. Do not
use an unverified broad `pip install -U` in the framework environment.

**Acceptance checklist:**

- [ ] Record exact repo/revision or artifact digest, complete runtime file
  manifest, hashes, bytes, license/NOTICE, tokenizer digest, runtime and Python
  versions.
- [ ] Resolve dependencies against supported Python versions and current locked
  Hub constraints without changing the base dependency graph.
- [ ] Load text encoder only; prove vision/audio components are not loaded using
  the verified library API.
- [ ] Use CPU FP32 on S-Book. BF16 requires a different host with verified
  native support. FP16 is prohibited.
- [ ] Measure 768d and 256d with the same permitted development set, normalized
  after truncation. Do not run an unbounded dimension/prompt grid.
- [ ] Count the exact tokenizer input, including profile/title/special tokens;
  reject or explicitly account for overlength input within 8,192 tokens.
- [ ] Measure bounded cold/warm runtime, peak process-tree RSS, CPU threads,
  memory/swap/cgroup headroom, vector bytes, dimensions, finiteness, and norms.
- [ ] Record incomplete outcomes honestly if preflight or resource headroom
  fails. No model or source data leaves the approved local boundary.
- [ ] Mark EG2-03 `PASSED / BACKEND ADMITTED` and choose the sole EG2-04
  candidate only if compatibility, supply-chain, offline behavior, and
  resource-fit gates pass. Otherwise record `DEFERRED`.

**Allowed artifacts:** local disposable model cache/environment and one dated
sanitized evidence report. Do not commit model weights or modify runtime files
in this gate.

## Gate EG2-04 — optional adapter and whole-generation migration

**Preconditions:** EG2-02 `PASSED`; EG2-03 `PASSED / BACKEND ADMITTED`; one
backend and exact descriptor admitted; changed file allowlist reviewed before
implementation.

**Adapter acceptance checklist:**

- [ ] Reuse `get_embedding_manager` and existing lazy/provider boundaries; no
  second retrieval engine.
- [ ] Query and document profiles are distinct, server-selected, versioned, and
  applied once. Real document titles are preserved.
- [ ] Batch output count/order, expected dimension, finite values, non-zero
  norms, and normalized output tolerance are validated before storage.
- [ ] Full versioned embedding-space descriptor is used consistently in cache,
  query validation, manifest, generation, diagnostics, and receipts.
- [ ] Default discovery remains side-effect free. Explicit readiness uses only
  local approved files; any selected probe cannot download assets.
- [ ] Query does not sync/index/repair, mutate vault/ledger/active generation,
  or acquire model files unexpectedly.
- [ ] FTS-only base dependencies remain unchanged. Optional extra and lock
  changes require their own resolver/security review; open PR #477/#486 must be
  rechecked first.
- [ ] No public MCP tool or new capability is registered in this gate.

**Migration acceptance checklist:**

- [ ] Preserve active BGE generation and source snapshot.
- [ ] Build staged Gemma generation separately; no mixed-model rows.
- [ ] Validate full source/chunk coverage, hashes, dimensions, norms, DB
  integrity, and unchanged source snapshot.
- [ ] Activate atomically only in explicitly authorized disposable scope.
- [ ] Verify rollback to BGE identity and query correctness.
- [ ] Do not implement per-source dirty-set or persistent queue behavior; that
  remains Phase 5F/6 scope.

**Expected allowlist split:**

- Adapter/descriptor sub-slice: `src/power_framework/experimental/embeddings.py`,
  `src/power_framework/core/model_policy.py`, and focused adapter/descriptor
  tests, with no more than five paths in the admitted change.
- Generation/migration sub-slice: `src/power_framework/core/generation_index.py`,
  `src/power_framework/core/index_sync.py`, and focused migration tests, with no
  more than five paths in the admitted change.
- Packaging/docs are separate bounded files only when EG2-03 proves they are
  required. Do not update generated release history or bump versions.

## Gate EG2-05 — development-only shadow comparison

**Preconditions:** EG2-02 `PASSED`, EG2-03 `PASSED / BACKEND ADMITTED`, and the
EG2-04 backend/migration gate `PASSED`; development source snapshot and
protocol/config digests are frozen; no active or historical sealed holdout is
opened, read, or used for tuning.

**Acceptance checklist:**

- [ ] Model-only matrix holds source, scope, chunking, budgets, fusion, and
  reranking fixed while comparing BGE, Gemma 768d, and Gemma 256d.
- [ ] System-only matrix holds backend/profile/source fixed while comparing
  legacy served retrieval with corrected planner/ContextPack shadow behavior.
- [ ] Any unequal chunk/input budgets are reported separately; no model+system
  change is claimed as a pure model win.
- [ ] Freeze queries/qrels ownership, data/config digests, metrics, sample
  coverage, missing-outcome handling, cold/warm definitions, resource limits,
  stop rules, and selection rule before running.
- [ ] Use only the separately admitted development set. Do not open, read, or
  tune against active or historical sealed holdout queries/qrels.
- [ ] Hard invariants have zero failures: no scope escape, query writes,
  fabricated provenance, secret exposure, authority promotion, or false stage
  reporting.
- [ ] Prospective development thresholds in ADR-0009 are evaluated per
  adequately represented preregistered stratum. No threshold is weakened after
  observing results.
- [ ] Results are labeled development/shadow only; they do not pass Phase 5E or
  change the BGE default.

## EG2-06 — official Phase 5E procedure boundary

EG2-06 is not an EmbeddingGemma shortcut or continuation of EG2-05. It is a
separate invocation of the current Phase 5E procedure after exact live
predecessor reconciliation and its own independent authoring/admission gates.
No active holdout queries/qrels, fresh revision, one-shot, or ground-truth data
were opened or created in EG2-00/01.

## Current EG2-00/01 acceptance checklist

- [x] Live main/tree, PR #485 merge, signature, release/package/phase state
  revalidated from GitHub REST and local Git objects.
- [x] Relevant issue and open PR state recorded; failed Dependabot runs are not
  called failed tests.
- [x] Stage 3, registry, semantic/vector branches, and current positive test
  coverage inspected at the exact source tree.
- [x] Model manager, dense readiness, manifest, generation activation, doctor,
  capability, query path, scope pushdown, and synthesize receipt inspected.
- [x] Officially published model facts and source conflicts recorded.
- [x] Hermetic planner call-path probe: `PASS` with an explicit search double;
  observed `mode="vector"` and `dense_used=True`. This did not invoke the real
  dense scorer or a model.
- [ ] Root `./verify.sh`: `PENDING` until a signed clean candidate HEAD and
  exact `POWER_VERIFY_*` selectors are supplied. The isolated dev/docs
  environment now exists at `/tmp/opencode/power485-docs-verify`; the candidate
  remains intentionally uncommitted and the root verifier requires it clean.
- [x] No code, dependency, model, evaluation, release, production vault, or
  remote repository change is included in this preparation.

## Proposed changed-path allowlist for this preparation

- `artifacts/project-state/evidence/2026-10-11_embeddinggemma2_EG2-00_audit.md`
- `docs/adr/0009-embeddinggemma2-optional-text-retrieval.md`
- `docs/plans/2026-10-11-embeddinggemma2-integration-plan.md`
- One dated EG2-00/01 handoff receipt under `artifacts/project-state/handoffs/`
- A bounded link/live-status overlay in `docs/plans/README.md` only

No other current-state, roadmap, protocol, source, test, dependency, model,
benchmark, phase-evidence, or release file is in this preparation allowlist.
The stale post-#485 projection findings are reported in the audit; this plan
does not create a second remote reconciliation PR or silently turn this
proposal into canonical planning.

## Stop conditions

- F-01 is not reproduced in a working isolated test environment.
- Exact model revision, file hashes, license, tokenizer identity, or
  SentenceTransformers API compatibility is unknown.
- Dependency resolution requires a broad refresh or changes the FTS-only base.
- Model acquisition would use unapproved egress, arbitrary code, or unverified
  mutable references.
- Resource preflight lacks headroom or causes swap/cgroup pressure.
- Any active holdout is opened or used for tuning.
- A source snapshot changes during generation build/evaluation.
- Any hard authority, scope, provenance, determinism, or zero-write invariant
  fails.
- Any generation/mutation outcome is unknown; reconcile receipts rather than
  blindly retrying.
