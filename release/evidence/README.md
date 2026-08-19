# Release evidence

## Claim policy

Use `benchmark-manifest.schema.json` for any performance, quality, resource, or
security claim that may be cited in a release. The manifest is intentionally
environment-scoped: it records the source and vault snapshot hashes, model
revisions and runtime file hashes, hardware/cgroup, exact cold/warm commands,
raw artifact checksums, and the claim state.

```bash
python scripts/verify_benchmark_manifest.py --schema-only
python scripts/verify_benchmark_manifest.py benchmark-manifest.json
```

`measured` claims require a clean source tree and retained matching artifacts.
Historical artifacts without a matching manifest are diagnostic only, not a
release guarantee. The governing definitions are in
[`docs/adr/0002-memory-os-principles.md`](../../docs/adr/0002-memory-os-principles.md).

## POWER 3.1 harness

Run the POWER 3.1 harness to create a local JSON evidence artifact:

```bash
PYTHONPATH=src python3 benchmarks/power31/scripts/evaluation/run_release_evaluation.py \
  --timestamp 2026-07-22T00:00:00+00:00 \
  --output release/evidence/power31-evidence.json
PYTHONPATH=src python3 benchmarks/power31/scripts/evaluation/verify_evidence.py \
  release/evidence/power31-evidence.json
```

JSON artifacts are intentionally ignored because each run records the exact
working-tree commit, hardware and model state and should be archived by CI or
the release process, not committed as mutable repository state.

## 3.6.3 candidate boundary

`scripts/generate_release_candidate.py` creates a candidate-only baseline from
the content-free `power.release-validation.v1` receipt plus the current commit
and a SHA-256 of the dirty worktree. Validate it with
`scripts/verify_release_contract.py --candidate --require-worktree-hash`; this
mode is never a final release proof. A publishable 3.6.3 baseline must instead
be generated from a clean signed `v3.6.3` tag and checked with `--require-tag`.

When local technical receipts are available, pass them with
`--phase8-outcome-receipt` and `--phase8-continuity-receipt`; the candidate then
records their hashes and validates their content-free technical contract while
keeping the real-vault and human-quality gates closed.

The tag-bound generator also requires the content-free
`power.release-validation.v1` receipt produced from the release job's JUnit
and coverage JSON artifacts. This prevents a final baseline from inheriting
historical candidate counts from a template; the receipt must report passed
tests, skipped tests, coverage, warning policy, zero skipped mandatory gates,
and hashes of its JUnit, coverage, and executed-gate manifest inputs. The final
baseline additionally binds the generated SPDX SBOM and the aggregate Linux
upgrade receipt produced on the Ubuntu CI runner.

## Optional Phase 8 quality evidence

The synthetic `benchmarks/power35` receipts are technical CI evidence only.
Real-vault and sealed-human evidence are optional quality evaluations and are
not required to publish a stable 3.6.3 tag. If a maintainer wants to make those
additional quality claims, two content-free files can be validated separately:

- `real-vault-receipt.json`, validated by `scripts/verify_phase8_evidence.py`
  for exact source/runtime identity, build/transfer/import/query separation,
  sealed-dataset coverage, outcome metrics and continuity safety thresholds;
- `human-manifest.json`, a hash-bound `m2-v2.1` adjudicated
  `sealed_holdout` manifest validated by
  `benchmarks/human_retrieval/scripts/validate_human_evidence.py`.

`scripts/materialize_phase8_evidence.py` remains an optional local utility for
turning explicitly supplied JSON environment values into mode-`0600` files.
The GitHub release workflow does not call it and does not require private
evidence secrets.

If the human manifest carries an `embedded_artifacts` object, the materializer
also writes only its referenced protocol, receipt, corpus, query, judgment and
qrels files into the same private runner directory. Every referenced artifact
must be present, UTF-8 text, and confined to that directory; malformed or
incomplete embedded artifacts fail closed before evidence is written.

The public repository intentionally contains neither raw vault material nor
private qrels. Their absence limits quality claims but does not block the
technical Linux release.

The release workflow also archives the synthetic outcome and continuity
receipts from the stable `benchmarks/power35` harness and binds their SHA-256
values into the tag-bound baseline. Their v2 schemas also carry release,
commit, tree, clean-state, and worktree-hash identity; candidate and final
baseline generation rejects stale receipts from another checkout. For
`v3.6.3`, the Linux upgrade aggregate is executed on the Ubuntu runner;
macOS and Windows are explicitly deferred and do not appear as supported
platforms in the release artifact. Their deferral has no scheduled release
target. The synthetic receipts prove only technical safety/continuity;
their explicit `real_vault=false` and `human_quality_certification=false`
fields are required and cannot be promoted into quality claims.
