# POWER v3.3.2 — Windows 11 25H2 validation after CRLF fix

Validation date: 2026-08-08<br>
Result: **TECHNICAL CERTIFICATION PASSED**<br>
Validation target: Windows 11 Home 25H2, OS build `26200.8973`, x64<br>
Runtime: CPython `3.13.5`, `uv 0.11.33`, GitHub CLI `2.97.0`<br>
Visual C++ runtime: x64 `v14.44.35211.00`

## Scope

This receipt records the Windows-tested source/build branch
`fix/windows-release-contract-crlf`. It verifies the CRLF-stable release
contract implementation and the locally built wheel acceptance path.

The immutable public `v3.3.2` tag and its release assets were not changed,
replaced, or reissued. This report therefore does not claim that the original
unchanged public wheel contains the follow-up source fix.

## Host gate

- Windows 11 Home 25H2, OS build `26200.8973`, x64.
- The stale Windows registry `ProductName` value reports Windows 10 Home; the
  authoritative Settings/OS build evidence reports Windows 11 Home 25H2.
- The x64 Visual C++ runtime was present on the validation host.

## Release and source identity

- Immutable tag: `v3.3.2` at commit
  `519bf1dd090f4e05368527b713059e61645405f4`.
- Public wheel SHA-256:
  `6013b4bbf0e82491ec03be7ac944387890aec1ac1ebbfd421879c089801a4a85`.
- Public sdist SHA-256:
  `d2afd14eef0d26d7789babf5968b1fb9036dda5ac709d05161cba33b54777e40`.
- The public release receipt matches both public asset hashes.
- Current `origin/main` base:
  `be86d82068dbb2010ffba9752b0e91cc5c17111a`.
- Fix branch: `fix/windows-release-contract-crlf`.

## Fix applied

The release verifier canonicalizes CRLF to LF before hashing
`release/models.lock.json`, so a Windows checkout is validated against the same
Git-blob content as Linux. `.gitattributes` pins that tracked lock file to LF,
and a regression test covers a Windows-style CRLF checkout copy.

Changed files:

- `.gitattributes`;
- `scripts/verify_release_contract.py`;
- `tests/test_release_contract.py`.

## Gates

- `uv sync --locked --group dev`: PASS.
- `pip check`, `power --version` (`3.3.2`), production imports and ONNX Runtime:
  PASS.
- Ruff check/format, MyPy, documentation drift and release contract: PASS.
- Release contract with `--require-tag`: PASS.
- Immutable tag validated against the exact public release baseline: PASS.
- Full pytest: **747 passed, 14 skipped**, coverage **79%**.
- sdist and wheel build: PASS.
- Linux and Windows GitHub Actions checks for PR #234: PASS.

## Locally built wheel acceptance

The locally built wheel was installed outside the checkout in a clean CPython
3.13.5 environment:

- dependency check, imports and version: PASS;
- clean vault init, ingest, strict index, lint, Markdown and FTS: PASS;
- dense sync on `CPUExecutionProvider`: PASS;
- semantic and reranked search returned the validation note: PASS;
- overwrite-safe Windows rename with `--no-dry-run`: PASS;
- MCP server import preflight: PASS.

Pinned model evidence used by the acceptance run:

- BGE-M3 revision `76a603396f5eb9f03ed51bbab8f4893fcea7b2fe`;
- BGE reranker revision `6f5ff65298512715a1e669753bc754d2bc8f367b`;
- ONNX Runtime provider: `CPUExecutionProvider`.

## Publication boundary

The code fix, regression test, `.gitattributes`, and this sanitized receipt are
published through PR #234. The commit is intentionally unsigned because GPG
signing was unavailable in the Windows environment. Review and merge remain
subject to the normal GitHub workflow.

The public `v3.3.2` release remains immutable. The certification claim applies
to the Windows-tested source/build branch and its locally built wheel, not to an
unmodified public wheel rebuilt from the immutable release tag.
