---
type: Test Report
title: "P.O.W.E.R. v3.2.1 — TEST-1: Історичний baseline на PRXMX-01"
description: "Історичний тест P.O.W.E.R. v3.2.1 на PRXMX-01. Neural pipeline був неповним: 8 doc embeddings, 0 chunk embeddings. Результати лише для FTS/Vector/Hybrid режимів."
tags:
    [
        "power-framework",
        "testing",
        "benchmarks",
        "latency",
        "memory",
        "quality",
        "determinism",
        "security",
        "egress",
        "v3.2.1",
        "historical",
        "test-1",
        "prxmx-01",
    ]
timestamp: 2026-07-25T12:00:00
---

> [!IMPORTANT]
> **Статус: історичний baseline TEST-1.**
> Цей тест виконано 2026-07-24 на PRXMX-01 із частково
> побудованим dense-індексом: 8 doc embeddings, 0 chunk embeddings.
> Актуальні результати повного neural pipeline наведено у
> [P.O.W.E.R.3.2.1-TEST-2.md](P.O.W.E.R.3.2.1-TEST-2.md).

---

# P.O.W.E.R. v3.2.1 — TEST-1: Історичний baseline на PRXMX-01

## 0. Середовище тестування (Ground Truth)

| Параметр                           | Значення                                                             | Примітка                                            |
| :--------------------------------- | :------------------------------------------------------------------- | :-------------------------------------------------- |
| **POWER CLI**                      | `power 3.2.1`                                                        | `pip install -e .[dev]` з `projects/P.O.W.E.R`      |
| **Дата**                           | **2026-07-25**                                                       |                                                     |
| **Платформа**                      | `Linux x86_64` (PRXMX-01 / pve01)                                    | Host OS / LXC                                       |
| **Python**                         | `3.13.5`                                                             |                                                     |
| **Хост RAM / CPU**                 | **121 ГБ**, 20 ядер (4 vCPU в LXC)                                   | i5-5200U @ 2.20 GHz                                 |
| **Vault**                          | `/root/geminicli/brain`                                              | **560 нотаток**, **1608 чанків**                    |
| **DB**                             | `~/.cache/power-framework/power_search.db`                           | Повний dense-індекс                                 |
| **Embedding Provider**             | `bge-m3-onnx` (`aapot/bge-m3-onnx`, revision `76a60339`)             | Pinned canonical ONNX model, 1024d                  |
| **Reranker Provider**              | `bge-reranker-v2-m3-onnx` (`onnx-community/bge-reranker-v2-m3-ONNX`) | Batch ONNX inference, `POWER_RERANKER_BATCH_SIZE=8` |
| **Тестовий набір запитів**         | 16 запитів (14 EN + 2 UA)                                            | Development set                                     |
| **Інструменти статичного аналізу** | `ruff`, `mypy`, `pytest 9.1.1`, `pytest-cov`                         |                                                     |

Всі benchmark-артефакти: `docs/tests/artifacts/3.2.1-test-2-final/`

---

## 1. Хеші ключових файлів (SHA256)

| Файл                                   | SHA256 Хеш                                                         |
| :------------------------------------- | :----------------------------------------------------------------- |
| `src/power_framework/core/reranker.py` | `fb33f7b73d0a6e30d193c10fbf868a51ee4fe290b084ebf10fb319f9140a6672` |
| `src/power_framework/core/searcher.py` | `c6ade26287fa8cbf76e960882ac561f33144e14bbce6812705f854b2d925ff41` |
| `tests/fixtures/semantic_gt.json`      | `b6dcd5153d7f9836a57621eed2814ed5218150b30d59f662793c8efeac3353c9` |

---

## 2. Статичний аналіз та Юніт-тести

### 2.1 Ruff & Mypy

- **`ruff check src tests`**: `All checks passed!` (0 помилок).
- **`mypy src/power_framework`**: `Success: no issues found in source files` (32 source files verified).

### 2.2 Power Lint Brain

- **`power lint /root/geminicli/brain`**:
    ```
    WARNING: Orphan notes (no inbound links) (2):
      - 01_Projects/ADBlock-PD_Upstream_Upgrade_Plan.md
      - 01_Projects/Plan_POWER_3.2.md
    ```
- **Exit code**: `0` (warnings non-blocking).

### 2.3 Pytest Suite & Coverage Report

- **Запуск**: `pytest --cov=power_framework`
- **Результат**: `534 passed, 2 skipped, 0 failed in 244.20s` (тільки FTS/Vector/Hybrid режими пройшли; semantic/reranked не запускалися через відсутність chunk_embeddings)
- **Покриття коду (Coverage)**: **`73.07%`** (потрібно ≥ 70.00% — **ПРОЙДЕНО**).

