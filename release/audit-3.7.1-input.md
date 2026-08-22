# POWER 3.7.1 Stable — Stage 0 audit input

Captured: 2026-08-22 (Europe/Kyiv)

This file records the public baseline used for the POWER 3.7.1 stabilization
audit. It intentionally contains no credentials, vault contents, or private
configuration values.

## Public baseline

| Component | Latest public stable | Published source | Public 3.7.x status |
| --- | --- | --- | --- |
| POWER core | `v3.6.7` | `d53cd8e9b718009f393dec03c54e4451e78853bb` | No public `v3.7.0` or `v3.7.1` tag/release |
| POWER GUI | `v0.7.5` | `7397ab6cab92cc54b9ac5a54d78b61acad22dd78` | No public GUI candidate equivalent for the 3.7.1 pair |

Public references:

- [POWER v3.6.7 release](https://github.com/weby-homelab/power-framework/releases/tag/v3.6.7)
- [GUI v0.7.5 release](https://github.com/weby-homelab/ai-second-brain-gui/releases/tag/v0.7.5)
- [POWER release workflow run](https://github.com/weby-homelab/power-framework/actions/runs/32525805600)
- [GUI publish workflow run](https://github.com/weby-homelab/ai-second-brain-gui/actions/runs/32526751797)

The public baseline therefore does not support a claim that POWER 3.7.1 is
already released. Any 3.7.1 result remains a candidate until immutable source
tags, artifacts, publication readback, and the exact core/GUI pair are proven.

## Candidate under audit

| Item | Candidate value |
| --- | --- |
| Core branch | `stabilize/power-3.7.1` |
| Core audit branch HEAD | `80381b33b4d2dca71ec6a3841734b5dcddedf960` |
| Core package source bound in the candidate manifest | `be1496ae067ee66075a969335afafe315a4ac669` |
| GUI branch | `stabilize/power-gui-3.7.1` |
| GUI package source bound in the candidate manifest | `334d7b388b9ed33a2881f1aecd494ef567975ac2` |
| Candidate suite | POWER `3.7.1` + GUI `0.7.6` |
| Candidate Python range | `>=3.13,<3.15` |
| Candidate publication | Pending; no stable tag, public artifact pair, or immutable container digest |

The candidate deliberately skips a fabricated `v3.7.0`. The manifest uses
`tag: null` and `stable_readback: false` until the release workflow creates and
publishes the real immutable pair.

## Stage 0 decisions

1. Treat `v3.6.7` / `v0.7.5` as the only public stable baseline.
2. Treat all 3.7.1 artifacts, local installs, and branch commits as candidate
   evidence only.
3. Require the exact suite manifest, source/artifact/public-readback identity,
   and release receipt before any stable claim.
4. Keep secrets in `/root/gemma/.env`; this audit input does not copy or expose
   them.

