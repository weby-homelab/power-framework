# Phase 5D (P38-WP02) Forensic Erratum — P38-WP02-R1

```text
EVIDENCE_TYPE: phase5d_r1_erratum
CREATED_AT_UTC: 2026-09-17T05:30:00Z
BASE_SHA: 0ea7a92a853c128165f5dcabd9283f5be241263b
TARGET: Phase 5D / P38-WP02 Historical Closure Artifacts
```

## 1. Summary of Errata

| Erratum | Historical Report / Narrative Claim | Live / Correct Verified Fact | Impact & Resolution |
| :--- | :--- | :--- | :--- |
| **F1 (PR #439 Tuple)** | Inconsistent narrative base/head/merge SHAs | base: `6ee9f34a09fdfd02a0122bdac95ae32a5485220f`<br>head: `79888f6f1ccae77b91feb815e6a5bb4d5dc2afec`<br>merge: `b8ee40ae7df2faf40509b6c6760d884e59cac65a`<br>merged_at: `2026-09-16T14:26:19Z` | Re-anchored to exact Git objects. |
| **F2 (PR #440 Tuple)** | Shorthand `c6a9a68a...` or stale tree references | base: `b8ee40ae7df2faf40509b6c6760d884e59cac65a`<br>head: `c6a9a68398ad32cf82ec2af6e838691d43b76aaf`<br>merge: `19bab5a8b23f79a69a54ba110bfbffe7a35f64c8`<br>merged_at: `2026-09-16T19:20:13Z`<br>merge tree: `9071a95b1cfd072a64d008afd488c5c847f374c8` | Correct tuple recorded in canonical handoffs. |
| **F3 (Invalid Base SHA)** | `b8ee40ab1286c12ad12a78f28877bc9da924ebf4` in `phase5d_verification.json` & `PHASE_5D_REPORT.md` | Non-existent Git object. Correct base SHA is `b8ee40ae7df2faf40509b6c6760d884e59cac65a` | Historical files preserved append-only; corrected via this erratum and R1 verification. |
| **F4 (Check Accounting)** | "12/12 required including CodeRabbit" | 11 required status checks in GitHub branch protection. PR-head ran 12 checks (11 required SUCCESS + 1 deploy SKIPPED). CodeRabbit is an optional informational app. | Disaggregate REQUIRED vs OPTIONAL / INFORMATIONAL. |
| **F5 (Byte Limit Drift)** | `MAX_CONTEXT_PACK_BYTES = 256_000` in report | `MAX_CONTEXT_PACK_BYTES = 2_000_000` in runtime (`context_contracts.py`, `context_compiler.py`) | Runtime constant preserved at 2,000,000; report documentation corrected. |

## 2. Immutable Policy Notice

Historical artifacts (`phase5d_verification.json`, `PHASE_5D_REPORT.md`) are not destructively rewritten.
This erratum document serves as the binding authoritative correction record for forensic auditors.
