# POWER 3.7.10 post-release evidence

This directory contains sanitized, content-free evidence collected after the
published `v3.7.10` release snapshot. It is not part of the `v3.7.10` release
asset set and does not replace or rewrite any published asset, tag, receipt, or
SBOM.

The evidence separates the signed release source from the later protected-main
merge commits and records public GitHub, registry, attestation, and clean-room
runtime readbacks. Hashes, public identifiers, URLs, versions, statuses, and
content-free summaries are retained; credentials, authorization material,
private vault content, and unrelated host inventory are intentionally excluded.

The PRXMX section is explicitly `BLOCKED_AUTHORIZATION` because this WS session
had no permitted read-only remote transport. Historical local claims are not
used as a substitute for that required remote audit.

The signed release boundary and observed source snapshot are:

```text
tag: v3.7.10
tag object: 440a589572ba42867af92e6215a8ca4e1f8b3153
release source: f6cdaa35b552ed0a335051f2f268f57d52302161
source tree: 0f6a5e399bd3a78792a6c5fab983a2136cb2b335
```
