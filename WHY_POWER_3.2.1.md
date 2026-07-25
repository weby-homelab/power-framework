# Why P.O.W.E.R. 3.2.1 — Measured Performance

## Empirical Benchmarks (560 documents / 1608 chunks, WS)

| Metric                | FTS (BM25) | Vector (TF) | Hybrid   | Semantic (BGE-M3) | Reranked  |
| :-------------------- | :--------- | :---------- | :------- | :---------------- | :-------- |
| Cold p50              | 274 ms     | 1844 ms     | 1124 ms  | 8040 ms           | 28947 ms  |
| Warm p50 (in-process) | 5.9 ms     | 146.7 ms    | 148.3 ms | 67.1 ms           | 6733.6 ms |
| Warm p95              | 166 ms     | 2788 ms     | 2253 ms  | 200 ms            | 15000 ms  |
| Peak RSS              | 345 MB     | 345 MB      | 345 MB   | ~1.56 GB          | ~2.26 GB  |

### Quality (development set, 16 queries)

- Semantic nDCG@5: **0.4350**
- Reranked NEW nDCG@5: **0.4244** (vs OLD 0.2859)
- Reranked поки не перевищує semantic; batch inference оцінюється окремо.

### Key Details

- Batch ONNX inference (POWER_RERANKER_BATCH_SIZE=8) у BGEM3Reranker
- Full sync peak RSS: ~2.81 GB
- Профільовано на PRXMX-01 (i5-5200U, 4 vCPU, LXC)
- Pytest coverage: 74.14% (540 passed, 1 skipped)
- Quality-набір: 16 development-запитів; production holdout (64+ запитів) готується

| Критерій / Фреймворк        | ⚡ **P.O.W.E.R. 3.2.1**                                                                          | 🦜 **LangChain / LlamaIndex**            | 🕸️ **Microsoft GraphRAG**                 | 🧠 **MemGPT / Letta**          | 🔍 **Chroma / Standard Vector**        |
| :-------------------------- | :----------------------------------------------------------------------------------------------- | :--------------------------------------- | :---------------------------------------- | :----------------------------- | :------------------------------------- |
| **Призначення**             | База знань + MCP суперпам'ять AI-агентів                                                         | Загальний конструктор RAG                | Важкий графовий аналіз аналітики          | Довготривала пам'ять чат-ботів | Сире векторне сховище                  |
| **Економія токенів**        | 🟢 **До 95%** (Sub-indexes + Chunks)                                                             | 🔴 Низька (липкий контекст, dump файлів) | 🟡 Середня (дорого коштує побудова графа) | 🟡 Середня (компресія сесій)   | 🔴 Низька (немає ієрархічних індексів) |
| **Споживання RAM**          | 🟡 **~1.6–2.8 ГБ** (BGE-M3 ONNX, залежить від режиму)                                            | 🟡 2–6 ГБ (Python runtime + PyTorch)     | 🔴 16–32 ГБ (OOM на VPS/LXC)              | 🟡 2–4 ГБ                      | 🟢 1–3 ГБ                              |
| **Швидкість пошуку**        | 🟡 **68 ms – 29 s** (залежить від режиму: FTS 274ms, semantic 8s cold / 68ms warm, reranked 29s) | 🟡 300 – 1500 ms                         | 🔴 2000 – 8000 ms                         | 🟡 500 – 2000 ms               | 🟢 50 – 200 ms                         |
| **Двомовність UA ↔ EN**     | 🟢 **nDCG@5=0.4350** (BGE-M3 1024d, bilingual UA+EN)                                             | 🔴 Базовий OpenAI / MiniLM               | 🟡 OpenAI Embeddings (дорого)             | 🔴 Базові моделі               | 🔴 Потребує важких моделей             |
| **Захист від втрати даних** | 🟡 **Linter + Backups** (Zero Data Loss потребує підтвердження crash-recovery)                   | 🔴 Відсутній (memory reset)              | 🔴 Складний rebuild                       | 🟡 Залежить від БД             | 🔴 Немає лінтера метаданих             |
| **MCP 3.x підтримка**       | 🟢 **Нативна (12 інструментів out-of-the-box)**                                                  | 🟡 Потребує обгорток                     | 🔴 Відсутня                               | 🟡 Обмежена                    | 🔴 Відсутня                            |
| **Контроль якості коду**    | 🟢 **OKF Linter + Pydantic v2 + Heal**                                                           | 🔴 Відсутній                             | 🔴 Відсутній                              | 🔴 Відсутній                   | 🔴 Відсутній                           |

## Статус production-ready

Semantic pipeline: близький до production для постійно запущеного процесу.
Reranked, memory contract і доказова база звіту потребують фінальної валідації.
