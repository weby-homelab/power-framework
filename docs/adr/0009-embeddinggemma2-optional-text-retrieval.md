# ADR-0009: Optional Text-Only EmbeddingGemma 2 Retrieval Backend

## Status

**Proposed — NOT ACCEPTED / NOT IMPLEMENTED.** This document records an
architecture proposal only. It does not change the canonical retrieval default,
served behavior, phase status, package metadata, model lock, or release policy.

## Date

2026-10-11

## Context

POWER 3.8 already has a local optional dense retrieval path using BGE-M3,
`BGEM3OnnxManager`, SQLite generations, `SearchScope`, and a read-only doctor
probe. EmbeddingGemma 2 is a Google-published multilingual text/code embedding
model with a native 768-dimensional space and supported Matryoshka dimensions.
The goal is to evaluate it as an opt-in text-only alternative without allowing
derived vectors to become canonical authority or changing the current BGE-M3
default.

The live main at the time of this proposal is
`aa295a4073ba4c0fff0e45721610a4bcdb5489c8`, tree
`a25c80d6b5a77c4d36ec8373032d1e91ccdb36ac`. PR #485 is merged. Live planning
still has Phase 5E open/not passed and Phase 5F blocked. The proposal sequence
below is not yet reconciled with that canonical queue.

The EG2-00 audit also confirms a semantic-stage dispatch defect in the current
tree: `RetrievalPlanner` passes `mode="vector"`, which is lexical TF-vector in
the search registry, but reports `dense_used=True`. This correction must be
admitted and verified separately before any semantic quality comparison can be
treated as trustworthy.

## Proposed decision

### 1. Scope and compatibility boundary

- The first experiment is **local, text-only, opt-in retrieval**. It does not
  load vision or audio encoders and does not claim multimodal support.
- The only candidate output dimensions for the bounded first comparison are
  768 and 256. A dimension change is a distinct embedding space and requires a
  separate dense generation.
- Reuse the existing `get_embedding_manager` factory/cache boundary,
  `model_policy`, `SearchScope`, `SemanticChunker`, SQLite dense storage,
  generation resolver, `ApplicationService`, and existing receipts.
- Do not create a parallel retrieval engine, new canonical state store,
  `ContextPack2`, public MCP tool, remote inference service, or mandatory vector
  database.
- Keep BGE-M3 as the default. Do not change served `auto` behavior, public
  version, release line, or active production vault in this experiment.

### 2. F-01 correction before model comparison

EG2-02 is a bounded corrective gate. It must dispatch the planner's semantic
stage to the executable dense mode without changing the historical lexical
meaning of `mode="vector"`. The correction must preserve the resolved
`SearchScope`, access policy, candidate budget, explicit failure behavior,
stable ordering, and existing canonical-owner rules. `dense_used`, attempted
stages, skipped stages, fallback mode, and fallback reason must describe the
execution that actually occurred.

The current canonical roadmap's next gate is still Phase 5E fresh evaluation
authoring. Before EG2-02 changes runtime, an explicit governance decision must
reconcile whether this correctness prerequisite precedes that Phase 5E
invocation. This proposal recommends EG2-02 before any EmbeddingGemma baseline;
it does not silently reorder the canonical roadmap.

### 3. Reference PoC and sole production candidate

- **Reference PoC:** the Google-published SentenceTransformers route for
  `google/embeddinggemma-2`, isolated in a disposable environment and using
  verified local artifacts only after the separate EG2-03 acquisition scope is
  admitted.
- **Production candidate:** one optional local SentenceTransformers adapter
  behind a separately admitted extra. This is the sole candidate proposed for
  EG2-04 because the Google-published model card demonstrates this library path
  and describes selective modality loading. It is **DEFERRED**, not selected for
  implementation, until EG2-03 proves exact artifact identity, package
  resolution, text-only loading, numerical behavior, safe offline construction,
  and host resource fit.
- If those proofs fail, record `DEFERRED` with the specific failed gate. Do not
  silently pivot to Ollama, ONNX, LiteRT, OpenVINO, or another runtime in the
  same gate.

The current `OllamaEmbeddingManager` is not the selected candidate: its default
model is `qwen3-embedding:0.6b`, the Ollama dependency is not declared in the
current `pyproject.toml`, model-name dimension inference can fall back to 1024,
and its `embed_batch` interface has no `batch_size` argument. The Ollama catalog
also advertises a 256K badge that conflicts with the Google-published 8,192
token model-card limit. Existing OpenVINO BGE acceptance does not prove Gemma
compatibility. No model/runtime package is added by this proposal.

