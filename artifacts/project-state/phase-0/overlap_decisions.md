# POWER 3.7.11 Binding Overlap Decisions for Project State Engine (PSE)

**Date:** 2026-09-03
**Repository:** https://github.com/weby-homelab/power-framework
**Baseline Commit:** `af2e3022422b2ee3f249e0b2e0aa08b6ce09450c`
**Status:** BINDING ARCHITECTURAL MANDATE (Phase 0 Gate G0.4)

---

## 1. Мета документу

Цей документ фіксує обов’язкові правила інтеграції та розмежування між існуючими сервісами POWER 3.7.11 та створюваним модулем Project State Engine (PSE). 

**Головний імператив:** Запобігти випадковому створенню паралельного ядра (second core), дублюванню сховищ задач, роздвоєнню механізмів пам’яті або створенню другого джерела правди.

---

## 2. Зобов’язуючі рішення щодо 6 критичних зон перетину

### Зона 1: Task v2 (`task_models.py`, `task_store.py`, `task_service.py`) vs PSE Tasks

- **Класифікація:** **`REUSE`** + **`RELATION`** (Категорично **`PROHIBITED DUPLICATE`** для окремого сховища задач).
- **Обґрунтування кодом:**
  `src/power_framework/core/task_models.py:87-126` та `task_store.py:60-250` реалізують канонічну модель `PowerTask` з атомарним збереженням у `.power/tasks/`, оптимістичним блокуванням за `revision`, строгою валідацією переходів (`VALID_TRANSITIONS`), дайджест-ланцюгом подій (`TaskEvent`) та журналом під транзакційним маніфестом.
  Модель `PowerTask` на базовому коміті `af2e3022422b2ee3f249e0b2e0aa08b6ce09450c` використовує `ConfigDict(extra="forbid")` і **НЕ містить** поля `metadata`. Спроби передати довільні ключі викликають `ValidationError`. Модель `PowerTask` у Фазі 0 залишається незмінною.
- **Рішення та напрямок Фази 1:**
  1. `TaskService` та `TaskStore` залишаються єдиним канонічним сховищем і джерелом правди для Task v2 (`.power/tasks/`).
  2. PSE категорично заборонено створювати власне незалежне сховище задач, паралельні таблиці в SQLite чи окремі файли завдань.
  3. Належність задачі до проекту (`Project↔Task membership`) управляється PSE через типізовані зв'язки/події (`TASK_ATTACHED_TO_PROJECT`) або еквівалентні sidecar-реляції, що посилаються на канонічний `task_id`.
  4. Додавання `project_id` безпосередньо в `PowerTask` вимагає окремого ADR у Фазі 1 і **НЕ передбачається за замовчуванням**.
  5. Доступ до операцій над задачами здійснюється виключно через канонічний `TaskService` (`ApplicationService.task_*`).

---

### Зона 2: Decision Workflow (`decision_service.py`, `decision_models.py`) vs PSE Decisions & ADRs

- **Класифікація:** **`REUSE`** + **`ADAPTER`**.
- **Обґрунтування кодом:**
  `src/power_framework/core/decision_service.py:48-260` та `core/decision_models.py` реалізують повноцінний workflow прийняття рішень (`PROPOSED -> APPROVED / REJECTED -> SUPERSEDED`), зберігання в `.power/decisions/` та зв’язок із задачами.
- **Рішення:**
  1. Семантична сутність PSE `DECISION` є тонким адаптером навколо канонічного `DecisionModel`.
  2. Всі операції узгодження та зміни статусу рішень делегуються в `DecisionService`.
  3. PSE додає рівень матеріалізації: затверджені рішення автоматично експортуються у людсько-читабельні файли `architecture/ADR-*.md` із захисним маркером `<!-- POWER-MANAGED-DO-NOT-EDIT-DIRECTLY -->`.

---

### Зона 3: Transactional Memory (`memory_api.py`) vs PSE Event Ledger & State

