---
type: Resource
title: "Синтетичний приклад code-контракту — українською"
description: "Синтетичний code fixture для canonical serialization."
timestamp: 2026-09-10T08:30:00+00:00
owner: "power38-fixture"
status: active
tags: [power38, synthetic, code]
---

# Canonical bytes

Валідовані enum-значення серіалізуються як стабільні рядки, aware timestamps
нормалізуються до UTC, optional значення опускаються замість null, а UTF-8
compact JSON хешується SHA-256.
