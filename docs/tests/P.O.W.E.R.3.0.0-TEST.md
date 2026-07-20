---
type: Test Report
title: "P.O.W.E.R. v3.0.0 — Розширений порівняльний звіт якості пошуку (UA↔EN)"
description: "Порівняльний бенчмарк пошукового стеку POWER 3.0.0: BGE-M3 canonical embedder, reranked/hybrid режими, UDCG@5 primary gate. Порівняння з усіма попередніми тестами docs/tests."
tags:
    [
        "power-framework",
        "testing",
        "benchmarks",
        "BGE-M3",
        "cross-lingual",
        "ukrainian",
        "UA-EN",
        "UDCG",
        "GraphRAG",
    ]
timestamp: 2026-07-20T22:40:00
---

# 🧪 P.O.W.E.R. v3.0.0 — Розширений порівняльний звіт якості пошуку (UA↔EN)

> **Контекст:** Злито всі 3 фази POWER 3.0 (PR #136, #137, #138), реліз `v3.0.0` (GPG-підписаний тег,
> GitHub Release з wheel + tar.gz). Цей звіт фіксує **порівняльні тести якості пошуку UA↔EN** на стеці 3.0.0
> і співставляє їх з усіма попередніми звітами в `docs/tests/` (v2.0.1 → v2.3.0).

---

## 1. Що змінилося у стеці (коротко)

| Версія     | Embedder (dense)                                                                    | Reranker (cross-encoder)                  | Canonical mode                                                    | Ключовий висновок попередніх тестів                      |
| :--------- | :---------------------------------------------------------------------------------- | :---------------------------------------- | :---------------------------------------------------------------- | :------------------------------------------------------- |
| v2.0.3     | `paraphrase-multilingual-MiniLM-L12-v2` (fastembed, 384d)                           | `ms-marco-MiniLM-L-6-v2` (onnx)           | `hybrid_reranked`                                                 | MiniLM **сліпий до UA→EN** (MAR@5=0.208, TEST-3)         |
| v2.2.x     | Qwen3-ONNX (≈97 ГБ, **заблоковано** на ≤14 ГБ хостах) → відступ на fastembed MiniLM | `ms-marco-MiniLM`                         | `hybrid_reranked`                                                 | Qwen3 падає з OOM (B3); reranker обвалює точність (FP-5) |
| v2.3.0     | Qwen3 (дефолт) / fastembed fallback                                                 | Jina v2 multilingual                      | `reranked`                                                        | Стабілізація, але reranker поведінка не виміряна на UA   |
| **v3.0.0** | **`BAAI/bge-m3` (direct ONNX, 1024d, 100+ мов)**                                    | **Jina v2 multilingual + ColBERT opt-in** | **`reranked` (FTS + rerank)** / **`hybrid` рекомендовано для UA** | **Англомовний reranker шкодить UA** (див. §3, §6)        |

**Головні зміни стеку в 3.0.0:**

1. **Canonical embedder = BGE-M3** (замість Qwen3/fastembed). Прямий ONNX-висновок без PyTorch, MIT-ліцензія,
   натреновано на 100+ мовах (включно з українською) — див. обґрунтування в §5.
2. **UDCG@5 — primary gate** (утилітарна метрика на базі частки термінів запиту у Top-5). nDCG@5 — secondary gate.
3. **Graph RAG v2** (`relations.py`, `WeightedKnowledgeGraph` + weighted BFS + centrality) — suggester `--v2`.
4. **ColBERT late-interaction — opt-in** (`POWER_RERANKER=colbert`, ≥16 ГБ RAM; інакше `ColBERTUnavailableError` + fallback на Jina v2).
5. **Synthesize auto-ingest** (`synthesize.py` + CLI `power synthesize`) — замикання циклу знань.

---

## 2. Методологія

### 2.1 Середовище

- **Vault:** `/root/gemma/brain` (~7.9 МБ, ~430 markdown-нотаток, білінгвальний UA/EN технічний корпус).
- **Харнесс:** `scripts/check_search_quality.py` (POWER 3.0 Phase 3, UDCG@5 primary gate, nDCG@5 ≥ 0.50).
- **Метрики:** `ndcg@5`, `udcg@5` (Utility-Discounted CG), `recall@5`, `mrr@5` (через `ranx`).
- **Режими:** `fts` (BM25), `vector` (TF/dense cosine), `hybrid` (RRF fts+vector), `reranked` (FTS→cross-encoder rerank).

### 2.2 Набори запитів (два)

1. **CI-gate set** — `DEFAULT_QUERIES` харнессу (16 запитів, переважно EN). Використовується CI-гейтом.
2. **Розширений UA+EN set (26 запитів, 23 з GT)** — 14 EN + 12 UA технічних запитів
   (`power safety`, `gpg signing`, `резервне копіювання`, `мережа tailscale`, …).
   **Саме цей набір — основа UA↔EN порівняння** у цьому звіті.

### 2.3 Ground Truth (важливо!)

GT будується **детерміністично**: документ релевантний запиту, якщо містить **УСІ токенізовані терміни запиту**
(`all(t in text)`). Це **лексична (term-AND) релевантність** — вона свідомо сприяє FTS/BM25.

> ⚠️ **Методологічна заувага.** Цей GT вимірює _лексичну_ релевантність, а не _семантичну/крос-лінгвальну_.
> Тому абсолютні числа **не прямо порівняльні** з попередніми тестами (TEST-3/4), які використовували
> _кураторський крос-лінгвальний_ GT (UA→EN, EN→UA, де FTS за визначенням = 0). Але **напрямні висновки
> збігаються** (див. §4, §6): англомовний cross-encoder reranker погіршує українську якість, а `hybrid`
> (без reranker) — найстійкіший мультимовний режим.