### 4. Query/document task profile

The initial admitted profile is server-selected and versioned. For asymmetric
text search, the Google-published model card specifies:

```text
Query: task: search result | query: {query}
Document: title: {real_title_or_none} | text: {content}
```

Apply the task prefix exactly once, by either a named prompt or manual
formatting. Do not combine both. A titled document must retain its real title;
the model-card `Document` prompt name means `title: none`. Future code retrieval
may use `task: code retrieval | query: {query}`, but codebase crawling is not in
this slice. The task profile is configuration controlled by POWER, not by an
arbitrary caller prompt, and its digest is part of generation identity.

The model's 8,192-token window includes task/title formatting and special
tokens. Count with the exact admitted tokenizer, reject or explicitly subdivide
over-limit content with recorded coverage, and never silently truncate. The
existing structural/character chunker is not a tokenizer-aware limit.

### 5. Numerical and dimensional contract

- Compare only 768d and 256d in the first bounded development experiment.
- Apply L2 normalization after truncation for both query and documents.
- On the S-Book CPU-only policy, use FP32. BF16 is permitted only on a later
  host where native support is explicitly verified. Do not use FP16: the
  Google-published model card warns of NaN or silently degraded outputs.
- Every batch must return exactly one finite vector per input, with expected
  dimension, non-zero norm, and declared normalization tolerance. Any count,
  dimension, NaN, infinity, or zero-norm mismatch fails before generation
  publication; no truncating `zip` or dummy vector is allowed.
- Do not claim bit-identical outputs across providers, devices, or quantized
  exports. Any export or quantization is a separate descriptor and evidence
  profile.

### 6. Versioned embedding-space identity

The proposed typed descriptor must bind, at minimum:

```text
provider_id
model_repository
immutable_revision OR exact_artifact_digest
required_runtime_file_hashes
tokenizer_or_processor_digest
task_prompt_profile and profile_digest
native_dimension and output_dimension
normalization_strategy
inference_dtype
quantization_or_export_identity
runtime_version
input_preprocessing_revision
chunker_revision
```

Use the existing schema and `model_policy` boundary where possible. The
descriptor must be checked consistently in manager-cache identity, query
validation, dense manifest, generation metadata, doctor diagnostics, and
evidence receipts. Same dimension with a different model revision, prompt,
tokenizer, normalization, or export is incompatible. Source snapshot, source
scope, and chunk identities remain separate bindings. All model revisions,
file hashes, and tokenizer digests remain unknown until EG2-03; this ADR
intentionally invents none.

### 7. Acquisition, privacy, and readiness

- Preserve FTS-only base install. Any heavy inference dependency belongs only
  in a separately reviewed optional extra; do not broaden the existing Hub pin
  or perform a general dependency refresh for this feature.
- Use exact approved model identity, license/NOTICE review, required-file
  allowlist and hashes, `model_policy`, verified local staging, and offline
  loader construction. Do not enable `trust_remote_code=True`, arbitrary pickle
  execution, or global egress.
- Default discovery must not import or load the optional runtime, probe a model
  session, download assets, create a cache, or mutate vault/search state. An
  explicit diagnostic may perform a no-download probe and must distinguish
  configured, not-probed, available, verified, failed, and disabled states.
- A configured or listed provider is not proof of a bound runtime/device.
  Device claims require an actual admitted session and readback; provider-list
  presence alone is insufficient.
- Query execution must not invoke sync, index, repair, source mutation, ledger
  writes, or active-generation publication. A query must not unexpectedly
  acquire model files; if required assets are missing, the explicit mode fails
  closed and `auto` may use only its permitted labelled fallback.
- Keep principal and `SearchScope` enforcement in the current application and
  search boundaries. Embedding score, path, tag, model output, or retrieved text
  cannot increase authority.

### 8. Whole-generation migration and rollback

In disposable fixture/sandbox scope only:

1. Preserve the active BGE generation and immutable source snapshot.
2. Build a separate staged generation for the exact admitted descriptor and
   dimension; never append Gemma rows to BGE rows.
3. Verify source/chunk coverage, hashes, row counts, dimensions, finite values,
   norms, generation manifest, SQLite integrity, and unchanged source snapshot.
4. Activate only through the existing atomic generation-publication boundary
   when the fixture mutation is explicitly authorized.
5. Prove rollback to the prior BGE generation and query correctness.

