# P.O.W.E.R. roadmap: 3.9 and beyond

**Status:** This is a reviewable proposal, not evidence of shipped features or a release schedule; [STATUS](STATUS.md) and the accepted ADRs retain their authority until changed separately.

[Український додаток](ROADMAP-3.9-and-beyond.ua.md) preserves background and prior proposals; reconcile any discrepancy with this English entry and the authoritative documents.

## Scope and terms

- **Edge:** a locally operated node that can work without a hub or cloud.
- **Observation:** a bounded candidate fact from work, not automatically trusted memory.
- **Receipt / evidence:** a record of an action or check / material supporting a claim; neither grants permission by itself.
- **OpenCode:** one possible local agent client; **QMD:** an optional external retrieval benchmark, not a dependency.

[ADR-0007](../adr/0007-power-3.8-north-star-control-plane-architecture.md) and
[ADR-0008](../adr/0008-phase5d-runtime-contextpack-issuance.md) define existing
authority boundaries. Canonical sources remain authoritative; indexes, caches,
and possible graphs are rebuildable projections. Retrieved text and model output
are untrusted data, never authority to mutate state.

## Separate closeout and pilot

- **3.8 closeout:** verify outstanding work and its actual scope independently.
  [#474](https://github.com/weby-homelab/power-framework/issues/474) concerns
  3.8 MCP scope; its current detailed status needs verification and it is not
  the sole release tracker. Do not infer release readiness from this roadmap.
- **3.7.14:** [#525](https://github.com/weby-homelab/power-framework/issues/525)
  is separate maintenance work, not a dependency of the 3.9 pilot.
- **3.9:** [#523](https://github.com/weby-homelab/power-framework/issues/523)
  and its [milestone](https://github.com/weby-homelab/power-framework/milestone/1)
  track a finite pilot, not the whole long-term release roadmap.

## First: baseline and one narrow path

1. [#526](https://github.com/weby-homelab/power-framework/issues/526) is the
   first task for an implementation PR: reuse the work in
   [#520](https://github.com/weby-homelab/power-framework/issues/520) where
   applicable; version the UA/EN corpus, queries and qrels, and measure a
   reproducible SQLite FTS baseline **before** introducing a queue or graphs.
   Record dataset and software versions, language slices, sample sizes, metrics,
   hardware, failures and uncertainty. QMD is optional and only comparable
   with pinned versions, equivalent scope and reproducible conditions.
2. Alongside early 3.9 work,
   [#527](https://github.com/weby-homelab/power-framework/issues/527) proposes
   a clean Linux non-root wheel install, MCP connection, backup and restore;
   report the exact environment and results. This smoke is not deferred to 3.13.
3. [#528](https://github.com/weby-homelab/power-framework/issues/528) proposes
   one observation → explicit approval → an existing canonical source → lookup
   by a clean client using the smallest suitable existing components. Apply
   existing authorization, sensitivity and secret-handling rules before
   persistence; no raw event or full prompt is promoted automatically.

The first implementation PR should deliver the baseline and/or this thin
pilot, not claim an unbuilt feature. No implementation PR is asserted here.
Issue scope and sequencing remain subject to owner review.

## Gates and conditional architecture

- **Deterministic gates:** protocol and storage contracts, authorization and
  permissions, rebuild and hash checks, crash/restart and duplicate behavior,
  plus rejection without unintended effects. Test failed and unauthorized
  paths as well as successful paths.
- **Statistical LLM evaluation:** pin prompts, model versions, datasets and
  sampling conditions; repeat runs and report separate rates, confidence
  intervals, sample sizes and representative failures. Statistical rates do
  not replace deterministic safety gates or silently override ADR-0007's
  `DUPLICATE_EFFECTFUL_ACTIONS = 0`, `UNAUTHORIZED_MUTATIONS = 0`, and
  `FALSE_DONE = 0` invariants.
- **IndexWorkQueue:** consider it only if crash tests expose a durable-work
  gap and a cheaper correction using existing components cannot close it.
  Any proposal must specify idempotency, recovery and bounded resource use.
- **EvidenceGraph, ExecutionGraph, LocalCAS:** gate each independently on a
  measured consumer need and comparison with simple references or joins.
  Prove rebuild, integrity, access controls and operational cost before
  adopting any of them; a stored reference is not authority to execute.

The existing [STATUS](STATUS.md) names Queue and Graphs for later work; the
conditional sequencing here is a proposal for review, not a silent amendment.

## Later options, not scheduled commitments

- **3.10 candidate:** evidence and handoff across clients, using existing
  records first; any format migration requires a separate compatibility,
  recovery and rollback decision.
- **3.11 option:** temporal validity, supersession and explicit conflicts,
  if a consumer demonstrates a need.
- **3.12 option:** broaden the early multilingual retrieval benchmark and
  candidate baselines under comparable, versioned conditions.
- **3.13 option:** expand the early Linux install and recovery smoke
  into an evidence-backed support matrix; it is not the first install test.
- **3.14 option:** edge-to-edge exchange or a hub only after a separate
  consumer, threat-model and architecture decision. Revocation can remove
  trust, keys or future synchronization; it cannot revoke plaintext or
  offline bytes already copied by a recipient.

None of 3.11–3.14 is a promised feature, release assignment or date. Other
platforms remain governed by the [support matrix](../support-matrix.md) and
their own evidence rather than by the Linux-first ordering above.