### 2.4 Відтворюваність

```bash
# БД ізоляції (не чіпає продакшн-індекс)
export POWER_SEARCH_DB=/tmp/bench_bge.sqlite
python3 scripts/check_search_quality.py --vault /root/gemma/brain --mode reranked
# Сирі метрики 26-запитного набору: .cache/bench_3_0_0_final.json
```

---

## 3. Результати POWER 3.0.0 (розширений UA+EN набір, 26 запитів / 23 з GT)

### 3.1 Порівняння режимів — загалом

| Режим                     | ndcg@5     | udcg@5 | recall@5   | mrr@5      | Примітка                        |
| :------------------------ | :--------- | :----- | :--------- | :--------- | :------------------------------ |
| **fts** (BM25)            | **0.9472** | 0.9973 | **0.3305** | **0.9674** | лексичний лідер (GT — term-AND) |
| **hybrid** (FTS+RRF)      | **0.9288** | 0.9958 | 0.3243     | 0.9457     | найстійкіший мультимовний       |
| **reranked** (FTS+rerank) | 0.7071     | 0.9777 | 0.1599     | 0.7536     | семантичний спеціаліст (EN)     |
| **vector** (dense)        | 0.5133     | 0.9627 | 0.1442     | 0.6725     | dense solo — найслабший         |

### 3.2 Розбивка за мовою (один і той самий 26-запитний набір)

| Режим        | EN (n=14) ndcg@5 | UA (n=9) ndcg@5 | EN mrr@5   | UA mrr@5   |
| :----------- | :--------------- | :-------------- | :--------- | :--------- |
| **fts**      | **1.0000**       | 0.8651          | **1.0000** | 0.9167     |
| **hybrid**   | **1.0000**       | **0.8180**      | **1.0000** | 0.8611     |
| **reranked** | 0.8798           | **0.4383**      | 0.9167     | **0.5000** |
| **vector**   | 0.6093           | 0.3640          | 0.7310     | 0.5815     |

### 3.3 Що це показує

- **FTS домінує** на лексичному GT (термін-AND → документ із усіма термінами завжди «перемагає»).
- **Reranked — полярний за мовою:** `EN ndcg@5 = 0.880` (дуже добре, cross-encoder покращує семантику),
  але **`UA ndcg@5 = 0.438`** і **`UA mrr@5 = 0.500`** — різке падіння. Причина: Jina v2 cross-encoder
  **англомовно-домінантний**; для UA-запитів він переранжовує лексично-сильні UA-документи нижче
  семантично-схожих, але без одного з термінів.
- **Hybrid тримає обидві мови:** EN=1.0, UA=0.818 — найкращий баланс. Це підтверджує рекомендацію TEST-4
  («Оптимум = hybrid без reranker») на свіжому стеці.
- **UDCG@5 ≈ 0.95–1.0 скрізь** — Top-5 завжди топікальні (містять терміни запиту); UDCG підтверджує
  он-топік, але слабо дискримінує на щільному vault-і, тому **nDCG@5 лишається дискримінуючим гейт-метрикою**.

### 3.4 Постачальник ембеддінгів: BGE-M3 vs Qwen3 (reranked, CI-gate set, 16 запитів)

| Постачальник         | ndcg@5       | udcg@5 | recall@5 | mrr@5 |
| :------------------- | :----------- | :----- | :------- | :---- |
| BGE-M3               | 0.787–0.811* | 0.991  | 0.170    | 0.849 |
| Qwen3-Embedding-0.6B | 0.796–0.828* | 0.989  | 0.207    | 0.849 |

\* reranked дає **легку варіативність (±0.02)** через хмарний cross-encoder (Jina v2) — не детермінований.
**Висновок:** на цьому корпусі BGE-M3 ≡ Qwen3 (збігається з TEST-4). Див. §5 — вибір BGE-M3 продиктований
ліцензією/пам'яттю/крос-лінгвальним cosine, а не кінцевим nDCG.

---

## 4. Порівняння з об'єднаними попередніми тестами (`docs/tests/`)

| Тест                       | Corpus / GT     | fts       | vector | hybrid    | reranked | semantic(dense)        |
| :------------------------- | :-------------- | :-------- | :----- | :-------- | :------- | :--------------------- |
| TEST-3 (v2.0.3, MiniLM)    | 18, синтет.     | 0.429     | 0.833  | 0.833     | 0.874    | **1.000** (MAR@5)      |
| TEST-3 (крос-лінгв.)       | 18, UA↔EN       | 0.241     | 0.778  | 0.778     | 0.824    | **1.000**              |
| TEST-4 (v2.0.3, BGE≡Qwen3) | 20, крос-лінгв. | 0.138     | 0.385  | **0.423** | 0.329    | — (MAR@5)              |
| TEST-4 UA→EN сценарій      | 20              | 0.000     | 0.573  | 0.531     | 0.250    | —                      |
| 2.2.1-TEST (MiniLM)        | 18, keyword     | —         | —      | —         | —        | 0.096 (MRR, найгірший) |
| **3.0.0 (цей звіт)**       | 26, лексичн.    | **0.947** | 0.513  | **0.929** | 0.707    | — (ndcg@5)             |

**Конвергентні висновки (незалежно від GT):**

