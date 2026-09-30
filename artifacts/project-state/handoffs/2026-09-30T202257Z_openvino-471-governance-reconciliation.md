# OPENVINO_471_GOVERNANCE_RECONCILIATION

STAGE: OPENVINO_471_GOVERNANCE_RECONCILIATION
PUBLIC_VERSION: 3.7.13
STARTING_MAIN: e68bc4eacd5d49db451d0f1379299c17c9175ad1
STATE_BASE_SHA: e68bc4eacd5d49db451d0f1379299c17c9175ad1
STATE_BASE_TREE: e612557afeaaf7d2f8c08dd8f10d1dc86f2cc61b
OBSERVED_AT_UTC: 2026-09-30T20:22:57Z

## Acceptance disposition

`OPENVINO_471_CURRENT_KNOWLEDGE_BASE_FULL_REBUILD_ACCEPTANCE` is PASS for the
explicitly authorized frozen private KB snapshot `eb9890057a9ff3507b6818a24ef86eb70750f0ba`
(tree `0e542bb25479ea44410bc53091f78ae21c3765d3`). The measured POWER source is
`22788b17b54b5e9f1a10561e72fbe35ba4e769d4` (tree
`3fc32d0d1330eb9afd35e82f990cc0078489faf6`). Results: 791/791 sources, 5,876
chunks, 100% eligible FTS and dense coverage, zero retries/errors/exclusions,
SQLite integrity PASS, semantic and reranked real results without fallback,
and 83 focused tests passed.

The historical 3,624-note snapshot remains unrecovered and was not used. No
byte-for-byte or performance-comparability claim is made. Criterion 5 is
dispositioned to the merged PR #478 fail-closed provider contract; criterion 8
is not applicable to this explicitly authorized current-snapshot run. The
sanitized acceptance receipt is published at
https://github.com/weby-homelab/power-framework/issues/471#issuecomment-5914573383.

The private KB session record was separately published after the measured run;
that intentional `SOURCE_DRIFT_AFTER_FREEZE` moved private KB `main` to
`c4d8e9f8e029f34db323a23fb455dcdfd28b3ab9` (tree
`e7a37ae2c817134dfee0fd3c4414a7b8942d7588`). It did not replace the frozen
benchmark input or alter the recorded run.

## POWER security base

PR #481 security dependency remediation is CLOSED / MERGED / VERIFIED:

```text
head: feccdd2f469a04656c4ee589f8c5f7eb8f349527
merge: e68bc4eacd5d49db451d0f1379299c17c9175ad1
tree: e612557afeaaf7d2f8c08dd8f10d1dc86f2cc61b
parents: 22788b17b54b5e9f1a10561e72fbe35ba4e769d4, feccdd2f469a04656c4ee589f8c5f7eb8f349527
GitHub signature: verified=true / reason=valid
required checks: 11/11 passed, including security
merged at: 2026-09-30T19:58:31Z
```

The earlier governance PR #480 is based on the pre-security main
`22788b17b54b5e9f1a10561e72fbe35ba4e769d4`; its required `security` check
failed against the vulnerable dependency resolutions then in its lockfile. It
is a stale candidate and must not be merged. The replacement governance PR is
to be based on current protected main `e68bc4eacd5d49db451d0f1379299c17c9175ad1`.

## Signing and publication

The operator explicitly authorized importing the GPG signing key into a
dedicated protected local keyring. The replacement governance commit is to be
signed locally and verified with GPG; no private key material is included in
the repository, handoff, or public evidence. Repository guidance requires a
signed commit, protected PR checks, a normal protected merge, and post-merge
REST readback. No direct `main` write or protection bypass is authorized.

At this handoff timestamp, the replacement governance PR has not yet been
created. Issue #471 remains OPEN pending that signed PR, required-check success,
protected merge, and post-merge readback. Close #471 only after confirming the
merged evidence and that every acceptance criterion is pass or explicitly
dispositioned.

## Next gate and boundary

After governance reconciliation and issue disposition, the next runtime gate is
fresh Phase 5E evaluation authoring in a separate invocation. Phase 5E remains
OPEN / NOT PASSED; no fresh revision, holdout, or one-shot was authored or
executed for this acceptance. Phase 5F remains BLOCKED. Do not start Phase 5E or
Phase 5F in this governance reconciliation.
