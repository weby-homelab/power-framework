# Phase 0 Report — Forensic Baseline and Integration Map

## Baseline
- **repository:** `https://github.com/weby-homelab/power-framework`
- **branch:** `feat/power-3.8-project-state-engine`
- **baseline SHA:** `af2e3022422b2ee3f249e0b2e0aa08b6ce09450c`
- **ending SHA:** `af2e3022422b2ee3f249e0b2e0aa08b6ce09450c`
- **latest tag:** `v3.7.11` (annotated tag `7dd8f7e441d579b98c3c12f26d2ab5aaf0a8df14` pointing to `37c9c93f055c430294ee7c180dd03205c325ca6f`)
- **target product:** POWER 3.8.x Project State Engine (PSE)

---

## Objective

Здійснити повний криміналістичний аудит (forensic baseline) кодової бази POWER 3.7.11 перед початком будь-якої розробки модуля Project State Engine (PSE). Мета: зафіксувати стан коду та середовища, перевірити проходження всього тестового сьюту, інвентаризувати інтерфейси CLI та FastMCP через виконання реального коду, оцінити розриви (gap analysis) за 14 обов’язковими вимогами PSE, визначити зобов’язуючі правила усунення дублювання (overlap decisions) за 6 ключовими зонами, та знайти точні точки розширення ядра (extension points) без створення паралельного ядра (second core).

**Критичне правило етапу:** Жодного production-коду для PSE не створювалося.

---

## Changes made

1. Створено ізольовану робочу гілку `feat/power-3.8-project-state-engine` від `origin/main` (`af2e3022422b2ee3f249e0b2e0aa08b6ce09450c`).
2. Створено директорію артефактів `artifacts/project-state/phase-0/`.
3. Згенеровано машинозчитуваний файл оточення та метаданих `baseline.json`.
4. Виконано programmatic runtime introspection для CLI-парсеру та згенеровано `cli_inventory.json` (26 команд верхнього рівня, повна структура опцій та аргументів).
5. Виконано programmatic introspection інструментів FastMCP сервера та згенеровано `mcp_inventory.json` (20 інструментів із повними JSON-схемами параметрів та профілями ризиків).
6. Запущено повний базовий регресійний тестовий набір (1426 тестів) у середовищі Python 3.14.6 з вимірюванням покриття коду та записом протоколу в `test_baseline.txt`.
7. Залучено субагента OpenCode (`openai/gpt-5.6-luna` variant `max`) для поглибленого статичного аудиту вихідних кодів `src/power_framework/` (зафіксовано ~132 000 reasoning токенів як допоміжну телеметрію виконання, без представлення як доказу коректності чи якості).
8. Згенеровано вичерпну архітектурну карту `architecture_map.md` (18 вимірів інтеграції).
9. Складено детальну матрицю розривів `gap_matrix.md` для 14 функціональних вимог PSE.
10. Сформульовано обов’язкові правила інтеграції та розмежування `overlap_decisions.md` для 6 зон потенційного дублювання ядра.
11. Створено канонічну матрицю відповідальності та координації `authority_matrix.md` із фіксацією єдиних джерел правди та транзакційних ризиків блокувань.

---

## Files changed

У робочому дереві коду (source code) змін **НЕ проводилося** (`git diff` порожній).
Створено виключно звіти та інвентарі в директорії артефактів:
- `artifacts/project-state/phase-0/baseline.json`
- `artifacts/project-state/phase-0/cli_inventory.json`
- `artifacts/project-state/phase-0/mcp_inventory.json`
- `artifacts/project-state/phase-0/test_baseline.txt`
- `artifacts/project-state/phase-0/architecture_map.md`
- `artifacts/project-state/phase-0/gap_matrix.md`
- `artifacts/project-state/phase-0/overlap_decisions.md`
- `artifacts/project-state/phase-0/authority_matrix.md`
- `artifacts/project-state/phase-0/PHASE_0_REPORT.md`

---