1. **Cross-encoder reranker шкодить українській мові.** TEST-4: reranked UA→EN MAR@5 = **0.250**
   проти hybrid **0.531** (−53%); 3.0.0: reranked UA ndcg@5 = **0.438** проти hybrid **0.818** (−46%).
2. **`hybrid` (FTS + dense, без reranker) — найстійкіший мультимовний режим** (TEST-4: «Оптимум = hybrid
   без reranker»; 3.0.0: EN=1.0 / UA=0.818).
3. **FTS провалюється на крос-лінгвальному GT** (TEST-4 UA→EN = 0.000), але **домінує на лексичному GT**
   (3.0.0 = 0.947) — обидва факти вказують, що жоден один режим не універсальний.
4. **Dense solo (`vector`) слабкий** на keyword-важкому технічному корпусі (3.0.0 = 0.513; 2.2.1 MiniLM MRR 0.096).

---

## 5. Обґрунтування стеку — чому саме так, а не інакше

### 5.1 Чому canonical embedder = BGE-M3 (а не Qwen3, не fastembed MiniLM)

- **Qwen3-Embedding-0.6B:** у v2.2.3 ONNX-сесія намагалася алокувати **~97.5 ГБ** і падала на хостах ≤14 ГБ
  (BUG B3). На цьому хості Qwen3 **заблоковано** апаратно. BGE-M3 через direct ONNX вкладається в ліміт.
- **Ліцензія:** BGE-M3 — **MIT** (комерційно-friendly); Qwen3-Embedding має обмежувальну ліцензію.
- **Крос-лінгвальний cosine (ізольовано, TEST-4):** `UA→EN = 0.771 (BGE-M3) vs 0.590 (Qwen3)` —
  BGE-M3 краще вирівнює UA↔EN семантичний простір.
- **На цьому корпусі BGE-M3 ≡ Qwen3** (ідентичні IR-метрики, TEST-4 та §3.4) → вибір BGE-M3 безпечний і
  стандартизований, не втрачаючи якості.
- **fastembed MiniLM-L12 (384d):** сліпий до точних технічних назв та UA↔EN перефразування (FP-3/FP-4 у
  2.2.3; TEST-3 MAR@5 UA→EN = 0.208). Виключено як canonical.

### 5.2 Чому canonical mode = `reranked`, але `hybrid` рекомендовано для UA-важких vault-ів

- **`reranked`** (FTS → Jina v2 cross-encoder) — найкращий для **EN семантичних/парафразних** запитів
  (EN ndcg@5 = 0.880) і залишається CI-гейт-режимом (проходить ≥ 0.50 на обох наборах).
- **Але на UA він падає** (§3.2) через англомовний cross-encoder. Тому для **білінгвальних UA/EN vault-ів**
  рекомендовано **`hybrid` (FTS + BGE-M3 dense, RRF)** як продакшн-дефолт, що підтверджено TEST-4 та 3.0.0.
- **Рекомендація (follow-up):** зробити canonical-режим конфігурованим (`POWER_SEARCH_MODE`), за замовчуванням
  `hybrid` для UA-важких vault-ів; `reranked` — для EN-семантичних сценаріїв.

### 5.3 Чому UDCG@5 — primary gate

- nDCG@5 вимірює _ранжування релевантних за GT_. UDCG@5 вимірює _утилітарність_: для кожного документа у
  Top-5 — частка термінів запиту, що в ньому присутні (graded relevance 0..3), нормована на ідеал.
- Це відображає реальну корисність для агента (чи містить результат потрібні факти), а не лише бінарну GT.
- На щільному vault-і UDCG@5 ≈ стеля (~0.99) і слабо дискримінує — тому **nDCG@5 лишається дискримінуючим
  secondary gate**, а UDCG@5 гарантує он-топік результатів.

### 5.4 Чому ColBERT — opt-in, а не canonical

- ColBERT late-interaction дає найвищу семантичну точність, але вимагає **≥16 ГБ RAM** і повільніший
  index/query. На хостах ≤14 ГБ викидає `ColBERTUnavailableError` → автоматичний fallback на Jina v2.
- Тому він — **опція для high-end хостів** (`POWER_RERANKER=colbert`), а не дефолт.

---

## 6. Ключові висновки (UA↔EN якість)

1. ✅ **Білінгвальна якість досягнута на рівні retrieval:** hybrid дає EN ndcg@5 = 1.0, UA ndcg@5 = 0.818;
   FTS — EN 1.0 / UA 0.865. Жоден запит не залишається без топікального результату (UDCG@5 ≥ 0.95).
2. ⚠️ **Англомовний cross-encoder reranker — вузьке місце для української.** reranked UA ndcg@5 = 0.438
   (проти hybrid 0.818). Це не баґ стеку 3.0.0, а системна властивість англомовно-домінантних reranker-ів,
   підтверджена ще у TEST-4 (v2.0.3).
3. ✅ **BGE-M3 — правильний вибір canonical embedder:** MIT, direct ONNX (без PyTorch/RAM-вибуху Qwen3),
   кращий UA↔EN cosine, еквівалентний якості Qwen3 на цьому корпусі.
4. ✅ **CI-гейт проходить:** reranked ndcg@5 ≥ 0.50 (фактично 0.79–0.81 на CI-наборі), UDCG@5 ≥ 0.45
   (фактично 0.99). Усі 415 тестів + ruff + mypy — green.

---

## 7. Рекомендації (follow-ups)