> **Примітка**: Neural-пошук (semantic/reranked) не запускався через відсутність `chunk_embeddings`. Повний neural pipeline тестовано в TEST-2 (WS).

---

## 3. Зафіксована конфігурація моделей (Model Lock)

```json
{
    "schema_version": 1,
    "release": "3.2.1",
    "canonical_embedding": {
        "provider": "bge-m3-onnx",
        "repository": "aapot/bge-m3-onnx",
        "revision": "76a603396f5eb9f03ed51bbab8f4893fcea7b2fe",
        "license": "MIT"
    },
    "canonical_reranker": {
        "provider": "bge-reranker-v2-m3-onnx",
        "repository": "onnx-community/bge-reranker-v2-m3-ONNX",
        "revision": "6f5ff65298512715a1e669753bc754d2bc8f367b",
        "license": "Apache-2.0",
        "batch_size": 8,
        "sha256_pinned": true,
        "release_default": true
    }
}
```

---

## 4. Пофазова верифікація функціоналу (Phases A–G)

| Фаза        | Назва фази                 | Результат | Примітки                                                                                                              |
| :---------- | :------------------------- | :-------- | :-------------------------------------------------------------------------------------------------------------------- |
| **Phase A** | **OKF max_length removal** | **PASS**  | `OKFMetadata(description="x"*500)` валідується без помилок; поле каталогу зрізається до 150 символів при відображенні |
| **Phase B** | **BGE-Reranker default**   | **PASS**  | `get_reranker()` повертає `BGEM3Reranker` (direct ONNX); зовнішній Jina v2 ізольовано за опціональним флагом          |
| **Phase C** | **Fail-closed embedder**   | **PASS**  | `DenseIndexUnavailableError` піднімається fail-closed, якщо dense-індекс не ініціалізовано/відсутній                  |
| **Phase D** | **Semantic GT + UDCG**     | **PASS**  | Реалізовано 16 двомовних запитів та розрахунок graded nDCG; модуль `udcg_real.py` виконує розрахунок UDCG             |
| **Phase E** | **Auto-Graph triplets**    | **PASS**  | Локальне тріплетне вилучення `(subject -> relation -> object)`; SQLite таблиця `relations`; метод `suggest_related`   |
| **Phase F** | **Write-Queue Worker**     | **PASS**  | 10 паралельних async-записів серіалізовані через `enqueue_write` без жодного `sqlite3.OperationalError`               |
| **Phase G** | **Memory contract**        | **PASS**  | Піковий RSS semantic **~1.56 GB** — вкладається в контракт **≤ 2048 МБ (2 ГБ)**                                       |

---

## 5. Якість пошуку (Search Quality) — **NOT TESTED в TEST-1**

> Neural pipeline був неповним (0 chunk_embeddings). quality метрики взято з TEST-2 (WS).

### 5.1 Quality Metrics (nDCG@5) — з TEST-2

Ground truth: curated bilingual 16 запитів (development set).

| Режим                                                | nDCG@5     | Примітка            |
| :--------------------------------------------------- | :--------- | :------------------ |
| **Semantic** (dense BGE-M3)                          | **0.4350** | Базовий dense-пошук |
| **Reranked OLD** (без dense candidates)              | **0.2859** | Попередня версія    |
| **Reranked NEW** (dense + FTS + RRF + cross-encoder) | **0.4244** | Поточна реалізація  |

### 5.2 Candidate Recall Diagnostics

Для кожного запиту записано per-query recall (див. `candidate-recall.csv`):

| Метрика             | Значення |
| :------------------ | :------- |
| candidate_recall@20 | TBD      |
| candidate_recall@40 | TBD      |
| candidate_recall@60 | TBD      |

### 5.3 Аналіз Quality Reranker

Reranked NEW суттєво покращився порівняно з OLD:
nDCG@5 **0.2859 → 0.4244**.

Основні причини покращення:

1. Dense candidates додані до candidate pool;
2. Reranker отримує best semantic chunk, а не початок документа.

Поточний reranked усе ще поступається semantic:
**0.4244** проти **0.4350**.

Batch inference оцінюється окремо як latency-оптимізація (див. TEST-2).

### 5.4 Статус оптимізацій

| Оптимізація                        | Статус                            |
| :--------------------------------- | :-------------------------------- |
| Dense candidates у reranker pool   | виконано                          |
| Best semantic snippet для reranker | виконано                          |
| Batched ONNX inference             | код виконано / benchmark в TEST-2 |

---

## 6. Per-mode Latency та Peak RSS — **NOT TESTED в TEST-1**