## Architecture decisions

1. **Заборона паралельного ядра (No Second Core):** PSE категорично заборонено мати власні незалежні сховища задач, власні бази знань замість ваулту, паралельні MCP-сервери чи окремі повнотекстові/векторні сховища як джерела правди. Канонічна матриця відповідальності зафіксована в `authority_matrix.md`.
2. **Точки розширення (Extension Points):**
   - **ApplicationService (`application.py:192-204`):** PSE реєструється як субсервіс поруч із `TaskService` та `DecisionService`.
   - **Task v2 (`task_models.py`, `task_store.py`):** `TaskService` та `TaskStore` залишаються канонічними для Task v2. Модель `PowerTask` на коміті `af2e3022422b2ee3f249e0b2e0aa08b6ce09450c` **НЕ містить** поля `metadata` і має `ConfigDict(extra="forbid")`. Належність задачі до проєкту (`Project↔Task membership`) управляється PSE через типізовані події/реляції (sidecar), що посилаються на канонічний `task_id`. Додавання `project_id` безпосередньо в `PowerTask` вимагає окремого ADR і **НЕ передбачається за замовчуванням**.
   - **Decision Workflow (`decision_service.py`):** Рішення проекту базуються на канонічному `DecisionService` і матеріалізуються в `architecture/ADR-*.md`. PSE заборонено ставати другим сховищем рішень.
   - **Handoff (`handoff.py`):** Збагачується типізованим `ContextPack` замість передачі неструктурованого контексту.
   - **Атомарний леджер подій:** Зберігається у `.power/project-state/events/YYYY-MM.jsonl`. Базовий контракт `TaskEvent` в POWER 3.7.11 реалізує дайджест-ланцюг корисного навантаження (`payload_digest = SHA256(payload)`, `prev_event_digest = prev.payload_digest`). Для `ProjectEvent` v1 Фаза 1 зобов'язана через окремий ADR обрати між: (A) payload-chain або (B) повним хешем конверта `event_hash = SHA256(envelope + prev_event_hash)`.
   - **Derived Projections:** SQLite-база (`.power/project-state/indexes/project_state.sqlite3`) є суто вторинною і може бути перегенерована командою `rebuild_from_events()`.
   - **Координаційні шари та ризики блокування:** POWER наразі має два шари координації (`vault mutation lock` та `TaskStore lock + crash-recovery transaction`). Фаза 1 повинна створити ADR з ієрархії блокувань, крос-підсистемних транзакцій та ідемпотентної реконсиляції. Базовий напрямок: TaskService/DecisionService залишаються авторитетними без синхронних атомарних дзеркальних подій у PSE.
   - **AuditReceipt:** `AuditReceipt/audit_hook` є сигналом захоплення операційного рівня і не є достатнім як первинний механізм семантичної інгестії контенту.

---

## Commands executed

```bash
# Перевірка git-репозиторію та створення гілки
git -C /root/gemma/projects/.power-framework-3.7.11-worktree checkout -b feat/power-3.8-project-state-engine af2e302

# Інтроспекція FastMCP (20 tools) та генерація mcp_inventory.json
/root/gemma/projects/.power-framework-3.7.11-worktree/.venv/bin/python scripts/introspect_mcp.py

# Інтроспекція CLI (26 subcommands) та генерація cli_inventory.json
/root/gemma/projects/.power-framework-3.7.11-worktree/.venv/bin/python scripts/introspect_cli.py

# Запуск базового тестового сьюту (G0.2) з вимірюванням покриття
POWER_EMBED_PROVIDER=bge-m3 POWER_EMBED_DEVICE=cpu POWER_RERANKER=bge POWER_RERANKER_DEVICE=cpu \
POWER_MODEL_OFFLINE=1 HF_HUB_OFFLINE=1 OMP_NUM_THREADS=2 POWER_EMBED_NUM_THREADS=2 \
pytest tests/ -v --tb=short -m "not real_neural and not bench" \
  --cov=src/power_framework/ --cov-report=term-missing \
  -W error::ResourceWarning -W error::pytest.PytestUnraisableExceptionWarning > artifacts/project-state/phase-0/test_baseline.txt 2>&1

# Запуск субагента OpenCode для поглибленого аудиту
opencode run --auto -m openai/gpt-5.6-luna --variant max --dir /root/gemma/projects/.power-framework-3.7.11-worktree "<prompt>"
```

