# POWER 3.8 — Gate P38-G2 Product Identity & Documentation Rebaseline Handoff

```text
HANDOFF_SCHEMA: power.handoff.v2
CREATED_AT_UTC: 2026-09-16T08:48:00Z
GATE: P38-G2 (Product Identity & Documentation Rebaseline)
REPOSITORY: https://github.com/weby-homelab/power-framework
BRANCH: docs/p38-g2-product-identity-documentation
BASE_SHA: 38f656b50da3b2307456f673ed1f77e01e907470
BASE_TREE: ac7c62872f0fe9d1de6d5d0b232aa24ea58509c0
```

---

## 1. Objective & Product Alignment

Gate **P38-G2** rebaselines the Class A, Class B, and Class E product identity and documentation
to fully align with [ADR-0007](../../../docs/adr/0007-power-3.8-north-star-control-plane-architecture.md):

- **Product Identity:** POWER is established as a local-first control plane for verifiable
  AI-assisted software engineering and Linux infrastructure operations.
- **Knowledge Substrate:** Second Brain (Obsidian vault) is explicitly positioned as a
  supported data substrate and memory tier, not the sole or primary product identity.
- **Release Distinction:** Clear separation between current stable release (`v3.7.13`, maintained
  on `release/3.7`) and active development line (`3.8`, targeted on `main`).
- **Core Principles:** Proof Chain (`Goal → Evidence → Plan → Authority → Action → Verification → Receipt → Canonical State`)
  and the Three Authorities (Truth, Action, Completion) prominently documented with core invariants:
  1. `LLM OUTPUT NEVER GRANTS AUTHORITY`
  2. `DERIVED STATE MUST NEVER SILENTLY BECOME CANONICAL AUTHORITY`
- **Feature Matrix:** Clear capability table categorizing features into:
  - Available in 3.7.x (Stable v3.7.13)
  - Merged on Main (`3.8-dev`)
  - Planned for 3.8 (Roadmap)

---

## 2. Invariants & Distinctions

- **Runtime Changes:** None beyond cosmetic metadata strings (`__init__.__doc__`, CLI parser description/version, MCP server instructions).
- **SemVer Discipline:** Package version remains `3.7.11` on `main`; no false SemVer bumps.
- **Byte-Identity:** `skills/power/SKILL.md` and `.agents/skills/power/SKILL.md` are byte-identical.
- **Interface Counts Preserved:** 27 top-level CLI commands and 21 MCP tools accurately declared across all documents.
- **Doc-Drift Check:** 100% passing (`uv run pytest tests/test_doc_drift.py -o addopts=""`).
- **Strict Docs Build:** Clean exit code 0 (`uv run mkdocs build --strict`).
- **Next Step Post-Merge:** Phase 5C admission audit (SearchScope pushdown).

---

## 3. Exact Files Modified

1. `pyproject.toml` (Class E: description & keywords updated)
2. `src/power_framework/__init__.py` (Class E: docstring updated)
3. `src/power_framework/core/cli.py` (Class E: parser description & version updated)
4. `src/power_framework/mcp/power_server.py` (Class E: MCP instructions updated)
5. `README.md` (Class A: complete rewrite of product definition, proof chain, feature table, JSON-LD)
6. `README.ua.md` (Class A: complete Ukrainian rewrite with semantic parity)
7. `docs/index.md` (Class A: control plane rebaseline and ADR-0007 router link)
8. `SECURITY.md` (Class B: expanded to control plane, tool execution, and merged broker boundary)
9. `CONTRIBUTING.md` (Class B: architectural context, ADR-0007, gate discipline)
10. `.agents/AGENTS.md` (Class B: control plane mission, invariants, relative link fix)
11. `docs/architecture.md` (Class B: control plane executive introduction & ADR-0007 reference)
12. `docs/architecture/unified-runtime.md` (Class B: control plane introduction & v3.7.13/3.8 split)
13. `skills/power/SKILL.md` (Class B: repositioned as governed knowledge/context operations)
14. `.agents/skills/power/SKILL.md` (Class B: byte-identical synchronization)
15. `artifacts/project-state/handoffs/2026-09-16T084800Z_p38_g2_product_identity_rebaseline.md` (this file)