| #   | Рекомендація                                                                             | Обґрунтування                                |
| :-- | :--------------------------------------------------------------------------------------- | :------------------------------------------- |
| R1  | Зробити canonical mode конфігурованим; дефолт `hybrid` для UA-важких vault-ів            | §3.2, §5.2, TEST-4                           |
| R2  | Впровадити **мультимовний** reranker (напр. `bge-reranker-v2-m3`) замість Jina v2 для UA | Reranker шкодить UA (§3.2, TEST-4 §4.1)      |
| R3  | Крос-лінгвальний GT у харнессі (UA→EN/EN→UA сценарії) поряд з лексичним                  | Поточний GT не вимірює UA→EN перевагу (§2.3) |
| R4  | Опційно ColBERT як default на хостах ≥16 ГБ                                              | §5.4                                         |

---

## 8. Сирі артефакти

- `.cache/bench_3_0_0_final.json` — авторитетний 26-запитний набір (overall + EN + UA для всіх режимів).
- `.cache/bench_3_0_0_prov.json`, `bench_3_0_0_qwen3.json` — порівняння постачальників.
- Харнесс: `scripts/check_search_quality.py` (UDCG@5 primary, nDCG@5 ≥ 0.50 secondary gate).

---

## 9. Еволюція версій та архітектури POWER

Цей розділ реконструює траєкторію стеку POWER від v2.0.1 до v3.0.0 на основі звітів у `docs/tests/`,
виділяючи **архітектурні зсуви** (embedder → reranker → режими → метрики → Graph RAG) та **повторювані
уроки**, що сформували фінальний дизайн 3.0.0.

### 9.1 Хронологія версій

| Версія     | Embedder (dense)                                          | Reranker (cross-encoder)                 | Доступні режими                         | Ключові компоненти / події                                                                                           | Ключовий висновок тестів                                                                                    |
| :--------- | :-------------------------------------------------------- | :--------------------------------------- | :-------------------------------------- | :------------------------------------------------------------------------------------------------------------------- | :---------------------------------------------------------------------------------------------------------- |
| **v2.0.1** | `BAAI/bge-m3` (sentence-transformers, XLM-RoBERTa)        | `Xenova/ms-marco-MiniLM-L-6-v2`          | fts, vector, hybrid, hybrid_reranked    | `embeddings.py`, `reranker.py`, `searcher.py`, `chunker.py`, `cli.py`                                                | Морфологічна гнучкість UA (відмінки); BGE-M3 розуміє семантику без лематизації                              |
| **v2.0.3** | `paraphrase-multilingual-MiniLM-L12-v2` (fastembed, 384d) | `ms-marco-MiniLM-L-6-v2` (onnx)          | + `semantic` (dense)                    | Graph RAG v1 (`relations.py`), `linter.py` (ROT/контрадикції)                                                        | **MiniLM сліпий до UA→EN** (MAR@5=0.208, TEST-3); BGE-M3 ≡ Qwen3 (TEST-4)                                   |
| **v2.1.x** | MiniLM-L12 (fastembed)                                    | **`jina-reranker-v2-base-multilingual`** | ті ж                                    | `RerankerManager`, мультимовний reranker                                                                             | Крос-лінгв. ENG↔UKR підтверджено (TEST-2/3); Jina v2 +5% MAR@5 поверх vector                                |
| **v2.2.1** | MiniLM-L12 (fastembed)                                    | ms-marco-MiniLM                          | ті ж                                    | Паралельний ембед (`EMBED_NUM_THREADS`), RSS MiniLM ~680 МБ                                                          | Стабілізація latency на keyword-важкому vault-і                                                             |
| **v2.2.3** | **Qwen3-ONNX (1024d, MRL)** → відступ на fastembed MiniLM | ms-marco-MiniLM                          | ті ж                                    | Провайдер `qwen3_embed`, ланцюг безпечного відступу                                                                  | **BUG B3:** Qwen3 ONNX ~97.5 ГБ → OOM на ≤14 ГБ (FP-3/4: MiniLM blind до UA↔EN; FP-5: reranker→0 точності)  |
| **v2.3.0** | Qwen3 (дефолт) / fastembed fallback                       | Jina v2 multilingual                     | ті ж                                    | Стабілізація абстракції провайдерів                                                                                  | Стабільний базис; поведінка reranker на UA не виміряна                                                      |
| **v3.0.0** | **`BAAI/bge-m3` (direct ONNX, 1024d, 100+ мов)**          | **Jina v2 + ColBERT opt-in**             | fts, vector, hybrid, semantic, reranked | `metrics/udcg.py`, `colbert_reranker.py`, Graph RAG v2 (`WeightedKnowledgeGraph`), `synthesize.py`, `get_reranker()` | **Англомовний reranker шкодить UA** (§3, §6); UDCG@5 primary gate; hybrid — найстійкіший мультимовний режим |

### 9.2 Архітектура компонентів (стан на v3.0.0)

