# Semantic adjudication — retrieval evaluation v1.1

This is the human-readable companion to `semantic-adjudication.json`. It is
content-addressed by the active manifest's `semantic_adjudication_digest` and
is included in the active `dataset_digest` through that JSON artifact.

## Method and decision rules

- Reviewer A and Reviewer B independently read the 40 queries, 40 ground-truth
  records, all 20 source bodies, source metadata, scenario families, and the
  Phase 5 planning contracts. They did not see each other's verdicts.
- Their bounded input receipts are `semantic-review-a-v1.1.json` (SHA-256
  `fd506348b4862d2194015cf0661027d98262a3d380b4208b8d1624070aa2c985`) and
  `semantic-review-b-v1.1.json` (SHA-256
  `14a4549f67b6efc40489a5e708fd0eafa35f464f94e5aa7d1153969db783c7b7`).
- The orchestrator then compared both reports with the primary fixtures. A
  disagreement was resolved from query wording, declared intent/categories,
  scenario family, source metadata, ground-truth reason/outcomes, and source
  content—not by majority vote.
- No search result, score, embedding, model, router, threshold, or retrieval
  metric was used. The correction happened before Phase 5B implementation.
- Quarantine cases have `temporal_expectation: not_applicable` because they ask
  about handling/disposition, not source time; this preserves the source metadata
  value `temporal_state: unknown`.
- Authority ordering does not erase query intent. First select the answer set
  requested by the query; then apply authority, temporal, supersession, and
  contradiction policy within that set. A diagnostic query may intentionally
  identify stale, hard-negative, or unverified evidence without promoting it.

Abbreviations in the matrix: `R` relevant, `X` excluded, `W` authority winner,
`D` disposition, `T` temporal expectation, and `G` graded relevance/outcome.
All source IDs are complete POWER fixture IDs after the `p38-src-` prefix is
omitted only for readability.

## Rationale reference map

Each machine-readable `rationale_ref` resolves to the corresponding matrix row
above; keeping the map explicit prevents an opaque reference from silently
losing its human-reviewable basis.

| RATIONALE_REF | QUERY_ID |
|---|---|
| adjudication-r01 | p38-dev-q01 |
| adjudication-r02 | p38-dev-q02 |
| adjudication-r03 | p38-dev-q03 |
| adjudication-r04 | p38-dev-q04 |
| adjudication-r05 | p38-dev-q05 |
| adjudication-r06 | p38-dev-q06 |
| adjudication-r07 | p38-dev-q07 |
| adjudication-r08 | p38-dev-q08 |
| adjudication-r09 | p38-dev-q09 |
| adjudication-r10 | p38-dev-q10 |
| adjudication-r11 | p38-dev-q11 |
| adjudication-r12 | p38-dev-q12 |
| adjudication-r13 | p38-dev-q13 |
| adjudication-r14 | p38-dev-q14 |
| adjudication-r15 | p38-dev-q15 |
| adjudication-r16 | p38-dev-q16 |
| adjudication-r17 | p38-dev-q17 |
| adjudication-r18 | p38-dev-q18 |
| adjudication-r19 | p38-dev-q19 |
| adjudication-r20 | p38-dev-q20 |
| adjudication-r21 | p38-ho-q01 |
| adjudication-r22 | p38-ho-q02 |
| adjudication-r23 | p38-ho-q03 |
| adjudication-r24 | p38-ho-q04 |
| adjudication-r25 | p38-ho-q05 |
| adjudication-r26 | p38-ho-q06 |
| adjudication-r27 | p38-ho-q07 |
| adjudication-r28 | p38-ho-q08 |
| adjudication-r29 | p38-ho-q09 |
| adjudication-r30 | p38-ho-q10 |
| adjudication-r31 | p38-ho-q11 |
| adjudication-r32 | p38-ho-q12 |
| adjudication-r33 | p38-ho-q13 |
| adjudication-r34 | p38-ho-q14 |
| adjudication-r35 | p38-ho-q15 |
| adjudication-r36 | p38-ho-q16 |
| adjudication-r37 | p38-ho-q17 |
| adjudication-r38 | p38-ho-q18 |
| adjudication-r39 | p38-ho-q19 |
| adjudication-r40 | p38-ho-q20 |