- **Класифікація:** **`BOUNDARY SEPARATION`** (Категорично **`PROHIBITED DUPLICATE`** сховища нотаток).
- **Обґрунтування кодом:**
  `src/power_framework/core/memory_api.py:60-350` управляє транзакційними змінами вмісту файлів нотаток у сховищі (Obsidian vault): генерація diff, пропозиція, апрув користувача, атомарний commit, відкат. `memory-history.jsonl` фіксує операції над нотатками, але перезаписується цілком (`memory_api.py:380-420`).
- **Рішення:**
  1. Чітке розділення меж відповідальності:
     - **Transactional Memory:** відповідає за зміст документів та нотаток у ваулті (Vault Knowledge Layer).
     - **Project State Engine Event Ledger:** відповідає за часову шкалу подій проекту, зміну статусів задач, ризики та контекст агентів (Project Execution & Governance Layer).
  2. PSE не використовує `memory-history.jsonl` як леджер подій. Леджер PSE реалізується як фізично незмінний файл з режимом `O_APPEND` у `.power/project-state/events/YYYY-MM.jsonl`.
  3. **Криптографічний ланцюг подій:**
     - Фактичний базовий контракт `TaskEvent` (`task_models.py:162-209`, `task_store.py:291-318`):
       ```text
       payload_digest = SHA256(canonical payload)
       prev_event_digest = previous TaskEvent.payload_digest
       ```
       де процедура replay валідує послідовність (`sequence`), попередній дайджест навантаження та поточний дайджест навантаження.
     - Для `ProjectEvent` v1 у Фазі 1 має бути прийнято явне рішення через ADR:
       - **Варіант A:** повторно використати еквівалентну семантику payload-chain; або
       - **Варіант B:** реалізувати сильніший повний хеш події:
         ```text
         event_hash = SHA256(
             canonical event envelope
             including previous_event_hash
         )
         ```
       Жодне рішення не успадковується мовчазно від `TaskEvent`.

---

### Зона 4: Handoff Workflow (`handoff.py`) vs PSE Context Packs & Agent Handoff

- **Класифікація:** **`EXTENSION`**.
- **Обґрунтування кодом:**
  `src/power_framework/core/handoff.py:100-380` надає механізм передачі контексту між агентами (`handoff_create`, `handoff_advance`), прив’язаний до активної задачі Task v2 (`active_task_id`), та зберігає стан передачі у `.power/handoff/`.
- **Рішення:**
  1. PSE розширює існуючий `handoff_create`, інтегруючи в нього скомпільований пакет контексту (`ContextPack`).
  2. Замість передачі сирого тексту або дампу пам’яті, агент-наступник отримує строго структурований пакет: поточна фаза проекту, активні обмеження, список валідних рішень, відкриті блокери та чіткий DoR/DoD.

---

### Зона 5: Receipt / Audit Logs (`core/application.py`) vs PSE Append-Only Ledger

- **Класифікація:** **`ADAPTER`** + **`CAPTURE SIGNAL`**.
- **Обґрунтування кодом:**
  `src/power_framework/core/application.py:85-106, 1052-1102` реалізує `AuditReceipt`, який є строго content-free (фіксує лише назву операції, статус, хід виконання, SHA-256 і тривалість, без копіювання тіла запиту чи контенту).
- **Рішення:**
  1. Канонічний аудит операцій рівня програми залишається в `AuditReceipt`.
  2. `AuditReceipt/audit_hook` є сигналом захоплення операційного рівня (`operation-level capture signal`).
  3. Він **НЕ є достатнім** як первинний механізм інгестії семантичного контенту (`primary semantic-content ingestion mechanism`), оскільки квитанція навмисно несе лише метадані операції та дайджести, а не повні семантичні вхідні/вихідні дані.
  4. PSE підключається до `ApplicationService(audit_hook=...)` суто для операційної телеметрії та кореляції виконання.
  5. Події предметної області (наприклад, додавання ризику RAID чи фіксація архітектурного рішення) записуються в леджер PSE через типізовані прикладні API з повним набором метаданих та хеш-ланцюгом.