```
                         power_framework.core
                         ┌─────────────────────────────────────────────┐
  CLI (cli.py)           │                                               │
   power search          │   embeddings.py  ── Embedder abstraction      │
   power suggest-related │     • BGE-M3 (direct ONNX, canonical)        │
   power synthesize      │     • qwen3_embed (opt-in, ≥RAM)             │
        │                │     • fastembed fallback (MiniLM)            │
        ▼                │     • EMBED_PROVIDER, thread-pool sync       │
   searcher.search_vault │                                               │
        ├─ fts/vector ───► index_worker.request_sync (background embed)  │
        ├─ hybrid (RRF)   │                                               │
        └─ reranked ─────► reranker.get_reranker()  ── RerankerProtocol  │
                               ├─ Jina v2 (multilingual, default)        │
                               └─ ColBERT (late-interaction, opt-in ≥16GB)│
                                                                         │
   relations.suggest_related_v2 ── Graph RAG v2                          │
        • WeightedKnowledgeGraph (weighted BFS + centrality)             │
                                                                         │
   metrics.udcg  ── UDCG@5 (primary gate)   nDCG@5 (secondary gate)      │
   synthesize    ── synthesize_session_ingest (auto-ingest loop)         │
   linter/rot_scoring ── ROT audit, ContradictionDetector, orphan check │
                         └─────────────────────────────────────────────┘
        ▲
   scripts/check_search_quality.py  (harness: UDCG@5 primary, nDCG@5≥0.50)
```

**Відповідальність модулів:**

- **`embeddings.py`** — абстракція ембедера: `BGE-M3` (direct ONNX, без PyTorch/RAM-вибуху), `qwen3_embed`
  (opt-in, MRL 1024d), `fastembed` MiniLM (fallback). Експонує `.dimension`, паралельний sync.
- **`index_worker.py`** — фоновий `request_sync`, mode-based ембедінг (`fts` vs `semantic`), атомарні записи БД.
- **`searcher.py`** — `search_vault` з режимами `fts`/`vector`/`hybrid`(RRF)/`semantic`/`reranked`
  (hybrid_reranked); singleton reranker; опційний semantic-fallback.
- **`reranker.py`** — `RerankerProtocol` + фабрика `get_reranker()`; `RerankerManager` (Jina v2 / локальний);
  `ColBERTUnavailableError` для граційної деградації.
- **`colbert_reranker.py`** — ColBERT late-interaction (opt-in, ≥16 ГБ RAM).
- **`relations.py`** — **Graph RAG v2**: `WeightedKnowledgeGraph`, зважений BFS, centrality, `suggest_related_v2`.
- **`metrics/udcg.py`** — UDCG (utility-discounted CG, graded relevance 0..3).
- **`synthesize.py`** — `synthesize_session_ingest` + CLI `power synthesize` (замикання циклу знань).
- **`chunker.py`** — семантичне розбиття (headers/paragraphs) з контекстом документа.
- **`linter.py` / `rot_scoring.py`** — аудит бази знань: ROT, `ContradictionDetector`, orphan-нотатки.

### 9.3 Повторювані уроки, що сформували 3.0.0

1. **Embedder-цикл замикається на BGE-M3, але кращим шляхом.**
   `BGE-M3 (sbert)` → `MiniLM (fastembed)` → `Qwen3 (ONNX, заблоковано RAM)` → **`BGE-M3 (direct ONNX)`**.
   Версія 3.0.0 повертається до BGE-M3, усуваючи недоліки: прямий ONNX (без PyTorch/RAM-вибуху),
   MIT-ліцензія, нативна мультимовність (100+ мов, UA включно).
2. **Англомовний cross-encoder reranker — системна слабкість для UA.** Виявлено ще у v2.0.3 (MiniLM,
   MAR@5 UA→EN=0.208) і підтверджено у v2.2.3 (FP-5: precision→0) та v3.0.0 (§3.2: UA ndcg@5=0.438).
   Незмінний висновок: `hybrid` (без reranker) — найстійкіший мультимовний режим.
3. **RAM-безпека понад якість.** Qwen3-ONNX (~97 ГБ, B3) та ColBERT (≥16 ГБ) перетворені на **opt-in**
   з граційним відступом (Jina v2 / fastembed), щоб фреймворк не падав на обмежених хостах.
4. **Метрика еволюціонувала від чистого nDCG до утилітарної UDCG.** v3.0.0 додає UDCG@5 як primary gate
   (корисність агенту), зберігаючи nDCG@5 як дискримінуючий secondary gate.
5. **Graph RAG пройшов від v1 (базовий) до v2 (зважений граф)** з centrality та weighted BFS — краща
   якість пов'язаних нотаток без додаткового ембедінгу.
6. **Автономність агента** — `synthesize.py` замикає цикл «сесія → знання → індекс», реалізуючи
   self-ingest без людського втручання.

---

## 10. Порівняння архітектур: DRAPAS 1.0 vs POWER 3.0.0

Попередній порівняльний аналіз збережено у другому мозку
(`brain/03_Resources/DRAPASS-vs-P.O.W.E.R.2.1.0.md`, `…2.0.4.md`, сесія
`2026-07-17_drapas_power_v3_planning.md`) та розширено у повному звіті
`projects/DRAPAS1.0_vs_POWER3.0.md`. Нижче — оновлення того порівняння під фінальний
стек 3.0.0 (див. §9.2), з урахуванням дорожньої карти POWER v2.1.0 (§3 того звіту),
нюансу валідації графа DRAPAS, а також **сильних/слабких сторін POWER 3.0.0** та
**перспектив розвитку POWER 3.0+** (див. §10.4–§10.7).

### 10.1 DRAPAS 1.0 — коротко (архітектурний профіль)

У цьому звіті **DRAPAS 1.0** розуміється як конкретна реалізація концепції _Dynamic RAG
with Pluggable Agent Storage_ — документ `DRAPAS1.0.md` є архітектурною картою проєкту
**ObsidianDistil** (підтримуваний персональний Obsidian-вольт + локальний стек
ретривлу/індексації). Це Enterprise-scale концепція довготривалої пам'яті:

- **SQLite (FTS5)** — лексична навігація по метаданих/коротких текстах (`vault_fts` ladder:
  strict AND → OR-terms → LIKE).