## Complete 40-query adjudication matrix

| QUERY_ID | QUERY_GOAL | EXPECTED_ANSWER_CLASS | GT_CURRENT | SEMANTIC_ALIGNMENT | ACTION | RATIONALE | REVIEWER_A | REVIEWER_B | FINAL STATUS |
|---|---|---|---|---|---|---|---|---|---|
| p38-dev-q01 | current project status in Ukrainian | PROJECT_STATE/current | R project-current-ua; T current | PASS | KEEP_QUERY_KEEP_GT | UA canonical body states the current Phase 5A boundary. | PASS | PASS | PASS |
| p38-dev-q02 | authoritative current phase status | PROJECT_STATE/authoritative-current | R/W project-current; G project-current 3/prefer, project-raw-chat 1/do_not_cite; T current | PASS | KEEP_QUERY_KEEP_GT | Canonical current state outranks raw chat. | PASS | PASS | PASS |
| p38-dev-q03 | current decision on holdout tuning | DECISION/current-successor | R/W decision-current; X decision-old 0/exclude; T current | PASS | KEEP_QUERY_KEEP_GT | Current no-tuning decision supersedes the provisional preview. | PASS | PASS | PASS |
| p38-dev-q04 | ready canonical task for corpus verification | TASK/canonical-ready | R task-current; T current | PASS | KEEP_QUERY_KEEP_GT | Task body explicitly says ready and read-only. | PASS | PASS | PASS |
| p38-dev-q05 | required canonical byte serialization rule | CODE/serialization | R code-en; T current | PASS | KEEP_QUERY_KEEP_GT | English code fixture directly states the serialization rule. | PASS | PASS | PASS |
| p38-dev-q06 | current infrastructure policy rather than stale policy | INFRASTRUCTURE/current-not-stale | R/W infra-current; X infra-stale 0/exclude; T current | PASS | KEEP_QUERY_KEEP_GT | Query explicitly asks for current, not the archived host assumption. | PASS | PASS | PASS |
| p38-dev-q07 | curated research practice for split integrity | RESEARCH/curated | R research-curated; T current | PASS | KEEP_QUERY_KEEP_GT | Curated body states disjoint families, queries, and reproducible proof. | PASS | PASS | PASS |
| p38-dev-q08 | relation between task verification and resource policy | CROSS_DOMAIN/verified-relation | R cross-domain; T current | PASS | KEEP_QUERY_KEEP_GT | Verified projection directly joins the three admission concerns. | PASS | PASS | PASS |
| p38-dev-q09 | authoritative side of the tuning contradiction | CONTRADICTION/canonical-outcome | R/W contradiction-canonical; G contradiction-canonical 3/prefer, contradiction-raw 1/report_conflict; T conflicted | PASS | KEEP_QUERY_KEEP_GT | Canonical outcome wins while raw conflict remains diagnostic evidence. | PASS | PASS | PASS |
| p38-dev-q10 | whether prompt-injection text is valid evidence | NOISE/PROMPT_INJECTION/quarantine | R none; X noise-injection 0/quarantine; D QUARANTINE; T not_applicable | PASS | CHANGE_GROUND_TRUTH | Disposition is quarantine; no temporal view is requested by the diagnostic query. | AMBIGUOUS | AMBIGUOUS | PASS |
| p38-dev-q11 | real current project rather than hard negative | PROJECT_STATE/current-hard-negative | R/W project-current; X hard-negative 0/exclude; T current | PASS | KEEP_QUERY_KEEP_GT | Query explicitly rejects the similarly named distractor. | PASS | PASS | PASS |
| p38-dev-q12 | whether raw chat can override canonical decision | DECISION/authority-before-similarity | R/W decision-current; G decision-current 3/prefer, decision-raw 1/do_not_cite; T current | PASS | KEEP_QUERY_KEEP_GT | Authority ordering precedes semantic similarity. | PASS | PASS | PASS |
| p38-dev-q13 | current source that supersedes provisional wording | PROJECT_STATE/current-successor | R/W project-current; X project-superseded 0/exclude; T current | PASS | KEEP_QUERY_KEEP_GT | Current source explicitly supersedes the historical wording. | PASS | PASS | PASS |
| p38-dev-q14 | whether injected text may change retrieval scope | NOISE/PROMPT_INJECTION/quarantine | R none; X noise-injection 0/quarantine; D QUARANTINE; T not_applicable | PASS | CHANGE_GROUND_TRUTH | Injection cannot change policy or scope; the query requests no temporal view. | AMBIGUOUS | AMBIGUOUS | PASS |
| p38-dev-q15 | handling of a quarantined synthetic message | NOISE/quarantine-preserve | R none; X noise-injection 0/quarantine; D QUARANTINE; T not_applicable | PASS | CHANGE_GROUND_TRUTH | Quarantine preserves evidence and does not authorize deletion; time is not requested. | AMBIGUOUS | AMBIGUOUS | PASS |
| p38-dev-q16 | curated research source rather than unverified claim | RESEARCH/curated-not-unverified | R/W research-curated; X research-unverified 0/exclude; T current | PASS | KEEP_QUERY_KEEP_GT | Query asks for curated evidence, not promotion of the proposed claim. | PASS | PASS | PASS |
| p38-dev-q17 | record explaining contradiction and canonical outcome | CONTRADICTION/canonical-with-raw-context | R/W contradiction-canonical; G raw 1/report_conflict; T conflicted | PASS | KEEP_QUERY_KEEP_GT | Canonical resolution and retained raw conflict are both represented. | PASS | PASS | PASS |
| p38-dev-q18 | canonical-byte rule in Ukrainian | CODE/UA-serialization | R code-ua; T current | PASS | KEEP_QUERY_KEEP_GT | UA code fixture directly answers the query. | PASS | PASS | PASS |
| p38-dev-q19 | host-neutral resource profile | INFRASTRUCTURE/host-neutral-profile | R infra-current; T current | PASS | CHANGE_GROUND_TRUTH | The current infrastructure body, not the cross-domain projection, states host-neutrality. | AMBIGUOUS | DEFECT | PASS |
| p38-dev-q20 | cross-domain admission-package relation | CROSS_DOMAIN/verified-projection | R cross-domain; T current | PASS | REWRITE_QUERY | Wording now names the verified package contents, removing the task-vs-projection ambiguity while retaining the GT. | AMBIGUOUS | AMBIGUOUS | PASS |
| p38-ho-q01 | current POWER 3.8 gate in Ukrainian | PROJECT_STATE/current | R project-current-ua; T current | PASS | KEEP_QUERY_KEEP_GT | UA canonical current-state fixture directly answers. | PASS | PASS | PASS |
| p38-ho-q02 | current authoritative project projection | PROJECT_STATE/authoritative-current | R/W project-current; G raw-chat 1/do_not_cite; T current | PASS | KEEP_QUERY_KEEP_GT | Canonical projection is authoritative; raw chat is non-citable. | PASS | PASS | PASS |
| p38-ho-q03 | frozen decision replacing provisional policy | DECISION/current-successor | R/W decision-current; X decision-old 0/exclude; T current | PASS | KEEP_QUERY_KEEP_GT | Current decision replaces the provisional holdout preview. | PASS | PASS | PASS |
| p38-ho-q04 | canonical task for evaluation verification | TASK/canonical-ready | R task-current; T current | PASS | KEEP_QUERY_KEEP_GT | The task fixture directly names the required verification. | PASS | PASS | PASS |
| p38-ho-q05 | runtime digest normalization | CODE/serialization | R code-en; T current | PASS | KEEP_QUERY_KEEP_GT | English code fixture directly states normalization. | PASS | PASS | PASS |
| p38-ho-q06 | current infrastructure record instead of old host assertion | INFRASTRUCTURE/current-not-stale | R/W infra-current; X infra-stale 0/exclude; T current | PASS | REWRITE_QUERY | Original wording asked for stale evidence while GT intentionally selected current; wording now asks for the current record. | DEFECT | DEFECT | PASS |
| p38-ho-q07 | curated research record for disjointness rules | RESEARCH/curated | R research-curated; T current | PASS | KEEP_QUERY_KEEP_GT | Curated fixture states the disjointness rules. | PASS | PASS | PASS |
| p38-ho-q08 | governance/task/infrastructure link without authority merge | CROSS_DOMAIN/verified-relation | R cross-domain; T current | PASS | KEEP_QUERY_KEEP_GT | Verified projection covers all three domains and keeps authority orthogonal. | PASS | PASS | PASS |
| p38-ho-q09 | canonical winner in tuning-access conflict | CONTRADICTION/canonical-outcome | R/W contradiction-canonical; G raw 1/report_conflict; T conflicted | PASS | KEEP_QUERY_KEEP_GT | Canonical ledger resolves the conflict while retaining raw evidence. | PASS | PASS | PASS |
| p38-ho-q10 | whether injection is valid retrieval evidence | NOISE/PROMPT_INJECTION/quarantine | R none; X noise-injection 0/quarantine; D QUARANTINE; T not_applicable | PASS | CHANGE_GROUND_TRUTH | Quarantine is the disposition; the query does not request source temporal validity. | AMBIGUOUS | AMBIGUOUS | PASS |
| p38-ho-q11 | current project despite keyword hard negative | PROJECT_STATE/current-hard-negative | R/W project-current; X hard-negative 0/exclude; T current | PASS | REWRITE_QUERY | Original wording asked for the distractor while GT intentionally selected current; wording now asks for the current project. | DEFECT | DEFECT | PASS |
| p38-ho-q12 | whether raw evidence can override canonical decision | DECISION/authority-before-similarity | R/W decision-current; G raw 1/do_not_cite; T current | PASS | KEEP_QUERY_KEEP_GT | Raw similarity cannot override canonical decision authority. | PASS | PASS | PASS |
| p38-ho-q13 | current source superseding old project record | PROJECT_STATE/current-successor | R/W project-current; X project-superseded 0/exclude; T current | PASS | KEEP_QUERY_KEEP_GT | Current source is explicitly the superseding record. | PASS | PASS | PASS |
| p38-ho-q14 | whether scope-changing injection is usable | NOISE/PROMPT_INJECTION/quarantine | R none; X noise-injection 0/quarantine; D QUARANTINE; T not_applicable | PASS | CHANGE_GROUND_TRUTH | Injection cannot change policy or scope; the query requests no temporal view. | AMBIGUOUS | AMBIGUOUS | PASS |
| p38-ho-q15 | whether quarantine implies deletion | NOISE/quarantine-preserve | R none; X noise-injection 0/quarantine; D QUARANTINE; T not_applicable | PASS | CHANGE_GROUND_TRUTH | Quarantine is non-destructive and preserves the source; time is not requested. | AMBIGUOUS | AMBIGUOUS | PASS |
| p38-ho-q16 | curated evidence when another claim is unverified | RESEARCH/curated-not-unverified | R/W research-curated; X research-unverified 0/exclude; T current | PASS | REWRITE_QUERY | Original wording asked for the unverified note while GT selected curated; wording now asks for curated evidence. | DEFECT | DEFECT | PASS |
| p38-ho-q17 | canonical record resolving raw contradiction | CONTRADICTION/canonical-with-raw-context | R/W contradiction-canonical; G raw 1/report_conflict; T conflicted | PASS | KEEP_QUERY_KEEP_GT | Canonical resolution is selected and raw conflict remains reportable. | PASS | PASS | PASS |
| p38-ho-q18 | UTC normalization in UA code fixture | CODE/UA-serialization | R code-ua; T current | PASS | KEEP_QUERY_KEEP_GT | UA code fixture directly answers. | PASS | PASS | PASS |
| p38-ho-q19 | record stating host facts are deployment evidence only | INFRASTRUCTURE/host-neutral-profile | R infra-current; T current | PASS | CHANGE_GROUND_TRUTH | That exact policy sentence is in the current infrastructure fixture; the projection only mentions an abstract profile. | DEFECT | DEFECT | PASS |
| p38-ho-q20 | cross-domain admission-package relation | CROSS_DOMAIN/verified-projection | R cross-domain; T current | PASS | REWRITE_QUERY | Wording now names the verified projection and package contents, removing the task-vs-projection ambiguity while retaining the GT. | AMBIGUOUS | AMBIGUOUS | PASS |

