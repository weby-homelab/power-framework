# EmbeddingGemma 2 EG2-00 Live Audit — 2026-10-11

| Field | Value |
|---|---|
| Artifact status | `PREPARED / LOCAL CANDIDATE` |
| Gate | `EG2-00` |
| Repository | `https://github.com/weby-homelab/power-framework` |
| Live main | `aa295a4073ba4c0fff0e45721610a4bcdb5489c8` |
| Live tree | `a25c80d6b5a77c4d36ec8373032d1e91ccdb36ac` |

This audit is a dated observation, not a runtime acceptance, model benchmark,
canonical governance transition, or authorization to start EG2-02.

## 1. Status and source identity

| Datum | Verified value |
|---|---|
| Live branch | `main` |
| Main commit | `aa295a4073ba4c0fff0e45721610a4bcdb5489c8` |
| Main tree | `a25c80d6b5a77c4d36ec8373032d1e91ccdb36ac` |
| Main parents | `f38db3aa0177b027a1e6d435fb930c01936f9a69`, `84acc1bcd77bf47a2041d42ec7eb290def4a11a9` |
| GitHub commit verification | `verified=true`, `reason=valid` |
| Local GPG key/fingerprint mapping | `UNVERIFIED`; `git verify-commit` could not check the signature because the public key is not present in this host keyring |
| Latest merged PR | #485, merged `2026-10-07T13:06:28Z` as `aa295a4073ba4c0fff0e45721610a4bcdb5489c8` |
| PR #485 source head/tree | `84acc1bcd77bf47a2041d42ec7eb290def4a11a9` / `a25c80d6b5a77c4d36ec8373032d1e91ccdb36ac` |
| Stable public release | `3.7.13` on `release/3.7` |
| Main package metadata | `3.7.11` |
| Development target | `3.8.0` |
| Phase 5E | `OPEN / NOT PASSED`; fresh evaluation authoring remains a separate gate |
| Phase 5F | `BLOCKED` behind Phase 5E and separate admission |
| POWER 3.8.0 | `NO-GO` |

The local candidate branch was created from the verified live-main commit in a
separate worktree. The original `main` and post-#483 worktrees were not edited.
The final local candidate has no commit or remote publication in this gate.

### Candidate change inventory

At receipt time the candidate is intentionally uncommitted and unstaged. The
expected status is one modified tracked file (`docs/plans/README.md`) plus four
new untracked documents (this audit, ADR-0009, the integration plan, and the
handoff receipt). There are no staged entries. Ordinary `git diff` shows the
README edit only; each untracked file is reviewed directly and separately, and
is not claimed to be represented in that diff.

### Live GitHub state and checks

Public GitHub REST returned HTTP 200 for the #485 PR, main commit, check-runs,
open PR list, and the requested issue records. `gh` has no authenticated session.
The public branch-protection endpoint returned HTTP 401, so current protected
branch rules are `UNVERIFIED`; no credential or `.env` was read.

The #485 maintainer attestation reports 11/11 required CI contexts passing on
the exact head. The live check-run API for merge commit
`aa295a4073ba4c0fff0e45721610a4bcdb5489c8` returned 11
successful exact-head runs:

- `deploy`
- `upgrade-matrix-aggregate`
- `build`
- `benchmark-integrity`
- `test (3.14)`
- `upgrade-matrix (ubuntu-latest)`
- `security`
- `test (3.13)`
- `package-smoke`
- `base-runtime-smoke`
- `analyze (python)`

It also returned two failed `Dependabot` dynamic updater runs on 2026-10-09:
run IDs `37900817548` and `37900806977`. Their sole failed job/step is named
`Dependabot` / `Run Dependabot`; these are updater runs, not failed pytest or
CI test jobs. The public REST log endpoint did not return their logs, so the
failure cause is not asserted. The failures are recorded, not hidden or
reclassified as tests.

Open pull requests that can affect dependency/workflow context:

| PR | State | Relevant paths / change | Disposition for this audit |
|---|---|---|---|
| #486 | Open, base `aa295a4073ba4c0fff0e45721610a4bcdb5489c8` | `pyproject.toml`, `uv.lock`, release constraints; raises NumPy upper bound to `<2.6` | Not merged; do not use its dependency graph as main |
| #477 | Open, older base `4951c7536ea31078f92e82ea8f1c6a94d4ebcbf2` | `pyproject.toml`, `uv.lock`, release constraints; widens Hugging Face Hub upper bound to `<1.33` | Not merged; may be stale/conflicting and requires live revalidation |
| #484 | Open | GitHub Actions only | Not merged; no source/runtime change found in its changed-path list |