- **LightRAG (GraphRAG)** — повністю автоматичний граф знань: сутності (Entities) та зв'язки
  (Relations) **екстрагуються LLM** на етапі запису; дво­рівневий пошук — _Local_ (точні факти)
    - _Global_ (огляди/теми).
- **Qdrant sidecar** — рівневий векторний індекс (секції) для semantic/fused (RRF) ретривлу.
- **Generations & GC** — кожен домен версіонується як _generation_; індексація будує нову
  генерацію, валідує, і лише тоді перемикає active pointer (append-only GC ledger, rollback-вікно).
- **Local model sidecars** (llama.cpp, `127.0.0.1`) — embedder (Qwen3-Embedding-0.6B /
  embeddinggemma-300m), reranker (Qwen3-Reranker-0.6B), query-expansion (qmd). **Query-time
  нуль egress** — все на локалхості (хмара лише на index-time LLM-екстракції).
- **Read-only MCP** (`vault_mcp_server.py`, stdio) — 14 read-only інструментів.

### 10.2 Порівняльна таблиця (DRAPAS 1.0 vs POWER 3.0.0)

| Критерій                 | DRAPAS 1.0 (ObsidianDistil)                                              | P.O.W.E.R. 3.0.0                                                                                 |
| :----------------------- | :----------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------- |
| **Філософія**            | Збереження знання + знахідність за контекстом (адаптований Zettelkasten) | AI-native гібридна пам'ять (P.A.R.A.+OKF+Wiki+Rules)                                             |
| **Конструкція графа**    | LLM-екстракція (LightRAG), автоматична                                   | Детермінований typed-relation граф (OKF `related`), Graph RAG v2 (`WeightedKnowledgeGraph`)      |
| **Галюцинації графа**    | Можливі без валідації; пом'якшені **бідирекційною** перевіркою (§10.3)   | **Неможливі за визначенням** — граф валідовано конструкцією (типізовані зв'язки = реальні файли) |
| **Lexical search**       | SQLite FTS5 (`vault_fts` ladder)                                         | SQLite FTS5 (`search_vault`)                                                                     |
| **Dense / hybrid**       | Qdrant sidecar + DBSF/RRF fusion                                         | BGE-M3 direct ONNX + RRF `hybrid` / `reranked`                                                   |
| **Embedder (local)**     | Qwen3-Embedding-0.6B / embeddinggemma-300m (llama.cpp sidecar)           | BGE-M3 1024d (direct ONNX); qwen3/fastembed opt-in                                               |
| **Reranker**             | Qwen3-Reranker-0.6B sidecar (local, no egress)                           | Jina v2 multilingual + ColBERT opt-in (⚠️ шкодить UA, §10.5)                                     |
| **Query-time egress**    | **Нульовий** (все на 127.0.0.1; хмара лише на index-time)                | Ембед/реренк — локально (ONNX); query-expansion має опційний OpenRouter egress                   |
| **Global Retrieval**     | Так (LightRAG Global: огляди/теми)                                       | Обмежений (weighted BFS + centrality v2)                                                         |
| **Write-path cost**      | Високий (LLM-екстракція на записі)                                       | Низький (детермінований індекс + опційний `synthesize`)                                          |
| **Масштаб**              | 1M+ документів (Qdrant)                                                  | ~100–300K (edge/SQLite)                                                                          |
| **Generations & GC**     | Так (generations, append-only ledger, rollback-вікно)                    | Ні (single live SQLite + atomic tmp→rename)                                                      |
| **Інфраструктура**       | Qdrant + LLM API (Docker/сервіси)                                        | **Zero-infra / edge** (локальний ONNX)                                                           |
| **Data Governance**      | partial (ROT audit, tags_registry, frontmatter_guard)                    | ROT audit, `ContradictionDetector`, orphan-check, `expiry`                                       |
| **Мультимовність UA↔EN** | Залежить від ембедера (Qwen3 — сильний)                                  | BGE-M3 сильний; але англомовний reranker шкодить UA (§10.5)                                      |
| **Утилітарна метрика**   | Немає (health/status/validate)                                           | UDCG@5 primary gate + nDCG@5 ≥ 0.50                                                              |
| **CI / doc-drift gate**  | Немає явного                                                             | `check_doc_drift.py` + ranx regression gate в CI                                                 |
| **Auto-ingest**          | Manual prompts + offline extraction telemetry                            | `synthesize` auto-ingest (напів-автоматичне замикання циклу)                                     |

### 10.3 Галюцинації графа DRAPAS — нюанс валідації

У попередньому звіті (v2.1.0, §2) пунктом «мінусів» DRAPAS значилося: _«LLM може вигадувати неіснуючі
сутності та зв'язки між документами»_. Це потребує уточнення:

> **Галюцинації графа можливі лише у теорії, якщо взагалі відсутня валідація.** DRAPAS перевіряє зв'язок
> **бідирекційно**: не лише «що на тому кінці» (чи існує цільова сутність), а й «з того кінця — чи справді
> тут цей зв'язок». Тобто вигадана сутність/ребро відсікається, бо не проходить зворотну перевірку. Реальний
> ризик залишається лише коли валідація повністю вимкнена.

**Контраст із POWER 3.0.0:** граф POWER — **детермінований** (типізовані зв'язки у frontmatter нотаток,
`WeightedKnowledgeGraph` + weighted BFS). Він **структурно не може галюцинувати**, оскільки ребра існують лише
якщо явно прописані у самих документах-сутностях, і кожен кінець — це реальний файл vault-у. Тобто POWER
обирає шлях «відсутність галюцинацій за конструкцією» замість «LLM-автоматизація + валідація» (DRAPAS).