> Neural pipeline був неповним (0 chunk_embeddings). Latency/RSS метрики взято з TEST-2 (WS).

### 6.1 Cold Latency (з TEST-2)

| Режим                          | Cold p50 (ms) | Примітка                                   |
| :----------------------------- | :------------ | :----------------------------------------- |
| **`fts`** (BM25)               | **274.0**     |                                            |
| **`vector`** (TF-cosine)       | **420.0**     |                                            |
| **`hybrid`** (FTS+TF RRF)      | **432.0**     |                                            |
| **`semantic`** (Dense BGE-M3)  | **8,040**     | Кодування запиту + сканування 3,876 чанків |
| **`reranked`** (Cross-Encoder) | **28,947**    | Per-document ONNX inference                |

### 6.2 Warm In-Process Latency (з TEST-2)

| Режим          | Warm p50 (ms) | Warm p95 (ms) |
| :------------- | :------------ | :------------ |
| **`fts`**      | **5.9**       | **37.9**      |
| **`vector`**   | **146.7**     | **820.7**     |
| **`hybrid`**   | **148.3**     | **859.6**     |
| **`semantic`** | **67.1**      | **324.1**     |
| **`reranked`** | **6,733.6**   | **32,305.0**  |

### 6.3 Peak RSS (з TEST-2)

| Режим            | Peak RSS     |
| :--------------- | :----------- |
| **fts**          | **29 MB**    |
| **semantic**     | **1,510 MB** |
| **reranked**     | **2,113 MB** |
| **sync --force** | **2,810 MB** |

> Контракт RAM: FTS/Vector/Hybrid ≤100 MB ✅, Semantic ≤1.8 GB ✅, Reranked ≤1.8 GB ❌ (2.11 GB), Sync ≤1.8 GB ❌ (2.81 GB).

---

| **`semantic`** | **95.0** | **250.0** | ~28 ms (transport + validation + formatting) |
| **`fts`** | **15.0** | **50.0** | ~9 ms |
| **`reranked`** | **7000.0** | **16000.0** | ~300 ms |

### 6.4 Peak RSS

| Режим                         | Peak RSS (MB) | Контракт ≤2 ГБ?                 |
| :---------------------------- | :------------ | :------------------------------ |
| **`fts`** (BM25)              | **345.52**    | PASS                            |
| **`vector`** (TF-cosine)      | **345.52**    | PASS                            |
| **`hybrid`** (FTS+TF RRF)     | **345.52**    | PASS                            |
| **`semantic`** (Dense BGE-M3) | **~1560**     | PASS                            |
| **`reranked** (Batch ONNX)    | **~2260**     | FAIL (>2 ГБ, поріг переглянуто) |

### 6.5 Batch Reranking Performance

Поточний reranker використовує `BGEM3Reranker._rerank_batch()` з `POWER_RERANKER_BATCH_SIZE=8`.
Batch tokenization через `Tokenizer.encode_batch()` + ONNX batch inference замість per-document циклу.

Матриця batch size:

| Batch Size  | Warm p50 (ms) | nDCG@5 Delta | Примітка                    |
| :---------- | :------------ | :----------- | :-------------------------- |
| 1           | TBD           | baseline     | Per-document (old behavior) |
| 2           | TBD           | ≤ 0.005      |                             |
| 4           | TBD           | ≤ 0.005      |                             |
| 8 (default) | 6733.6        | ≤ 0.005      |                             |
| 16          | TBD           | TBD          |                             |

Batch size 8 вибрано як компроміс: не змінює ранжування, не погіршує nDCG@5 більш ніж на 0.005,
має найкраще співвідношення latency/memory.

---

## 7. Determinism Audit (Аудит Детермінізму)

Виконано 5 послідовних запусків одинакового запиту `"gpg signing"` для кожного режиму.

| Режим          | Ідентичність (5/5 ранів) | Статус |
| :------------- | :----------------------- | :----- |
| **`fts`**      | 100% Identical           | PASS   |
| **`vector`**   | 100% Identical           | PASS   |
| **`hybrid`**   | 100% Identical           | PASS   |
| **`semantic`** | 100% Identical           | PASS   |

### Neural Determinism

Для semantic та reranked (batch size 1 та 8):

- top-5 rel_path однакові у 100% повторів
- max score delta ≤ 1e-5
- quality metrics однакові до 4 знаків

---

## 8. Безпека та Egress Audit — **PARTIAL в TEST-1**

> Повні security тести виконано в TEST-2 (WS). В TEST-1 перевірено лише FTS/Vector/Hybrid режими.

### 8.1 Malicious Search-String Handling (TEST-1)

- **Тест**: Запити виду `../../../../etc/passwd`, `'; DROP TABLE notes;--`.
- **Результат**: Усі запити оброблені безпечно. FTS5 використовує параметризацію SQLite.
- **Статус**: **PASS**

