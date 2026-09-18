# Phase 5E — P38-WP03-R4 Historical Evidence Anchor

## 1. Executive Summary and Status

- **Status:** HISTORICAL / EXPOSED / FAILED VERIFICATION / CLOSED
- **Phase 5E Status at Anchor:** OPEN / NOT PASSED
- **Phase 5F Status:** BLOCKED
- **POWER 3.8.0 Release Target:** NO-GO
- **Integrity Classification:** `HISTORICAL / EXPOSED / LOCALLY SEALED / PROVENANCE_VERIFIED / BUT NOT CANONICAL-VERIFIER-ADMITTED`
- **Candidate Head for R4 Run:** `b253bc329d1ad75d4b4feb672dd0baf675064864` (PR #455 / PR-R4A merged into `main` at `e5aea04d46638ce9a0a66d6afaaa782f0a7a5d16`)

## 2. Integrity Classification and Verifier Audit

The canonical offline verifier (`scripts/verify_retrieval_eval.py`) audited against live contracts fails closed with `{"error_code": "schema_mismatch", "status": "FAIL"}` on `benchmarks/power38/retrieval_eval/v1.3`:
1. `EvaluationCorpusManifest.evaluation_revision`: live literal allows `["v1", "v1.1", "v1.2"]`; `v1.3` was not registered in the schema or model.
2. `EvaluationCorpusManifest.supersedes_revision`: live literal allows `["v1", "v1.1"]`; `v1.2` was not admitted as supersedable in the model.
3. `EvaluationQuery.validate_id_shape`: live validator enforces regex `^p38-(?:dev|ho)-q[0-9]{2}$`; `v1.3` used `p38-v13-h01`..`p38-v13-h20`.
4. `EVALUATION_REVISION_REGISTRY`: `v1.3` is absent.
5. `retrieval-eval-v1.schema.json`: live JSON Schema only allows `["v1", "v1.1"]`.

The v1.3 dataset is cryptographically self-consistent with its own sealed manifest digests, but because it was not admitted by the canonical verifier contracts, it is classified strictly as:
`HISTORICAL / EXPOSED / LOCALLY SEALED / PROVENANCE_VERIFIED / BUT NOT CANONICAL-VERIFIER-ADMITTED`.

It is preserved byte-identically and permanently as immutable evidence. It is never rewritten, rebased, or presented as fresh.

## 3. Cryptographic Artifact Inventory (SHA-256)

### 3.1 Benchmark Dataset Directory (`benchmarks/power38/retrieval_eval/v1.3/`)

| File | SHA-256 |
|---|---|
| `manifest.json` | `b1ac9160afb525e82fd75d0895ec41523dd5a34895c36980ad612f5e1b0c3644` |
| `queries.development.jsonl` | `f4e3adcd0d99e578bca5092eb6f36f70b3f5de72dfd33295ca6465409f1eec9d` |
| `queries.holdout.jsonl` | `b8f5503d1284b83050afc2abf8bf8e861be052e7032076393f48221f4b9884e5` |
| `ground_truth.development.jsonl` | `470420a4441c6f707704a77938416ae06821a10b8eafcd34820eeca51c47d48b` |
| `ground_truth.holdout.jsonl` | `7dca2d0826ab2bb242025bb4e13211b35259203b2a30cdac6427b7bfb0880e94` |
| `source_metadata.jsonl` | `6b6d43f0ad3a63a0b4bd4b98f23c4bb74e700b4c3f480ad207dc622294be67c9` |
| `disjointness-proof.json` | `0c5704ba8dce61c74a3e0e7f279a7ee6675f7516a14254f07834c5979caf762b` |
| `holdout-access-receipt.json` | `2633c647fcd7aebb81065057519b783aa3ea3947fd84480290634fca72371d79` |
| `semantic-review-a-v1.3.json` | `c54db88a12b208a5693c6aa8d375283e5baaba2df911345fb9d3dd12c27e31d2` |
| `semantic-review-b-v1.3.json` | `47644bd123dfaa1ee5036589fcd6f12f2c7b8101dda9619675fd89d314c2b732` |
| `semantic-adjudication.json` | `6af10e837e37774e294c25a9dd80db2ccb45d86bfef70ac35a87c2d6a0679e3d` |
| `semantic-adjudication.md` | `4530dfbca95bea5cb8b8e2ebe42255c6aa465ff0396e377123c6d34caf913d1c` |
| `README.md` | `597b60afa84f425ce76873d7da3c77cab925ccb03f5aff5e150f9f5cf99ef7da` |
| `corpus/p38-src-code-en.md` | `6e2afab08afad604560d02bc0bdac57c2e64561b41e036c33aa97f1ccffc4f3d` |
| `corpus/p38-src-code-ua.md` | `78c069eae85f6ddff14a249d05e3f640a1fd0210d0ef5117f8e5fbc63a54c478` |
| `corpus/p38-src-contradiction-canonical.md` | `ad26827f1728789f77c645c4a773261b23ccd11987ab50ad76b4a35483305e59` |
| `corpus/p38-src-contradiction-raw.md` | `4ab3cda9776457bda38fe49dbed14cfbaffc5332367ac64678b7f336d74f1bc4` |
| `corpus/p38-src-cross-domain.md` | `024fead7cfc087304264a29b8ffb1404c0ba732ee035fbac9f0667232d8d55ed` |
| `corpus/p38-src-decision-current.md` | `f23e14ca7b3827c5cb1f72f64b3a94b95e3a7d04c81eaea6175ce072df940923` |
| `corpus/p38-src-decision-old.md` | `893e9cabd2728942907abec377d46b7cd2303e40bc627b55f12471acfa7bf5c7` |
| `corpus/p38-src-decision-raw.md` | `692ec5410735116a9b0137a636932bbe501f89b2ef8bbcda9739c747ea5bb889` |
| `corpus/p38-src-hard-negative.md` | `953041221895f577ba835d81a760e3fe4136d62667fc8b4ad6db4b014be6814d` |
| `corpus/p38-src-infra-current.md` | `c55d82f3587cd15b25afd8d3666e5ec06eece83410f7e794c3f5baf4f8376fdf` |
| `corpus/p38-src-infra-stale.md` | `e76539faafbddf2edda5c65947e4da584bc313e9c61828a3334a72075da04383` |
| `corpus/p38-src-noise-injection.md` | `51d2e89657ee0f794d43edefe87dfcc75c3ff1e4991628e193044ac976b8ee59` |
| `corpus/p38-src-project-current-ua.md` | `0a2c82a84528dfbbaf5da825bfe4b04bab5ee613adb2ad5497ff12d232c42f49` |
| `corpus/p38-src-project-current.md` | `5a5b8fa65a46a6e015026ffefc4e76cc3bb46ab9287917ce2f22460de359c3e8` |
| `corpus/p38-src-project-raw-chat.md` | `df8b10e45dd223c819a650373f84917a8b03d8ed949670d228ba4cc76f207f7d` |
| `corpus/p38-src-project-superseded.md` | `56c7a6e50f054908410b4acb9a2d9c217a0236ef7e37e2162c3eae98f54d3c00` |
| `corpus/p38-src-research-curated.md` | `ce464c98b9d4d40ef3fedb8753683a172a48cafc9f21eaac9c53336f3579116c` |
| `corpus/p38-src-research-unverified.md` | `c156396d712146854df8c0b4a11b56054c1aa02df59d398a11a12494b1151995` |
| `corpus/p38-src-task-current.md` | `b3f5c0072e4d08baed59a288096c8759f1d64c5df595829466147a799c669512` |
| `corpus/p38-src-task-raw.md` | `b2213109a1d8bb18bc6bdeb3f86cf65aeedac397476dafd9ed3c06b713f35fc9` |

### 3.2 Evaluation Result Artifact

- `artifacts/project-state/phase-5e/phase5e_holdout_v13_epoch.json`: `3565a574e4acec7b31236846089d9ed2f43d9e2333a3448d22ee5637351f71e4`

### 3.3 Protocol and Runtime Artifacts Frozen at R4

- `scripts/benchmark_phase5e_r4.py`: `df2ff71dd5dc4f41fc74817055c8ee341155ba3c4634f4950bb98aff9f7b3500`
- `scripts/phase5e_concept_mapping.py`: `4685f1ae2fda335ee19bec38ba2acb4e651ad0c3285667c2c1b882101bdfc89a`
- `artifacts/project-state/phase-5e/phase5e_runtime_fixture_manifest_v2.json`: `2fb4e40b9d8f91cd3ed98eae8d29bdb8bab6c341066f6924f2599bc6c4c8c699`
- `artifacts/project-state/phase-5e/phase5e_protocol_r4_freeze.json`: `a5c0b05b3ec79fcfd5a15320e8b28ae58aee96a60db2802d2994e637848fdbef`
- `artifacts/project-state/phase-5e/phase5e_development_r4_fast.json`: `97d526e03ea2913bf84c31fc232c40c5f49df744a5697eaee2a6f202353381a1`

## 4. R4 One-Shot Verdict: FAILED VERIFICATION

- **Holdout Execution Date:** 2026-09-18
- **Run Profile:** FAST (CPU-only, no neural weights downloaded)
- **Split:** holdout, 20 queries, 8 owner-backed queries
- **Overall Result:** `all_hard_invariants_pass = false`
- **Failing Invariants:**
  - `authority_winner_missing = 1` (applicable = 8, failures = 1)
  - `authority_outranked_by_relevance = 1` (applicable = 8, failures = 1)
- **Failing Query:** `p38-v13-h20`
  - Query text: "Узгодьте суперечливі твердження про статус проєкту за канонічним записом, відкинувши шумовий блок і застарілий знімок."
  - Expected winner: `p38-src-contradiction-canonical`
  - Shadow return: `01_Projects/corpus/p38-src-project-current-ua.md` (winner_present=false, outranked=1, recall/mrr/ndcg=0.0)

## 5. Root-Cause Input Inventory

The following primary inputs were used for the root-cause adjudication:
1. `h20 query`: `p38-v13-h20` in `benchmarks/power38/retrieval_eval/v1.3/queries.holdout.jsonl`
2. `h20 GT`: `ground_truth.holdout.jsonl` row `p38-v13-h20`
3. `h20 semantic review`: `semantic-review-a-v1.3.json`, `semantic-review-b-v1.3.json`
4. `h20 adjudication`: `semantic-adjudication.json`, `semantic-adjudication.md`
5. `relevant source fixture`: `benchmarks/power38/retrieval_eval/v1.3/corpus/p38-src-contradiction-canonical.md`
6. `R4 fixture manifest`: `artifacts/project-state/phase-5e/phase5e_runtime_fixture_manifest_v2.json`
7. `R4 concept mapping`: `scripts/phase5e_concept_mapping.py`
8. `RetrievalPlanner`: `src/power_framework/core/retrieval_planner.py`
9. `ProjectStateService`: `src/power_framework/core/state_service.py`
10. `TaskService`: `src/power_framework/core/task_service.py`
11. `DecisionService`: `src/power_framework/core/decision_service.py`
12. `governance architecture`: ADR-0007, ADR-0008, `POWER_3.8_CONTEXT_MEMORY_ARCHITECTURE.md`
13. `EvidenceOrderingPolicy`: `src/power_framework/core/context_contracts.py`
14. `Phase 5E acceptance gate`: `artifacts/project-state/phase-5e/PHASE_5E_ADMISSION.md`

## 6. Append-Only Handoff to R5

1. **R4 Dataset Disposition:** `v1.3` is permanently burned as a fresh holdout. It is retained strictly as regression and development historical evidence.
2. **R5 Remediation Mandate:** Remediate root cause defects according to architecture principles (Section 2 & 3). Do not patch production to fit h20 specifically.
3. **Future Fresh Holdout:** When authoring a fresh holdout, use an allowlisted blind bundle, ensure legitimate owner mapping (no fabricated runtime owners for non-runtime policy concepts), and use the canonical revision naming admitted in R5A.