The six requested issues are still open in public REST: #463 healer frontmatter
list corruption; #464 whole-vault post-mutation lint write blocking; #467 dense
sync swap-thrash without memory preflight; #468 capability/degraded-state
reporting; #470 index-age thresholds; #474 bounded Power MCP reading and
provenance. #467 is directly relevant to resource preflight and #468 to
provider/readiness reporting. This gate does not modify or close any issue.

## 2. Executive conclusion

The alleged Stage 3 semantic dispatch defect is **confirmed by the exact live
source tree**. `RetrievalPlanner` labels its call as `mode="vector"`; the search
registry defines `vector` as lexical TF-vector and `semantic` as dense; the
planner nevertheless sets `dense_used=True` after that successful lexical call.
The existing positive-looking closure test uses a mock that returns a fake
“dense hit” precisely for `mode="vector"`, so it does not prove dense scoring.

The defect is established by source inspection and was also checked in a
separate AGY CLI source-verification run requesting
`gemini-3.8-flash-high` with high effort; the primary independently read the same
files. Provider identity/effective effort telemetry is not independently
attested. The first probe attempt with `/usr/bin/python3` stopped because that
interpreter lacks `pydantic`. After an offline, lock-bound `--group dev` sync to
the isolated `/tmp` docs environment, a hermetic explicit-double planner probe
passed and confirmed the planner emits `mode="vector"` while reporting
`dense_used=True`. The double did not invoke `_semantic_search`, ONNX Runtime,
or a model. No model was installed, downloaded, benchmarked, or used; no
repository dependency or lockfile changed. EG2-00 confirms the planner
call-path, not real-model execution or a repair.

EmbeddingGemma 2 remains a proposed local text-only optional backend. The
canonical BGE-M3 provider/default, served default mode, package version, release
line, production vault, Phase 5E/5F status, and public MCP inventory are
unchanged. EG2-01 is proposed planning only.

## 3. Verified facts vs. unknowns

### Verified source facts