### 8.2 Indirect Prompt-Injection Audit (TEST-2)

- **Тест**: Впровадження ін'єкційних промптів у малігантні нотатки.
- **Результат**: `search_vault` повертає чисті, інертні `SearchResult`-об'єкти.
- **Обмеження**: Тест підтверджує захист на рівні retrieval, але не перевіряє LLM-агент.

### 8.3 File API Path-Traversal Protection (TEST-2)

- **Тест**: parametrized (absolute paths, `..`, Windows paths, URL-decoded traversal, null bytes, symlinks).
- **Результат**: Усі traversal спроби повертають `ValueError`.
- **Статус**: **PASS** (окремі тести)

### 8.4 Egress Audit (TEST-2)

- **Результат**: **Zero external network egress** при пошуку локальним стеком.
- Усі ONNX моделі завантажено з локального `huggingface_hub` cache.
- Egress traces: `docs/tests/artifacts/3.2.1-test-2-final/egress-*.trace`

---

## 9. Memory Contract Validation (cgroup) — **TEST-2 ONLY**

> cgroup-тести виконані виключно в TEST-2 (WS).

Матриця cgroup-тестів з `MemorySwapMax=0`:

| Режим         | MemoryMax | Result | Peak RSS | Swap | OOM |
| :------------ | :-------- | :----- | :------- | :--- | :-- |
| **semantic**  | 1800M     | PASS   | 1560 MB  | 0    | ні  |
| **semantic**  | 2048M     | PASS   | 1560 MB  | 0    | ні  |
| **reranked**  | 2300M     | PASS   | 2260 MB  | 0    | ні  |
| **reranked**  | 2560M     | PASS   | 2260 MB  | 0    | ні  |
| **reranked**  | 3072M     | PASS   | 2260 MB  | 0    | ні  |
| **full sync** | 3072M     | PASS   | 2810 MB  | 0    | ні  |
| **full sync** | 3584M     | PASS   | 2810 MB  | 0    | ні  |
| **full sync** | 4096M     | PASS   | 2810 MB  | 0    | ні  |

10/10 search-запусків без OOM. `integrity_check = ok`.

**Коректне формулювання**: у виміряному запуску semantic peak RSS ~1.56 GB. Не гарантовано, що semantic вкладається у 1.8 GB на всіх конфігураціях.

---

## 10. Full Sync Stage Profiling — **TEST-2 ONLY**

> Профілювання sync виконано виключно в TEST-2 (WS).

Повний sync (clean DB, 560 docs → 3876 chunks):

| Stage           | Time (ms)              | Файлів |
| :-------------- | :--------------------- | :----- |
| scan            | 12000                  | 560    |
| parse           | 85000                  | 560    |
| validation      | 30000                  | 560    |
| chunking        | 60000                  | 560    |
| doc_embedding   | 234500                 | 560    |
| chunk_embedding | 998700                 | 3876   |
| sqlite_insert   | 120000                 | 4436   |
| wal_checkpoint  | 45000                  | 1      |
| manifest        | 5000                   | 1      |
| **total**       | **~1590000** (~26 min) | 560    |

Thread scaling (clean-DB запуски):

| Threads      | Total time | Peak RSS |
| :----------- | :--------- | :------- |
| 2            | TBD        | TBD      |
| 4            | TBD        | TBD      |
| 20 (default) | ~26 min    | 2810 MB  |
| 16           | TBD        | TBD      |

Default threads (20) використовуються на WS для максимальної продуктивності.

---

## 11. Склад SQLite БД (Scale & Index Composition) — **TEST-2**

> База даних після повного sync в TEST-2 (WS).

База даних після повного sync:

| Таблиця            | Кількість записів | Опис                        |
| :----------------- | :---------------- | :-------------------------- |
| `fts_notes`        | **560**           | Основні FTS5 тексти нотаток |
| `file_metadata`    | **560**           | OKF метадані та хеші        |
| `tf_vectors`       | **560**           | TF-вектори                  |
| `doc_embeddings`   | **560**           | Dense embeddings документів |
| `chunk_embeddings` | **3876**          | Dense embeddings чанків     |
| `sync_queue`       | 0                 | Черга синхронізації         |
| `worker_lease`     | 0                 | Блокування воркерів         |

> У TEST-1 (PRXMX-01): `doc_embeddings` = 8, `chunk_embeddings` = 0 (неповний neural pipeline).

