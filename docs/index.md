# P.O.W.E.R. Framework 3.6.7

P.O.W.E.R. is a local-first, Git-native toolkit for structured knowledge bases. It combines
P.A.R.A., validated OKF frontmatter, hierarchical indexes, full-text and semantic retrieval,
and an MCP interface for AI agents.

## Start here

- [Clean installation (English)](getting-started.md)
- [Чисте встановлення (українською)](getting-started.ua.md)
- [Windows 11 25H2 installation](windows-11-installation.md)
- [Встановлення на Windows 11 25H2](windows-11-installation.ua.md)
- [Windows 11 25H2 validation after CRLF fix](tests/windows-11-25h2-v3.3.2-validation-fixed.md)
- [Migration from an existing knowledge base](migration-guide.md)
- [Міграція з наявної бази знань](migration-guide.ua.md)
- [MCP client onboarding](mcp-client-onboarding.md)
- [Підключення MCP-клієнтів](mcp-client-onboarding.ua.md)
- [Platform support matrix](support-matrix.md)
- [Матриця підтримки платформ](support-matrix.ua.md)
- [Інвентаризація документації](documentation-inventory.ua.md)

These guides define the current `v3.6.7` candidate artifact contract, use an
isolated virtual environment, and include acceptance checks. Publication is
complete only when the signed tag, wheel, source archive, SBOM, and release
receipts can be read back from GitHub. The
migration guides keep the source immutable, reconcile every file by manifest
and hash, and make cutover reversible.

## Executable contract

- Python 3.13 or 3.14.
- 26 top-level CLI commands; see the [CLI reference](cli.md).
- 20 MCP tools; see the [MCP server reference](mcp-server.md).
- `auto` is the default search profile: verified dense when ready, otherwise
  labelled FTS; `semantic` and `reranked` are explicit opt-ins.
- The generated root index and MCP sub-index operations cover the canonical P.A.R.A.
  directories. Arbitrary source layouts must be mapped during migration.
- The canonical dense backend is `BAAI/bge-m3`; model-backed checks download large artifacts.
  FTS5 works without model downloads.

## Minimal quick start

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install \
  "https://github.com/weby-homelab/power-framework/releases/download/v3.6.7/power_framework-3.6.7-py3-none-any.whl"

power init ./my-vault
power index ./my-vault --strict
power lint ./my-vault
power sync ./my-vault --fts-only
```

On Windows, use the dedicated PowerShell guide rather than translating these POSIX commands.

## Claims and evidence

Historical vault measurements and synthetic benchmarks are useful diagnostics, not universal
performance guarantees. The [POWER 3.1 trust-release baseline](adr/0001-power-3.1-trust-release-baseline.md)
defines the evidence boundary. The [hierarchical-index reports](hierarchical-index-migration.md)
are explicitly preserved as v1.6 historical snapshots.

## More documentation

- [Architecture](architecture.md)
- [Application API v2 and source read model](api/application.md)
- [Security threat model](threat-model.md)
- [POWER 3.6.3 historical release notes](release-3.6.3.md)
- [POWER 3.6.1 release notes](release-3.6.1.md)
- [POWER 3.6.0 release notes](release-3.6.0.md)
- [Windows 11 25H2 validation receipt](tests/windows-11-25h2-v3.3.2-validation-fixed.md)
- [M2 human-evaluation contract](m2-human-evaluation.md)
- [Real-vault retrieval receipt](benchmarks/real-vault-retrieval.md)
- [Changelog](https://github.com/weby-homelab/power-framework/blob/main/CHANGELOG.md)
- [Contributing](contributing.md)

GPLv3 — Built in Ukraine ⚡