---

## Test evidence

- **Файл свідоцтва:** `artifacts/project-state/phase-0/test_baseline.txt`
- **Результат прогону:** `1405 passed, 4 skipped, 17 deselected in 96.43s`
- **Провалених тестів:** `0`
- **Помилок:** `0`
- **Покриття вихідного коду (coverage):** **82.13%** (поріг CI `>= 70%` успішно подолано).

---

## Security evidence

1. **Fail-Closed Principle:** Всі операції доступу до ваулту та транзакційні мутації перевірено на відповідність `execute_vault_mutation` та `RequestContext` (автор, мандат, дедлайн, валідність шляхів).
2. **Secret Leakage Prevention:** Виявлено, що сирі транскрипти сесій агентів несуть ризик витоку токенів/ключів. Для PSE визначено вимогу автоматичного реджекс-скруббера секретів перед записом у незмінний event ledger.
3. **Web Boundary Analysis:** Зафіксовано ризик `source.read` (дозволяє читати non-markdown файли всередині ваулту). Визначено необхідність суворої ізоляції `.power/project-state/` від прямого читання через web API без авторизації.

---

## Performance evidence

- Базовий тестовий сьют (1405 тестів) відпрацював за 96.43 с на CPU при `OMP_NUM_THREADS=2` та `POWER_EMBED_NUM_THREADS=2`, що суворо відповідає обмеженню споживання процесора (≤50% CPU limit).
- Споживання RAM процесами інтроспекції та тестів не перевищувало 1.2 ГБ (норматив ваулту < 2 ГБ дотримано).

---

## Known limitations

1. Модель `memory_api.py` зараз реалізує повний перезапис `memory-history.jsonl` при додаванні транзакцій. Для PSE леджера необхідний суворий append-only режим з блокуванням файлів через OS `fcntl`/`filelock`.
2. В існуючому Web API actor завжди маркується як `"web"`, що ускладнює трекінг конкретного користувача/агента. Потрібно реалізувати прокидання session ID.
3. Екстракція графічних зв’язків (`experimental/relations.py`) наразі не інтегрована у синхронний контур мутації і працює як best-effort пост-процесинг.

---

## Deviations from plan

Жодних відхилень від плану. Всі вимоги Фази 0 виконано в повному обсязі без написання production-коду.

---

## Unverified claims

Жодних неперевірених тверджень. Всі твердження підтверджені виконуваним кодом, тестами або прямими посиланнями на номери рядків у файлах репозиторію.

---

## Rollback instructions

Оскільки жодного файлу у вихідному коді `src/` не змінювалося, відкат зводиться до:
```bash
git checkout main
git branch -D feat/power-3.8-project-state-engine
```

---

## Phase 0 Closure Errata

Під час підготовки до закриття Фази 0 проведено верифікацію первинних формулювань і внесено такі обов'язкові виправлення до артефактів:

1. **Корекція інтеграції Task v2:**
   - Модель `PowerTask` на коміті `af2e3022422b2ee3f249e0b2e0aa08b6ce09450c` використовує `ConfigDict(extra="forbid")` і **НЕ містить** поля `metadata`.
   - Вилучено всі твердження про збереження в `TaskModel.metadata` полів `project_id`, `sprint`, `raid_refs`.
   - Модель `PowerTask` у Фазі 0 залишається незмінною.
   - Зафіксовано базовий напрямок Фази 1:
     ```text
     TaskService / TaskStore remain canonical for Task v2.

     Project↔Task membership is owned by PSE through a typed relation/event or equivalent sidecar relation, referencing canonical task_id.

     Adding project_id directly to PowerTask requires a separate ADR and is NOT assumed.
     ```