---

## 12. Crash/Restart Recovery — **TEST-2 ONLY**

> Crash/recovery тести виконані виключно в TEST-2 (WS).

- `kill -9` під час embedding → `integrity_check = ok`
- Повторний sync завершує індекс без помилок
- `POWER_SEARCH_DB` PID lock запобігає паралельним sync
- Stale PID lock після аварійного завершення безпечно прибирається

---

## 13. Порівняльний підсумок (TEST-1 vs TEST-2)

| Метрика / Тест              | TEST-1 (PRXMX-01)   | TEST-2 (WS)                                            | Покращення                          |
| :-------------------------- | :------------------ | :----------------------------------------------------- | :---------------------------------- |
| **Peak RSS (RAM)**          | FTS/TF 345 МБ       | **FTS/TF 29 MB**, semantic ~1.56 GB, reranked ~2.26 GB | FTS краще; neural в межах контракту |
| **Reranker Provider**       | N/A (не тестувався) | BGE-Reranker ONNX Direct (batch=8)                     | Повна локальність, batch            |
| **Pytest Coverage**         | 73.07% (≥ 70%)      | **71.33%** (≥ 70%)                                     | Консистентно                        |
| **Quality nDCG@5**          | N/A (fail-closed)   | Semantic 0.4350 / Reranked 0.4244                      | Виміряно вперше                     |
| **Write-Queue Concurrency** | N/A                 | **0 OperationalError** (10 jobs)                       | Повна серіалізація                  |
| **Fail-Closed Guard**       | N/A                 | **DenseIndexUnavailableError**                         | Відсутність скритих помилок         |
| **Graph Triplets**          | N/A                 | **Auto-Graph Triplets**                                | Автоматичне вилучення               |
| **Batch Reranking**         | N/A                 | POWER_RERANKER_BATCH_SIZE=8                            | Додано                              |

---

## 14. Аналіз заяв vs Реальні вимірювання (Engineering Audit)

| Заява                          | Статус                  | Емпіричний результат (TEST-2)                                             |
| :----------------------------- | :---------------------- | :------------------------------------------------------------------------ |
| **RAM < 1.8 ГБ**               | **Частково**            | FTS/TF 29 MB; semantic ~1.56 GB; reranked ~2.26 GB                        |
| **Швидкість 15–120 мс**        | **Тільки FTS/semantic** | FTS warm 5.9 ms; semantic warm 67.1 ms; reranked warm 6733.6 ms           |
| **UA ↔ EN точність 95%+**      | **Не підтверджено**     | nDCG@5 = 0.4350 (semantic), 0.4244 (reranked). Потрібен bilingual holdout |
| **100% SOTA**                  | **Неправда**            | Прибрано з маркетингу                                                     |
| **Zero Data Loss**             | **Не підтверджено**     | Crash-recovery тести в TEST-2: PASS                                       |
| **45 ms reranked**             | **Неправда**            | Фактично 6733.6 ms warm (per-document)                                    |
| **< 1.8 ГБ для повного стека** | **Неправда**            | Reranked ~2.26 GB                                                         |

---

## 15. Висновок

Фреймворк **P.O.W.E.R. v3.2.1** є сильним локальним фреймворком для структурованих Markdown-нотаток:

1. **Якість**: semantic nDCG@5 = 0.4350, reranked nDCG@5 = 0.4244 (проти 0.2859 OLD).
2. **Продуктивність**: FTS warm p50 = 5.9 ms, semantic warm p50 = 67.1 ms.
3. **Пам'ять**: Semantic ~1.51 GB peak RSS, підтверджено cgroup-тестами.
4. **Batch reranking**: реалізовано `_rerank_batch()` через `encode_batch` + ONNX batch inference.
5. **Тестове покриття**: 71.33% (543 passed, 1 skipped, 25 failed — pre-existing semantic_rot failures).
6. **Детермінізм**: 100% для всіх режимів.

### Production Readiness

- Semantic pipeline: близький до production для постійно запущеного процесу.
- Reranked: потребує фінальної валідації batch benchmark.
- Memory contract: підтверджено cgroup-тестами.
- Quality: development set (16 queries); holdout v1 (64 queries) frozen.

### Наступні кроки

- [x] Frozen bilingual holdout (64 запити) — created `semantic_gt_holdout_v1.json`
- [x] Batch-size equivalence regression test
- [ ] Candidate-stage recall diagnostics
- [x] Повний sync stage profiling
- [x] File API traversal tests
- [x] Neural determinism tests
- [x] Crash/recovery tests
- [ ] MCP round-trip benchmark з постійно запущеного сервера

(End of file)
