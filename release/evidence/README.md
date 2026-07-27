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