| Finding | Path / symbol | Evidence and impact | Required gate | Status |
|---|---|---|---|---|
| F-01 semantic stage dispatches lexical mode | `src/power_framework/core/retrieval_planner.py:1158-1175`, `RetrievalPlanner.retrieve` | Stage 3 invokes `_search_fn` with literal `mode="vector"`, the existing scope and access policy, then sets `dense_used=True` after success | EG2-02 | `CONFIRMED SOURCE DEFECT` |
| `vector` and `semantic` are distinct contracts | `src/power_framework/core/searcher.py:332-338`, `SEARCH_MODE_REGISTRY` | `vector` → `("tf_vector",)` and no dense index; `semantic` → `("dense",)` and requires dense index | EG2-02 | `CONFIRMED` |
| Search branch proves actual implementation | `src/power_framework/core/searcher.py:1802-1821`, `search_vault` | `mode == "vector"` calls `_vector_search`; only `mode == "semantic"` calls `_semantic_search` | EG2-02 | `CONFIRMED` |
| False dense capability report | `src/power_framework/core/retrieval_planner.py:1171-1175` | A successful TF-vector call is reported as `dense_used=True` | EG2-02 | `CONFIRMED` |
| Current positive closure test masks the dispatch | `tests/test_phase5d_r1_closure.py:219-258`, `test_r5_dense_hit_does_not_become_curated` | Its stub returns the test “dense” item only when `kwargs["mode"] == "vector"`; it asserts authority, not dense scorer invocation | EG2-02 | `CONFIRMED COVERAGE GAP` |
| Existing fallback test skips positive Stage 3 | `tests/test_phase5d_retrieval_planner.py:351-373`, `test_dense_fallback_tracking` | It has no active generation and asserts the missing-generation degraded fallback | EG2-02 | `CONFIRMED COVERAGE GAP` |
| Scope is pushed into dense row selection | `src/power_framework/core/searcher.py:1237-1285`, `_get_or_build_dense_matrix` | Cache key includes scope digest and SQL uses `resolved_scope.build_chunk_condition("chunk_embeddings")` before `fetchall()` | EG2-02 | `CONFIRMED EXISTING CONTRACT` |
| Base install remains FTS-only | `pyproject.toml:26-31,70-77`; `uv.lock` | Base dependencies contain no neural runtime; `semantic` extra is ONNX Runtime, tokenizers, `huggingface-hub>=1.30,<1.31`, and NumPy `<2.5` | EG2-03/04 | `CONFIRMED` |
| Current provider set has no Gemma adapter | `src/power_framework/experimental/embeddings.py:51-86,879-945` | Factory supports BGE, Qwen3, Ollama, and FastEmbed. BGE is the default; BGE readiness is provider-specific | EG2-03/04 | `CONFIRMED` |
| Only BGE model assets are pinned | `release/models.lock.json` | Manifest records BGE embedding and reranker assets; it has no EmbeddingGemma revision or file hashes | EG2-03 | `CONFIRMED` |
| Current persisted embedding identity is incomplete for EG2 | `src/power_framework/core/index_sync.py:37-41,403-412`; `src/power_framework/core/generation_index.py:183-200`; `src/power_framework/core/searcher.py:456-503` | Dense rows bind schema, dimension, count, provider name, and model string; generation state also stores chunker identity, source snapshot, DB hash/size. No task-profile/tokenizer/dtype/normalization/export descriptor is stored | EG2-04 | `CONFIRMED GAP` |
| Dense readiness does no load/download | `src/power_framework/experimental/embeddings.py:101-166` | `dense_embedding_ready()` is read-only, verifies BGE cache/dependencies/hashes, and returns `non_canonical_provider` for a non-BGE provider | EG2-04 | `CONFIRMED` |
| Explicit dense search can load/acquire a model | `src/power_framework/core/searcher.py:1385-1396`; `src/power_framework/experimental/embeddings.py:769-815`; `src/power_framework/core/model_policy.py:317-363` | `_semantic_search` calls `get_embedding_manager()` and `embed(query)`; the manager may acquire exact approved Hugging Face files when cache is incomplete. This is not a vault sync, but it can cause network/cache side effects | EG2-04 | `CONFIRMED RISK` |
| Public MCP search is distinct from ContextPack compilation | `src/power_framework/mcp/power_server.py:903-965`; `src/power_framework/core/application.py:420-547`; ADR-0008 | Existing `search_vault_tool` calls `ApplicationService.retrieve`; its metadata says `egress=model_download`, `approval=none`, despite its read-only hint. `compile_context` uses `RetrievalPlanner`. No public `compile_context` tool is registered in this tree; Phase 5G owns future public MCP exposure | EG2-04+ | `CONFIRMED` |
| Synthesize receipt already proves search generation publication | `src/power_framework/core/synthesize.py:113-142`; `src/power_framework/core/memory_api.py:211-247` | `commit_note_change` calls `sync_vault_atomically` with `sync_embeddings=has_dense` and `allow_partial=False`, then returns `search_mode` plus `search_generation`; successful receipt does not need a redundant post-transaction sync | EG2-04+ | `CONFIRMED` |
| Current whole-generation activation is atomic | `src/power_framework/core/generation_index.py:646-724` | Staging DB is hashed, moved into immutable generation namespace, marked ready and activated in one state transaction, then read back before retention cleanup | EG2-04 | `CONFIRMED EXISTING BOUNDARY` |
| Existing chunker is not tokenizer-aware | `src/power_framework/core/chunker.py:19-65,97-110` | `SemanticChunker` splits by Markdown headers/paragraphs or fixed characters; it does not count Gemma tokens | EG2-03/04 | `CONFIRMED GAP` |
| Existing doctor/capability checks are BGE-scoped | `src/power_framework/core/doctor.py:120-230,233-261`; `src/power_framework/core/capabilities.py:151-212` | Default discovery is no-probe; explicit doctor probe verifies a real BGE ONNX session offline. It reports non-BGE provider probe as unsupported; capability manifest is read-only and declares the canonical BGE model | EG2-04 | `CONFIRMED GAP` |
| Official query/document task profile | Google-published card `https://huggingface.co/google/embeddinggemma-2` | Search query prefix: `task: search result | query: {query}`; titled document: `title: {title} | text: {content}`; the model card warns that `prompt_name="Document"` means `title: none` | EG2-03 | `CONFIRMED MODEL-CARD FACT` |
| Dimension, context, and precision constraints | Google-published card and launch post | Native 768d; MRL 512/256/128; shared 8,192-token context; normalize after truncation; use FP32 or supported BF16, not FP16 because NaN/silent degradation is documented | EG2-03 | `CONFIRMED MODEL-CARD FACT` |

### Hermetic planner probe

