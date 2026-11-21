# POWER — Статус і робочий протокол (Solo-Engineer)

> **Джерела правди:** коміти = `git log` та GitHub Releases; задачі = GitHub Issues і Milestones; архітектура = `docs/adr/`. Окремі Admission PR, Closure Reconciliation PR і ручне переписування SHA у Markdown **скасовано**.

## Робочий режим

1. **1 задача = 1 PR:** код + тести + коротке оновлення документації в одному PR від свіжого `main`.
2. **Незмінні гейти якості й безпеки:** `11/11` required CI checks, CodeQL, GPG-підпис (`2D49E810C7F2527E`), protected normal merge (`SOLO_MAINTAINER`), `authority > relevance`, `query_side_writes == 0`, `scope_escape == 0`, `prompt_injection == 0`.
3. **Перевірка якості пошуку (без one-shot культу `v1.7+`):**
   - Інваріанти безпеки й авторитетності перевіряються детермінованими `pytest`-тестами в CI.
   - Якість (`Recall@5`, `MRR`, `nDCG`) перевіряється одним живим регресійним набором на режимах `FAST` (лексика) та `BALANCED` (реальний dense після фіксу `F-01`; `benchmarks/power38/living_regression/` + `scripts/run_living_benchmark.py`). Знайдено баг → фікс → перезапуск того самого тесту.
4. **Правило «2 тижні до живого dogfooding»:** якщо гілка/фаза триває довше 2 тижнів і не запускається на реальному `/brain` — спрощувати й випускати робочий зріз.
5. **Жорсткий мораторій до релізу `v3.8.0` на S-Book:** 0 годин на EmbeddingGemma 2, PostgreSQL, pgvector, AGE, S3/MinIO, A2A, GUI, нові мета-промпти та переписування старих handoff-ів.

## Дорожня карта релізів

| Версія | Фокус | Ключовий обсяг | Статус |
|---|---|---|---|
| **`v3.8.0`** | **Retrieval + Fast Index + Lean MCP** | 1. Solo-reform (**DONE**)<br>2. Фікс `F-01` (`RetrievalPlanner` → реальний dense, **DONE**)<br>3. Живий регресійний бенчмарк (`FAST` + `BALANCED`, **DONE**)<br>4. Інкрементальний dense dirty-set (Phase 5F)<br>5. Lean MCP + `#468`, `#469`, `#470`, `#474` (`read_note` сторінками, компактний `get_server_info`, пороги свіжості, `compile_context`/`explain_context`)<br>6. Реліз `v3.8.0` і встановлення на S-Book | **IN PROGRESS** |
| **`v3.9.0`** | **Capture + Queue** | `power.observation.v1`, SQLite `IndexWorkQueue`, 1–2 адаптери (Codex / OpenCode / Antigravity) | **PLANNED** |
| **`v3.10.0`** | **Views + Graphs + Handoff** | SQLite `EvidenceGraph` / `ExecutionGraph`, `LocalCAS`, уніфікація `.power/tasks` vs `work-packets`, Chaos + Zero-Explanation Handoff тест | **PLANNED** |
| **Post-3.10** | **Опційно (за фактом вузького місця)** | EmbeddingGemma 2 (ADR-0009), Fleet GPU Builder, Docker GUI Cockpit v2, Remote MCP / Hub (Postgres/pgvector/AGE/S3) | **DEFERRED** |

## Опорна база

- Активна публічна гілка підтримки: `release/3.7` (`v3.7.13`).
- Історичні документи планування перенесено до [`artifacts/project-state/archive/plans/`](https://github.com/weby-homelab/power-framework/tree/main/artifacts/project-state/archive/plans).

## Поточний стан і наступні кроки до v3.8.0

Повні результати, вимірювання й пастки середовища: [handoff 2026-11-21](https://github.com/weby-homelab/power-framework/blob/main/artifacts/project-state/handoffs/2026-11-21T002900Z_phase5e_living-benchmark_open-pr520.md).

- **Зроблено:** #518 (реформа), #519 (F-01), #520 (живий бенчмарк; `BALANCED` R@5=1.0 проти `FAST` 0.78, усі інваріанти 0) — #520 ще відкритий, чекає незалежного рев'ю та merge.
- **Далі, по черзі:** закрити #520 → PR 4 (Phase 5F: incremental dense + symlink-фікс ONNX) → PR 5 (#468/#469/#470) → PR 6 (Phase 5G + #474) → PR 7 (реліз `v3.8.0`, dogfooding 2 тижні).
- **Інваріанти:** 1 задача = 1 PR, GPG-підпис, 11/11 CI + CodeQL, protected normal merge, жодного обходу гейтів.