## Source-fixture review inventory

All 20 source fixtures were read in full and checked against title, body,
frontmatter metadata, authority, trust/lifecycle, temporal state, domains,
digest. `source_corpus_digest` is unchanged from v1.

| SOURCE_ID | AUTHORITY / TRUST | TEMPORAL | DOMAINS | SEMANTIC ROLE |
|---|---|---|---|---|
| p38-src-project-current | canonical / CANONICAL | current | governance, project-state | current EN project state |
| p38-src-project-current-ua | canonical / CANONICAL | current | governance, project-state | current UA project state |
| p38-src-project-raw-chat | unknown / RAW | current | agent-conversations, project-state | non-authoritative chat distractor |
| p38-src-project-superseded | verified / SUPERSEDED | stale | project-state | historical project wording |
| p38-src-decision-current | canonical / CANONICAL | current | decisions, governance | current no-tuning decision |
| p38-src-decision-raw | unknown / RAW | current | agent-conversations, decisions | untrusted decision discussion |
| p38-src-decision-old | verified / SUPERSEDED | stale | decisions | provisional decision |
| p38-src-task-current | canonical / CANONICAL | current | governance, tasks | ready read-only verification task |
| p38-src-task-raw | unknown / RAW | current | agent-conversations, tasks | non-authoritative task chat |
| p38-src-code-en | verified / VERIFIED | current | code | EN canonical-byte contract |
| p38-src-code-ua | verified / VERIFIED | current | code | UA canonical-byte contract |
| p38-src-infra-current | canonical / CANONICAL | current | governance, infrastructure | host-neutral resource policy |
| p38-src-infra-stale | curated / ARCHIVED | stale | infrastructure | stale host-specific policy |
| p38-src-research-curated | curated / CURATED | current | research | curated split-integrity evidence |
| p38-src-research-unverified | unverified / PROPOSED | current | research | explicitly unverified hard negative |
| p38-src-contradiction-canonical | canonical / CANONICAL | current | decisions, governance | canonical conflict resolution |
| p38-src-contradiction-raw | unverified / RAW | current | agent-conversations, governance | retained conflicting raw evidence |
| p38-src-noise-injection | unknown / QUARANTINED | unknown | agent-conversations, governance | inert prompt-injection/noise fixture |
| p38-src-hard-negative | curated / CURATED | current | projects | similarly named project distractor |
| p38-src-cross-domain | verified / VERIFIED | current | governance, infrastructure, project-state, tasks | verified multi-domain projection |

The source fixture bodies remain identical to v1. The source metadata sidecar is
also byte-identical; only the new revision's query/ground-truth/adjudication
artifacts differ.