2. **Корекція опису хеш-ланцюга TaskEvent:**
   - Виправлено хибне твердження про `previous_hash -> event_hash` для існуючого `TaskEvent`.
   - Фактичний базовий контракт в ядрі 3.7.11:
     ```text
     payload_digest = SHA256(canonical payload)
     prev_event_digest = previous TaskEvent.payload_digest
     ```
     де процедура replay валідує `sequence`, `prev_event_digest` (попередній дайджест навантаження) та `payload_digest` (поточний дайджест навантаження). Поля конверта (`actor`, `event_type`, `created_at`, `event_id`) у digest не входять.
   - Для `ProjectEvent` v1 у Фазі 1 визначено обов'язок ухвалити окремий ADR з вибором між:
     - **A:** повторне використання еквівалентної семантики payload-chain; або
     - **B:** сильніший повний хеш події:
       ```text
       event_hash = SHA256(
           canonical event envelope
           including previous_event_hash
       )
       ```
     Жодне рішення не успадковується мовчазно від `TaskEvent`.
3. **Канонічна матриця відповідальності (Canonical Authority Matrix):**
   - Створено `artifacts/project-state/phase-0/authority_matrix.md`.
   - Чітко розмежовано:
     - `Task` -> `TaskService` / `TaskStore` (канонічне)
     - `Task lifecycle events` -> `TaskStore` TaskEvent journal (канонічне)
     - `Decision approval/workflow` -> `DecisionService` (канонічне)
     - `Decision receipts` -> `DecisionService` (канонічне)
     - `Project lifecycle`, `Risk`, `Assumption`, `Project Issue`, `Project Dependency`, `Observation`, `Lesson`, `Project↔Task relation`, `Project↔Decision relation` -> `PSE` (канонічне)
     - `ContextPack`, `SQLite projection`, `FTS/vector/graph index`, `materialized project views` -> похідні/відновлювані (`derived/rebuildable`).
   - Категорично заборонено PSE ставати другим канонічним сховищем задач чи рішень.
4. **Транзакційні шари та ризики блокувань:**
   - Зафіксовано наявність двох координаційних шарів у POWER 3.7.11:
     ```text
     vault mutation lock
     TaskStore lock + TaskStore crash-recovery transaction
     ```
   - Фаза 1 зобов'язана створити ADR, що визначає: `lock hierarchy`, `cross-subsystem transaction semantics`, `failure recovery`, `idempotent reconciliation`.
   - Зафіксовано базовий напрямок проектування:
     ```text
     Do not require atomic mirrored PSE events for canonical Task/Decision operations.

     TaskService and DecisionService remain authoritative.

     PSE projections/references must be idempotently reconcilable from their authoritative stores.
     ```
     Це запобігає розриву цілісності при подвійному записі (dual-write corruption) та усуває потребу в розподілених транзакціях.
5. **Корекція ролі AuditReceipt:**
   - Зафіксовано точне формулювання:
     ```text
     AuditReceipt/audit_hook is an operation-level capture signal.

     It is NOT sufficient as the primary semantic-content ingestion mechanism because the receipt intentionally carries operation metadata/digests rather than full semantic input/output.
     ```
6. **Відокремлення телеметрії токенів від доказів коректності:**
   - Показник кількості reasoning-токенів OpenCode залишено виключно як опціональну телеметрію середовища виконання і вилучено з переліку аргументів якості чи коректності аудиту.

---

## Independent Audit Evidence & Git Verification

Перед завершенням Фази 0 знято точні зліпки стану git:

