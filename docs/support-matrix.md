# P.O.W.E.R. platform support matrix

This matrix is the operational boundary for the `v3.7.10` patch release contract. It
separates automated lifecycle coverage from model-backed, physical-host, GPU,
and retrieval-quality evidence. A green CI job does not certify a different
host, provider, corpus, or performance envelope.

## Current support boundary

| Platform / environment | Tested now | Conditional | Not certified by this matrix |
| --- | --- | --- | --- |
| Linux, Python 3.13–3.14 | Ubuntu CI runs the full test suite, Ruff, MyPy, documentation and release-contract gates; package smoke runs wheel/sdist outside the checkout. | Dense, reranked, and provider-backed workflows require a local model cache and an actually bound provider. | Host-independent latency, GPU benefit, ANN recall, and reranker quality beyond the published release receipts. |
| macOS | Deferred indefinitely for `v3.7.10`; no macOS CI or release upgrade evidence is claimed. | No scheduled release target. A future proposal requires a named runner, owner, and fresh receipts. | All macOS compatibility, performance, GPU, dense real-vault, and reranker claims. |
| Hosted Windows CI | Deferred indefinitely for `v3.7.10`; no Windows CI or release upgrade evidence is claimed. | No scheduled release target. A future proposal requires a named runner, owner, and fresh receipts. | All hosted Windows lifecycle, provider, performance, GPU, dense real-vault, and quality claims. |
| Physical Windows 11 25H2 | Deferred indefinitely for `v3.7.10`; the installation guide is informational and is not a release certification. | No scheduled release target. A future proposal requires exact host and artifact receipts. | Physical Windows compatibility, GPU performance, CUDA availability, and latency claims. |

## Official deployment profiles

| Profile | Required runtime | Docker requirement | Canonical-vault contract | Supported scope |
| --- | --- | --- | --- | --- |
| **A — headless / agent server** | One native `power-framework[mcp]` runtime, `power`, required `power-mcp` over stdio, host-side POWER Skill, and one canonical vault. | None. Docker and Web UI are not prerequisites. | Native CLI and MCP use the same vault and `ApplicationService`; no Web container is expected. | Complete POWER installation for FTS and configured local MCP. Semantic/reranked search remains conditional on explicit model/provider evidence. |
| **B — full human + agent server** | Everything in Profile A plus exactly one matching `power-web` image with locked `[web,semantic,rerank]` dependencies. | Required only for the Web UI. | The Web container mounts the same canonical vault read-write for governed proposal/apply, uses the same `ApplicationService`, and stores only rebuildable cache in its named volume. | Authenticated Web UI on host loopback `127.0.0.1:8080`; FTS, semantic, and reranked modes require real non-fallback acceptance; Web MCP services and MCP TCP ports are absent. |

Profile B deployments must provision host-side permissions for the configured
non-root Web UID/GID. Deleting the Web cache must not change Markdown, Git, or
`.power` truth. Remote Web access requires an authenticated reverse proxy,
Tailscale, or an equivalent trusted access layer.

## Evidence rules for agents

- Treat `tested` as lifecycle coverage only. It proves the named command path on
  the named runner and Python version.
- Treat `conditional` as a precondition, not as a successful runtime claim.
  Check `power doctor --json` and require active provider readback before dense
  work.
- Treat `unsupported` or missing evidence as a stop condition. Do not silently
  fall back from an explicitly requested GPU provider to CPU.
- For a real vault, require an immutable generation, complete coverage, a
  content-free retrieval receipt, cold/warm/process/MCP controls, and resource
  attribution before making latency or ranking claims.

## Source of truth

The executable checks live in [CI](https://github.com/weby-homelab/power-framework/blob/main/.github/workflows/ci.yml), the release
workflow is [release.yml](https://github.com/weby-homelab/power-framework/blob/main/.github/workflows/release.yml). Windows procedures remain
outside the supported-platform boundary for `v3.7.10` and have no scheduled
release target.
The roadmap records evidence boundaries and pending gates in
[`ROADMAP_POWER.md`](https://github.com/weby-homelab/knowledge-base/blob/main/01_Projects/ROADMAP_POWER.md).