---

### Зона 6: Search & Graph Index (`searcher.py`, `indexer.py`, `relations.py`) vs PSE Derived Search

- **Класифікація:** **`REUSE`** + **`EXTENSION`** (Категорично **`PROHIBITED DUPLICATE`** для пошукового рушія).
- **Обґрунтування кодом:**
  `src/power_framework/core/searcher.py:120-450` та `generation_index.py` мають високоефективний гібридний рушій (SQLite FTS5 + векторний пошук + RRF + BGE reranker + Graph traversal).
- **Рішення:**
  1. PSE не створює власної паралельної векторної бази даних чи незалежного повнотекстового індексу як джерела правди.
  2. Локальна база SQLite для PSE (`.power/project-state/indexes/project_state.sqlite3`) є суто вторинною кеш-проекцією, яка будь-якої миті може бути на 100% перегенерована з леджера подій командою `rebuild_from_events()`.
  3. Матеріалізовані файли проекту (`ADR-*.md`, `lessons-*.md`) індексуються штатним індексатором POWER без будь-яких модифікацій ядра пошуку.

---

## 3. Транзакційні шари, блокування та ризики координації

В архітектурі POWER 3.7.11 наразі функціонують щонайменше два незалежні координаційні шари:
1. `vault mutation lock` (`core/mutation.py:69-99`): in-process `RLock` + міжпроцесне блокування `.power/vault.lock` для мутацій ваулту.
2. `TaskStore lock + TaskStore crash-recovery transaction` (`core/task_store.py:72-108, 366-432`): міжпроцесне блокування `.power/tasks/.tasks.lock` та транзакційні маніфести відновлення після збоїв.

### Ризики взаємних блокувань та подвійного запису:
- Додавання третього блокування без чіткої ієрархії може призвести до deadlocks при паралельних крос-сервісних операціях.
- Спроби синхронного двофазного запису між `TaskStore`/`DecisionService` та PSE несуть ризик розриву узгодженості (dual-write corruption).

### Обов’язковий мандат для Фази 1:
Фаза 1 повинна створити окремий ADR, що визначає:
- `lock hierarchy` (ієрархію захоплення блокувань);
- `cross-subsystem transaction semantics` (семантику транзакцій між підсистемами);
- `failure recovery` (протокол відновлення після збоїв);
- `idempotent reconciliation` (ідемпотентну реконсиляцію).

### Базовий напрямок проєктування (Default Design Direction):
```text
Do not require atomic mirrored PSE events for canonical Task/Decision operations.

TaskService and DecisionService remain authoritative.

PSE projections/references must be idempotently reconcilable from their authoritative stores.
```
Це дозволяє уникнути пошкодження даних внаслідок подвійного запису та запобігає необхідності впровадження важких розподілених транзакцій.

---

## 4. Зведена таблиця інтеграційних контрактів

| Компонент | Класифікація | Канонічне джерело | Сховище правди | Стан у PSE |
|---|:---:|---|---|---|
| **Task** | `REUSE` / `RELATION` | `core.task_service.TaskService` | `.power/tasks/*.json` | Канонічний Task v2; Project↔Task зв'язок через подію/реляцію PSE (без зміни `PowerTask` без ADR) |
| **Decision** | `REUSE` / `ADAPTER` | `core.decision_service.DecisionService` | `.power/tasks/decisions/*.json` | Адаптер + генерація `ADR-*.md` |
| **Memory** | `BOUNDARY SEPARATION` | `core.memory_api` | Vault Markdown files | Окремий домен (Vault vs Project) |
| **Handoff** | `EXTENSION` | `core.handoff` | `.power/handoff/*.json` | Збагачення через `ContextPack` |
| **Audit** | `ADAPTER` / `SIGNAL` | `core.application.AuditReceipt` | Application audit hook | Сигнал операційного рівня (недостатній для семантичної інгестії контенту) |
| **Search** | `REUSE` | `core.searcher.Searcher` | `.cache/power-framework/...` | Вторинна rebuildable проекція |