Model, prompt, tokenizer, dimension, chunker, or export changes require a new
whole generation. This proposal does not implement per-source dirty sets or a
persistent `IndexWorkQueue`; those remain separate Phase 5F/6 contracts.

### 9. Evaluation separation and gates

Proposed sequence for this experiment only:

```text
EG2-02 semantic dispatch correction
  → EG2-03 isolated text-only reference PoC and backend admission
  → EG2-04 one opt-in adapter plus sandbox generation migration
  → EG2-05 development-only shadow comparison
```

This sequence is proposed and not canonical. The current canonical Phase 5E
fresh evaluation authoring remains a separate next-gate record and must not be
replaced or silently delayed by this ADR. EG2-06 is the existing official
Phase 5E procedure in a separately admitted invocation; this proposal does not
authorize authoring, opening, tuning, or executing any holdout/ground-truth
material.

EG2-05 must preregister model-only and system-only comparisons, fixed source
snapshot and scope, language/code strata, metrics, resource limits, stop rules,
selection policy, and missing outcomes before any development result. Proposed
development-only thresholds are:

```text
All hard invariants pass.
For each adequately represented preregistered stratum:
  nDCG@10 and Recall@10 drop <= 0.02 absolute vs. controlled BGE baseline.
Practical resource win under the same measured limits:
  >=20% lower peak process-tree RSS OR >=20% lower warm p95 latency.
```

These are prospective development thresholds only. They do not weaken Phase 5E,
release, or canonical acceptance criteria. A synthetic or development corpus
cannot establish universal product quality.

## Alternatives considered

### Keep BGE-M3 as the only provider

This preserves the current validated default and is the mandatory fallback if
EG2-03/04 evidence is insufficient. It does not answer the requested optional
Gemma experiment, but it avoids an unverified runtime change.

### Ollama-managed `embeddinggemma-2:270m`

Not selected. The current adapter's API/identity/dimension behavior is not
adequate evidence for this model, no Ollama package is declared, and the public
catalog context badge conflicts with the publisher's model card. Reconsider only
under a new bounded admission with exact digest, dimension, prompt, batch,
resource, and actual execution evidence.

### Direct ONNX, OpenVINO, LiteRT, or another export

Not selected because no verified EmbeddingGemma 2 export/runtime compatibility,
artifact provenance, or device-binding evidence was established in EG2-00.
Existing BGE ONNX/OpenVINO acceptance does not transfer to Gemma.

### Remote inference or a new vector service

Rejected for this local-first text experiment. It adds a new data-egress and
operational trust boundary and is unnecessary for the stated scope.

## Consequences

- Positive: the default BGE/FTS contracts and canonical authority boundaries
  remain intact while a measurable optional experiment is prepared.
- Negative: runtime, model revision, dependency resolution, memory fit, and
  quality remain unproven until separately admitted EG2 gates pass.
- Rollback: keep the active BGE generation untouched and point back to its
  immutable generation ID after a failed disposable migration.
- Stop conditions: missing exact artifact identity/hash/license; unsupported
  dependency resolution; unsafe egress or loader behavior; no resource headroom;
  unresolved F-01; any mixed generation; failed hard invariant; or unknown
  mutation outcome.

## Acceptance for changing this ADR to Accepted

- EG2-02 is separately admitted, source-bound, regression-tested, and reports
  actual semantic execution truthfully.
- EG2-03 proves exact model/runtime artifact identity, license, offline
  construction, text-only loading, prompt correctness, finite normalized
  outputs, token-limit behavior, dependency compatibility, and resource fit.
- EG2-04 passes adapter, descriptor, whole-generation migration, rollback,
  scope, authority, cancellation, and low-resource tests in disposable scope.
- EG2-05 completes a preregistered development-only shadow comparison without
  touching official holdout/ground-truth assets.
- An operator/governance decision reconciles the proposed order with the live
  Phase 5E queue. Only a protected normal merge can make this ADR canonical.

Until then: `PROPOSED / NOT ACCEPTED / NOT IMPLEMENTED / DEFAULT UNCHANGED`.

## References

- EG2-00 audit: `artifacts/project-state/evidence/2026-10-11_embeddinggemma2_EG2-00_audit.md`.
- Google-published model card: <https://huggingface.co/google/embeddinggemma-2>.
- Google launch post: <https://blog.google/innovation-and-ai/technology/developers-tools/embeddinggemma-2/>.
- Ollama catalog, used only to document a conflicting catalog badge:
  <https://ollama.com/library/embeddinggemma-2>.
- Existing architecture: ADR-0007 and ADR-0008.