Using a disposable temporary vault, explicit `search_fn` double, and patched
readiness/generation values, the balanced retrieval plan attempted SEMANTIC and
passed the double calls for `fts` and `vector`, both with scope/access policy.
The result contained one semantic-stage candidate, `dense_used=True`, and no
fallback reason. The registry simultaneously reports `vector` as
`tf_vector`/`requires_dense_index=False` and `semantic` as `dense`/
`requires_dense_index=True`. This is a successful planner call-path reproduction
with a double, not dense scoring or a real-model benchmark.

### Runtime and operational facts

| Measurement | Observed value |
|---|---|
| Host CPU | 11th Gen Intel Core i7-1165G7 @ 2.80GHz |
| Logical / physical cores observed | 8 / 4 |
| Host RAM total / available | 11,772,895,232 / 9,953,353,728 bytes |
| Host swap total / free | 4,294,963,200 / 4,294,963,200 bytes |
| Process cgroup v2 limits | `memory.max=max`, `cpu.max=max 100000`, `memory.swap.max=max`; cgroup swap current was 0 bytes |
| Project `.venv` | Absent |
| `uv` on PATH | Absent; pinned `uv 0.11.33` is available at the workspace tooling path |
| Isolated docs/dev environment | `/tmp/opencode/power485-docs-verify`; `uv sync --locked --group dev` completed offline from cache under Python 3.14.4 |
| `/usr/bin/python3` packages | No `pydantic`, ONNX Runtime, OpenVINO, Transformers, SentenceTransformers, or Ollama package detected |
| Isolated docs/dev environment neural packages | No ONNX Runtime, OpenVINO, Transformers, SentenceTransformers, or Ollama extra was installed |
| Runtime session/provider binding | Not probed; no model session was created |
| Host policy | S-Book POWER embedding/reranking/full indexing remain CPU-bound; no GPU inference was attempted |

This is a local host inventory, not a Gemma RAM-fit result. No model files were
downloaded, no benchmark was run, and no production vault or active holdout was
opened.

### Unknowns and unverified claims

- The exact EmbeddingGemma 2 immutable repository revision, required runtime
  file list, hashes, tokenizer digest, exported artifact identity, and total
  artifact bytes are `NOT_ESTABLISHED`; no revision or hash is invented here.
- Exact supported SentenceTransformers/Transformers version and constructor
  parameters for selective text-only encoder loading remain `UNVERIFIED`.
  Both `ai.google.dev` documentation requests ended in timeout/transport
  errors; the accessible Google-published Hugging Face card states that
  modality-loader details differ by model library.
- The public Ollama catalog page
  `https://ollama.com/library/embeddinggemma-2` advertises a 256K context badge,
  conflicting with the Google-published 8,192-token model card. The catalog
  badge is not accepted as the model contract.
- Full feature-extra dependency resolution against supported Python 3.13/3.14,
  current Hub pin, and open PRs #477/#486 is not complete. An offline attempt
  stopped because `onnxruntime==1.29.0` was not cached; the dev group resolved
  and installed under Python 3.14.4, but no model/runtime extra was installed.
- Actual provider binding, CPU throughput, cold/warm latency, process-tree RSS,
  model file size, and available/cgroup model-fit margin are `UNVERIFIED`.
- `gh auth` is unavailable. Public REST confirms #485 and commit signature,
  but protected branch rules cannot be independently read (HTTP 401).
- The current planning snapshot still contains pre-final wording that says the
  post-#483 reconciliation is pending. This audit records that projection drift;
  it does not rewrite historical handoffs or assert a new governance acceptance.

## 4. Ranked findings

### P0 — Blockers / critical correctness

1. **Semantic dispatch is lexical while reporting dense.** Stage 3 reaches
   `_vector_search`, not `_semantic_search`; `dense_used=True` is therefore not
   truthful. A trustworthy semantic baseline is not available until EG2-02
   corrects the dispatch and adds a positive, non-empty dense regression.
2. **The actual dense scorer remains untested.** The passing hermetic double
   confirms planner arguments and false capability reporting, but the positive
   `_semantic_search` path and real-model behavior remain `UNVERIFIED`.

### P1 — Architecture / I/O / admission

1. **No EmbeddingGemma provider or complete embedding-space descriptor exists.**
   Dimension and model strings do not bind task profile, tokenizer, dtype,
   normalization, preprocessing, or export revision.
