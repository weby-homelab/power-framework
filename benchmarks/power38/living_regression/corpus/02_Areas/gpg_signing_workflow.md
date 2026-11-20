---
type: Area
title: "GPG Signing and Branch Protection"
description: "Cryptographic commit signature verification and protected pull-request merge hygiene"
tags: [gpg, git, signing, branch-protection, merge]
timestamp: 2026-10-11T10:00:00
---

# GPG Signing Workflow

Sign every commit with hardware or keyring key `2D49E810C7F2527E`, verify `git verify-commit HEAD`, enforce signed commits via GitHub branch protection rules, and land changes strictly through reviewed pull requests rather than direct pushes.