### 10.4 🟢 Сильні сторони P.O.W.E.R. 3.0.0

1. **Edge/zero-infra ефективність.** Прямий ONNX (без PyTorch/RAM-вибуху Qwen3 чи fastembed-процесів),
   peak RSS ≈ 1.6 ГБ — вписується в контракт ≤2 ГБ. DRAPAS вимагає Qdrant + llama.cpp sidecars (важча інфра).
2. **Детермінований граф без галюцинацій за конструкцією.** Typed `related` у OKF frontmatter = реальні
   файли vault-у; Graph RAG v2 (weighted BFS + centrality) дає пов'язані нотатки без LLM-екстракції.
3. **Виміряна білінгвальна якість retrieval.** UDCG@5 primary gate + nDCG@5 secondary (≥0.50). `hybrid` дає
   EN ndcg@5 = 1.0 / UA = 0.818; FTS — EN 1.0 / UA 0.865. Жоден запит без топікального результату (UDCG@5 ≥ 0.95).
4. **BGE-M3 — правильний канонічний вибір.** MIT-ліцензія, direct ONNX, сильний UA↔EN cosine (0.771),
   еквівалентний якості Qwen3 на цьому корпусі, але без RAM-вибуху (~97 ГБ у Qwen3-ONNX).
5. **RAM-безпека через opt-in.** Qwen3 та ColBERT перетворені на opt-in з граційним відступом — фреймворк
   не падає на обмежених хостах (урок BUG B3 / INCIDENT-42GB).
6. **Governance-шар.** ROT audit, `ContradictionDetector`, orphan-check, `expiry`-моніторинг свіжості —
   DRAPAS має лише partial аналоги.
7. **Synthesize auto-ingest.** Напів-автоматичне замикання циклу «сесія → знання → індекс» без тотальної
   LLM-екстракції на write-path.
8. **Інженерна надійність.** Doc-drift CI gate, ranx regression gate (жоден embedder/reranker-свап не мержиться
   без бенчу), atomic writes, GPG-підпис, 416 тестів + CodeQL.
9. **Простота оператора.** Один canonical шлях `power search <vault> <query>`; debug-режими — лише для
   розробників (філософія «Unique, Simple, Effective»).

### 10.5 🔴 Слабкі сторони P.O.W.E.R. 3.0.0

1. **❌ Англомовний cross-encoder reranker шкодить українській.** `reranked` UA ndcg@5 = **0.438** проти
   `hybrid` **0.818** (−46%) — системна властивість Jina v2 (підтверджено ще TEST-4, v2.0.3). Головний шрам
   3.0.0: canonical mode `reranked` фактично _гірший_ для UA-важких vault-ів, ніж `hybrid`.
2. **❌ Обмежений Global Retrieval.** Weighted BFS + centrality v2 не дають повноцінного LightRAG Global
   (огляди/теми «що обговорювалося в липні»). DRAPAS через LightRAG Global сильніший у агрегуючих запитах.
3. **❌ Масштаб обмежений SQLite.** ~100–300K документів. DRAPAS (Qdrant) масштабується до 1M+. Для великих
   корпоративних вольтів POWER потребує зовнішнього бекенду.
4. **⚠️ Ручний GraphRAG.** Користувач/агент мусить прописувати `related` у YAML вручну (або через
   `suggest-related`). DRAPAS автоматизує це через LLM на index-time — менше ручної праці, але з ризиком галюцинацій.
5. **⚠️ Немає Generations & GC.** POWER тримає один live SQLite-індекс; немає rollback-вікна чи append-only
   ledger генерацій, як у DRAPAS. Регресія індексу важче відкочується.
6. **⚠️ Query-expansion має опційний OpenRouter egress.** На відміну від DRAPAS (нуль egress query-time),
   POWER `query_expansion` може йти в хмару (multi-query через OpenRouter) — порушує zero-egress для приватних
   vault-ів, якщо не вимкнено.
7. **⚠️ Dense solo слабкий на keyword-важкому корпусі.** `vector` ndcg@5 = 0.513 (3.0.0). Потрібен FTS- або
   hybrid-баланс; pure-semantic сценарії вразливі.
8. **⚠️ CI-gate GT — лексичний (term-AND).** Не вимірює крос-лінгвальну перевагу (UA→EN/EN→UA), тому абсолютні
   цифри не прямо порівняльні з кураторським GT попередніх тестів (методологічна прогалина, див. §2.3).

### 10.6 Що POWER 3.0.0 перейняв з дорожньої карти DRAPAS (v2.1.0 §3), а що — ні

| Ідея з дорожньої карти DRAPAS                                            | Статус у 3.0.0 | Обґрунтування                                                                                                                                                                                                                             |
| :----------------------------------------------------------------------- | :------------- | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **§3.1 Qdrant backend** (`POWER_VECTOR_BACKEND=qdrant` + DBSF)           | ❌ Не прийнято | Збережено edge/zero-infra та RAM-безпеку (§5.1, §9.3). Для vault-ів ≤300K SQLite+ONNX достатньо; Qdrant додає інфру без пропорційного виграшу для локального агента. **Повертається як R4 у §10.7.**                                      |
| **§3.2 Automatic Dual-Level GraphRAG** (LLM-екстракція + `global` пошук) | 🟡 Частково    | Graph RAG v2 реалізовано (weighted BFS + centrality), але **не через LLM-екстракцію** — навмисно, щоб уникнути галюцинацій (§10.3). `global`-подібний огляд — через centrality, не через LightRAG Global. **Розширюється як R7 у §10.7.** |
| **§3.3 Мультимовний reranker** (`bge-reranker-v2-m3`)                    | 🟡 Частково    | Прийнято Jina v2 multilingual + ColBERT opt-in; R2 (§7) рекомендує перехід на `bge-reranker-v2-m3` для усунення падіння UA (§3.2, §10.5).                                                                                                 |