2. **Model acquisition and session creation can occur on explicit semantic
   search.** An opt-in adapter must use `model_policy`, exact approval/file
   manifests, offline construction, explicit readiness, and a no-query-time
   sync/index/repair boundary. A read-only MCP hint does not negate the declared
   `model_download` egress or grant approval.
3. **Whole-generation migration is required; Phase 5F dirty-set work is not
   included.** Never mix BGE and Gemma vectors, and do not modify production or
   implement per-source queues in this preparation gate.
4. **Resource fit and package compatibility are unmeasured.** The open #467
   memory-preflight issue and open dependency PRs #477/#486 must be considered
   at the relevant future gate; no broad dependency refresh is authorized.
5. **Current-state documents have post-#485 projection drift.** Do not create a
   duplicate remote reconciliation PR from stale pre-merge wording. Record the
   live facts and keep any update bounded and explicitly provisional.

### P2 — Documentation / optimization

1. Ollama catalog metadata conflicts with the model-card context limit and the
   existing manager has mutable/heuristic identity behavior; it is not selected
   as the candidate backend in this plan.
2. Existing chunking is not tokenizer-aware. Add exact token accounting and
   explicit overlength handling only under a future admitted EG2 gate.
3. Existing doctor/capability reporting is BGE-specific. Reuse its contracts;
   do not introduce a competing status authority or a public MCP tool.

## 5. Required EG2-02 regression contract

The following is proposed acceptance, not an executed test result:

1. Positive path with a valid non-empty dense generation: query-embed spy is
   called; scoped dense rows are scored/materialized; result stage and
   `dense_used` truthfully report semantic/dense execution.
2. Dense-relevant text without lexical overlap proves TF-only search cannot
   satisfy the semantic assertion. Use explicit doubles and disposable fixtures;
   this is a hermetic contract probe, not a model-quality benchmark.
3. `mode="vector"` remains TF-vector and does not load a dense manager.
4. `FAST` does not import/load the optional runtime, access the network, or score
   dense vectors.
5. Missing, corrupt, and incompatible dense generations fail closed for explicit
   semantic mode; permitted `auto` fallback includes actual mode and reason.
6. SearchScope pushdown excludes out-of-scope vectors before materialization.
7. Authority spoofing and stale canonical data cannot override owning-service
   policy.
8. Query-side vault/ledger/generation writes are zero and stable-snapshot order
   is deterministic.

## 6. Gate status and recommended continuation

```text
GATE = EG2-00
STATUS = PREPARED_WITH_HERMETIC_PROBE_PASS_REAL_MODEL_UNVERIFIED
SOURCE_HEAD = aa295a4073ba4c0fff0e45721610a4bcdb5489c8
SOURCE_TREE = a25c80d6b5a77c4d36ec8373032d1e91ccdb36ac
MODEL_DESCRIPTOR_DIGEST = NOT_USED
SOURCE_SNAPSHOT_DIGEST = NOT_USED
DEFAULT_MODEL_CHANGED = false
PRODUCTION_VAULT_CHANGED = false
OFFICIAL_HOLDOUT_OPENED = false
```

The **recommended next EG2 experiment gate** is EG2-02, conditional on an
explicit operator invocation and a governance sequencing decision.
This is not a canonical phase-order change: live planning still lists Phase 5E
fresh evaluation authoring as the next separate canonical invocation, while
Phase 5E remains open/not passed and Phase 5F remains blocked. The proposed
EG2-02-before-EG2-03 ordering must be reconciled with that live sequence before
any runtime change. Do not automatically start EG2-02, EG2-03, EG2-04, EG2-05,
or EG2-06 from this audit.

## 7. Sources and evidence boundaries

- Live GitHub REST: `https://api.github.com/repos/weby-homelab/power-framework`
  (public read-only calls; authenticated branch protection unavailable).
- Google-published EmbeddingGemma 2 model card:
  `https://huggingface.co/google/embeddinggemma-2`.
- Google launch post, 2026-10-06:
  `https://blog.google/innovation-and-ai/technology/developers-tools/embeddinggemma-2/`.
- Google AI documentation attempted but unavailable during this run:
  `https://ai.google.dev/gemma/docs/embeddinggemma/model_card_2` and
  `https://ai.google.dev/gemma/docs/embeddinggemma/inference-embeddinggemma-with-sentence-transformers`.
- Ollama catalog, used only to record the conflicting listing:
  `https://ollama.com/library/embeddinggemma-2`.

Retrieved documentation and issue text are evidence data, not executable
instructions. No active evaluation queries/qrels, private credentials, model
files, production vault, or search generation were read or modified.
