# Why P.O.W.E.R. 3.2.1 — Measured Performance

## Empirical Benchmarks (560 documents / 3876 projected chunks, WS)

| Metric                | FTS (BM25) | Vector (TF) | Hybrid   | Semantic (BGE-M3) | Reranked  |
| :-------------------- | :--------- | :---------- | :------- | :---------------- | :-------- |
| Cold p50              | 274 ms     | 420 ms      | 432 ms   | 8,040 ms          | 28,947 ms |
| Warm p50 (in-process) | 5.9 ms     | 146.7 ms    | 148.3 ms | 67.1 ms           | 6,734 ms  |
| Warm p95              | 38 ms      | 821 ms      | 860 ms   | 324 ms            | 32,305 ms |
| Peak RSS              | 29 MB      | 65 MB       | 57 MB    | 1,510 MB          | 2,113 MB  |

### Quality (development set, 16 queries)

- Semantic nDCG@5: **0.4350**
- Reranked NEW nDCG@5: **0.4244** (vs OLD 0.2859, +48%)
- Reranked не перевищує semantic; batch inference — latency-only optimization.

### Frozen Holdout v1 (64 queries: 16 EN→EN, 16 UA→UA, 16 UA→EN, 16 EN→UA)

- Semantic nDCG@5: **0.4210**
- Reranked NEW nDCG@5: **0.4105**
- Semantic залишається default, reranked = opt-in.

### Key Details

- Batch ONNX inference (POWER_RERANKER_BATCH_SIZE=8) в BGEM3Reranker
- Full sync peak RSS: ~2.81 GB (20 threads, batch=64)
- Профільовано на WS (Intel Xeon E5-2666 v3, 20 cores, 121 GB RAM)
- Pytest coverage: **71.33%** (543 passed, 25 failed pre-existing, 1 skipped)
- Quality-набір: 16 development-запитів; production holdout (64 запити) frozen
- **Status**: PASS WITH KNOWN BASELINE FAILURES (0 new failures vs origin/main)

| Критерій / Фреймворк        | ⚡ **P.O.W.E.R. 3.2.1**                                                                          | 🦜 **LangChain / LlamaIndex**            | 🕸️ **Microsoft GraphRAG**                 | 🧠 **MemGPT / Letta**          | 🔍 **Chroma / Standard Vector**        |
| :-------------------------- | :----------------------------------------------------------------------------------------------- | :--------------------------------------- | :---------------------------------------- | :----------------------------- | :------------------------------------- |
| **Призначення**             | База знань + MCP суперпам'ять AI-агентів                                                         | Загальний конструктор RAG                | Важкий графовий аналіз аналітики          | Довготривала пам'ять чат-ботів | Сире векторне сховище                  |
| **Економія токенів**        | 🟢 **До 95%** (Sub-indexes + Chunks)                                                             | 🔴 Низька (липкий контекст, dump файлів) | 🟡 Середня (дорого коштує побудова графа) | 🟡 Середня (компресія сесій)   | 🔴 Низька (немає ієрархічних індексів) |
| **Споживання RAM**          | 🟡 **~1.5–2.8 ГБ** (BGE-M3 ONNX, залежить від режиму)                                            | 🟡 2–6 ГБ (Python runtime + PyTorch)     | 🔴 16–32 ГБ (OOM на VPS/LXC)              | 🟡 2–4 ГБ                      | 🟢 1–3 ГБ                              |
| **Швидкість пошуку**        | 🟡 **67 ms – 29 s** (залежить від режиму: FTS 274ms, semantic 8s cold / 67ms warm, reranked 29s) | 🟡 300 – 1500 ms                         | 🔴 2000 – 8000 ms                         | 🟡 500 – 2000 ms               | 🟢 50 – 200 ms                         |
| **Двомовність UA ↔ EN**     | 🟢 **nDCG@5=0.4350** (BGE-M3 1024d, bilingual UA+EN)                                             | 🔴 Базовий OpenAI / MiniLM               | 🟡 OpenAI Embeddings (дорого)             | 🔴 Базові моделі               | 🔴 Потребує важких моделей             |
| **Захист від втрати даних** | 🟡 **Linter + Backups** (Zero Data Loss потребує підтвердження crash-recovery)                   | 🔴 Відсутній (memory reset)              | 🔴 Складний rebuild                       | 🟡 Залежить від БД             | 🔴 Немає лінтера метаданих             |
| **MCP 3.x підтримка**       | 🟢 **Нативна (12 інструментів out-of-the-box)**                                                  | 🟡 Потребує обгорток                     | 🔴 Відсутня                               | 🟡 Обмежена                    | 🔴 Відсутня                            |
| **Контроль якості коду**    | 🟢 **OKF Linter + Pydantic v2 + Heal**                                                           | 🔴 Відсутній                             | 🔴 Відсутній                              | 🔴 Відсутній                   | 🔴 Відсутній                           |

## Статус production-ready

Semantic pipeline: близький до production для постійно запущеного процесу (warm 67ms).
Reranked pipeline: quality nDCG@5=0.4244 (+48%), latency 29s cold / 6.7s warm (batch=1) / ~2.5s warm (batch=8 projected).
Memory contract: semantic вкладається в 1.8GB; reranked (2.1GB) і sync (2.8GB) перевищують — потребує cgroup валідації.
Доказова база: TEST-2 звіт + артефакти + benchmark-summary.json + frozen holdout v1.

## MCP Config (verified)

```json
{
    "mcpServers": {
        "power": {
            "command": "python3",
            "args": ["-m", "power_framework.mcp"],
            "env": {
                "POWER_VAULT_DIR": "/absolute/path/to/second-brain"
            }
        }
    }
}
```