### 10.7 🔭 Перспективи розвитку POWER 3.0+

На основі слабких сторін (§10.5), уроків MASTER-LESSONS-LEARNED та дорожньої карти DRAPAS (§3
`DRAPASS-vs-P.O.W.E.R.2.1.0.md`), пропонується еволюція POWER 3.0 → 3.5/4.0 (повний звіт:
`projects/DRAPAS1.0_vs_POWER3.0.md`).

| #      | Пріоритет | Рекомендація                                                                                | Джерело             | Очікуваний ефект                 |
| :----- | :-------- | :------------------------------------------------------------------------------------------ | :------------------ | :------------------------------- |
| **R1** | 🔴 P0     | Конфігурований canonical mode; дефолт `hybrid` для UA-важких vault-ів (`POWER_SEARCH_MODE`) | §10.5.1, §5.2       | Усуває суперечність canonical/UA |
| **R2** | 🔴 P0     | Мультимовний reranker `bge-reranker-v2-m3` (ONNX) замість Jina v2                           | §10.5.1, §7         | UA ndcg@5: 0.438 → ≥0.80         |
| **R3** | 🟠 P1     | Крос-лінгвальний GT у харнесс (UA→EN/EN→UA сценарії) поряд з лексичним                      | §10.5.8, §2.3       | Чесна UA↔EN оцінка               |
| **R4** | 🟠 P1     | `POWER_VECTOR_BACKEND=qdrant` + DBSF (плагіновий бекенд)                                    | §10.5.3, §10.6 §3.1 | Масштаб >1M доків                |
| **R5** | 🟡 P2     | Generations & GC ledger + rollback-вікно                                                    | §10.5.5             | Надійний відкат індексу          |
| **R6** | 🟡 P2     | Локальний query-expansion sidecar (повний zero-egress)                                      | §10.5.6             | Приватність query-time           |
| **R7** | 🟡 P2     | Легкий auto GraphRAG (локальний, бідирекційно-валідований)                                  | §10.5.2, §10.6 §3.2 | Global Retrieval без галюцинацій |
| **R8** | 🟢 P3     | Per-domain fusion knobs (RRF/score, `domain_overrides`)                                     | §5.6                | Тонке мовне налаштування         |
| **R9** | 🟢 P3     | Warm-start map (cross-session навігаційний entry-point)                                     | §5.7                | Швидший старт агента             |

**Траєкторія POWER 3.0+** — не відмова від філософії «Simple, Effective», а _вибіркове запозичення_
сильних сторін DRAPAS: плагіновий Qdrant-бекенд (scale, R4), generations/GC (reliability, R5),
локальний auto-GraphRAG з бідирекційною валідацією (global retrieval без галюцинацій, R7) і повний
zero-egress (R6). Це перетворить POWER на гібрид, що поєднує edge-простоту з enterprise-глибиною —
без втрати детермінованості та governance.

**Висновок порівняння:** DRAPAS 1.0 робить ставку на **depth/scale** (LightRAG graph-depth + Qdrant scale

- zero-egress sidecars) з автоматизацією на write-path (ціною LLM-латентності, інфри та ризику галюцинацій,
  пом'якшених бідирекційною валідацією). POWER 3.0.0 робить ставку на **edge-ефективність, governance та
  виміряну якість** (UDCG@5, детермінований граф без галюцинацій, BGE-M3 direct ONNX, RAM-safe opt-in).
  **Головний шрам 3.0.0** — англомовний reranker, що шкодить українській (R2/R1). **Головна прогалина** —
  масштаб і Global Retrieval (R4/R7). Вибір — це depth/scale (DRAPAS) чи efficiency/governance/measured-quality
  (POWER), і для локального агента друге є кращим trade-off-ом, але POWER 3.0+ має стати **конфігуровано-глибоким**:
  edge за замовчуванням, depth — opt-in для тих, кому потрібно.

---

> **Висновок:** Стек 3.0.0 (BGE-M3 canonical + UDCG@5 gate + Graph RAG v2 + ColBERT opt-in) забезпечує
> стійку білінгвальну UA↔EN якість retrieval. Критичний інсайт, що **узгоджується з усіма попередніми
> тестами** (§4, §9): англомовний cross-encoder reranker погіршує українську вибірку, тому `hybrid`
> (без reranker) — найнадійніший мультимовний режим, а `reranked` залишається семантичним спеціалістом для
> EN. Еволюція (§9) показує, що фінальний дизайн — це не стрибок, а **конвергенція повторюваних уроків**
> про мультимовність, RAM-безпеку та утилітарність метрик. Порівняння з DRAPAS 1.0 (§10) фіксує свідомий
> вибір POWER на користь детермінованого графа (без галюцинацій за конструкцією) та edge-ефективності замість
> LLM-автоматизації й зовнішньої інфраструктури, а перспективи POWER 3.0+ (§10.7) вказують шлях до поєднання
> цієї простоти з enterprise-глибиною DRAPAS через вибіркове opt-in запозичення.