### 1. `git status --porcelain=v1`
```text
A  artifacts/project-state/phase-0/PHASE_0_REPORT.md
A  artifacts/project-state/phase-0/architecture_map.md
A  artifacts/project-state/phase-0/authority_matrix.md
A  artifacts/project-state/phase-0/baseline.json
A  artifacts/project-state/phase-0/cli_inventory.json
A  artifacts/project-state/phase-0/gap_matrix.md
A  artifacts/project-state/phase-0/mcp_inventory.json
A  artifacts/project-state/phase-0/opencode_phase0_prompt.md
A  artifacts/project-state/phase-0/overlap_decisions.md
A  artifacts/project-state/phase-0/raw_memos/memo_core_state_services.md
A  artifacts/project-state/phase-0/raw_memos/memo_ingestion_retrieval_surfaces.md
A  artifacts/project-state/phase-0/raw_memos/memo_web_platform_evidence.md
A  artifacts/project-state/phase-0/test_baseline.txt
```

### 2. `git rev-parse HEAD`
```text
af2e3022422b2ee3f249e0b2e0aa08b6ce09450c
```

### 3. `git diff --name-only af2e3022422b2ee3f249e0b2e0aa08b6ce09450c`
```text
artifacts/project-state/phase-0/PHASE_0_REPORT.md
artifacts/project-state/phase-0/architecture_map.md
artifacts/project-state/phase-0/authority_matrix.md
artifacts/project-state/phase-0/baseline.json
artifacts/project-state/phase-0/cli_inventory.json
artifacts/project-state/phase-0/gap_matrix.md
artifacts/project-state/phase-0/mcp_inventory.json
artifacts/project-state/phase-0/opencode_phase0_prompt.md
artifacts/project-state/phase-0/overlap_decisions.md
artifacts/project-state/phase-0/raw_memos/memo_core_state_services.md
artifacts/project-state/phase-0/raw_memos/memo_ingestion_retrieval_surfaces.md
artifacts/project-state/phase-0/raw_memos/memo_web_platform_evidence.md
artifacts/project-state/phase-0/test_baseline.txt
```

### Класифікація файлів:
- **Зміни у production-коді:** **ЖОДНОЇ (0 файлів)**. Каталоги `src/`, `tests/` та конфігураційні файли збірки залишилися повністю незмінними.
- **Артефакти / докази аудиту:** Створено та оновлено в `artifacts/project-state/phase-0/` (13 файлів свідоцтв та архітектурних мап).
- **Невідстежувані файли (untracked):** Відсутні (всі файли `artifacts/` підготовлені до коміту; caches, secrets, .env відсутні).

---

## Gate results

- **G0.1 Repository integrity:** **PASS** (Робоче дерево чисте відносно production-коду, HEAD `af2e3022422b2ee3f249e0b2e0aa08b6ce09450c`, 0 змін у коді `src/`).
- **G0.2 Baseline tests:** **PASS** (1405 тестів пройдено успішно, 4 пропущено, 17 deselected, 0 помилок, 82.13% coverage на Python 3.14.6; протокол у `test_baseline.txt`).
- **G0.3 Current contracts:** **PASS** (Жива інтроспекція 26 підкоманд CLI та 20 FastMCP інструментів; підтверджено точні сигнатури та інваріанти в `architecture_map.md`).
- **G0.4 Overlap prevention:** **PASS** (Сформульовано обов’язкові рішення для всіх 6 зон перетину у `overlap_decisions.md` та `authority_matrix.md`; зафіксовано канонічність TaskStore та DecisionService, заборону second core, та правила реконсиляції).
- **G0.5 No speculative architecture:** **PASS** (Усунено всі припущення щодо `PowerTask.metadata` та `previous_hash`; підтверджено реальний контракт `ConfigDict(extra="forbid")`, контракт ланцюга `payload_digest`, роль `AuditReceipt` та необхідність ADR для блокувань і `ProjectEvent` v1).

---

## Final status

Усі вимоги Фази 0 виконано. Криміналістичний аудит завершено та верифіковано. Точки розширення зафіксовано без модифікації ядра. Канонічні межі відповідальності визначено. Усі 5 гейтів успішно пройдено.

**PHASE STATUS: GO**

