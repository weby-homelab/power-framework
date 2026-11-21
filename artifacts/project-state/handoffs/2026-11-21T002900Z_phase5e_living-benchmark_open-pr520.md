# Хвиля 1–2 (PR #518, #519, #520) — результати та передача роботи до v3.8.0

```text
STAGE: SOLO_REFORM_WAVE1_AND_PHASE5E_LIVING_BENCHMARK
PR: #520 (feat/phase5e-living-benchmark) — OPEN, не змерджений
BASE_SHA: 0c87cc1d8dc6548978a3a7ffe64e5e205a8639c9 (main після PR #519)
PR_HEAD_SHA: 7d85cee2a9dec20e59131a71bf1f95e00c71b9e7 (tree afdc62e09083c6f472d2471d3a18097993b48c2f, GPG verified/valid)
OBSERVED_AT_UTC: 2026-11-21T00:29:00Z
PHASE_STATUS: Phase 5E — живий бенчмарк реалізовано; merge НЕ виконано
```

## 1. Що зроблено й підтверджено

| PR | main після merge | Результат |
|---|---|---|
| #518 `chore/solo-engineer-reform` | `30c2f202abc8e91f58e885b4fbac79f4657ee86b` | Реформа «Соло-інженер»: `+36/-6718` рядків, мертві one-shot скрипти/тести/плани в архів, `docs/plans/STATUS.md` |
| #519 `fix/f01-planner-semantic-dense` | `0c87cc1d8dc6548978a3a7ffe64e5e205a8639c9` | F-01: Stage 3 `RetrievalPlanner` викликає `mode="semantic"` (реальний dense) замість лексичного `vector`, downgrade → `degraded` |
| #520 `feat/phase5e-living-benchmark` | — (open) | Живий регресійний набір + runner + тести fallback |

PR #520 на `7d85cee2`: `mergeable_state=clean`; усі required check-runs (`test (3.13)`, `test (3.14)`, `analyze (python)`, `CodeQL`, `build`, `package-smoke`, `security`, `benchmark-integrity`, `base-runtime-smoke`, `upgrade-matrix`, `upgrade-matrix-aggregate`) = `success`, `deploy` = `skipped`, `CodeRabbit` = `neutral` (rate limit).

## 2. Вимірювання бенчмарку (36 запитів, усі інваріанти = 0)

| Ембедер | Режим | R@5 | MRR | nDCG@10 | sem_R@5 | dense | Затримка |
|---|---|---:|---:|---:|---:|---:|---:|
| детермінований | FAST | 0.7778 | 0.7778 | 0.7768 | 0.0000 | 0/36 | 36 мс |
| детермінований | BALANCED | 1.0000 | 1.0000 | 0.9990 | 1.0000 | 36/36 | 86 мс |
| BGE-M3 (CPU) | FAST | 0.7778 | 0.7778 | 0.7768 | 0.0000 | 0/36 | 30 мс |
| BGE-M3 (CPU) | BALANCED | 1.0000 | 1.0000 | 0.9990 | 1.0000 | 36/36 | 3.1 с (інший прогін: 2.2 с) |

Локально пройшли: `ruff`, `ruff format --check`, scoped `mypy`, `check_doc_drift.py`, `complexity_dashboard.py`, `mkdocs build --strict`, `71 passed / 1 skipped` (docs-venv), `3/3` бенчмарк-тести і `6/6` dense-тести у `power/venv`, `/home/weby/verify.sh` = `exit 0`.

## 3. Що НЕ завершено (чесно)

1. **Незалежне рев'ю PR #520 не отримано:** CodeRabbit rate-limited, read-only subagent зупинився з `429 RESOURCE_EXHAUSTED`. Перед merge потрібен новий рев'ю (інший агент або власник) і `SOLO_MAINTAINER_ATTESTATION`.
2. **Повний локальний `pytest` на S-Book не пройшов:** 47 однакових падінь і на чистому HEAD PR, і зі змінами (INFRA-брокер, `complexity_dashboard`, `release_receipt` тощо; 0 лише з diff) — це обмеження середовища (`/tmp` з груповим доступом, відсутність `.git`), а не регресія; CI на GitHub зелений. Повторити пару в приватному `TMPDIR` з копією `.git`.
3. **Є незакомічена локальна робота іншого агента** у worktree `/home/weby/projects/P.O.W.E.R.living-bench` (змінено `scripts/run_living_benchmark.py`, `tests/test_phase5e_living_benchmark.py`, `benchmarks/power38/living_regression/README.md`; handoff-и `2026-11-21T001024Z_phase5e_local_validation.md` та `2026-11-21T002344Z_phase5e_archive_comparison.md`): ізольований кеш + перевірка `query_side_writes` по кешу (SHM/порожній WAL ігноруються). Цей diff не перевірений мною і не включений у коміт; перед публікацією — перевірити й закомітити окремо.
4. `--embedder real` на S-Book потребує `HF_HUB_CACHE=/home/weby/.cache/power-hw471/materialized-models/hub`: `onnxruntime >= 1.30` відхиляє symlink-блоби HF (`External data path escapes model directory`). Виправлення в `model_policy.py` — у PR 4.

## 4. Наступні кроки (виконувати по черзі, 1 задача = 1 PR)

1. **Закрити PR #520:** отримати рев'ю, врахувати/закомітити локальний diff п.3.3 (або відкинути свідомо), дочекатися CI, attestation, normal merge, прибрати worktree і гілку.
2. **PR 4 — Phase 5F (incremental dense):** dirty-set re-embed лише змінених чанків (`reembed_amplification ≈ 1.0`), `generation_reconcile.py` / `index_write.py` / `index_sync.py`. Preflight уже відтворив два дефекти: зміна моделі оновлює manifest без перерахунку векторів; зміна вмісту при збереженому `mtime` лишає застарілий індекс. Плюс фікс symlink external data (п.3.4). Gate: `pytest`, `mypy src/power_framework/`, `ruff`, `complexity_dashboard.py`, `scripts/run_living_benchmark.py --embedder real`.
3. **PR 5 — #468, #469, #470:** capability/state-звіт замість `degraded`, вимоги remote SSH, пороги свіжості індексу.
4. **PR 6 — Phase 5G + #474:** пагінований `read_note`, компактний `get_server_info`, `compile_context` / `explain_context` у MCP; `query_side_writes == 0`.
5. **PR 7 — реліз v3.8.0:** bump `pyproject.toml` → `3.8.0`, Tier 2 gate, підписаний тег, оновлення `~/.local/share/power/venv`, 2 тижні dogfooding на `/brain`.

## 5. Пастки середовища

- Worktree + `docs-venv`: `PYTHONPATH="$PWD/src:$PWD"`; numpy/ONNX — через `/home/weby/.local/share/power/venv/bin/python` (там немає `pytest`).
- CPU ≤4 потоки: `OMP_NUM_THREADS=4 POWER_EMBED_NUM_THREADS=4 POWER_EMBED_DEVICE=auto`.
- Кирилицю тримати поза `.py` (`RUF001`); `sqlite3.connect` — лише через `contextlib.closing` (`-W error::ResourceWarning`).
- `verify.sh`: додати `docs-venv/bin` і `/home/weby/.local/share/power/tooling/uv/bin` у `PATH`, задати `POWER_VERIFY_REPO/BASE/EXPECTED_HEAD`.
- GitHub: `gh` не авторизований; токен читати з `/home/weby/.env` лише в пам'яті Python; push — через тимчасовий `GIT_ASKPASS` (0600).
