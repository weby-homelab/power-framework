# POWER 3.8 Phase 5A Evaluation Corpus v1 Erratum

## Status

This is an append-only correction record. The historical Phase 5A report is not
rewritten. Its CodeRabbit classification of the holdout q06/q11/q16 finding as
non-actionable remains historical evidence and is corrected here.

```text
PHASE_5A_RUNTIME_CONTRACTS: CLOSED / MERGED / VERIFIED
HISTORICAL_V1: RETAINED / STRUCTURALLY VALID / SEMANTIC ERRATUM
CORRECTED_REVISION: v1.1 / CANDIDATE FOR PROTECTED ADMISSION
PHASE_5B: BLOCKED / NOT STARTED
```

## Independent finding and adjudication

Two independent read-only reviewers audited all 40 query/ground-truth pairs,
all 20 source bodies, all source metadata, scenario families, language strata,
and the architecture/acceptance contracts. The orchestrator reconciled their
reports against the primary fixtures. No search output, retrieval score,
embedding, model, router, threshold, or metric was observed.

The original CodeRabbit finding was valid for the holdout variants:

| Query | Original wording | Original GT direction | Adjudicated action |
|---|---|---|---|
| `p38-ho-q06` | `Яка note про host-specific policy є historical stale?` | prefer `p38-src-infra-current`; exclude `p38-src-infra-stale` | rewrite query toward current policy |
| `p38-ho-q11` | `Which project note is a keyword-matching hard negative?` | prefer `p38-src-project-current`; exclude `p38-src-hard-negative` | rewrite query toward current project |
| `p38-ho-q16` | `Which research note is explicitly unverified?` | prefer `p38-src-research-curated`; exclude `p38-src-research-unverified` | rewrite query toward curated evidence |

The corrected, independent holdout wording is:

| Query | Corrected wording | GT retained |
|---|---|---|
| `p38-ho-q06` | `Який current infrastructure record треба обрати замість старого host-specific твердження?` | current infrastructure |
| `p38-ho-q11` | `Which project record is authoritative and current despite a keyword-matching hard negative?` | current project |
| `p38-ho-q16` | `Which research record is suitable as curated evidence when another claim is explicitly unverified?` | curated research |

The change preserves the holdout query IDs, language stratum, scenario-family
identity, and exact normalized-query disjointness. The authoritative/current
ground-truth rows were not inverted; the accidental inversion was in the
holdout wording.

## Additional defect found by the full 40-query audit

Both q19 queries asked for the host-neutral/current infrastructure rule, but
both ground-truth rows selected the cross-domain projection. The exact answer
is in `p38-src-infra-current`:

> The framework uses abstract resource profiles. Host names and GPU facts are
> deployment evidence, not runtime policy constants.

The cross-domain fixture only mentions an abstract resource profile as part of a
larger admission package; it does not state the host-facts rule. Therefore:

- `p38-dev-q19` GT now prefers `p38-src-infra-current` and has no exclusion;
- `p38-ho-q19` GT now prefers `p38-src-infra-current` and has no exclusion;
- both affected GT reasons and provenance digests were regenerated;
- query wording and source fixtures were not changed for q19.

Two additional ambiguous designs were corrected without using implementation
output:

| Query rows | v1 issue | v1.1 correction |
|---|---|---|
| `p38-dev-q10/q14/q15`, `p38-ho-q10/q14/q15` | quarantine disposition paired with `temporal_expectation: current` while source metadata is `temporal_state: unknown` | set temporal expectation to `not_applicable`; quarantine/preservation remains unchanged |
| `p38-dev-q20` | “Який ready task пов'язаний із project verification?” was narrower than the cross-domain GT intent | `Який verified record об'єднує read-only contract tests, frozen corpus verifier та abstract resource profile?` |
| `p38-ho-q20` | “Який task пов'язує read-only verification із current state?” left task-vs-projection scope implicit | `Який cross-domain projection містить verifier, frozen corpus та abstract resource profile як один bounded package?` |

The q20 GT rows remain the cross-domain projection. The six noise GT rows and
both q20 rows have canonical v1.1 provenance digests; all active GT provenance
digests use the revision-bound formula documented below.

This is a second semantic defect family beyond the three originally reported
holdout rows. The full adjudication matrix, reviewer statuses, and rationale
references are in `benchmarks/power38/retrieval_eval/v1.1/semantic-adjudication.md`
and its machine-readable companion.

## Resolved review ambiguities

The reviewers conservatively marked both-split q10/q14/q15 and q20 as
ambiguous. Primary-fixture adjudication resolved them without a product
decision:

- q10/q14/q15 correctly quarantine and preserve the inert noise fixture. Their
  temporal expectation is corrected to `not_applicable`: these diagnostic
  queries do not request source time, and the source metadata
  `temporal_state: unknown` is preserved.
- q20 is intentionally a cross-domain relation case. Its wording is clarified
  to name the verified admission-package projection, while its declared
  `intent: cross_domain`, project/task categories, multi-domain metadata, and
  `cross-domain verified record` reason remain unchanged.

These resolutions are recorded as `PASS` in the v1.1 semantic artifact. They do
not change authority or trust semantics: a diagnostic query may identify stale,
hard-negative, or unverified evidence, while canonical authority still wins
when the query asks for authoritative current truth.

## Digest evidence

### Historical admitted v1 — unchanged

The v1 verifier passed before and after candidate construction. Its logical
digests remain:

```text
DATASET_DIGEST: 179ac7ee8d2e8ec0d5e0924cb322d32783da8ae1fdff379ecb0bfa7e0afc53b0
SOURCE_CORPUS_DIGEST: 3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118
QUERY_SET_DIGEST: 7e2c0aaf8e0b3940bfa97c949781ade43fc4d67709634f2fcf3f08016fe1b086
DEVELOPMENT_DIGEST: 29b4ff596a2a125cfb2a3be54a17570cc10a88051bf5b379d5e2472c481e9289
HOLDOUT_DIGEST: ef6f122eefe9f4482d016a05a35422e11f0b120be2a64ad08d7ce661bad6721a
DISJOINTNESS_DIGEST: 554ca3a962beb09c2f7e9afe0bebea19ca79b62d77378959082ab1cfc5ad4275
```

The 29-file per-byte baseline and comparison method are recorded in
`v1-immutability-proof.json`. `v1/` was not edited, deleted, renamed, or
rehashed in place.

### Corrected v1.1 candidate

```text
CORPUS_REVISION: v1.1
SCHEMA: power.retrieval-eval.v1
SUPERSEDES: v1 for future Phase 5 evaluation
SOURCE_CORPUS_DIGEST: 3a71c3d691cb1f3557b43f88a0717bf256479d74ff8d27e2b5f2cb5ba7de6118
DATASET_DIGEST: d3e9f0c0697e18572d9149a9c38bf6b02b72b44927d0fab481bd9cd74203fc4d
QUERY_SET_DIGEST: b3fdf772c6b744495a503651c5ceecc0302bd3d34c00e1f12e2f014c5797be3e
DEVELOPMENT_DIGEST: 4bcd6c464b212e771517e71d3fdb7d696efbf0ec5521117dc7e8e7ce9ddaeb95
HOLDOUT_DIGEST: 61aa9d85ab0804308c008635814cb79218b7e6cc3c78d331ca4b8d4656b5f551
DISJOINTNESS_DIGEST: cf8054395040f17e4d21a005e248b7804fd515cc555b12b52b0afca0f32376d4
SEMANTIC_ADJUDICATION_DIGEST: 0c1c2b32cb6ad84413dddfc93fe73777a37ba735468614a49afd97fc11784c48
SEMANTIC_ADJUDICATION_MARKDOWN_DIGEST: 7ee822bdb11db3497bf0057fe1df3a4aa9eb5ddfa44ce1e5db191bf5f3f24c60
GROUND_TRUTH_PROVENANCE_DIGEST: f307f47eb2eea70942fb114e5a41819db44bd9a614251946ef4e530118953b6c
HOLDOUT_ACCESS_RECEIPT_DIGEST: e0ecf2220e0db401c83366d0980b04b948596fe344794e871acc791f0207a997
REVIEWER_A_RECEIPT_DIGEST: 8d19e3c56ee2d85062ccebcbb6397dd0a8de7ec62c4a1df14d0a3630b15dc158
REVIEWER_B_RECEIPT_DIGEST: 14a4549f67b6efc40489a5e708fd0eafa35f464f94e5aa7d1153969db783c7b7
```

The semantic-adjudication JSON and the exact SHA-256 of its Markdown rationale
are included in `dataset_digest`; this is a deliberate revision of the v1
dataset-digest coverage and is declared in the v1.1 README and manifest. The
source corpus digest remains equal because source bytes and source metadata
remain equal. In v1.1 each ground-truth `provenance_digest` is the canonical
SHA-256 of `{revision, ground_truth-without-provenance_digest}`.

## Integrity versus semantics

The offline verifier proves structural validity, source-byte integrity,
reference safety, digest reproducibility, split disjointness, coverage, and
receipt binding. It cannot mathematically prove natural-language entailment:

```text
STRUCTURAL INTEGRITY != SEMANTIC ADJUDICATION
```

The v1.1 semantic pass therefore requires the deterministic verifier **plus**
two independent semantic reviews **plus** orchestrator primary-fixture
adjudication. Digest validation alone is not a future retrieval-quality claim.

## Impact

```text
RUNTIME_CONTRACTS: NO IMPACT
INTEGRITY_VERIFIER_CORRECTNESS: NO IMPACT (revision-aware extension only)
CRYPTOGRAPHIC_REPRODUCIBILITY: PRESERVED
SEMANTIC_EVALUATION_VALIDITY: IMPACTED / CORRECTED
FUTURE_ROUTING_RETRIEVAL_METRICS: IMPACTED / MUST USE v1.1
```

The correction occurred before Phase 5B implementation. No retrieval metric was
observed, no router threshold existed, and no algorithm output influenced a
query or ground-truth decision.
