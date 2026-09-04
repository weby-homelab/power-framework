# POWER 3.7.11 Forensic Architecture Map for Project State Engine (PSE)

**Generated:** 2026-09-03
**Repository:** https://github.com/weby-homelab/power-framework
**Baseline Commit:** `af2e3022422b2ee3f249e0b2e0aa08b6ce09450c`
**Active Branch:** `feat/power-3.8-project-state-engine`
**Target Release:** POWER 3.8.x
**Status:** FORENSIC BASELINE COMPLETE (Phase 0)

---

## 1. Executive Architecture Summary

Цей документ містить вичерпний криміналістичний аудит кодової бази POWER 3.7.11 за 18 обов’язковими інтеграційними вимірами. Аудит проведено методом статичного аналізу вихідного коду, інтроспекції середовища виконання та верифікації тестовим сьютом (1405 passed, 82.13% coverage).

Головний висновок: **POWER 3.7.11 має зрілу, проте розрізнену транзакційну базу (ApplicationService, Task v2, DecisionService, Transactional Memory, Generation-based Search). Для впровадження Project State Engine (PSE) КАТЕГОРИЧНО ЗАБОРОНЕНО створювати паралельне ядро (паралельний task store, паралельний MCP-сервер чи окрему базу даних правди). PSE має інтегруватися виключно через існуючі точки розширення ядра (extension points).**

---

Проведи read-only forensic audit у `/root/gemma/projects/.power-framework-3.7.11-worktree` лише для dimensions 1–6 місії: core/application.py; mutation.py, vault_storage.py, write_queue.py; task_models.py, task_store.py, task_service.py; decision_service.py, decision_models.py; handoff.py; memory_api.py та безпосередньо потрібні core dependencies. Не редагуй жоден файл і не запускай destructive operations. Для кожного факту поверни точний relative path, class/function/method signature і line range, contracts/invariants, tests що це підтверджують, та PSE extension points/gaps. Перевір actual code, не roadmap claims. Окремо вкажи, що відсутнє після пошуку в src. Не пиши звіт у файли; поверни структурований research memo українською, без placeholders/secrets.

План: прочитаю обов’язковий контекст і локальні правила, після чого інвентаризую заявлені модулі та їхні прямі залежності без змін. Далі зіставлю реалізацію з тестами, зафіксую точні line ranges, інваріанти, PSE gaps і окремо відсутні компоненти в `src`.

Контекст підтверджено: аудит виконується на WS у гілці `feat/power-3.8-project-state-engine`; робоче дерево вже має сторонній untracked `artifacts/`, його не чіпаю. Локальних `.opencode/rules.md`, `AGENTS.md` і `brain/foundations/python_standards.md` у перевірених місцях не знайдено; останній release summary фіксує `v3.7.11` як verified, але це не є доказом для цієї реалізації.

План оновлено: цільові модулі вже прочитані; тепер перевіряю лише їхні прямі callee-и та regression tests. Тестовий запуск, якщо виконуватиму, піде з вимкненим cache/bytecode і `basetemp` поза репозиторієм, щоб не змінювати workspace.

# Read-only forensic research memo

## 0. База аудиту

- Repository: `/root/gemma/projects/.power-framework-3.7.11-worktree`
- HEAD: `af2e3022422b2ee3f249e0b2e0aa08b6ce09450c`
- Гілка: `feat/power-3.8-project-state-engine`
- Версія: `3.7.11`, Python `3.14.6`
- `git diff`: порожній. Існуючий untracked `artifacts/` не змінювався.
- Перевірено 114 targeted tests: **114 passed за 4.54 s**. Тестові `basetemp`, cache і bytecode були винесені/вимкнені поза repository.

Розглянуто dimensions 1–6 та прямі dependencies: `application_models.py`, `models.py`, `utils.py`, `parser.py`, `source_service.py`, `indexer.py`, `linter.py`, `generation_index.py`, `temporal.py`, `provenance.py`, `lifecycle.py`, `fault_injection.py`, `db.py`.

---

# 1. ApplicationService та Application Envelope

## Фактичний surface

| Relative path / signature | Реальний контракт |
|---|---|
| `src/power_framework/core/application.py:62-83` — `RequestContext` та `RequestContext.__post_init__(self) -> None` | Immutable context: `actor`, `authority`, `idempotency_key`, `deadline_ms`, `request_id`. Перевіряються actor, authority enum, safe-token формат, positive deadline. |
| `src/power_framework/core/application.py:85-106` — `AuditReceipt`, `AuditReceipt.as_dict(self) -> dict[str, object]` | Content-free receipt: operation/status/request ID/idempotency key/SHA-256/duration. |
| `src/power_framework/core/application.py:109-133` — `ApplicationEnvelope`, `ApplicationEnvelope.as_dict(self) -> dict[str, object]` | Версіонований результат зі статусами лише `"ok"` або `"unavailable"`. |
| `src/power_framework/core/application.py:192-204` — `ApplicationService.__init__(self, vault_dir: Path, *, audit_hook: Callable[[AuditReceipt], None] \| None = None, search_fn: Callable[..., list[Any]] \| None = None, task_service: TaskService \| None = None) -> None` | Ін’єкція `audit_hook`, search function і canonical `TaskService`; `DecisionService` отримує той самий `TaskService`. |
| `src/power_framework/core/application.py:206-255` — `discover(...)`, `retrieve(...)` | `discover` не probe-ить optional runtime. `retrieve` обмежує query/max results і серіалізує retrieval як untrusted data. |
| `src/power_framework/core/application.py:257-321` — `propose(...)`, `apply(...)`, `apply_proposal(...)` | Proposal/apply розділені; `apply` вимагає `approved=True` та `authority="apply"`. |
| `src/power_framework/core/application.py:323-451` — `_mutation_context(...)`, `generate_index(...)`, `ensure_sub_index(...)`, `sync_vault(...)` | Mutation operations проходять через `execute_vault_mutation`. |
| `src/power_framework/core/application.py:453-565` — `ingest_note(...)`, `synthesize_session(...)` | Ingest валідовує OKF і публікує index/search/lint; synthesize делегує `synthesize_session_ingest`. |
| `src/power_framework/core/application.py:613-737` — `task(...)` | Compatibility facade над canonical Task v2, не створює legacy work-packet. |
| `src/power_framework/core/application.py:823-929` — `decision_create(...)`, `decision_list(...)`, `decision_read(...)`, `decision_resolve(...)` | Application boundary для typed decision gates. |
| `src/power_framework/core/application.py:931-1050` — `task_create(...)`, `task_transition(...)`, `task_list(...)`, `task_read(...)`, `task_events(...)` | V2 task use cases. |
| `src/power_framework/core/application.py:1052-1102` — `_run(self, operation: str, context: RequestContext \| None, action: Callable[[], Any], *, status: Literal["ok", "unavailable"] = "ok") -> ApplicationEnvelope` | Виконує action, перевіряє deadline після завершення, рахує digest і викликає audit hook. |

## Підтверджені invariants

- `RequestContext` не приймає порожній actor, невідому authority або unsafe request ID.
- Application receipt не копіює note content.
- `retrieve` додає `trust="untrusted"` і `data_only=True`.
- CLI/direct/MCP retrieval мають однаковий `data` contract.
- Application task facade зберігає задачі в `.power/tasks`, а не в `.power/work-packets`.

Підтвердження:

- `tests/test_application.py:16-33, 35-42, 45-69, 71-110, 111-131`
- `tests/test_application_contract.py:23-86, 89-108`
- `tests/test_application_v2.py:82-90, 92-212`

## PSE extension points

- `ApplicationService.__init__`: natural anti-corruption boundary для ін’єкції PSE service.
- `audit_hook`: extension point для content-free PSE event attribution. **Критичне уточнення:** `AuditReceipt/audit_hook` є сигналом захоплення операційного рівня (`operation-level capture signal`). Він **НЕ є достатнім** як первинний механізм семантичної інгестії, оскільки квитанція навмисно містить лише метадані операції та дайджести, а не повні семантичні вхідні/вихідні дані.
- `_run`: єдина точка для envelope, request correlation, timing і receipt.
- `task_service` injection дозволяє PSE reuse/extension без parallel task store.
- `decision_service` вже прив’язаний до того самого `TaskService`.

## Gaps

1. **Implicit apply authority**  
   `src/power_framework/core/application.py:323-329` створює `RequestContext(authority="apply")`, якщо context не переданий. Тому direct caller може викликати mutation API без explicit caller context.

2. **Authority не є authentication**  
   Actor — вільний string; немає identity provider, signed principal або session binding. `request_id` потрапляє лише до application receipt і не передається в task/decision/memory records.

3. **Немає structured failure envelope**  
   `_run` не перехоплює exceptions. Помилка не стає `ApplicationEnvelope(status="error")`, і failed operation не отримує audit receipt.

4. **Deadline не перериває операцію**  
   Перевірка виконується після `action()` (`application.py:1061-1069`). Повільна mutation/read вже завершилася до `TimeoutError`.

5. **Database override у default retrieval**  
   `application.py:202, 232-240` викликає `search_vault` без `allow_search_db_override=False`, хоча `search_vault` має default `True` (`searcher.py:1308-1318`). Direct ApplicationService може читати database, вказану через `POWER_SEARCH_DB`.

6. **`source_read` дозволяє не лише Markdown**  
   `src/power_framework/core/source_service.py:107-118, 382-441` перевіряє containment, але не extension або PARA category для direct path. In-root `.power/*`, `.env` або інший regular file може бути прочитаний. Тести покривають лише нормальні `.md` paths (`tests/test_application_v2.py:113-135`).

---

# 2. Vault Mutation Boundary та Storage

## Фактичний surface

| Relative path / signature | Реальний контракт |
|---|---|
| `src/power_framework/core/mutation.py:69-94` — `vault_mutation(vault_dir: Path) -> Iterator[Path]` | Canonical root, in-process `RLock` і cross-process advisory file lock. |
| `src/power_framework/core/mutation.py:96-99` — `execute_vault_mutation[T](vault_dir: Path, operation: Callable[[], T]) -> T` | Synchronous operation під mutation boundary. |
| `src/power_framework/core/mutation.py:102-119` — `run_blocking[T](sync_fn: Callable[[], T]) -> T`, `run_vault_mutation[T](...) -> T` | Blocking work запускається в executor; результат join-иться до return. |
| `src/power_framework/core/mutation.py:122-138` — `enqueue_compatibility_write[T](...)`, `_run_compatibility_write(...)` | Legacy compatibility API з process-local global `RLock`; background worker відсутній. |
| `src/power_framework/core/write_queue.py:19-30` — `enqueue_write[T](...)`, `drain()`, `reset_for_test()` | `write_queue.py` — aliases/no-op compatibility layer, не справжня queue. |
| `src/power_framework/core/vault_storage.py:19-26` — `VaultIdentity` | Stable UUID/schema/creation timestamp для vault. |
| `src/power_framework/core/vault_storage.py:51-87` — `ensure_vault_identity(...)`, `read_vault_identity(...)` | Atomic creation або read-only lookup vault identity. |
| `src/power_framework/core/vault_storage.py:148-192` — `vault_cache_dir(...)`, `existing_vault_cache_dir(...)`, `existing_vault_db_path(...)`, `vault_db_path(...)` | Cache namespace keyed by vault UUID; `POWER_SEARCH_DB` залишається override. |
| `src/power_framework/core/vault_storage.py:218-315` — `classify_cache_namespaces(...)`, `prune_vault_caches(...)` | Cache класифікується як live/stale/unknown; prune default dry-run. |
| `src/power_framework/core/utils.py:100-112` — `vault_control_dir(...)` | `.power` symlink заборонений. |
| `src/power_framework/core/utils.py:137-169` — `atomic_write(...)` | temp file + `os.replace`. |
| `src/power_framework/core/utils.py:172-215` — `resolve_path_in_vault(...)` | Reject traversal, Windows paths, control chars, symlinks і неіснуючі parents. |
| `src/power_framework/core/utils.py:218-283` — `atomic_write_in_vault(...)` | POSIX `O_NOFOLLOW`, directory FD і atomic replacement. |

## Підтверджені invariants

- Однаковий vault serializes mutations.
- Різні vaults можуть працювати паралельно.
- Lock file має mode `0600`.
- Lock звільняється після exception.
- Cross-process CLI mutation не втрачає notes/index.
- Cache live vault не prune-иться; deleted vault prune-иться лише з доказом.
- Unknown cache namespace зберігається без explicit `include_unknown=True`.

Підтвердження:

- `tests/test_mutation.py:30-141`
- `tests/test_write_queue.py:13-76`
- `tests/test_cross_process_mutation.py:27-75`
- `tests/test_generation_index.py:92-125`
- `tests/test_cli.py:1204-1327`

## PSE extension points

- PSE writes повинні reuse `execute_vault_mutation` / `run_vault_mutation`.
- `VaultIdentity.vault_id` придатний для namespacing derived PSE state.
- `TaskStore._transaction` (`task_store.py:366-432`) — існуючий, але приватний transaction primitive для multi-artifact writes.
- `atomic_write_in_vault` придатний для note projections, але не замінює event-ledger transaction.
- **Координаційні шари та транзакційні ризики:** POWER наразі має два критичні рівні координації:
  1. `vault mutation lock` (`core/mutation.py`)
  2. `TaskStore lock + TaskStore crash-recovery transaction` (`core/task_store.py`)
  У Фазі 1 обов'язково створити ADR, який визначить:
  - `lock hierarchy`
  - `cross-subsystem transaction semantics`
  - `failure recovery`
  - `idempotent reconciliation`
  Базовий напрямок проєктування: не вимагати атомарних дзеркальних подій PSE для канонічних операцій Task/Decision; `TaskService` та `DecisionService` залишаються авторитетними; проекції/посилання PSE мають реконсилюватися ідемпотентно. Це запобігає dual-write corruption та розподіленим транзакціям.

## Gaps

1. **`write_queue.py` не є single-writer queue**  
   Фактичний production contract — lock boundary. Немає черги, worker lifecycle, backpressure, ordering guarantee або queue receipt.

2. **Power-loss durability не доведена**  
   `atomic_write` (`utils.py:153-169`), `atomic_write_in_vault` (`utils.py:264-281`) і `TaskStore._atomic_write_bytes` (`task_store.py:339-356`) не роблять `fsync` file/parent directory. Це захищає від partial rename, але не гарантує переживання power loss.

3. **Race при першому vault identity**  
   `ensure_vault_identity` (`vault_storage.py:51-75`) робить check-then-create без власного lock. Два low-level callers можуть одночасно згенерувати різні UUID і замінити `vault.json`.

4. **Platform asymmetry**  
   `mutation.py` має POSIX/Windows lock branches, але `TaskStore.lock` (`task_store.py:80-89`) при відсутності `fcntl` одразу викидає `RuntimeError`. Task V2 writer path фактично не має Windows adapter.

5. **Nested state symlink policy непослідовна**  
   `.power` захищений у `vault_control_dir`, tasks directories перевіряються в `TaskStore._ensure_dirs`, але decision/handoff/proposals nested directories не мають однакового symlink guard.

---

# 3. Task v2 Subsystem

## Models та state machine

| Relative path / signature | Реальний контракт |
|---|---|
| `src/power_framework/core/task_models.py:13-36` — `TaskState`, `TaskPriority`, `TaskAuthority`, `TaskKind`, `ExecutionState`, `TERMINAL_STATES`, patterns | Типізовані states, authorities і safe task/receipt IDs. |
| `src/power_framework/core/task_models.py:46-84` — `VALID_TRANSITIONS` | Explicit transition graph; terminal states не мають outgoing transitions. |
| `src/power_framework/core/task_models.py:87-125` — `class PowerTask(BaseModel)` | Canonical Task v2 snapshot; `extra="forbid"`, revision, dependencies, gates, execution metadata, artifacts, receipts. |
| `src/power_framework/core/task_models.py:132-160` — `is_terminal`, `can_transition_to`, `validate_transition` | Terminal immutability, legal transition і completion receipt prerequisite. |
| `src/power_framework/core/task_models.py:162-203` — `class TaskEvent`, `TaskEvent.create(...)` | Append-only JSONL event record з sequence і payload digest. |
| `src/power_framework/core/task_models.py:206-209` — `canonical_payload_digest(payload: dict[str, Any]) -> str` | SHA-256 canonical JSON digest лише payload. |
| `src/power_framework/core/task_models.py:212-245` — `TaskCompletionReceipt` | Content-free completion evidence з task revision, postcondition hash і artifact digests. |

## Store та service

| Relative path / signature | Реальний контракт |
|---|---|
| `src/power_framework/core/task_store.py:35-58` — `TaskStore.__init__(self, vault_dir: Path) -> None` | State paths: `.power/tasks`, `events`, `checkpoints`, `receipts`, `.tx`. |
| `src/power_framework/core/task_store.py:72-108` — `lock(self) -> Generator[None]` | Per-vault thread/file writer lock; first lock invokes recovery. |
| `src/power_framework/core/task_store.py:118-172` — `save_task(...) -> None` | Atomic snapshot/event/checkpoint/receipt write under transaction manifest. |
| `src/power_framework/core/task_store.py:173-207` — `append_event(self, event: TaskEvent) -> None` | Append event and periodic checkpoint. |
| `src/power_framework/core/task_store.py:232-284` — `get_task(...)`, `get_completion_receipt(...)`, `list_tasks(...)` | Pydantic validation on reads; task listing sorted by `updated_at`. |
| `src/power_framework/core/task_store.py:286-325` — `get_task_events(...)`, `get_last_event_digest(...)` | Full journal validation: sequence, task ID, previous payload digest, payload digest. |
| `src/power_framework/core/task_store.py:327-333` — `delete_task(...) -> None` | Deletes task snapshot/events/checkpoints. |
| `src/power_framework/core/task_store.py:366-432` — `_transaction(...)` | Prepared/committed manifest, preimage backup, rollback, cleanup. |
| `src/power_framework/core/task_store.py:434-527` — `_rollback_tx(...)`, `_reconcile_tx(...)`, `recover(...)` | Crash reconciliation and redacted recovery log. |
| `src/power_framework/core/task_service.py:34-143` — `create_task(...) -> PowerTask` | Creates revision 1 plus initial event. |
| `src/power_framework/core/task_service.py:145-294` — `transition_task(...) -> PowerTask` | Revision check, legal transition, completion receipt, event append. |
| `src/power_framework/core/task_service.py:296-313` — `_find_idempotent_result(...) -> PowerTask \| None` | Replays prior result for same idempotency key and command digest. |
| `src/power_framework/core/task_service.py:315-369` — `_build_completion_receipt(...) -> TaskCompletionReceipt` | Requires nonempty postcondition and existing in-vault artifacts; hashes files. |
| `src/power_framework/core/task_service.py:393-535` — migration/rollback methods | V1 work-packet migration and reversible intent. |

## Підтверджені invariants

- Illegal transitions and terminal rewrites are rejected.
- Completion requires verified postcondition and existing artifact.
- Revision conflicts raise `ConflictError`.
- Same idempotency key with same command replays exact snapshot.
- Event journal rejects payload, sequence, task-ID, chain and schema tampering.
- Multi-file task writes recover from prepared manifests.
- Completion receipt binds to task ID and next revision.

Підтвердження:

- `tests/test_task_service.py:26-44, 47-123, 125-235, 238-320, 323-395, 397-447`
- `tests/test_crash_recovery_task.py:46-156`
- `tests/test_fault_injection.py:25-40`
- `tests/test_cli.py:875-1048`

## PSE extension points

- Reuse `PowerTask`, `TaskService`, `TaskStore`; parallel PSE task store заборонений архітектурно.
- **Базова модель `PowerTask`:** на коміті `af2e3022422b2ee3f249e0b2e0aa08b6ce09450c` модель `PowerTask` використовує `ConfigDict(extra="forbid")` і **НЕ містить** поля `metadata`. Будь-які довільні атрибути (`project_id`, `sprint`, `raid_refs`) відхиляються валідатором. У Фазі 0 `PowerTask` не модифікується.
- **Базовий напрямок Фази 1:**
  ```text
  TaskService / TaskStore remain canonical for Task v2.

  Project↔Task membership is owned by PSE through a typed relation/event or equivalent sidecar relation, referencing canonical task_id.

  Adding project_id directly to PowerTask requires a separate ADR and is NOT assumed.
  ```
- Existing fields usable for adapter: `vault_id`, `tenant_id`, `kind`, `scope`, `dependencies`, `open_gates`, `external_refs`, `artifact_refs`, `completion_policy`.
- `TaskEvent` — candidate source for PSE event ledger, але потребує extension для correlation/session/causation.
- `revision` + `expected_revision` — base для deterministic optimistic concurrency.
- `TaskCompletionReceipt` — base для DoD evidence adapter.

## Gaps

1. **Немає project-level lifecycle engine**  
   Task states не дорівнюють PSE phases `DISCOVERY → PLANNING → EXECUTION → MONITORING → CLOSING → CLOSED`. Немає project ID, phase gates або DoR/DoD engine.

2. **Немає deterministic state replay API**  
   Current state читається з mutable snapshot (`task_store.py:232-241`). Немає функції, яка відновлює `PowerTask` виключно з event journal і перевіряє snapshot проти replay.

3. **Специфікація Event hash chain та рішення для ProjectEvent v1**  
   Фактичний базовий контракт `TaskEvent` (`task_models.py:162-209`, `task_store.py:291-318`):
   ```text
   payload_digest = SHA256(canonical payload)
   prev_event_digest = previous TaskEvent.payload_digest
   ```
   Replay валідує послідовність (`sequence`), попередній дайджест навантаження та поточний дайджест навантаження. Поля конверта (`actor`, `event_type`, `event_id`, `created_at`) не входять у digest.
   Для `ProjectEvent` v1 у Фазі 1 обов'язково ухвалити окремий ADR з вибором:
   - **Варіант A:** повторне використання еквівалентної семантики payload-chain; або
   - **Варіант B:** сильніший повний хеш події:
     ```text
     event_hash = SHA256(
         canonical event envelope
         including previous_event_hash
     )
     ```
   Жодне рішення не повинно мовчазно успадковуватися від `TaskEvent`.

4. **Journal допускає gap при append**  
   `_append_event_unlocked` (`task_store.py:184-207`) перевіряє лише `event.sequence <= existing[-1].sequence`. Sequence `last+2` може бути записаний, а помилка з’явиться пізніше при read.

5. **Initial terminal state не має completion gate**  
   `create_task` (`task_service.py:93-143`) дозволяє створити `completed` або інший terminal state без completion receipt/postcondition.

6. **Optimistic concurrency optional**  
   `transition_task` перевіряє revision лише коли `expected_revision is not None` (`task_service.py:190-193`). Direct caller може виконувати non-completion transitions без concurrency guard.

7. **Rollback failure маскується cleanup-ом**  
   `_transaction` (`task_store.py:427-432`) suppress-ить rollback exception, а потім у `finally` видаляє transaction directory. При невдалому rollback recovery manifest може бути втрачений.

8. **`delete_task` не видаляє completion receipts**  
   `task_store.py:327-333` видаляє snapshot/events/checkpoints, але не `.power/tasks/receipts`.

9. **Migration не є повністю atomic**  
   `migrate_v1_work_packets` пише backup/task, а manifest — пізніше (`task_service.py:463-481`). Crash між цими кроками може залишити task без migration manifest. Додатково backup створюється як `packet_file.name`, а rollback шукає `<task_id>.json` (`task_service.py:523-531`), що ламається при різних filename і embedded `task_id`.

---

# 4. Decision Workflow

## Фактичний surface

| Relative path / signature | Реальний контракт |
|---|---|
| `src/power_framework/core/decision_models.py:25-95` — `class Decision` | Typed decision gate, task revision binding, optional proposal hash, actor allow-list, typed response schema, expiry. |
| `src/power_framework/core/decision_models.py:98-150` — `class DecisionReceipt`, `DecisionReceipt.digest_payload(...) -> str` | Content-free receipt; digest covers decision/task revision/action/actor/response. |
| `src/power_framework/core/decision_service.py:25-33` — `DecisionService.__init__(...)` | Reuses `TaskService.store`; decisions live below `.power/tasks/decisions`. |
| `src/power_framework/core/decision_service.py:35-92` — `create_decision(...) -> Decision` | Decision must bind to existing task and current revision; expiry must be future. |
| `src/power_framework/core/decision_service.py:94-134` — `get_decision(...)`, `list_decisions(...)` | Read/effective expiry projection and bounded list. |
| `src/power_framework/core/decision_service.py:136-230` — `resolve_decision(...) -> tuple[Decision, DecisionReceipt]` | Actor, authority, proposal hash, task revision and response schema are checked before atomic decision/receipt write. |
| `src/power_framework/core/decision_service.py:232-254` — `get_receipt(...)`, path helpers | Receipt read and safe receipt filename validation. |
| `src/power_framework/core/decision_service.py:257-307` — `_validate_response(...)`, `_matches_type(...)`, `_parse_timestamp(...)`, `_effective_decision(...)` | Exact structured input schema, type checks, timezone-aware expiry, read-only expiry projection. |

## Підтверджені invariants

- Actor must be allow-listed unless `"*"`.
- Required authority is ranked `read-only < propose < apply`.
- Proposal hash must match when a decision contains one.
- Decision cannot resolve against stale task revision.
- `provide_input` requires exact response-schema fields and primitive types.
- Expired pending decision fails closed.
- Same resolution by same actor replays the same receipt.
- Decision and receipt write are protected by TaskStore transaction manifest.

Підтвердження:

- `tests/test_decision_service.py:26-83, 86-171, 174-260`
- `tests/test_crash_recovery_decision.py:21-80`
- `tests/test_fault_injection.py:43-67`
- `tests/test_application_v2.py:172-212`

## PSE extension points

- `Decision` / `DecisionService` мають бути reused як approval gate.
- `DecisionReceipt` може бути evidence для ADR materializer.
- Shared `TaskService` already supplies task revision binding.
- `response_schema` придатний для structured human input.

## Gaps

1. **Proposal не перевіряється проти durable proposal record**  
   `create_decision` (`decision_service.py:65-79`) приймає довільні `proposal_id` і `proposal_sha256`; сервіс не читає `.power/proposals` і не перевіряє, що hash відповідає payload. Resolve перевіряє лише equality з переданим hash (`:182-183`).

2. **Немає ADR representation/materializer**  
   `Decision` — approval/input gate, але немає ADR number, rationale, alternatives, supersession або окремого ADR artifact.

3. **Немає decision event journal**  
   Persisted state складається з mutable decision snapshot і receipt. Немає append-only resolution history або deterministic replay.

4. **Receipt integrity не перевіряється при read**  
   `DecisionReceipt.response_sha256` лише перевіряється як 64-hex (`decision_models.py:103-110`). `get_receipt` (`decision_service.py:232-242`) не перераховує digest. Replay (`:168-175`) перевіряє receipt ID/action/actor, але не `response_sha256`.

5. **Model допускає суперечливі direct snapshots**  
   `Decision.validate_binding` (`decision_models.py:87-95`) не вимагає відповідності `status` і `resolution_action`, не вимагає `resolved_at/resolved_by` для всіх terminal fields і дозволяє неповний `expired` state.

6. **Expiry є read projection, не durable event**  
   `_effective_decision` (`decision_service.py:300-307`) повертає in-memory `expired`; snapshot не переписується і не виникає event про expiry.

7. **Немає idempotency key у decision API**  
   Create використовує duplicate-ID error; resolve має лише content-derived receipt replay, без explicit request correlation.

---

# 5. Handoff Workflow

## Фактичний surface

| Relative path / signature | Реальний контракт |
|---|---|
| `src/power_framework/core/handoff.py:39-48` — `WorkPacketState` | Окремий state enum: submitted/working/input-required/completed/failed/canceled. |
| `src/power_framework/core/handoff.py:50-95` — `class WorkPacket` | Markdown control-plane packet з objective, owner, actor, authority, scope, phases, artifacts, receipts, checkpoint і fingerprints. |
| `src/power_framework/core/handoff.py:98-178` — `create_work_packet(...) -> dict[str, object]` | Idempotent creation під vault mutation lock. |
| `src/power_framework/core/handoff.py:181-328` — `advance_work_packet(...) -> dict[str, object]` | Resume/checkpoint/input-required/complete/fail/cancel, checkpoint Markdown і idempotency. |
| `src/power_framework/core/handoff.py:331-347` — `read_work_packet(...)`, `list_work_packets(...)` | Read-only packet access. |
| `src/power_framework/core/handoff.py:349-372` — `_advance_maintenance_phase(...)`, `_default_next_action(...)` | Deterministic maintenance phase order. |
| `src/power_framework/core/handoff.py:385-439` — path/load/recovery helpers | State зберігається у `.power/work-packets`. |
| `src/power_framework/core/handoff.py:482-557` — `_render_packet(...)`, `_write_packet(...)` | Main Markdown і immutable checkpoint; manual rollback при звичайному exception. |

## Підтверджені invariants

- Packet body містить fixed warning, що retrieved text є untrusted data.
- Idempotency fingerprint collision reject-иться.
- Resume з `input-required` вимагає approval.
- Maintenance phases рухаються лише в порядку `detect → dry-run → repair → verify → receipt`.
- Repair і cancel потребують explicit approval.
- Completion вимагає receipt token і закриті gates.
- Read-only inspection не materialize-ить missing main packet.

Підтвердження:

- `tests/test_handoff.py:13-50, 53-98, 100-147, 150-223, 225-248`

## PSE extension points

- Handoff має бути **adapter над canonical Task v2**, не другим canonical store.
- `external_refs` Task v2 може зберігати ContextPack ID.
- `changed_artifacts`, `receipt_ids`, `open_gates`, `next_action` придатні для ContextPack metadata.
- `_render_packet` задає стабільний human-readable control-plane формат.

## Gaps

1. **Parallel state store**  
   Handoff functions пишуть `.power/work-packets` (`handoff.py:385-390`), тоді як ApplicationService Task facade пише `.power/tasks` (`application.py:621-737`). Це два формати з task ID/state/objective/owner/authority/receipts.

   Підтвердження розділення:

   - `tests/test_handoff.py:46-50` — checkpoints у `.power/work-packets`.
   - `tests/test_application.py:111-131` — canonical task у `.power/tasks`.
   - `tests/test_cli.py:807-872` — CLI handoff уже делегує canonical Task і не створює work-packets.

2. **Authority зберігається, але не enforced**  
   `WorkPacket.authority` (`handoff.py:50-80`) записується, але `advance_work_packet` (`:213-326`) не порівнює packet authority з action/actor. Packet `"read-only"` може бути advanced/completed через direct API.

3. **Fake completion receipt приймається**  
   Complete перевіряє лише `_TOKEN_PATTERN` (`handoff.py:261-269`), не існування durable receipt і не його digest. Тест використовує довільний `"receipt-001"` (`tests/test_handoff.py:203-223`).

4. **Invalid runtime action падає у cancel branch**  
   Signature має `Literal`, але runtime `else:  # cancel` (`handoff.py:281-287`) трактує будь-яке невідоме значення як cancel, якщо `approved=True`.

5. **Crash consistency між main packet і checkpoint неповна**  
   `_write_packet` спочатку пише main (`handoff.py:542-544`), потім checkpoint (`:545-551`). Process kill між цими операціями залишає новий main зі старим checkpoint; `_load_packet` (`:429-439`) тоді може викинути `"main state does not match its latest checkpoint"`.

6. **Немає ContextPack compiler**  
   Packet містить metadata, але не має role/task-based context compilation, source selection, token budget або provenance bundle.

7. **Artifact references не валідовуються**  
   `changed_artifacts` нормалізуються лише як non-empty strings (`handoff.py:82-88`); path containment і content digest не перевіряються.

---

# 6. Memory Subsystem

## Фактичний surface

| Relative path / signature | Реальний контракт |
|---|---|
| `src/power_framework/core/memory_api.py:45-53` — `get_context(vault_dir: Path, query: str, max_results: int = 5) -> list[SearchResult]` | FTS context read без proposal/cache mutation і без DB override. |
| `src/power_framework/core/memory_api.py:56-99` — `propose_change(...) -> dict[str, str]` | Валідує OKF, створює content-addressed durable proposal і не пише target note. |
| `src/power_framework/core/memory_api.py:102-264` — `commit_note_change(...) -> dict[str, str]` | Write → index → lint → search publication → receipt/history, з in-process rollback snapshots. |
| `src/power_framework/core/memory_api.py:267-326` — `apply_change(...) -> dict[str, str]` | Explicit approval, schema/hash/durable-record/stale-before checks. |
| `src/power_framework/core/memory_api.py:329-345` — `apply_change_by_id(...) -> dict[str, str]` | Apply canonical proposal без transport payload. |
| `src/power_framework/core/memory_api.py:348-424` — `_is_sha256`, proposal parsing/path/public projection | Content-addressed proposal validation. |
| `src/power_framework/core/memory_api.py:427-527` — snapshots, projection restore, receipt append і idempotency lookup | Manual rollback and content-free history handling. |
| `src/power_framework/core/memory_api.py:530-546` — `validate_state(...) -> bool`, `read_history(...) -> list[dict[str, str]]` | Validation фактично делегує lint; history лише JSONL read. |
| `src/power_framework/core/models.py:99-125` — `MemoryMetadata` | Note-level kind, confidence, dates, `supersedes`, sources/evidence, write policy, sensitivity. |
| `src/power_framework/core/temporal.py:138-216` — `resolve_temporal_statuses(...)` | Inclusive validity dates, supersession chain, historical/conflicted projection. |

## Підтверджені invariants

- Invalid proposal content не створює target/proposal.
- Proposal ID є SHA-256 повного payload.
- Apply без explicit approval reject-иться.
- Stale proposal не overwrites changed note.
- Post-write lint/index/sync failure відновлює note, log, projections і search у межах живого process.
- History receipt містить path, before/after hashes, schema, trace/span IDs.
- Existing dense search не втрачається при failed later sync.
- `MemoryMetadata` вимагає sources/evidence для agent-managed memory.
- Temporal supersession не приховує competing current heads.

Підтвердження:

- `tests/test_memory_api.py:17-42, 45-129, 131-202, 205-346`
- `tests/test_memory_contract.py:41-163`
- `tests/test_crash_recovery_memory.py:25-83`
- `tests/test_fault_injection.py:69-96`

## PSE extension points

- `propose_change` / `apply_change` — note-memory transaction boundary, але не PSE project ledger.
- `before_sha256`, `after_sha256`, `proposal_id` і history receipt можуть бути referenced from PSE events.
- `MemoryMetadata` і `temporal.py` — reuse для note-level provenance/supersession.
- `ProvenanceRecord` (`src/power_framework/core/provenance.py:34-124`) — reusable content-addressed evidence model, але він не підключений до Application/Task/Decision workflow.

## Gaps

1. **`commit_note_change` обходить approval workflow**  
   `commit_note_change` (`memory_api.py:102-264`) не має `approved` або authorization argument. Будь-який direct library caller може записати валідну note без durable proposal. `apply_change` approval enforced лише у wrapper (`:273-276`).

2. **Memory transaction не повністю crash-atomic**  
   Transaction manifest створюється з touched artifacts лише `target` і `history` (`memory_api.py:169-176`). Index, catalogs, cache і `log.md` відсутні в manifest. In-process exception rollback їх відновлює (`:223-262`), але hard process kill може залишити projections/log після rollback note.

3. **Memory recovery не запускається автоматично з memory path**  
   `commit_note_change` створює `TaskStore` (`memory_api.py:169`), але викликає приватний `_transaction` без `store.lock()`. Отже, залишений memory transaction manifest не обов’язково буде recovered наступним memory operation; recovery запускається через TaskStore lock або explicit `recover()`.

4. **History не є hash-chained append-only ledger**  
   `_append_receipt` (`memory_api.py:488-495`) просто читає весь файл і переписує його через `atomic_write`. Немає `prev_digest`, sequence, signature або immutable append primitive. `read_history` (`:539-546`) не валідовує schema/content-free invariants.

5. **Proposal content зберігається plaintext і без size/redaction gate**  
   `propose_change` (`memory_api.py:72-97`) записує повний `content`; немає max size, secret scrubber або sensitivity enforcement.

6. **Idempotent replay може повернути старий receipt без перевірки поточного note**  
   `_find_idempotent_receipt` (`memory_api.py:497-519`) знаходить matching operation/path/after hash і повертає його до повторної перевірки current target state.

7. **`validate_state` не перевіряє transaction/replay integrity**  
   `validate_state` (`memory_api.py:530-536`) перевіряє лише `run_lint_vault`. Воно не перевіряє history chain, orphan manifests, snapshot/event consistency або search-generation binding.

8. **Note temporal model не є project temporal model**  
   `MemoryMetadata` має лише note-level `valid_from`, `valid_until`, `supersedes`; немає `invalidates`, bitemporal transaction time, project state transitions або event causality.

---

# Відсутнє після пошуку в `src`

Пошук виконувався за filenames і symbols у `src/power_framework`.

## Не знайдено файлів

- `src/power_framework/project_state/**`
- `src/power_framework/core/*ledger*.py`
- `src/power_framework/core/*context*.py`
- `src/power_framework/core/*pack*.py`
- `src/power_framework/core/*raid*.py`
- `src/power_framework/core/*adr*.py`
- `src/power_framework/core/*raci*.py`
- `src/power_framework/core/*replay*.py`

## Не знайдено спеціалізованих symbols

- `ProjectState`
- `ContextPack`
- `RAID`
- `RACI`
- `DoR`
- `DoD`
- `event ledger`
- `bitemporal`
- `invalidates`
- `deterministic state replay`

## Що існує, але не є PSE

- `core/lifecycle.py:1-190` — read-only session lifecycle adapter: `session-start`, `post-write`, `pre-compact`, `stop`; project lifecycle engine відсутній.
- `core/temporal.py:24-216` — note-level validity/supersession/conflict projection.
- `core/provenance.py:16-298` — opt-in evidence capture/provenance; немає автоматичної інтеграції з task/decision/memory receipts.
- `core/source_projection.py` — derived source/search projection, не project-state engine.
- `core/task_store.py` — per-task event journal, не global append-only ledger.
- `core/memory_api.py` — vault note transaction/history, не project state ledger.

## Підсумкова класифікація

- Application boundary: **EXTENSION**
- Mutation/storage boundary: **REUSE + EXTENSION**
- Task v2: **REUSE/EXTENSION; parallel PSE task store — PROHIBITED**
- Decisions: **REUSE + ADR ADAPTER**
- Handoff: **ADAPTER/DEPRECATION toward Task v2**
- Memory: **REUSE as vault-note projection, but separate PSE event ledger required**

Найкритичніші фактичні gaps для PSE: відсутність global event ledger/replay, неenforced actor authority у handoff, неповна crash-atomicity memory projections, відсутність ContextPack/ADR/project lifecycle surfaces і недостатня integrity-перевірка snapshot/receipt metadata.

Попередній memo був обрізаний. Продовж/уточни лише пропущену частину dimensions 1–6, особливо повний dimension 6 Memory (усі facts/gaps/PSE points) і будь-які пропущені завершальні розділи. Не перечитуй і не повторюй уже повернений текст; дай exact path:symbol:line citations, verified facts, tests, gaps. Ніяких writes/secrets.

Продовження буде лише для пропущеного блоку: повний D6 Memory, його невидимі failure paths, PSE integration boundaries і завершальний evidence/absence section. Перевірю тільки потрібні рядки та targeted memory tests; файлів не змінюватиму й нічого destructive не запускатиму.

## Продовження memo: повний Dimension 6 — Memory

### 6.1 Read-only context

- **`src/power_framework/core/memory_api.py:get_context:45-53`**  
  Викликає `search_vault(..., mode="fts", allow_search_db_override=False)`. Не створює proposal, cache або search DB. Повертає `list[SearchResult]`, тобто source material залишається untrusted retrieval data.
- **Тест:** `tests/test_memory_api.py:39-42` підтверджує пошук і `validate_state`; Application-level retrieval contract — `tests/test_application.py:16-33`.
- **Gap:** `max_results` не обмежується у `get_context` власною Pydantic-моделлю; bounded contract покладається на downstream searcher.

### 6.2 Proposal creation

- **`src/power_framework/core/memory_api.py:propose_change:56-99`**
  - Приймає лише string `rel_path` і `content`.
  - Валідовує path через `resolve_path_in_vault(..., allowed_directories=PARA_FOLDERS)` — traversal, Windows separators, symlinks і неіснуючі parents відхиляються.
  - Валідовує OKF через `validate_metadata`.
  - Обчислює `before_sha256`, `after_sha256`.
  - Proposal ID формується з повного payload через **`_proposal_id:369-372`**.
  - Target note не записується.
  - Durable record містить повний plaintext `content`, hashes, `proposal_id`, idempotency key, schema version і timestamp (**`propose_change:72-97`**).
  - Уся persistence-операція проходить через `execute_vault_mutation` (**`propose_change:99`**).

- **Durable validation:**  
  **`_read_proposal_file:380-397`** перевіряє, що файл не symlink, JSON є object, payload types коректні, proposal ID відповідає content-addressed payload, а idempotency key валідний.

- **Тести:**  
  `tests/test_memory_api.py:72-108, 111-128` підтверджують reject invalid content, durable proposal, missing proposal і malformed fields.

- **Gaps:**
  1. **Idempotency key не входить у proposal ID.**  
     **`_proposal_id:369-372`** хешує path/content/before/after, але не key. Повторний виклик з тим самим payload і новим key повертає старий proposal через **`propose_change:82-86`**, не сигналізуючи про відмінність key.
  2. **Немає content-size limit або secret scrubbing.**  
     `propose_change:56-99` приймає необмежений plaintext.
  3. **Nested symlink gap.**  
     **`_proposal_path:375-377`** захищає `.power`, але `proposals/` окремо не перевіряється на symlink перед `mkdir`/`atomic_write`.
  4. **Schema metadata неповна.**  
     `_read_proposal_file:390-397` перевіряє payload/ID/key, але не вимагає `schema_version == 1` і не парсить `created_at` як timestamp.

### 6.3 Apply та commit workflow

- **`src/power_framework/core/memory_api.py:apply_change:267-326`**
  - Вимагає truthy `approved`.
  - Перевіряє типи `path`, `content`, hashes і `proposal_id`.
  - Перераховує content hash.
  - Перевіряє content-addressed proposal ID.
  - Завантажує canonical durable proposal і порівнює payload.
  - Перевіряє idempotency key.
  - Передає mutation у `commit_note_change` з `expected_before_sha256` і `allowed_directories=PARA_FOLDERS`.

- **`apply_change_by_id:329-345`**  
  Завантажує proposal за SHA-256 ID і делегує у `apply_change`; transport може не передавати note content.

- **`commit_note_change:102-264`** виконує послідовність:
  1. path resolution і optional idempotency replay — `117-137`;
  2. source snapshot — `131-149`;
  3. receipt construction — `153-167`;
  4. transaction manifest — `169-176`;
  5. atomic note write — `178-183`;
  6. optional `log.md` append — `184-185`;
  7. hierarchical index — `186`;
  8. blocking lint — `187-195`;
  9. dense/FTS publication — `197-207`;
  10. history receipt — `208-222`.

- **Тести:**  
  `tests/test_memory_api.py:17-42, 45-69` підтверджують explicit approval, hashes, history, search publication, idempotent replay і stale proposal rejection.

### 6.4 Receipt та history

- **Receipt schema:**  
  **`commit_note_change:153-167`** створює:
  - `receipt_schema`
  - operation
  - path
  - before/after SHA-256
  - timestamp
  - random `trace_id` і `span_id`
  - status
  - optional proposal/idempotency identifiers.

- **`_append_receipt:488-495`**  
  Перевіряє, що history не symlink, читає весь `memory-history.jsonl`, додає JSON line і повністю переписує файл через `atomic_write`.

- **`_find_idempotent_receipt:497-519`**
  - відхиляє malformed JSON;
  - відхиляє non-dict record;
  - відхиляє records з non-string values;
  - шукає matching `idempotency_key`.

- **`read_history:539-546`**  
  Перевіряє лише history path і symlink, після чого повертає результат `json.loads` без schema validation.

- **Verified tests:**  
  `tests/test_memory_api.py:29-38, 45-56`.

- **Gaps:**
  1. Назва/docstring каже “append-only”, але implementation фізично переписує весь файл через `atomic_write`; немає immutable append primitive, sequence, `prev_receipt_digest`, signature або chain root.
  2. `read_history` annotation `list[dict[str, str]]` не гарантується runtime: JSON може бути scalar/list або мати non-string values.
  3. `_find_idempotent_receipt` перевіряє shape, але не перевіряє `receipt_schema`, `status`, hashes, timestamp або відповідність фактичному note.
  4. Receipt не містить actor, authority, session ID, request ID, approval identity або causal parent. `trace_id`/`span_id` — correlation tokens, не provenance proof.
  5. Idempotent replay (**`commit_note_change:119-130`**) повертає старий receipt до перевірки актуального стану target note. Якщо note пізніше змінена, replay все одно повертає старий success receipt.

### 6.5 Transaction, projections і rollback

- **Snapshot coverage:**  
  **`_projection_paths:436-446`** включає root `index.md`, existing catalog pages і existing hierarchical-index cache.

- **In-process rollback:**  
  **`_restore_projection_snapshot:464-485`** відновлює catalogs/cache; **`_restore_file_snapshot:454-462`** відновлює note, history і log.

- **Exception path:**  
  **`commit_note_change:223-262`** окремо відновлює:
  - target note;
  - projection snapshot;
  - history;
  - `log.md`;
  - search projection після вже виконаної publication.

- **Тести:**  
  - write/log/index/lint/sync failures: `tests/test_memory_api.py:131-285`;
  - later search failure: `tests/test_memory_api.py:288-321`;
  - receipt failure: `tests/test_memory_api.py:324-346`.

- **Critical crash gap:**  
  **`commit_note_change:169-176`** передає у `TaskStore._transaction` лише:
  ```text
  target note
  memory-history.jsonl
  ```
  `index.md`, catalog pages, hierarchical cache і `log.md` не входять у crash manifest. In-process exception path їх відновлює, але hard process kill між index/log writes і history commit може залишити projections або log у стані, який не відповідає відновленій note.

- **Recovery trigger gap:**  
  `commit_note_change` створює `TaskStore` і викликає private `_transaction` (**`memory_api.py:169-176`**), але не входить у `TaskStore.lock()`. Автоматичний `TaskStore.recover()` викликається в `TaskStore.lock` під час першого lock (**`task_store.py:80-93`**), тому наступна memory operation сама по собі не гарантує recovery orphaned memory manifest.

- **Test limitation:**  
  `tests/test_crash_recovery_memory.py:25-72` вручну викликає `store.recover()` на line 62. Тест підтверджує manual recovery note/history, але не автоматичне відновлення через наступний `commit_note_change`, і не перевіряє crash після index/log writes.

- **Generation identity gap:**  
  Якщо search publication вже відбулася, rollback повторно викликає `sync_vault_atomically` (**`memory_api.py:236-247`**). Це відновлює semantic search content, але створює іншу generation identity; exact попередній active generation не відновлюється.

- **Vault identity side effect:**  
  `sync_vault_atomically` (**`generation_index.py:889-917`**) може створити vault identity/cache state. Ці artifacts не входять у memory snapshot і можуть залишитися після failed note transaction.

### 6.6 Direct bypasses та authorization gaps

1. **`commit_note_change` не має approval argument**  
   **`memory_api.py:102-114`** дозволяє direct library caller записувати валідну note без proposal/apply workflow.

2. **`commit_note_change` default `allowed_directories=None`**  
   **`memory_api.py:107-110, 117-118`** дозволяє direct caller target у будь-якому in-root `.md`, а не лише PARA. `apply_change` передає PARA explicitly, але low-level API — ні.

3. **`approved` не має runtime type check**  
   **`apply_change:267-276`** перевіряє `if not approved`; truthy non-bool value може пройти direct Python call.

4. **`WritePolicy.AGENT_APPROVED` не доводить approval**  
   **`src/power_framework/core/models.py:99-125`** вимагає sources/evidence для agent-managed memory, але не вимагає decision ID, approval receipt або actor binding.

5. **Sensitivity — metadata only**  
   **`models.py:91-110`** має `PUBLIC`, `INTERNAL`, `SENSITIVE`, але `memory_api.py` не застосовує egress/redaction policy до content або history.

6. **Plaintext operational log**  
   **`_append_text:522-527`** записує caller-supplied `log_entry` без size/redaction/schema enforcement. Receipts content-free, але log не має такого ж контракту.

### 6.7 Note-level MemoryMetadata і temporal semantics

- **`src/power_framework/core/models.py:MemoryMetadata:99-125`**
  - `kind`: лише `semantic`, `episodic`, `procedural`, `intent`;
  - confidence;
  - inclusive date fields;
  - `supersedes`;
  - sources/evidence;
  - write policy;
  - sensitivity;
  - `extra="allow"`.

- **Verified contracts:**
  - `valid_until` не може бути раніше `valid_from`;
  - non-human write policy потребує sources/evidence;
  - unknown additive fields зберігаються.
- **Тести:** `tests/test_memory_contract.py:41-67, 70-105`.

- **`src/power_framework/core/temporal.py:scan_temporal_records:71-84`**  
  Читає metadata з authoritative Markdown scan.

- **`load_temporal_records:87-135`**  
  Приймає derived projection лише коли `file_metadata` і `temporal_records` мають однаковий path set; malformed/incomplete projection повертає `None`.

- **`resolve_temporal_statuses:138-216`**  
  Реалізує:
  - current/historical/conflicted;
  - valid-from/valid-until;
  - supersession graph;
  - conflict при competing heads;
  - cycle detection.

- **Тести:** `tests/test_memory_contract.py:108-163, 166-202`.

- **Gaps:**
  - немає semantic entity types `FACT`, `DECISION`, `ASSUMPTION`, `RISK`, `ISSUE`, `LESSON`;
  - немає `invalidates`;
  - `supersedes` зберігається як string list і не перевіряється на існування target;
  - unknown supersession targets silently ignored у **`resolve_temporal_statuses:168-171`**;
  - temporal data — note-level projection, не project event history;
  - немає transaction-time/bitemporal model;
  - немає event causality або supersession receipt.

### 6.8 Existing Provenance foundation

- **`src/power_framework/core/provenance.py:ProvenanceRecord:43-124`**
  - content hash;
  - source identity;
  - capture time;
  - authority;
  - freshness;
  - support;
  - contradiction;
  - review state;
  - egress policy.

- **`capture_bytes:127-154`** не persist-ить і не transmit-ить bytes.
- **`capture_file_to_store:229-298`** створює exact evidence blob і record, перевіряє existing blob.
- **`read_captured_evidence:301-312`** fail-closed перевіряє exact bytes.
- **Тести:** `tests/test_provenance.py:26-104`.

- **PSE point:** це найкраща наявна основа для evidence references, але `memory_api.commit_note_change`, task events і decisions її не викликають. Інтеграція відсутня.

## 6.9 PSE boundary decision

### REUSE

Reuse як **vault-note mutation/projection subsystem**:

- `propose_change`
- `apply_change_by_id`
- `commit_note_change`
- `before_sha256` / `after_sha256`
- OKF `MemoryMetadata`
- temporal projection
- provenance evidence references.

### ADAPTER

PSE adapter може перетворювати memory receipt на зовнішнє evidence reference:

- `proposal_id`
- `path`
- `before_sha256`
- `after_sha256`
- `search_generation`
- `trace_id`
- `span_id`.

### НЕ МОЖНА робити canonical ledger

`memory-history.jsonl` не повинен бути PSE canonical event ledger, оскільки actual implementation не має:

- event sequence;
- previous-event digest;
- actor/session attribution;
- causal links;
- signed authority;
- deterministic replay;
- tamper-evident chain.

PSE ledger має лише reference memory receipt і note hashes; note content залишається окремим vault artifact.

# Завершальні пропущені висновки

## Verified status

- У targeted memory suite: **29 passed, 3 deselected за 2.04 s**.
- Перевірені approval, proposal durability, stale detection, idempotency, projection rollback, dense/FTS publication, temporal semantics і provenance.
- Repository після перевірки: `git diff` порожній; untracked `artifacts/` залишився без змін.

## Static gaps, не замасковані тестами

Найбільш значущі:

1. Memory crash manifest не охоплює всі artifacts transaction.
2. Memory recovery не запускається автоматично з memory path.
3. Direct `commit_note_change` обходить approval boundary.
4. History фізично не є hash-chained append-only ledger.
5. Receipt не має actor/session/authority provenance.
6. Немає PSE-specific memory event/replay model.
7. Немає secret redaction/size/sensitivity enforcement.
8. Existing ProvenanceRecord не інтегрований у memory transaction.

## Відсутні D6-specific surface-и після пошуку в `src`

Не знайдено окремих:

- `MemoryEvent`;
- `MemoryLedger`;
- `MemoryReplay`;
- `ContextPack` для memory;
- memory-to-ADR materializer;
- memory receipt hash-chain implementation;
- project-level memory state reducer;
- event schema з actor/session/causation fields.

Наявні `MemoryMetadata`, `temporal.py` і `provenance.py` є reusable foundations, але не PSE engine.

---

Проведи read-only forensic audit у `/root/gemma/projects/.power-framework-3.7.11-worktree` лише для dimensions 7–10 місії: core/synthesize.py, importer.py, parser.py та потрібні OKF modules; searcher.py, indexer.py, relations.py, db.py, generation/index_sync/source projections, experimental/embeddings.py, reranker.py, graph_extraction.py; core/cli.py; mcp/power_server.py, entrypoint.py, contract.py, preflight.py. Не редагуй файли. Знайди точні line ranges, класи й повні signatures, persistence/FTS/vector/graph contracts, CLI/MCP registration, risk/idempotency behavior і tests. Для PSE вкажи reuse/adapter/extension points та missing capabilities, але не вигадуй. Поверни лише verified research memo українською з шляхами і citations; не пиши звіт у файли.

План: прочитаю протоколи й карту репозиторію, потім побудую verified-карту вказаних модулів із точними рядками, контрактами та тестами. Зміни не вноситиму; висновки позначатиму лише за наявними доказами.

Контекст синхронізовано: аудит виконую на WS у чистому source-worktree POWER 3.7.11; останній release memo підтверджує `v3.7.11`, але це не замінює перевірку коду. Застосую лише read-only огляд і не запускатиму операцій, що пишуть vault, індекс або model cache.

# Verified research memo: POWER 3.7.11, dimensions 7–10

**Root:** `R = /root/gemma/projects/.power-framework-3.7.11-worktree`  
**Scope:** dimensions 7–10 із mission prompt `[R/artifacts/project-state/phase-0/opencode_phase0_prompt.md:L17-L27]`.  
**Revision:** `af2e3022422b2ee3f249e0b2e0aa08b6ce09450c`. Tracked diff порожній; на старті й завершенні присутній лише untracked `R/artifacts/`. Файли не редагувалися. Тести не запускалися.

---

## 7. Session synthesis, ingestion та OKF

### Основні signatures і класи

- `synthesize_session_ingest(name: str, title: str, description: str, content: str, note_type: str = "Daily Log", tags: list[str] | None = None, related: list[str] | None = None, owner: str | None = None, vault_path: str | str | Path = ".", timestamp: datetime.datetime | None = None) -> str`  
  `[R/src/power_framework/core/synthesize.py:L33-L49]`

- `ImportPolicy(StrEnum)` зі станами `strict`, `quarantine`; `QuarantineChange`, `ImportItem`, `ImportPlan` — dataclass-моделі плану імпорту `[R/src/power_framework/core/importer.py:L27-L108]`.

- `normalize_foreign_fields(source: Mapping[str, object], policy: ImportPolicy) -> tuple[dict[str, object], list[QuarantineChange]]`  
  `[R/src/power_framework/core/importer.py:L135-L169]`

- `_plan_item(source: Path, relative: str, destination: Path, policy: ImportPolicy) -> ImportItem`  
  `[R/src/power_framework/core/importer.py:L190-L224]`

- `build_import_plan(source_dir: Path, target_dir: Path, policy: ImportPolicy) -> ImportPlan`  
  `[R/src/power_framework/core/importer.py:L227-L235]`

- `apply_import_plan(plan: ImportPlan, *, allow_partial: bool = False) -> int`  
  `[R/src/power_framework/core/importer.py:L238-L256]`

- `format_import_report(plan: ImportPlan, *, dry_run: bool) -> str`  
  `[R/src/power_framework/core/importer.py:L259-L284]`

- Parser API:  
  `extract_frontmatter_raw(content: str) -> str | None`,  
  `parse_frontmatter(content: str) -> dict | None`,  
  `validate_metadata(content: str) -> OKFMetadata | None`,  
  `has_frontmatter(content: str) -> bool`,  
  `has_type_field(content: str) -> bool`,  
  `build_frontmatter(metadata: OKFMetadata) -> str`,  
  `read_file_content(filepath: Path) -> str`  
  `[R/src/power_framework/core/parser.py:L19-L133]`

### Synthesis contract

1. Нормалізує vault path, додає `.md`, перевіряє існування target `[R/src/power_framework/core/synthesize.py:L50-L64]`.
2. Створює `OKFMetadata`:
   - `MemoryKind.EPISODIC`;
   - source `power://synthesize_session`;
   - SHA-256 body як evidence;
   - `WritePolicy.AGENT_PROPOSED` `[R/src/power_framework/core/synthesize.py:L65-L81]`.
3. Формує frontmatter і повний Markdown body `[R/src/power_framework/core/synthesize.py:L83-L84]`.
4. Викликає `commit_note_change(..., require_absent=True, operation="synthesize.session")` `[R/src/power_framework/core/synthesize.py:L87-L101]`.
5. Після основної транзакції окремо запускає optional graph extraction; exception лише логують, вже записаний note не rollback-иться `[R/src/power_framework/core/synthesize.py:L103-L112]`.
6. Після `commit_note_change` повторно запускає lint `[R/src/power_framework/core/synthesize.py:L112-L119]`.

`ApplicationService.synthesize_session` перед викликом перевіряє тільки шлях у `PARA_FOLDERS`, потім делегує core-функції `[R/src/power_framework/core/application.py:L527-L565]`.

`commit_note_change` виконує note write, hierarchical index, blocking lint, search-generation publication і receipt у recoverable transaction `[R/src/power_framework/core/memory_api.py:L102-L222]`. Повторний lint у `synthesize_session_ingest` є додатковим full-vault scan.

### OKF contract

`OKFMetadata` має required `type`, `title`, `description`, `timestamp`; `title` обмежений 200 символами, `description` має лише `min_length=1`, без max-limit `[R/src/power_framework/core/models.py:L152-L200]`.

Підтримуються:

- `TypedRelation(path, relation="related_to", confidence=1.0)` з `extra="allow"` `[R/src/power_framework/core/models.py:L21-L52]`;
- `MemoryMetadata` з `valid_from`, `valid_until`, `supersedes`, `sources`, `evidence`, `write_policy`, `sensitivity` `[R/src/power_framework/core/models.py:L99-L125]`;
- URL лише з `http://` або `https://` `[R/src/power_framework/core/models.py:L212-L219]`;
- legacy string і typed object форми `related` `[R/src/power_framework/core/models.py:L226-L245]`;
- naive datetime автоматично отримує UTC; string/date напряму моделлю не приймаються `[R/src/power_framework/core/models.py:L247-L254]`.

`build_frontmatter` серіалізує governance, memory, typed/legacy relations і unknown `model_extra` поля `[R/src/power_framework/core/parser.py:L67-L127]`.

### Import contract

- `_source_notes` використовує sorted recursive glob, пропускає `SKIP_FILES` і `EXCLUDED_DIRS`, але прямо документує відсутність vault-scope `[R/src/power_framework/core/importer.py:L111-L121]`.
- `strict` не змінює metadata.
- `quarantine` переносить invalid `status` у `x-status`, invalid `related` у `x-related` `[R/src/power_framework/core/importer.py:L135-L169]`.
- Invalid YAML, missing frontmatter/type або invalid OKF отримують стабільні exclusion reasons `[R/src/power_framework/core/importer.py:L172-L216]`.
- Existing destination із відмінним content — collision; identical destination — `unchanged` `[R/src/power_framework/core/importer.py:L216-L224]`.
- Перед кожним write destination перевіряється повторно; write atomic per-file `[R/src/power_framework/core/importer.py:L238-L256]`.

### Verified risks/gaps

- Core synthesis не має `idempotency_key`; duplicate note дає `FileExistsError`, replay receipt не підтримується `[R/src/power_framework/core/synthesize.py:L43-L49,L61-L64]`.
- `ApplicationService.synthesize_session` не передає `RequestContext.idempotency_key` у synthesis workflow `[R/src/power_framework/core/application.py:L527-L565]`.
- Direct core synthesis не передає `allowed_directories` до `commit_note_change`; PARA-обмеження існує лише у wrapper-рівні `[R/src/power_framework/core/synthesize.py:L94-L101]`.
- Graph extraction відбувається після commit і поза canonical mutation lock `[R/src/power_framework/core/synthesize.py:L103-L110]`.
- Multi-file import не має aggregate rollback manifest: уже записані notes залишаються, якщо наступний file/index/sync падає `[R/src/power_framework/core/importer.py:L238-L256]`; CLI обгортає лише lock, не transaction snapshot `[R/src/power_framework/core/cli.py:L381-L395]`.
- Import source symlink-и перевіряються через `path.is_file()`, а не через regular in-root policy `[R/src/power_framework/core/importer.py:L111-L121]`.
- `read_file_content` ігнорує decode errors; importer при цьому виключає `UnicodeError`, тобто поведінка різна `[R/src/power_framework/core/parser.py:L130-L133]`, `[R/src/power_framework/core/importer.py:L190-L197]`.

---

## 8. Indexing, Search та Graph RAG

### Persistence topology

SQLite schema створюється `_init_db(conn: sqlite3.Connection) -> None` `[R/src/power_framework/core/db.py:L88-L261]`.

Основні таблиці:

- FTS5: `fts_notes(title, tags, description, content, rel_path UNINDEXED, note_type UNINDEXED)`;
- `file_metadata`;
- `temporal_records`;
- `tf_vectors`;
- `doc_embeddings`;
- `chunk_embeddings`;
- `dense_index_manifest`;
- `source_metadata`, `source_links`, `source_link_ambiguities`, `source_projection_meta`;
- accepted `relations`;
- `relation_candidates`;
- `relation_candidate_decisions`.

SQLite використовує WAL, `busy_timeout=30000`, incremental vacuum, synchronous `NORMAL`, 64 MB page cache і до 1 GB mmap `[R/src/power_framework/core/db.py:L88-L113]`.

Accepted graph relations мають `candidate_id`, `accepted_by`, `accepted_at`; heuristic legacy rows reclassify-яться в unreviewed candidates `[R/src/power_framework/core/db.py:L19-L86,L204-L260]`.

### Atomic generation contract

`sync_vault_atomically(vault_dir: Path, *, sync_embeddings: bool, force_rebuild: bool = False, allow_partial: bool = True, accept_dense_loss: bool = False) -> GenerationReport`  
`[R/src/power_framework/core/generation_index.py:L889-L999]`

Generation state:

- `generation-state.db`;
- `index_generations`;
- `generation_sources`;
- `active_generation`;
- `generation_invalid_sources`  
  `[R/src/power_framework/core/generation_index.py:L178-L241]`.

`SourceInventory`, `GenerationReport`, `ActiveGeneration` — typed immutable records `[R/src/power_framework/core/generation_index.py:L50-L85]`.

Flow:

1. Ensure vault identity/cache namespace.
2. Scan valid/invalid sources and compute BLAKE2 snapshot.
3. Stage SQLite generation.
4. Sync FTS/vector/projections.
5. Recheck source snapshot.
6. Validate source coverage, projection coverage, dense manifest and SQLite integrity.
7. `fsync`, atomic move staging → immutable generation.
8. CAS-update active pointer.
9. Verify active readback; retain two ready generations `[R/src/power_framework/core/generation_index.py:L646-L724,L727-L793]`.

Active generation validation checks state, DB SHA-256, size and `PRAGMA integrity_check`; once an active state exists, fallback to legacy DB is forbidden `[R/src/power_framework/core/generation_index.py:L433-L500]`.

### FTS/vector sync

`_sync_vault_to_db(vault_dir: Path, conn: sqlite3.Connection, sync_embeddings: bool = False, force_rebuild: bool = False) -> None`  
`[R/src/power_framework/core/index_sync.py:L77-L103]`

- FTS-only mode does not load model.
- Incremental change detector uses path + mtime `[R/src/power_framework/core/index_sync.py:L124-L205]`.
- FTS stores full note content plus title/tags/description `[R/src/power_framework/core/index_sync.py:L215-L253]`.
- `temporal_records` stores only serialized `MemoryMetadata`, not body `[R/src/power_framework/core/index_sync.py:L235-L243]`.
- TF-vector is normalized term frequency over title/tags/description/content.
- FTS-only source changes invalidate dense manifest and changed dense rows `[R/src/power_framework/core/index_sync.py:L290-L305]`.
- Source projection is rewritten after lightweight sync `[R/src/power_framework/core/index_sync.py:L307-L313]`.

Dense path:

- short notes under 200 tokens get one whole-document chunk;
- longer notes use `SemanticChunker`;
- chunk ID is SHA-256 over source hash, section identity, ordinal and normalized content `[R/src/power_framework/core/index_sync.py:L315-L372]`.
- `_embed_and_store` uses batched embedding, adaptive batch halving, periodic commits and bounded thread settings `[R/src/power_framework/core/index_sync.py:L404-L519]`.

### Source projection

`scan_projection(vault_dir: Path, *, max_sources: int | None = None, max_source_bytes: int | None = None) -> ScannedProjection`  
`write_projection(conn: Any, projection: ScannedProjection) -> None`  
`[R/src/power_framework/core/source_projection.py:L120-L125,L235-L306]`

Projection records:

- `SourceRecord`;
- `SourceLink`;
- `SourceAmbiguity`;
- `ScannedProjection`  
  `[R/src/power_framework/core/source_projection.py:L26-L70]`.

Links originate from:

- wikilinks;
- Markdown `.md` links;
- explicit OKF `related` metadata  
  `[R/src/power_framework/core/source_projection.py:L22-L24,L180-L215]`.

Resolution is exact path → source-relative path → unique case-insensitive stem; ambiguous stems are persisted separately, never arbitrarily selected `[R/src/power_framework/core/source_projection.py:L83-L117]`.

`source_service` validates projection table presence, counts, revision, current source file size/mtime and fails closed if stale `[R/src/power_framework/core/source_service.py:L136-L267]`.

Degraded no-generation reads are bounded to 5000 sources and 2 MB per source, with `healthy=False` and `degraded_bounded_source_scan` `[R/src/power_framework/core/source_service.py:L270-L285]`.

### Search modes

`SearchModeSpec(candidate_sources, fusion, reranker, requires_dense_index)` and registry `[R/src/power_framework/core/searcher.py:L269-L286]`:

| Mode | Contract |
|---|---|
| `fts` | SQLite FTS5/BM25 |
| `vector` | TF-vector cosine |
| `hybrid` | FTS + TF RRF; dense candidates optional |
| `semantic` | dense chunk cosine; dense index required |
| `reranked` | FTS + TF + dense → RRF → cross-encoder |
| `graph_assisted` | FTS + TF → accepted/explicit relation-based expansion |

`search_vault(vault_dir: Path, query: str, max_results: int = 20, mode: str = DEFAULT_SEARCH_MODE, temporal_view: str = "current", as_of: date | str | None = None, domain: str | None = None, *, allow_search_db_override: bool = True) -> list[SearchResult]`  
`[R/src/power_framework/core/searcher.py:L1308-L1345]`.

`SearchResult` includes score, snippet, tags, actual mode, fallback reason, temporal status and index-generation provenance `[R/src/power_framework/core/searcher.py:L327-L348]`.

Dense validation checks:

- nonempty vectors;
- equal byte width;
- dimension;
- provider;
- model;
- schema version;
- chunk count  
  `[R/src/power_framework/core/searcher.py:L403-L450]`.

Explicit dense modes fail closed unless `POWER_ALLOW_DENSE_FALLBACK=1`; fallback is labeled `fts_fallback` `[R/src/power_framework/core/searcher.py:L1390-L1413]`.

MCP/application retrieval envelope is untrusted, data-only, bounded to 120-character snippets, and includes source SHA-256, result ID and index provenance `[R/src/power_framework/core/searcher.py:L1929-L2017]`.

### Embeddings/reranker

Canonical model configuration:

- BGE-M3 ONNX repository/revision and file hashes `[R/src/power_framework/experimental/embeddings.py:L62-L77]`;
- canonical embedding identity `[R/src/power_framework/experimental/embeddings.py:L273-L282]`;
- model lock release 3.7.11 confirms BGE-M3 and BGE reranker pins `[R/release/models.lock.json:L1-L62]`.

`BGEM3OnnxManager` uses direct ONNX Runtime, pinned Hugging Face revision, SHA checks, provider verification, disabled CPU arena and eager probe `[R/src/power_framework/experimental/embeddings.py:L606-L764]`.

`get_embedding_manager(model_name: str | None = None) -> ...` defaults to BGE-M3; unknown providers raise `RuntimeError`; qwen3 allocation/dependency failures may fall back to fastembed with warning `[R/src/power_framework/experimental/embeddings.py:L770-L844]`.

`RerankerProtocol` defines `rerank(query: str, documents: list[str]) -> list[float]` `[R/src/power_framework/experimental/reranker.py:L43-L48]`.

`BGEM3Reranker` is canonical default and uses pinned ONNX model, provider binding and eager probe `[R/src/power_framework/experimental/reranker.py:L117-L245]`. Runtime rerank batch default is 8 `[R/src/power_framework/experimental/reranker.py:L311-L335]`.

`RerankerManager` is Jina CC-BY-NC opt-in only with both flags `[R/src/power_framework/experimental/reranker.py:L68-L114]`. `LexicalReranker` exists `[R/src/power_framework/experimental/reranker.py:L338-L363]`, але `get_reranker()` не повертає його при BGE failure; default path returns `BGEM3Reranker` `[R/src/power_framework/experimental/reranker.py:L366-L388]`.

### Graph behavior

Compatibility shims redirect `core/relations.py`, `core/embeddings.py`, `core/reranker.py`, `core/graph_extraction.py` у `experimental/*` `[R/src/power_framework/core/relations.py:L1-L9]`, `[R/src/power_framework/core/graph_extraction.py:L1-L9]`.

Graph implementations are separate:

1. `KnowledgeGraph` — explicit typed OKF relations, directed BFS, quarantined missing targets `[R/src/power_framework/experimental/relations.py:L219-L353]`.
2. `suggest_related` — keyword/tag Jaccard `[R/src/power_framework/experimental/relations.py:L131-L216]`.
3. `suggest_related_v2` — keyword/tag overlap plus explicit-link bonus `[R/src/power_framework/experimental/relations.py:L396-L511]`.
4. `WeightedKnowledgeGraph` — bidirectional weighted BFS `[R/src/power_framework/experimental/relations.py:L514-L563]`.
5. `suggest_related_semantic` — embeds first 2000 characters of target/candidates, falls back to keyword with warning `[R/src/power_framework/experimental/relations.py:L587-L657]`.
6. `graph_extraction.extract_triplets(content: str, note_path: str | None = None) -> list[Triplet]` — deterministic regex/cue extraction `[R/src/power_framework/experimental/graph_extraction.py:L33-L142]`.
7. `store_triplets(...)` writes `relation_candidates`, never accepted `relations` `[R/src/power_framework/experimental/graph_extraction.py:L145-L182]`.

### Verified risks/gaps

- `synthesize_session_ingest` writes triplets after generation publication through `_db_path()` → legacy `search.db`; active generation uses separate immutable `generations/<id>.db` `[R/src/power_framework/experimental/graph_extraction.py:L272-L292]`, `[R/src/power_framework/core/searcher.py:L124-L126]`, `[R/src/power_framework/core/vault_storage.py:L185-L192]`.
- `source_projection` and `graph_assisted_search` do not consume `relation_candidates`; graph-assisted search calls `suggest_related_v2` directly `[R/src/power_framework/core/searcher.py:L1730-L1823]`.
- `graph_extraction.py` documentation mentions an OpenRouter LLM backend, але executable code implements only local regex extraction `[R/src/power_framework/experimental/graph_extraction.py:L1-L14,L105-L142]`.
- Candidate evidence stores the source sentence in JSON, so this projection is not content-free `[R/src/power_framework/experimental/graph_extraction.py:L157-L177]`.
- No CLI/MCP candidate approve/reject surface was found; approval functions exist only as direct Python APIs `[R/src/power_framework/experimental/graph_extraction.py:L201-L269]`.
- Semantic relation suggestion is not indexed-vector based; it re-embeds notes per request and silently degrades to keyword with warning `[R/src/power_framework/experimental/relations.py:L601-L657]`.
- Relation suggesters skip `_index.md` but do not explicitly skip numbered `_index-N.md`, unlike index sync/catalog code `[R/src/power_framework/experimental/relations.py:L150-L155]`, `[R/src/power_framework/core/constants.py:L76-L82]`.
- `accept_dense_loss=True` bypasses the refusal guard, але dense rows are explicitly deleted only when changed/deleted files exist `[R/src/power_framework/core/generation_index.py:L909-L915]`, `[R/src/power_framework/core/index_sync.py:L290-L305]`; a no-change FTS-only downgrade can retain old dense rows despite the documented discard contract.
- Low-level `sync_vault_atomically` defaults `allow_partial=True` `[R/src/power_framework/core/generation_index.py:L889-L905]`.

---

## 9. CLI registration та conventions

### Registration

`main() -> None` запускає CPU environment enforcement, Windows UTF-8 setup, root parser і `subparsers` `[R/src/power_framework/core/cli.py:L1203-L1224]`.

Top-level commands зареєстровані в `[R/src/power_framework/core/cli.py:L1226-L1862]`:

`init`, `lint`, `index`, `ingest`, `import`, `search`, `cache`, `doctor`, `integrations`, `connect`, `memory`, `handoff`, `task`, `sync`, `rot`, `archive`, `status`, `control-plane`, `maintenance`, `migrate-state`, `cron`, `heal`, `markdown-check`, `suggest-related`, `synthesize`, `rename`.

`capabilities._cli_commands()` витягує registrations статичним AST-скануванням `[R/src/power_framework/core/capabilities.py:L24-L46]`.

### Relevant handlers

- `_cmd_index(args: argparse.Namespace) -> int` — mutation lock, hierarchical index, optional strict warning check `[R/src/power_framework/core/cli.py:L210-L224]`.
- `_cmd_ingest(args: argparse.Namespace) -> int` — domain routing, OKF generation, note commit/search publication `[R/src/power_framework/core/cli.py:L227-L329]`.
- `_cmd_import(args: argparse.Namespace) -> int` — path checks, deterministic plan, dry-run/partial policy, index + FTS sync `[R/src/power_framework/core/cli.py:L347-L412]`.
- `_cmd_search(args: argparse.Namespace) -> int` — `ApplicationService.retrieve`, JSON або full envelope `[R/src/power_framework/core/cli.py:L415-L444]`.
- `_cmd_sync(args: argparse.Namespace) -> int` — atomic generation, optional address-space cap `[R/src/power_framework/core/cli.py:L480-L567]`.
- `_cmd_suggest_related(args: argparse.Namespace) -> int` — лише keyword або v2 suggester `[R/src/power_framework/core/cli.py:L797-L812]`.
- `_cmd_synthesize(args: argparse.Namespace) -> int` — core synthesis wrapper `[R/src/power_framework/core/cli.py:L815-L837]`.

Path resolution: explicit CLI path → `POWER_VAULT_DIR` → cwd `[R/src/power_framework/core/cli.py:L129-L137]`.

### Flags/contracts

- Search modes, temporal view, `--json`, `--envelope`, domain `[R/src/power_framework/core/cli.py:L1302-L1343]`.
- Sync supports `--fts-only`, `--accept-dense-loss`, `--force`, mutually exclusive `--strict`/`--allow-partial` `[R/src/power_framework/core/cli.py:L1677-L1715]`.
- Synthesis accepts body only through required `--content` argv `[R/src/power_framework/core/cli.py:L1843-L1862]`.
- Ingest help still says description max 150, while runtime model has no max constraint `[R/src/power_framework/core/cli.py:L1246-L1257]`, `[R/src/power_framework/core/models.py:L161-L168]`.
- CPU hooks: `enforce_cpu_throttling_env()` caps OpenMP/BLAS/ONNX-related env values to half CPU cores `[R/src/power_framework/core/utils.py:L507-L546]`; sync optionally applies `RLIMIT_AS` from `POWER_SYNC_VMEM_LIMIT_MB` `[R/src/power_framework/core/cli.py:L491-L512]`.
- No NVIDIA MPS/`ws-gpu-task-50` hook exists in `core/cli.py`; only CPU/environment controls are present there.

### CLI risk findings

1. **Partial sync publication discrepancy.** `_cmd_sync` does not pass `allow_partial` or `strict` to `sync_vault_atomically` `[R/src/power_framework/core/cli.py:L520-L530]`, whose low-level default is `allow_partial=True` `[R/src/power_framework/core/generation_index.py:L889-L905]`. CLI checks exclusions only after publication and may return exit code 1 after publishing a partial generation `[R/src/power_framework/core/cli.py:L548-L566]`.
2. Same default omission exists in CLI import’s `sync_vault_atomically(...)` call `[R/src/power_framework/core/cli.py:L381-L392]`.
3. CLI `search --max-results` parses unrestricted `int`; validation happens later in `ApplicationService`, while `_cmd_search` has no exception wrapper `[R/src/power_framework/core/cli.py:L415-L444]`, `[R/src/power_framework/core/application.py:L214-L230]`.
4. Synthesis body can appear in process arguments because there is no file/stdin input option `[R/src/power_framework/core/cli.py:L1843-L1862]`.
5. CLI `suggest-related --max-results` has no positive bound and no semantic method flag `[R/src/power_framework/core/cli.py:L1819-L1841]`.

### CLI tests

- lint/index/error codes: `[R/tests/test_cli.py:L125-L194]`;
- sync coverage and partial policy: `[R/tests/test_cli.py:L227-L420]`;
- ingest/search: `[R/tests/test_cli.py:L422-L558]`;
- CLI memory boundary: `[R/tests/test_cli.py:L561-L804]`;
- handoff/task idempotency and revision checks: `[R/tests/test_cli.py:L807-L1117]`;
- dense-loss guard: `[R/tests/test_cli.py:L1120-L1201]`;
- import plan/dry-run/rerun: `[R/tests/test_importer.py:L54-L151]`.

У перевірених CLI-тестах немає assertion, що default CLI sync **не публікує** partial generation перед поверненням exit 1.

---

## 10. MCP server, entrypoint, contract, preflight

### Server architecture

Використовується official SDK `MCPServer`, не FastMCP `[R/src/power_framework/mcp/power_server.py:L34-L36]`.

`PowerMCPServer(MCPServer)`:

- `tool(...) -> Callable[...]` нормалізує legacy annotation names;
- `call_tool(name, arguments, context) -> CallToolResult | InputRequiredResult` перетворює `ToolError` у безпечний framed result;
- `run(transport: str = "stdio", **kwargs: Any) -> None` приймає лише stdio  
  `[R/src/power_framework/mcp/power_server.py:L110-L155]`.

Global server і process-local limiters:

- `mcp = PowerMCPServer("power", version=__version__, ...)`;
- writes: 10/60 s;
- index operations: 5/60 s  
  `[R/src/power_framework/mcp/power_server.py:L158-L166]`.

Vault boundary:

`_get_vault_path(vault_path: str | None = None) -> Path` вимагає `POWER_VAULT_DIR`; переданий path повинен дорівнювати configured root `[R/src/power_framework/mcp/power_server.py:L275-L285]`.

`require_configured_vault_root() -> Path` відхиляє відсутній, неіснуючий або не-directory root `[R/src/power_framework/mcp/preflight.py:L14-L22]`.

Public launcher:

- `_build_parser() -> argparse.ArgumentParser`;
- `main(argv: Sequence[str] | None = None) -> int`;
- `preflight` повертає JSON і code 0;
- failure code 2;
- server import lazy, лише після preflight  
  `[R/src/power_framework/mcp/entrypoint.py:L18-L64]`.

`run(transport: str = "stdio") -> None` повторно enforce-ить CPU env, preflight і запускає `mcp.run(transport="stdio")` `[R/src/power_framework/mcp/power_server.py:L1080-L1086]`.

### MCP discovery contract

- `canonical_tool_catalog(tools: list[Any]) -> list[dict[str, Any]]`;
- `tool_catalog_fingerprint(tools: list[Any]) -> dict[str, Any]`;
- `mcp_discovery_contract(tools: list[Any]) -> dict[str, Any]`;
- `agent_integration_descriptor(tools: list[Any]) -> dict[str, Any]`  
  `[R/src/power_framework/mcp/contract.py:L25-L97]`.

Contract advertises stdio, preferred protocol `2026-07-28`, legacy compatibility, `POWER_VAULT_DIR`, read-only/network defaults and SHA-256 tool catalog.

### Registered tools

Реєстрація виконується `@mcp.tool`:

1. `get_server_info(vault_path: str | None = None, probe_provider: bool = False) -> str` `[R/src/power_framework/mcp/power_server.py:L288-L315]`
2. `lint_vault(vault_path: str | None = None) -> str` `[L318-L330]`
3. `generate_index(vault_path: str | None = None) -> str` `[L333-L356]`
4. `sync_vault(fts_only: bool = True, accept_dense_loss: bool = False, force_rebuild: bool = False, allow_partial: bool = False, vault_path: str | None = None) -> str` `[L359-L415]`
5. `read_sub_index(category: str, vault_path: str | None = None, page: int = 1) -> str` `[L418-L444]`
6. `ensure_sub_index(category: str, vault_path: str | None = None, page: int = 1) -> str` `[L446-L478]`
7. `ingest_note(name: str, note_type: str, title: str, description: str, content: str, resource: str | None = None, tags: list[str] | None = None, vault_path: str | None = None) -> str` `[L481-L534]`
8. `get_memory_context(query: str, vault_path: str | None = None) -> str` `[L537-L551]`
9. `propose_memory_change(path: str, content: str, vault_path: str | None = None) -> str` `[L554-L573]`
10. `apply_memory_change(proposal: dict[str, str], approved: bool, vault_path: str | None = None) -> str` `[L576-L600]`
11. `validate_memory_state(vault_path: str | None = None) -> bool` `[L603-L615]`
12. `read_memory_history(vault_path: str | None = None) -> str` `[L618-L631]`
13. `handoff_work(action: Literal[...], task_id: str | None = None, objective: str | None = None, owner: str | None = None, actor: str = "agent", scope: list[str] | None = None, authority: Literal[...] = "read-only", source_revision: str = "unknown", next_action: str | None = None, profile: Literal[...] = "standard", required_approval: str | None = None, idempotency_key: str | None = None, expected_revision: int | None = None, approved: bool = False, blocker: str | None = None, receipt_id: str | None = None, completion_postcondition: str | None = None, changed_artifacts: list[str] | None = None, open_gates: list[str] | None = None, phase: Literal[...] | None = None, vault_path: str | None = None) -> str` `[L634-L761]`
14. `search_vault_tool(query: str, max_results: int = 20, search_mode: str = DEFAULT_SEARCH_MODE, temporal_view: str = "current", as_of: str | None = None, domain: str | None = None, vault_path: str | None = None) -> str` `[L764-L826]`
15. `synthesize_session(name: str, title: str, description: str, content: str, note_type: str = "Daily Log", tags: list[str] | None = None, related: list[str] | None = None, owner: str | None = None, vault_path: str | None = None) -> str` `[L829-L891]`
16. `rot_audit(vault_path: str | None = None, extended: bool = False, allow_link_rot: bool = False, allow_remote_llm: bool = False, approved: bool = False) -> str` `[L894-L934]`
17. `archive_notes(dry_run: bool = True, approved: bool = False, vault_path: str | None = None) -> str` `[L937-L961]`
18. `suggest_related_tool(target_path: str | None = None, max_results: int = 5, method: str = "semantic", vault_path: str | None = None) -> str` `[L964-L994]`
19. `heal_frontmatter_tool(dry_run: bool = True, approved: bool = False, vault_path: str | None = None) -> str` `[L997-L1021]`
20. `check_markdown_tool(vault_path: str | None = None) -> str` `[L1024-L1077]`.

Static manifest parsing знаходить MCP decorators і ризики `[R/src/power_framework/core/capabilities.py:L58-L98]`.

### Risk/approval annotations

- Read-only, no approval: discovery, lint, sub-index read, memory context/history, validation, markdown check.
- Caller approval: index generation, sync, ensure sub-index, ingest, propose, handoff, synthesis.
- Explicit approval: apply memory, archive, heal, remote ROT.
- Model download risk: sync, search, semantic relation suggestion.
- Network/open-world risk: `rot_audit`; requires both `extended=True` and `approved=True` `[R/src/power_framework/mcp/power_server.py:L909-L934]`.
- Destructive tools are server-side approval-gated, not merely advisory metadata `[R/src/power_framework/mcp/power_server.py:L946-L961,L1006-L1021]`.

Search tool disables `POWER_SEARCH_DB` redirection by injecting `partial(search_vault, allow_search_db_override=False)` `[R/src/power_framework/mcp/power_server.py:L803-L826]`.

Mutation tools delegate through `ApplicationService`; static boundary test forbids direct low-level calls `[R/tests/test_mcp_application_boundary.py:L30-L62]`.

### MCP risks/gaps

- `ingest_note` і `synthesize_session` не приймають idempotency key; duplicate name — error, not replay `[R/src/power_framework/mcp/power_server.py:L490-L534,L838-L891]`.
- `generate_index`/`ensure_sub_index` advertise idempotency, але index renderer writes a fresh timestamped root index on each run `[R/src/power_framework/mcp/power_server.py:L333-L356]`, `[R/src/power_framework/core/indexer.py:L397-L407]`.
- `suggest_related_tool` silently maps invalid `method` to semantic and does not bound `max_results` `[R/src/power_framework/mcp/power_server.py:L973-L994]`.
- `apply_memory_change` has `idempotentHint=False`, although durable proposal application ultimately passes its stored key into `commit_note_change` `[R/src/power_framework/mcp/power_server.py:L585-L600]`, `[R/src/power_framework/core/memory_api.py:L307-L326]`.
- `call_tool` explicitly catches only `ToolError`; other tool functions perform their own inconsistent exception mapping `[R/src/power_framework/mcp/power_server.py:L134-L149]`.
- Base package does not include MCP runtime; it is an explicit optional extra `[R/pyproject.toml:L26-L36,L95-L100]`. Entrypoint keeps preflight/version usable before lazy server import `[R/src/power_framework/mcp/entrypoint.py:L37-L64]`.

### MCP tests

- 20-tool registry, schemas, annotations and risk metadata: `[R/tests/test_mcp_server.py:L79-L185]`.
- read-only discovery/no model/cache mutation: `[R/tests/test_mcp_server.py:L196-L265]`.
- stdio legacy/modern handshakes and restart: `[R/tests/test_mcp_server.py:L266-L323]`.
- safe framed errors and approval/egress gates: `[R/tests/test_mcp_server.py:L326-L417]`.
- preflight and stdout-only protocol: `[R/tests/test_mcp_server.py:L452-L490]`.
- catalog page contract: `[R/tests/test_mcp_server.py:L492-L558]`.
- search, memory, handoff, ingest, synthesis and traversal: `[R/tests/test_mcp_server.py:L597-L1001]`.
- stdio-only server run: `[R/tests/test_mcp_server.py:L1020-L1039]`.
- public launcher/preflight: `[R/tests/test_power_mcp_entrypoint.py:L17-L64]`.
- documented client shapes and proposal-without-write: `[R/tests/test_mcp_client_onboarding.py:L59-L123]`.

---

## PSE integration verdict

| Audited area | Classification | Verified reuse/extension point | Missing capability |
|---|---|---|---|
| Synthesis/OKF | **REUSE + EXTENSION** | `ApplicationService.synthesize_session`, `OKFMetadata`, `MemoryMetadata`, `build_frontmatter` | PSE project ID, session/actor attribution, project lifecycle state and event ledger absent |
| Importer | **ADAPTER** | `ImportPlan`, `ImportPolicy`, `normalize_foreign_fields` provide Level-C import seam | No project-level mapping, aggregate rollback, PSE receipt or idempotency key |
| SQLite/FTS/vector | **REUSE as derived projection** | `sync_vault_atomically`, `source_projection`, `fts_notes`, `tf_vectors`, dense manifest | Not canonical PSE state; no deterministic project-state replay/event sourcing |
| Graph | **ADAPTER + EXTENSION** | `relation_candidates`, `approve_candidate`, `reject_candidate`, typed `related` | Candidate review not exposed through Application/CLI/MCP; active graph ignores heuristic candidates |
| CLI | **ADAPTER** | `ApplicationService`, `RequestContext`, `ApplicationEnvelope`, capabilities manifest | No PSE commands, project lifecycle/RAID/RACI/DoR/DoD surfaces |
| MCP | **ADAPTER** | `@mcp.tool`, `PowerMCPServer`, risk metadata, catalog fingerprint, configured-vault boundary | No PSE tool schemas or context/event compilation surface |

No `R/src/power_framework/project_state/` files and no PSE implementation references were found. Parallel PSE storage would violate the existing adapter boundary: MCP tests explicitly require mutation delegation through `ApplicationService` `[R/tests/test_mcp_application_boundary.py:L30-L62]`.

The existing `memory-history.jsonl` is append-only content-free receipt storage, but it is not a hash-chained project event ledger `[R/src/power_framework/core/memory_api.py:L488-L519]`. The source graph, FTS, vector and generation databases are rebuildable projections, not a PSE canonical event source.

Попередній memo був обрізаний. Продовж лише пропущену частину dimensions 7–10, особливо завершення MCP (tools 19–20, risk/idempotency, application boundary) і всі відсутні PSE gaps/extension points. Дай exact path:symbol:line citations і тести; не повторюй уже видимий текст; без writes/secrets.

Продовження: перевірю лише невидимі/недостатньо розкриті фрагменти MCP 19–20, boundary/idempotency та PSE capability gaps. Файли не змінюватиму й не запускатиму write-capable операцій.

## Продовження verified memo: MCP 19–20, boundary та PSE gaps

### MCP tool 19 — `heal_frontmatter_tool`

**Signature:**  
`async def heal_frontmatter_tool(dry_run: bool = True, approved: bool = False, vault_path: str | None = None) -> str`  
`/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/mcp/power_server.py:heal_frontmatter_tool:L997-L1021`

**Registration/risk:**

- `readOnlyHint=False`
- `destructiveHint=True`
- `idempotentHint=False`
- `openWorldHint=False`
- `power.risk = {local_only: True, egress: "none", approval: "explicit"}`  
  `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/mcp/power_server.py:heal_frontmatter_tool:L997-L1005`

**Behavior:**

- `dry_run=False` без `approved=True` відхиляється `ToolError`.
- Vault path проходить configured-root validation.
- Виконання offload-иться через `run_blocking`.
- Mutation делегується `ApplicationService.heal_frontmatter(...)`.
- `RequestContext(actor="mcp", authority="apply")` створюється лише для live apply.
- Повертається лише `str(envelope.data["result"])`, без окремого структурованого heal receipt.  
  `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/mcp/power_server.py:heal_frontmatter_tool:L1012-L1021`

**Важливий gap:** `ApplicationService.heal_frontmatter` викликає `heal_vault(...)`, але після live healing не запускає hierarchical index, FTS/dense sync або search readback.  
`/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/application.py:ApplicationService.heal_frontmatter:L590-L611`

Underlying healer пише notes і backups, але не публікує пошукову генерацію:  
`/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/healer.py:heal_vault_report:L368-L449`

Отже, успішний tool-19 apply може залишити FTS/vector/source projections застарілими до окремого `sync`.

**Idempotency:** параметра `idempotency_key` немає; annotation чесно вказує `idempotentHint=False`. Backup filenames timestamp-based, а multi-note healing не має aggregate idempotency/replay contract.

---

### MCP tool 20 — `check_markdown_tool`

**Signature:**  
`async def check_markdown_tool(vault_path: str | None = None) -> str`  
`/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/mcp/power_server.py:check_markdown_tool:L1024-L1036`

**Registration/risk:**

- `readOnlyHint=True`
- `destructiveHint=False`
- `idempotentHint=True`
- `openWorldHint=False`
- `power.risk = {local_only: True, egress: "none", approval: "none"}`  
  `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/mcp/power_server.py:check_markdown_tool:L1024-L1032`

**Behavior:**

- Валідовує тільки configured vault root.
- Повний scan виконується в `run_blocking`.
- Використовує `iter_vault_markdown_files`, `should_skip`, `SKIP_FILES`.
- Для unreadable files exception лише логують на DEBUG і продовжують.
- Формує string report із типами та номерами проблем.  
  `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/mcp/power_server.py:check_markdown_tool:L1033-L1077`

**Edge case:** `SKIP_FILES` містить `_index.md`, але не numbered `_index-N.md`; тому numbered generated catalogs не виключені спеціальним іменним фільтром tool-20.  
`/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/constants.py:is_catalog_filename:L76-L82`  
`/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/constants.py:SKIP_FILES:L67-L67`

У перевірених тестах немає прямого виклику `check_markdown_tool`; тестується underlying `check_all`, а не MCP adapter:  
`/root/gemma/projects/.power-framework-3.7.11-worktree/tests/test_markdown_checks.py:TestCheckAll:L89-L99`

---

## Application boundary: точний MCP contract

`PowerMCPServer.call_tool` ловить лише `ToolError`, перетворює його на `CallToolResult(is_error=True)`, видаляє absolute paths і обрізає повідомлення до 512 символів.  
`/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/mcp/power_server.py:_safe_mcp_error_text:L101-L107`  
`/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/mcp/power_server.py:PowerMCPServer.call_tool:L134-L149`

Mutation boundary:

- `_mutation_context` приймає лише `propose` або `apply`.
- `heal_frontmatter` live path проходить цю boundary.
- MCP static test забороняє прямі виклики `heal_vault`, `run_generate_*`, `sync_vault_atomically`, `synthesize_session_ingest` тощо.
- Для `heal_frontmatter_tool` тест явно вимагає `ApplicationService.heal_frontmatter`.  
  `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/application.py:ApplicationService._mutation_context:L323-L329`  
  `/root/gemma/projects/.power-framework-3.7.11-worktree/tests/test_mcp_application_boundary.py:test_mcp_mutations_do_not_import_or_call_core_implementation_details:L19-L62`

`ApplicationService._run` створює application receipt із `request_id`, idempotency key, data digest і duration, але receipt не містить `actor`.  
`/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/application.py:AuditReceipt:L85-L106`  
`/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/application.py:ApplicationService._run:L1052-L1105`

`RequestContext.actor` існує, але для synthesis/healing не потрапляє у persisted note metadata або memory-history record.  
`/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/application.py:RequestContext:L62-L82`  
`/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/application.py:ApplicationService.synthesize_session:L527-L565`

---

## PSE: додатково виявлені gaps та extension points

| PSE capability | Verified foundation | Missing / boundary |
|---|---|---|
| Append-only event ledger | `memory-history.jsonl` receipts; task-local hash chain | Memory history не має `prev_digest`, sequence або replay validation; task chain є лише task-scoped, не project-scoped. `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/memory_api.py:_append_receipt:L488-L519`; `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/task_store.py:TaskStore.get_task_events:L286-L318` |
| Session/actor provenance | `RequestContext(actor, request_id)`; synthesis evidence SHA | Actor/request/session не зберігаються у note frontmatter, graph candidate або memory receipt; `AuditReceipt` actor не має. `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/application.py:RequestContext:L62-L82`; `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/models.py:MemoryMetadata:L99-L125` |
| Temporal validity/supersession | `MemoryMetadata.valid_from`, `valid_until`, `supersedes`; temporal resolver | Є derived status, але немає PSE bitemporal event model, `invalidates`, project identity або event-time/record-time separation. `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/temporal.py:resolve_temporal_statuses:L138-L216` |
| Semantic entity typing | `NoteType` і generic `Triplet` | `NoteType` містить лише PARA/system types; немає FACT/DECISION/ASSUMPTION/RISK/ISSUE тощо. Triplet entity fields — plain strings. `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/models.py:NoteType:L55-L64`; `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/experimental/graph_extraction.py:Triplet:L33-L42` |
| Project lifecycle engine | `NoteStatus(active/review/archived)`; task transitions | Note status не є project lifecycle; deterministic project gates/states відсутні в audited surfaces. `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/models.py:NoteStatus:L66-L72` |
| RAID log | `owner`, `status`, `expiry`, `supersedes` metadata | Немає typed RAID objects, project RAID persistence, CLI/MCP RAID use case або projection. `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/models.py:OKFMetadata:L152-L200` |
| RACI governance | `OKFMetadata.owner`; `RequestContext.actor` | Відсутні Responsible/Accountable/Consulted/Informed fields і authorization mapping. |
| DoR/DoD gates | Handoff має `phase`, `open_gates`, `completion_postcondition` | Поля передаються як task payload; PSE project-level enforcement відсутній. `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/mcp/power_server.py:handoff_work:L643-L761` |
| Deterministic project replay | Atomic generation rebuild із source snapshot | Generation rebuild-ить SQLite projections із Markdown, не project state із canonical event log. `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/generation_index.py:sync_vault_atomically:L889-L999` |
| Contradiction/supersession detection | Temporal resolver позначає competing heads/cycles | Це note-memory temporal semantics, не typed PSE claim/decision contradiction engine. `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/temporal.py:resolve_temporal_statuses:L186-L216` |
| Context compilation | `get_context` повертає FTS `SearchResult` | Немає role/task-based ContextPack, bounded section compiler або provenance bundle. `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/memory_api.py:get_context:L45-L53` |
| Automatic capture | Explicit synthesis, ingestion, foreign-note import | Немає session hook/Level-B capture; CLI/MCP потребують явного виклику tool/command. `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/synthesize.py:synthesize_session_ingest:L33-L120`; `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/importer.py:build_import_plan:L227-L235` |
| Privacy/redaction boundaries | Untrusted bounded retrieval envelope; content-free receipts | Graph candidate evidence зберігає raw sentence; synthesis зберігає повний content; PSE capture modes/redaction policy відсутні. `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/experimental/graph_extraction.py:store_triplets:L145-L182`; `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/searcher.py:format_untrusted_search_envelope:L1929-L2017` |
| Materialized project views | Hierarchical catalogs, generation DBs, cache | В audited source не знайдено PSE `meta.json`, `ADR-*.md`, `raid_log.json`, `dependencies.json`, `lessons-*.md` materialization contract. Existing catalog/generation outputs є generic vault/search projections. `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/indexer.py:run_generate_hierarchical_index:L847-L930`; `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/generation_index.py:_init_state_db:L178-L241` |

### Concrete PSE reuse/extension points

1. **REUSE OKF/application boundary:** PSE ingestion має входити через `ApplicationService`, `RequestContext` і `ApplicationEnvelope`; `extra="allow"` дозволяє additive metadata, але namespace/validation PSE наразі не існує.  
   `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/models.py:OKFMetadata:L152-L200`  
   `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/application.py:ApplicationEnvelope:L109-L133`

2. **EXTENSION synthesis:** `ApplicationService.synthesize_session` є єдиним явним session-artifact seam; додаткові PSE references повинні бути application-level fields, а не прямим записом `.power` чи SQLite.  
   `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/application.py:ApplicationService.synthesize_session:L527-L565`

3. **ADAPTER temporal state:** PSE може проєктувати project claims у `MemoryMetadata.supersedes`/`temporal_records`, але не повинен трактувати note temporal resolver як повний project event ledger.  
   `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/index_sync.py:_sync_vault_to_db:L235-L243`  
   `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/temporal.py:load_temporal_records:L87-L135`

4. **ADAPTER graph review:** `relation_candidates` + `approve_candidate`/`reject_candidate` — готова review seam; відсутня Application/CLI/MCP exposure і active-generation integration.  
   `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/experimental/graph_extraction.py:approve_candidate:L258-L269`

5. **REUSE derived search:** PSE notes, якщо валідні OKF, автоматично можуть входити в existing FTS/vector/source projections; ці індекси не можуть бути PSE canonical state.  
   `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/index_sync.py:_sync_vault_to_db:L215-L305`  
   `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/source_projection.py:write_projection:L235-L296`

6. **ADAPTER CLI/MCP:** PSE transport additions мають викликати новий application use case; static boundary уже тестує заборону low-level storage calls.  
   `/root/gemma/projects/.power-framework-3.7.11-worktree/tests/test_mcp_application_boundary.py:test_mcp_mutations_do_not_import_or_call_core_implementation_details:L30-L62`

7. **PROHIBITED duplicate:** PSE не повинен створювати окремий task store, паралельну FTS/vector DB або альтернативний receipt source. Existing task transaction/recovery machinery є task-specific і не замінює PSE ledger.  
   `/root/gemma/projects/.power-framework-3.7.11-worktree/src/power_framework/core/task_store.py:TaskStore._transaction:L365-L432`

---

## Додаткові тести й coverage gaps

- `heal_frontmatter_tool` approval refusal, але не позитивний MCP live-apply/readback:  
  `/root/gemma/projects/.power-framework-3.7.11-worktree/tests/test_mcp_server.py:test_destructive_mcp_tools_require_explicit_approval:L346-L353`
- Underlying healer behavior, backups і failure isolation:  
  `/root/gemma/projects/.power-framework-3.7.11-worktree/tests/test_healer.py:TestHealFrontmatter:L67-L128`  
  `/root/gemma/projects/.power-framework-3.7.11-worktree/tests/test_healer.py:TestHealVault:L130-L201`
- MCP mutation/application boundary:  
  `/root/gemma/projects/.power-framework-3.7.11-worktree/tests/test_mcp_application_boundary.py:test_mcp_mutations_do_not_import_or_call_core_implementation_details:L30-L62`
- Memory replay is tested only for note mutation receipt, not a PSE global event ledger:  
  `/root/gemma/projects/.power-framework-3.7.11-worktree/tests/test_memory_api.py:test_memory_apply_replay_with_same_idempotency_key_is_not_a_duplicate:L45-L57`
- Temporal current/historical filtering:  
  `/root/gemma/projects/.power-framework-3.7.11-worktree/tests/test_searcher.py:test_search_temporal_views_filter_one_shared_corpus:L56-L110`
- Graph candidate review and accepted-relation boundary:  
  `/root/gemma/projects/.power-framework-3.7.11-worktree/tests/test_graph_extraction.py:test_candidate_review_is_deterministic_and_only_approval_creates_relation:L101-L130`
- Synthesis triplet integration test uses explicit `POWER_SEARCH_DB`, so it does not prove default active-generation behavior:  
  `/root/gemma/projects/.power-framework-3.7.11-worktree/tests/test_mcp_server.py:test_synthesize_session_serializes_write_and_stores_candidate_triplets:L948-L970`

Аудит залишався read-only; тести в цій сесії не виконувалися.

---

Проведи read-only forensic audit у `/root/gemma/projects/.power-framework-3.7.11-worktree` лише для dimensions 11–18 місії: web/app.py, web/routes/, web/clients/power.py, web/auth/*; core/capabilities.py, utils.py, cpu_throttling.py, state_migration.py, temporal.py, provenance.py, errors.py, constants.py та потрібні dependencies; pyproject.toml; scripts/verify_*.py; release/evidence/. Перевір authentication/CSRF/rate limits/concurrency, config/env/vault resolution, logging/receipts/telemetry, hardware guard, Python/platform matrix, migrations/schema evolution, release attestation/public surface. Не редагуй файли і не виконуй destructive/network actions. Поверни verified research memo українською: exact path, symbols/signatures, line ranges, contracts, tests, PSE extension points/gaps. Познач відсутність лише після пошуку в actual source.

План: зафіксую протокол і стан робочого дерева, потім зіставлю dimensions 11–18 із фактичними символами, конфігурацією, тестами та release-evidence.  
Працюю read-only: без редагування, мережі, destructive-команд і припущень про відсутність без пошуку у фактичних джерелах; наприкінці дам доказовий memo з шляхами й діапазонами рядків.

Контекст зафіксовано: це WS, аудит локального worktree `feat/power-3.8-project-state-engine`; дерево має лише вже наявний untracked `artifacts/`, його не чіпаю. У brain актуальний релевантний запис — P.O.W.E.R. і сесії 2026-09-01; читаю тільки індекси/вказані нотатки та фактичні файли репозиторію.

# Verified forensic research memo — dimensions 11–18

## 0. Статус аудиту

- **Worktree:** `/root/gemma/projects/.power-framework-3.7.11-worktree`
- **Branch:** `feat/power-3.8-project-state-engine`
- **HEAD:** `af2e3022422b2ee3f249e0b2e0aa08b6ce09450c`
- **HEAD tree:** `7c81158db87a1d804c3c1fd71f8772709316651b`
- **Tag:** `v3.7.11`, annotated object `7dd8f7e441d579b98c3c12f26d2ab5aaf0a8df14`
- **Tag target:** `37c9c93f055c430294ee7c180dd03205c325ca6f`
- `git verify-tag --raw v3.7.11`: криптографічна перевірка пройшла; maintainer primary fingerprint `7AF1EDA195FE29FF093FB1CA2D49E810C7F2527E`.
- Tracked diff відсутній; `git diff --check` пройшов.
- Є лише pre-existing untracked `artifacts/`; його не змінював.
- Мережеві, destructive та mutation actions не виконувалися.
- Scope dimensions підтверджено фактичним mission prompt: `artifacts/project-state/phase-0/opencode_phase0_prompt.md:16-35`.
- Окремого `src/power_framework/project_state/`, generic ledger, RAID/RACI/context-pack модулів не знайдено після пошуку у source tree.
- Окремого `src/power_framework/core/cpu_throttling.py` немає; CPU guard реалізовано у `core/utils.py`.

> Існуючий `artifacts/project-state/phase-0/test_baseline.txt:1-8` повідомляє `1405 passed`, `4 skipped`, `17 deselected`, coverage `82.13%`; це pre-existing evidence, не повторно виконаний тест у цьому read-only аудиті.

---

## 1. Executive verdict

### Сильні verified foundations

1. Web mutation routes проходять через `ApplicationService` → `PowerClient`, без прямого subprocess/MCP/backend bypass.
2. Є HMAC CSRF, signed session cookie, fail-closed credential handling.
3. Proposal/apply, optimistic task revisions, Task event hash-chain та atomic generation publication мають сильні контракти.
4. Release workflow має signed-tag admission, exact-tree binding, SBOM, artifact checksums, attestation та public readback gates.
5. Linux/Python 3.13–3.14 boundary явно задекларований.

### Основні блокери для PSE/Web hardening

| ID | Рівень | Verified gap |
|---|---|---|
| WEB-01 | **P1** | `source.read` дозволяє читати будь-який regular file всередині vault, не лише Markdown; потенційно `.power/*`, proposals, task state, `.env`. |
| WEB-02 | **P1** | Web `ApplicationService.retrieve()` залишає активним `POWER_SEARCH_DB` override; fallback може читати/створювати зовнішню DB. |
| WEB-03 | **P1** | Web GET може матеріалізувати `.power` або навіть відсутній vault через `TaskStore.__init__`. |
| WEB-04 | **P1** | HTTP request ID, session identity та authenticated actor не доходять до core receipts/events; Web actor завжди `"web"`. |
| WEB-05 | **P1** | Explicit semantic/reranked paths можуть викликати `hf_hub_download()` без `POWER_EGRESS_POLICY`; Docker defaults не вмикають offline mode. |
| WEB-06 | **P1** | MPS 50% GPU guard відсутній у source; CPU cap не враховує cgroup/CPU affinity. |
| WEB-07 | **P1/P2** | Task transaction recovery довіряє `rel` з manifest без containment validation; rollback failure пригнічується і transaction backup видаляється. |
| WEB-08 | **P2** | `memory-history.jsonl` логічно append-only, але фізично повністю переписується; немає hash-chain/global ledger. |
| WEB-09 | **P2** | Release validators перевіряють aggregate кількість hashes, а не hash на кожну requirement line. |
| WEB-10 | **P2** | Local `release/evidence/` не містить поточного `3.7.11` public evidence; збережені артефакти переважно `3.7.1` та `3.2–3.4.5`. |

---

# Dimension 11 — Web API & GUI

## Архітектура та symbols

| Файл | Symbols / signatures | Рядки |
|---|---|---:|
| `src/power_framework/web/app.py` | `jinja_csrf_token(context) -> str`, `jinja_is_authenticated(context) -> bool` | 54–70 |
| same | `_maybe_set_csrf_cookie(...) -> None` | 73–84 |
| same | `create_app(settings: Settings \| None = None) -> FastAPI` | 87–271 |
| same | `main() -> None` | 274–298 |
| `web/routes/__init__.py` | fixed router registry | 3–22 |
| `web/clients/power.py` | `PowerClient.__init__(vault_path: Path)` | 20–25 |
| same | read methods `discover`, `get_source_stats`, `list_sources`, `read_source`, `get_graph_projection`, `search` | 27–91 |
| same | Task methods `list_tasks`, `get_task`, `create_task`, `transition_task`, `get_task_events` | 93–180 |
| same | mutation methods `propose`, `apply`, `resolve_decision`, `get_receipts` | 186–243 |
| `web/offload.py` | `run_power_call[R](request, settings, function, /, *args, timeout_seconds=None, **kwargs) -> R` | 21–49 |
| `web/routes/dashboard.py` | `dashboard_view(...)` | 21–51 |
| `web/routes/notes.py` | list/read/edit/propose/apply views | 24–179 |
| `web/routes/search.py` | `_normalize_search_results`, `search_view` | 21–98 |
| `web/routes/graph.py` | `graph_view`, `graph_data_api` | 20–85 |
| `web/routes/tasks.py` | board/new/create/detail/transition/SSE | 29–263 |
| `web/routes/decisions.py` | `decisions_view`, `resolve_decision_action` | 22–66 |
| `web/routes/receipts.py` | `receipts_view` | 20–40 |
| `web/routes/federation.py` | `_get_fleet_topology`, `_probe_node`, HTML/card routes | 55–173 |
| `web/routes/auth.py` | login, language/theme, logout routes | 26–188 |

## Verified contracts

- FastAPI disables Swagger/ReDoc: `app.py:91-97`.
- Static assets mounted at `/static`: `app.py:121-123`.
- Public paths when auth is enabled: `/login`, `/healthz`, `/readiness`, `/set-lang`, `/set-theme`, `/static/*`: `app.py:180-195`.
- All other paths rely on global auth middleware, not route-local authorization dependency.
- Mutation routes use `Depends(validate_csrf)` and `Depends(require_mutation_enabled)`:
  - notes: `notes.py:122-161`;
  - tasks: `tasks.py:88-88`, `tasks.py:154-157`;
  - decisions: `decisions.py:43-46`;
  - logout: `auth.py:180`.
- All blocking core calls are offloaded via `run_power_call`: verified by route source and `tests/web/unit/test_contract_boundaries.py:119-139`.
- HTML security headers: `app.py:201-225`.
- `/healthz` is cheap liveness; `/readiness` reports vault/auth readiness without indexing: `app.py:238-269`.
- A2A is not claimed: federation card explicitly uses `experimental/custom-discovery`: `federation.py:132-173`; tests assert this at `tests/web/contract/test_app_routes.py:259-269`.
- No `get_current_user`, OAuth/JWT, `HTTPBearer`, CORS, TrustedHost or proxy-header auth implementation was found in `web/`.

## Findings

### WEB-01 — arbitrary regular-file read

`src/power_framework/core/source_service.py:382-441`:

- `read_source()` resolves containment;
- but `if direct_target.is_file()` at `:402` accepts `.json`, `.jsonl`, `.env`, arbitrary binary, and `.power/*`;
- Markdown suffix and PARA-directory checks are not applied to the read path.

Web reaches it directly:

- `web/routes/notes.py:67-92`;
- `web/routes/notes.py:96-119`;
- `web/clients/power.py:56-62`.

The stricter writer boundary does enforce Markdown/PARA:

- `core/utils.py:172-215`;
- `core/memory_api.py:68-70`, `317-326`.

**Impact:** `/notes/read` or `/notes/edit` can expose `.power/proposals/*.json`, task snapshots/events, `memory-history.jsonl` or `.env` if located below the configured vault. Existing tests cover only Markdown paths: `tests/web/contract/test_app_routes.py:101-119`.

### WEB-02 — SSE discloses full canonical event payload

`web/routes/tasks.py:221-255` serializes `ev.model_dump()` directly. `TaskEventDTO.payload` is unrestricted `dict[str, Any]`: `application_models.py:183-195`.

Task event payloads include full task snapshots:

- creation: `task_service.py:120-140`;
- transition: `task_service.py:269-293`.

The HTML detail view shows only digest/actor, but SSE returns the full payload. SSE tests check cursor/sequence only: `tests/web/contract/test_read_only_and_e2e.py:264-302`.

### WEB-03 — OpenAPI is not disabled

`create_app()` sets `docs_url=None` and `redoc_url=None`, but does not set `openapi_url=None`: `app.py:91-97`.

Therefore FastAPI’s default `/openapi.json` surface remains configured. With `auth_enabled=True` it falls under private middleware; with `auth_enabled=False` it is exposed.

### WEB-04 — request body limit checks only Content-Length

`app.py:135-157` rejects only when `content-length` exists. Chunked/no-content-length requests proceed to multipart parsing. Form fields have some individual limits, but the parser receives the body before those validations.

Test coverage uses a normal `Content-Length`: `tests/web/contract/test_security_hardening.py:243-264`.

---

# Dimension 12 — Configuration, environment & vault resolution

## Symbols

| File | Contract | Рядки |
|---|---|---:|
| `web/config.py` | `_default_vault_path()` | 26–37 |
| same | `Settings(BaseSettings)` | 40–87 |
| same | cookie-name validator | 89–95 |
| same | `get_global_settings()` | 98–101 |
| same | `get_settings(request)` | 104–109 |
| same | `get_client(request)` | 112–117 |
| same | `require_mutation_enabled(request)` | 120–123 |
| same | duplicate `require_mutation_csrf(request)` | 126–141 |
| `core/utils.py` | `validate_vault_path(...)` | 30–63 |
| same | `resolve_vault_path(...)` | 115–134 |
| same | `resolve_path_in_vault(...)` | 172–215 |
| `core/vault_storage.py` | `ensure_vault_identity`, `read_vault_identity` | 16–87 |
| `core/capabilities.py` | `_environment_variables`, `manifest` | 106–215 |

## Effective configuration

Web settings use `POWER_WEB_` prefix: `config.py:83-87`.

Important fields:

- vault: `vault_path`, `POWER_WEB_VAULT_PATH`;
- host/port: `POWER_WEB_HOST`, `POWER_WEB_PORT`;
- auth: `POWER_WEB_AUTH_ENABLED`;
- secrets: `POWER_WEB_SECRET_KEY`, `POWER_WEB_ADMIN_PASSWORD`, `POWER_WEB_ADMIN_PASSWORD_HASH`;
- cookie flags: `cookie_secure`, `cookie_samesite`;
- execution: upload size, call timeout/concurrency, SSE lifetime/connections;
- `read_only_mode`;
- arbitrary JSON `federation_nodes`.

Docker contract:

- `deploy/web/compose.yaml:18-27`;
- non-root UID/GID, dropped capabilities and read-only root filesystem: `compose.yaml:27-33`;
- `/brain:rw` is canonical mutation mount;
- cache is separate named volume;
- Docker defaults are defined at `Dockerfile:72-85`.

## Findings

### CFG-01 — Web does not use the strict MCP vault resolver

MCP requires explicit `POWER_VAULT_DIR`:

- `mcp/preflight.py:14-22`.

Web instead falls back to:

1. `POWER_WEB_VAULT_PATH`;
2. `POWER_VAULT_DIR`;
3. `/brain` if it exists;
4. `cwd/brain`;
5. current working directory;

`web/config.py:26-37`.

`Settings` itself does not validate existence, directory type, dedicated-root constraint or `.power` symlink. Readiness only checks `is_dir()`: `app.py:243-269`.

### CFG-02 — Web GET constructs a stateful `TaskStore`

`get_client()` creates a new `PowerClient`: `web/config.py:112-117`.

`PowerClient.__init__()` creates `ApplicationService`: `web/clients/power.py:23-25`.

`ApplicationService` creates `TaskService`; `TaskStore.__init__()`:

- creates a missing vault directory: `task_store.py:38-47`;
- creates `.power` through `vault_control_dir(..., create=True)`: `task_store.py:48`;
- `vault_control_dir` materializes the directory: `utils.py:100-112`.

Thus an ordinary Web read may create a missing vault or `.power`, including under `read_only_mode`.

The existing test only asserts that `.power/tasks` is not created after a source read: `tests/test_application_v2.py:82-89`; fixtures already create `.power`.

### CFG-03 — Web search keeps `POWER_SEARCH_DB` compatibility override

`ApplicationService.retrieve()` calls the injected search function without disabling DB override: `application.py:231-255`.

`PowerClient.search()` uses that default: `web/clients/power.py:81-91`.

`search_vault()` defaults `allow_search_db_override=True`: `searcher.py:1308-1342`.

When no active generation exists, the override can cause writable DB initialization/sync from a GET:

- `searcher.py:1415-1442`.

By contrast, `memory_api.get_context()` explicitly disables it: `memory_api.py:45-53`.

### CFG-04 — capability environment inventory is incomplete

`core/capabilities.py:106-134` only AST-scans calls shaped as `os.getenv(...)`.

It misses:

- Pydantic-derived `POWER_WEB_*` fields;
- `os.environ.get(...)` values such as `POWER_LLM_*`;
- direct `os.environ[...]` assignments;
- inferred settings and model-cache variables.

No completeness/error field is emitted when variables are omitted.

### CFG-05 — weak/unvalidated settings

`Settings` has no validators for:

- `secret_key` minimum entropy/length;
- `host` exposure policy;
- `cookie_samesite` allowed values;
- `federation_nodes` structure/count;
- password complexity;
- numeric model/resource env variables.

`require_mutation_csrf()` is unused and inconsistent with canonical CSRF:

- it verifies the user ID returned from the session instead of the raw session token: `config.py:133-139`;
- routes use `validate_csrf`, not this function.

---

# Authentication, CSRF & rate limits

## Authentication

### Session

`SessionManager` uses `itsdangerous.URLSafeTimedSerializer`:

- constructor/salt: `web/auth/session.py:12-16`;
- signed session creation: `:18-20`;
- verification: `:22-32`.

Only `"admin"` is created by the login route: `auth.py:129-143`.

There is no server-side session store, revocation list, audience/role validation or multi-user authorization. The middleware stores only boolean `request.state.is_authenticated`: `app.py:167-178`.

### TTL mismatch

`Settings.session_max_age_seconds` is configurable: `config.py:66-70`.

Middleware calls:

```python
session_mgr.verify_session(cookie)
```

without passing configured TTL: `app.py:171-176`.

`SessionManager.verify_session()` defaults to `86400`: `session.py:22-26`.

Therefore configured values above/below one day are not enforced server-side. Cookie `max_age` is configured, but signed token acceptance remains 24 hours.

### CSRF

Strong HMAC contract:

- token generation: `csrf.py:24-29`;
- constant-time verification: `csrf.py:31-36`;
- session/cookie binding: `csrf.py:39-57`;
- form/header extraction and fail-closed 403: `csrf.py:60-112`.

Login has custom pre-auth CSRF verification: `auth.py:71-89`.

Positive tests:

- `tests/web/unit/test_auth.py:32-43`;
- `tests/web/unit/test_security_auth.py:47-96`;
- `tests/web/contract/test_security_hardening.py:147-180`.

Missing coverage:

- every private route’s auth redirect;
- session TTL setting;
- session revocation after logout;
- malformed signed payload;
- chunked oversized login body;
- hostile cookie duplication.

### Rate limiter

`LoginRateLimiter` is thread-safe within one process:

- state and lock: `rate_limiter.py:13-34`;
- lockout: `:41-96`;
- reset: `:98-111`.

Only login attempts use it: `auth.py:58-130`.

Gaps:

- no Web-wide request rate limiter;
- state is process-local, so multiple Uvicorn workers do not share limits;
- `_records` grows for unique keys;
- `time.time()` is used instead of monotonic time;
- exponential backoff is practically limited because locked requests return before `record_failure()`;
- raw client IP is logged: `auth.py:60`, `:80`.

---

# Dimension 13 — Logging, receipts & telemetry

## Existing primitives

| Primitive | Contract | Рядки |
|---|---|---:|
| HTTP correlation | random `request.state.request_id`, response `X-Request-ID` | `app.py:125-133` |
| public errors | redacted `PublicErrorResponse` | `web/errors.py:22-59` |
| error mapping | stable status/code/message | `web/errors.py:62-132` |
| application context | actor, authority, idempotency, deadline, request ID | `application.py:62-83` |
| application receipt | operation/status/request ID/hash/duration | `application.py:85-106` |
| receipt construction | `_run()` | `application.py:1052-1102` |
| memory receipt | hashes, trace/span, operation, timestamps | `memory_api.py:153-222` |
| task event | actor, sequence, payload digest, previous digest | `task_models.py:162-209` |
| task recovery log | redacted JSONL observations | `task_store.py:473-537` |
| timing | opt-in content-free spans | `timing.py:17-67` |
| external evidence | content-addressed provenance record | `provenance.py:34-312` |

## Major provenance gap

HTTP correlation ID is generated in `app.py:130`, but `PowerClient` creates a new `RequestContext` without using it:

- `PowerClient`: e.g. `:27-30`, `:52`, `:90`, `:135`, `:163`;
- `RequestContext` generates another random ID: `application.py:66-70`.

Additionally:

- Web actor is always `"web"`;
- authenticated `user_id` is not stored in `request.state`;
- `AuditReceipt` has no actor/session/authority field;
- memory receipts have no request ID/actor;
- Task/Decision receipts have actor but no session/request ID.

This makes a Web operation impossible to trace end-to-end from HTTP request → core receipt → task/decision event.

## Receipt coverage gap

`/receipts` calls:

```python
ApplicationService.receipt()
```

- route: `web/routes/receipts.py:20-40`;
- application method: `application.py:752-765`;
- source: `memory_api.read_history()` at `memory_api.py:539-546`.

This displays only `memory-history.jsonl`. It does not aggregate:

- `TaskStore` task events;
- `TaskCompletionReceipt`;
- `DecisionReceipt`;
- application-level `AuditReceipt`;
- recovery log;
- provenance records.

`ApplicationService._audit_hook` is optional: `application.py:192-204`, and Web does not inject one.

## Telemetry gaps

- No `loguru` import exists in `src/`.
- Only CLI configures standard logging: `core/cli.py:1879-1886`.
- Web creates loggers but no package-level handler/format/retention policy.
- `collect_timings()` exists only at `core/timing.py:44-53`; no Web caller was found.
- No `/metrics` or Prometheus/OpenTelemetry endpoint exists in Web source.
- Recovery logging suppresses write failures: `task_store.py:529-537`.
- `memory-history.jsonl` is rewritten wholesale: `memory_api.py:488-495`, not a durable append syscall/hash-chain.

---

# Dimension 14 — Rate limits & concurrency

## Existing controls

- Web call limiter: `app.py:111-115`.
- SSE semaphore: `app.py:111-114`; acquisition/release: `tasks.py:205-207`, `:248-257`.
- Blocking bridge: `offload.py:21-49`.
- Per-vault mutation lock: `mutation.py:69-100`.
- Cross-process file locks: `mutation.py:39-67`.
- Task writer lock: `task_store.py:72-108`.
- Task optimistic concurrency: `task_service.py:181-193`.
- Task idempotent replay: `task_service.py:296-313`.
- Core MCP rate limiters: `power_server.py:164-165`, usage `:342-355`, `:389-405`.

## Findings

### CON-01 — timeout abandons worker, not operation

`run_power_call()` uses:

```python
anyio.to_thread.run_sync(..., abandon_on_cancel=True)
```

`offload.py:35-45`.

The outer request can return `504`, while the synchronous operation continues in the worker. Core deadline checking also happens only after the action completes: `application.py:1052-1069`.

For mutation routes this creates:

- client-visible timeout;
- side effect committed later;
- possible retry/race;
- no cancellation receipt.

Current test covers sleeping timeout only: `tests/web/unit/test_contract_boundaries.py:66-75`, not mutation-after-timeout.

### CON-02 — core `RateLimiter` is not thread-safe

`core/utils.py:439-463` uses an unprotected `defaultdict` and list mutation.

It is used by asynchronous MCP handlers:

- `power_server.py:164-165`;
- `power_server.py:342-348`;
- `power_server.py:389-393`;
- write handlers around `:501-503`, `:857-858`.

Concurrent calls can race around the check/append pair.

### CON-03 — memory transaction uses a different lock plane

Memory apply enters `execute_vault_mutation`: `memory_api.py:264`.

Inside it, `commit_note_change()` directly calls `store._transaction(...)` without `store.lock()`:

- `memory_api.py:169-177`.

Task operations use `.power/tasks/.lock`: `task_store.py:72-108`.

Both transaction types write manifests under `.power/tasks/.tx`. A concurrent task operation can invoke `recover()` while a memory transaction manifest is prepared, because the locks are not unified.

### CON-04 — recovery manifest path trust

`TaskStore._reconcile_tx()` and `_rollback_tx()` construct:

```python
self.vault_dir / t["rel"]
```

without validating `rel` containment:

- `_rollback_tx`: `task_store.py:434-448`;
- `_reconcile_tx`: `task_store.py:450-471`.

A crafted valid transaction manifest can cause unlink/write operations outside the vault during recovery.

### CON-05 — rollback failure is masked

`_transaction()` suppresses rollback exceptions and removes the transaction directory:

- `task_store.py:427-432`.

If rollback fails, the original exception is re-raised, but recovery backups/manifest are deleted. This weakens crash recovery exactly when it is needed.

### CON-06 — federation fan-out is unbounded

`federation_view()` launches one probe per configured node:

- JSON parsing: `federation.py:55-64`;
- arbitrary host/port connection: `:67-83`;
- unbounded `asyncio.gather`: `:115-118`.

There is no node count cap, host allowlist, port validation before `int()` use, or separate probe concurrency limiter.

---

# Dimension 15 — Resource throttling & hardware guards

## CPU

`core/utils.py:507-517`:

```text
max(1, (os.cpu_count() or 4) // 2)
```

`enforce_cpu_throttling_env()` clamps:

- `OMP_NUM_THREADS`;
- `OPENBLAS_NUM_THREADS`;
- `MKL_NUM_THREADS`;
- `VECLIB_MAXIMUM_THREADS`;
- `NUMEXPR_NUM_THREADS`;
- `POWER_EMBED_NUM_THREADS`;

at `utils.py:520-546`.

It is invoked at package import: `src/power_framework/__init__.py:47-48`.

ONNX thread bounds:

- embedding session: `experimental/embeddings.py:704-711`;
- reranker session: `experimental/reranker.py:224-234`;
- ROT thread pool: `experimental/rot_scoring.py:476-484`.

Tests:

- `tests/test_cpu_throttling.py:16-90`.

## Missing requested file

`src/power_framework/core/cpu_throttling.py` was checked directly and through exact glob; it does not exist. The mission path is stale; implementation is in `core/utils.py`.

## GPU/MPS

No `CUDA_MPS_ACTIVE_THREAD_PERCENTAGE`, `CUDA_DEVICE_MAX_CONNECTIONS` or MPS enforcement was found in `src/`.

GPU provider selection and actual binding verification do exist:

- `select_onnx_providers`: `embeddings.py:200-260`;
- `verify_bound_provider`: `embeddings.py:167-197`.

Resource snapshot only reads aggregate GPU memory through local `nvidia-smi`:

- `experimental/benchmark_resources.py:62-100`.

Thus WS’s external 50% MPS/governor policy is not enforced by this repository’s runtime.

## Memory/cgroup gaps

Optional address-space cap exists only in CLI sync, is opt-in and POSIX-dependent:

- `cli.py:491-513`;
- default `POWER_SYNC_VMEM_LIMIT_MB=0` means disabled.

There is no source implementation for:

- cgroup `cpu.max`;
- cgroup memory limit;
- `sched_getaffinity`;
- automatic RSS/VRAM admission control.

`get_cpu_worker_limit()` uses host `os.cpu_count()`, not container quota.

Batch env parsing is unvalidated:

- `POWER_EMBED_BATCH_SIZE`, `POWER_EMBED_COMMIT_EVERY`: `index_sync.py:426-428`;
- invalid/zero values can raise or cause invalid loop/modulo behavior.
- `POWER_EMBED_NUM_THREADS` is converted at import: `embeddings.py:46-48`.

---

# Dimension 16 — Python/platform support matrix

## Verified declarations

- Package requirement: `pyproject.toml:11`.
- Classifiers: `pyproject.toml:16-24`.
- CI Python matrix: `.github/workflows/ci.yml:94-107`.
- Release upgrade matrix: `.github/workflows/release.yml:357-387`.
- Release platform authority: `scripts/release_platforms.py:5-7`.
- Lock requirement: `uv.lock:1-7`.

Current declared boundary:

```text
Supported: Linux, Python >=3.13,<3.15
Deferred indefinitely: macOS, Windows
```

Current docs agree:

- `docs/release-3.7.11.md:21-32`;
- `docs/support-matrix.md:8-15`.

## Platform implementation mismatch

Generic mutation code has a Windows `msvcrt` path:

- `mutation.py:19-67`;
- Windows-safe atomic write branch: `utils.py:233-255`.

But `TaskStore` imports `fcntl` and explicitly raises when unavailable:

- `task_store.py:24-27`;
- `task_store.py:81-88`, `:102-106`.

Therefore Task v2 write/recovery is not actually certified on Windows despite partial Windows branches elsewhere.

## Dependency versions

`pyproject.toml` separates base and optional profiles:

- base runtime: `pyproject.toml:26-31`;
- Web: `:57-69`;
- semantic/rerank/GPU: `:72-92`;
- MCP: `:95-99`.

Locked Web/runtime versions include:

- FastAPI `0.141.1`: `uv.lock:472-486`;
- AnyIO `4.14.2`: `uv.lock:27-37`;
- Jinja2 `3.1.6`: `uv.lock:718-728`;
- itsdangerous `2.2.0`: `uv.lock:709-716`;
- Markdown `3.10.3`: `uv.lock:831-838`;
- MCP `2.1.0`: `uv.lock:904-927`;
- ONNX Runtime `1.28.0`: `uv.lock:1280-1305`;
- ONNX Runtime GPU `1.28.0`: `uv.lock:1307-1324`.

`release/web-runtime.requirements.txt:6-539` is exact/hash-pinned and consumed by Docker.

### Evidence drift

`release/evidence/baselines/v3.4.5.json:10-18` still contains Python `3.11`, `3.12`, `3.13`, `3.14`.

`generate_release_baseline.py` chooses an old baseline template:

- default discovery: `:41-54`;
- copies template and updates selected fields only: `:183-205`.

It does not rewrite the inherited environment Python list. `verify_release_contract.py:345-452` validates release/validation/upgrade fields but does not validate `baseline.environment` against the current support matrix.

This can produce a `3.7.11` final baseline carrying stale Python claims.

---

# Dimension 17 — State migration & schema evolution

## Read-only state migration

`core/state_migration.py`:

- schemas/constants: `:18-20`;
- `StateEntry`: `:22-42`;
- `StateMigrationPlan`: `:44-67`;
- inventory builder: `:70-115`;
- apply hard-stop: `:118-123`;
- path classification/hash: `:126-175`.

CLI exposes only preview:

- `_cmd_migrate_state`: `core/cli.py:650-658`;
- parser: `core/cli.py:1780-1784`.

Contract:

```text
Markdown remains source of truth.
Migration currently inventories only.
Apply is disabled.
```

`apply_state_migration_plan()` always raises `PermissionError`.

## Migration risks

1. `build_state_migration_plan()` validates only `root.is_dir()`: `state_migration.py:77-80`.
2. It scans every file under the root: `:81-88`, including hidden/control/repository files.
3. There is no per-file byte ceiling; a large regular file is read fully at `:131-149`.
4. It can inventory `.env`, `.git`, model/cache and other sensitive files by path/hash.
5. No global migration event, actor, request ID or source revision is stored.
6. No JSON Schema artifact for `StateMigrationPlan` was found.

## Task v1 → v2 migration

Implementation exists only as library methods:

- `migrate_v1_work_packets()`: `task_service.py:393-492`;
- `rollback_v1_migration()`: `:509-535`.

No CLI, MCP or Web route calls either method; source search found only these definitions.

Positive contracts:

- retains original v1 bytes;
- writes content-free manifest;
- is intended idempotent/reversible;
- tests: `tests/test_migration_recovery.py:17-55`, `tests/test_task_service.py:323-342`, `:397-425`.

Gaps:

- migration loop has no outer `TaskStore.lock()`;
- manifest writes use non-atomic `path.write_text()`: `task_service.py:502-507`;
- rollback does not verify stored `source_sha256` against backup bytes;
- rollback trusts manifest `task_id` when constructing paths: `:523-531`;
- rollback deletes migrated tasks directly: `:525-527`;
- exceptions are logged and counted, then migration continues: `:483-492`.

## Database/schema evolution

### Vault identity

- `VAULT_SCHEMA_VERSION = 1`: `vault_storage.py:16`;
- read/create identity: `vault_storage.py:51-87`.

### Search DB

`core/db.py:88-261` creates FTS, temporal, dense, source projection and relation tables.

Only explicit graph migration:

- `_CANDIDATE_MIGRATION`: `db.py:11`;
- relation-column migration: `:19-29`;
- legacy relation reclassification: `:31-85`.

There is no general migration registry/version table for the entire DB and no `PRAGMA user_version`.

### Generation state

- generation schema constant: `generation_index.py:40`;
- additive columns: `:172-208`;
- generation tables: `:178-241`;
- active generation verification: `:433-500`.

### Dense schema

- `DENSE_INDEX_SCHEMA_VERSION = "3"`: `constants.py:71-74`;
- stale/reset behavior: `index_sync.py:104-121`;
- dense manifest write: `index_sync.py:382-399`.

### Temporal model

`MemoryMetadata` provides:

- `kind`;
- `confidence`;
- `valid_from`, `valid_until`;
- `supersedes`;
- `sources`, `evidence`;
- `write_policy`, `sensitivity`;

at `models.py:99-125`.

Temporal resolution:

- statuses/views: `temporal.py:24-46`;
- normalization: `:48-69`;
- projection load: `:87-135`;
- current/historical/conflicted resolution: `:138-216`.

Verified limitation: no `invalidates`, transaction-time, bitemporal interval, global supersession ledger or event-time ordering was found. `datetime` is accepted by `normalize_as_of()` because `datetime` subclasses `date`: `temporal.py:59-68`; this can violate the declared date-only contract.

---

# Provenance and errors

## Provenance

`core/provenance.py`:

- schema and literal states: `:16-27`;
- `ProvenanceRecord`: `:34-122`;
- byte/file capture: `:127-190`;
- verification/staleness: `:193-210`;
- persistent store: `:213-298`;
- readback: `:301-312`.

Positive:

- SHA-256 and byte-size verification;
- timezone requirement;
- bounded file capture;
- non-symlink source check;
- deduplicated blobs;
- atomic blob/record writes.

Gaps:

- no actor/session/request ID;
- no hash-chain/global ordering;
- `source_identity` has no length/redaction policy;
- `egress_policy` is free-form string;
- future timestamps are accepted;
- store directory and parent symlink/race safety is incomplete;
- existing record reuse verifies bytes but not requested source identity equality;
- no Web integration.

## Errors

`core/errors.py` contains only `ConflictError`: `:6-13`.

Web maps built-in exceptions to public codes/messages:

- `web/errors.py:62-88`;
- public HTTP mapping: `:106-132`.

This is safe for detail redaction, but not a complete domain error taxonomy for PSE.

---

# Dimension 18 — Release evidence & attestation

## Verify script inventory

| Script | Main contract | Рядки |
|---|---|---:|
| `scripts/verify_release.py` | native release contract + installer plan | 13–47 |
| `scripts/verify_release_contract.py` | source/tag/baseline/model/dataset/validation/SBOM/platform checks | 197–453, 456–513 |
| `scripts/verify_attestation_provenance.py` | exact SLSA subject, signer, repository, workflow, revision, event, ref, run ID | 305–429, 448–481 |
| `scripts/verify_public_release_bindings.py` | public assets, checksums, manifest, receipt, image digest, attestation subjects | 35–43, 609–857, 860–910 |
| `scripts/verify_benchmark_manifest.py` | JSON schema, model roles, cold/warm measurements, claim references | 35–77, 80–113 |
| `scripts/verify_neural_contract.py` | JUnit non-empty, zero failures/errors/skips | 11–37 |
| `scripts/verify_phase8_evidence.py` | real-vault, synthetic technical and human evidence contracts | 128–258, 293–490, 502–559 |
| `scripts/verify_test2_artifacts.py` | historical TEST-2 artifact completeness and source binding | 13–172 |
| `scripts/verify_upgrade_matrix.py` | Linux upgrade, crash checkpoints, state migration preview | 100–181, 334–398 |

Shared release identity helpers:

- `scripts/release_bindings.py:8-59`.

No dedicated `verify_web_security.py`, `verify_state_migration.py` or `verify_hardware_guard.py` exists in `scripts/verify_*.py`.

## Strong release workflow controls

`.github/workflows/release.yml`:

- signed annotated tag admission and exact remote object binding: `:36-166`;
- validation gates: `:168-356`;
- Linux upgrade matrix: `:357-443`;
- release permissions and publication: `:445-589`;
- package/Web attestations: `:808-840`;
- final public binding verification: `:962-986`;
- immutable tag/publication sequencing: `:1041-1117`;
- release metadata/assets readback: `:1119-1153`;
- public checksums/manifest/OCI verification: `:1156-1199`;
- artifact/Web attestation verification: `:1201-1284`;
- evidence upload: `:1286-1304`.

Current HEAD adds:

- exact-tree signed PR-head admission for unsigned GitHub merge commit;
- certificate identity instead of incomplete signer-workflow argument;
- `$GITHUB_SHA` for workflow attestation source revision.

These changes are visible in the local diff from tag target.

## Current repository evidence

`release/power-release-manifest.json:1-48` is intentionally a candidate template:

- `schema = power.release.manifest.template.v1`;
- `authority = candidate-only`;
- empty artifacts/attestations.

`release/unified-release-plan.json:1-22` defines one repo/package and Docker Web-only profile.

`release/models.lock.json:1-63` contains pinned BGE-M3 and BGE reranker repositories, revisions and file hashes.

`release/evidence/` contains:

- `public-readback-3.7.1.json`;
- `public-native-failure-3.7.1.json`;
- `python-matrix-3.7.1.json`;
- nine baselines from `v3.2.4` through `v3.4.5`;
- schema/README/gitignore.

Verified absence:

- no `release/evidence/3.7.11*`;
- no `release/evidence/**/3.7.10*`;
- no local `dist/*`;
- no `power-native-requirements.txt` in the worktree.

The README explicitly says final manifest is generated in CI `dist/`: `release/evidence/README.md:21-32`.

Therefore local source audit verifies the tag and release-control design, but not the current public GitHub asset bytes or public attestation readback without network access.

## Release validator gaps

### REL-01 — aggregate hash counting

The same pattern appears in:

- `scripts/build_release_manifest.py:48-73`;
- `src/power_framework/core/integrations.py:338-367`;
- `scripts/verify_public_release_bindings.py:426-460`.

They count total hashes and require:

```text
hashes >= requirements
```

rather than requiring every requirement entry to have at least one hash. A malformed lock with one line carrying multiple hashes and another line carrying none can pass this local validator, although pip’s later `--require-hashes` installation should reject it.

Tests cover positive/top-level option cases:

- `tests/test_public_release_bindings.py:52-70`;

but no mixed per-line missing-hash case exists.

### REL-02 — standalone strictness depends on flags

`verify_release_contract.py` defaults:

- `require_tag=False`;
- `require_signed_tag=False`;

at `:197-210`, CLI flags `:467-485`.

`verify_public_release_bindings()` defaults `require_release_provenance=False`: `:609-629`, and can return:

```text
release_provenance_status = not_present_legacy_release
```

at `:844-856`.

The release workflow supplies strict flags, but standalone misuse can validate legacy/non-attested evidence.

### REL-03 — benchmark manifest does not verify artifact bytes

`verify_benchmark_manifest.py:35-77` validates that claims reference known SHA strings, but it does not open artifact paths or recompute their hashes.

### REL-04 — attestation verifier trusts upstream `gh` output

`verify_attestation_provenance.py` structurally matches the JSON returned by `gh attestation verify`; it does not itself verify a cryptographic signature. That is acceptable as a layered design only when `gh` output is trusted and the workflow’s `gh attestation verify` step is mandatory.

### REL-05 — PSE has no release gate/artifact

`REQUIRED_ARTIFACTS` in `verify_public_release_bindings.py:35-43` has no PSE ledger/state/schema artifact.

No PSE terms occur in `release.yml` except unrelated `bootstrap_context_tokens` assertion. PSE state therefore cannot be part of the current public release attestation contract.

---

# PSE extension points and decisions

## Recommended classifications

| Existing surface | Classification | Exact extension point |
|---|---|---|
| Web → core | **REUSE / ADAPTER** | `PowerClient` and `ApplicationService`: `web/clients/power.py:20-247`, `application.py:189-205` |
| Request identity | **EXTENSION** | `RequestContext`: `application.py:62-83`; add session/actor propagation at adapter boundary |
| Application receipts | **EXTENSION** | `AuditReceipt` and `_audit_hook`: `application.py:85-106`, `:192-204`, `:1052-1102` |
| Vault mutation | **REUSE** | `execute_vault_mutation`: `mutation.py:96-100`; do not create a second writer |
| Task state | **REUSE / EXTENSION** | `TaskService`/`TaskStore` and TaskEvent hash chain: `task_service.py:145-294`, `task_store.py:286-318` |
| Temporal state | **EXTENSION** | `MemoryMetadata` and `resolve_temporal_statuses`: `models.py:99-125`, `temporal.py:138-216` |
| External provenance | **EXTENSION** | `ProvenanceRecord`: `provenance.py:34-312` |
| State migration | **REUSE / EXTENSION** | `StateMigrationPlan`: `state_migration.py:22-123` |
| Release proof | **EXTENSION** | add explicit PSE artifact/gate to release manifest, receipt and verifier |

## Scope-limited PSE capability status

| PSE capability | Status | Finding |
|---|---|---|
| Append-only event ledger | **Partial** | Task events are per-task hash-chained, not one global project ledger. |
| Session/actor provenance | **Partial** | Core has actor/request fields, but Web drops session/user/request identity. |
| Temporal validity/supersession | **Partial** | `valid_from/until` and `supersedes` exist; no `invalidates`/bitemporal transaction time. |
| Semantic entity typing | **Missing** | `MemoryKind` is semantic/episodic/procedural/intent, not FACT/DECISION/RISK/etc.; no unified entity type found. |
| Deterministic project-state replay | **Partial** | Task snapshot + events support task replay; no project-wide canonical replay engine. |
| Contradiction/supersession graph | **Partial** | Temporal conflicts exist; no unified project-state contradiction ledger. |
| Automatic agent capture | **Partial** | `LifecycleAdapter` is portable/read-only: `core/lifecycle.py:65-182`; no native session hook or PSE capture path. |
| Privacy/redaction | **Partial** | Public errors and several receipts are redacted; SSE/task payloads, paths and control state are not uniformly metadata-only. |
| Materialized PSE project views | **Missing** | No `project_state`, `meta.json`, RAID/RACI/DoR/DoD materializer found in source. |

## Boundary rule

PSE should **not** introduce:

- a parallel task store;
- a second canonical vault database;
- a Web-local mutation ledger;
- a second release identity model.

PSE should extend existing `TaskStore`/`TaskEvent`, `RequestContext`, `AuditReceipt`, temporal metadata and release evidence contracts while preserving Markdown/Git/`.power` as the canonical boundary.

---

## Read-only validation result

Final filesystem check:

```text
## feat/power-3.8-project-state-engine
?? artifacts/
```

No tracked files were edited, no destructive command was run, no network request was issued, and no secret values were read or emitted.

Попередній memo був обрізаний. Продовж лише пропущену частину dimensions 11–18 після logging/receipt section: concurrency/rate limits, CPU/hardware, support matrix, state migration/schema evolution, release evidence/attestation/public surface; додай точні line ranges, symbols, tests, PSE gaps/extension points. Не повторюй уже видимий текст і не редагуй файли.

## Dimension 14 — Rate limits & concurrency

### Verified symbols/contracts

| Path | Symbol | Lines |
|---|---|---:|
| `src/power_framework/web/app.py` | `app.state.sse_connections`, `app.state.power_call_limiter` | 111–115 |
| `src/power_framework/web/offload.py` | `run_power_call[R](...) -> R` | 21–49 |
| `src/power_framework/web/routes/tasks.py` | `sse_task_events_stream(...)` | 195–263 |
| `src/power_framework/web/auth/rate_limiter.py` | `AttemptRecord`, `LoginRateLimiter` | 13–111 |
| `src/power_framework/core/utils.py` | `RateLimiter` | 439–463 |
| `src/power_framework/core/mutation.py` | `vault_mutation`, `execute_vault_mutation` | 69–100 |
| same | `run_blocking`, `run_vault_mutation` | 102–120 |
| `src/power_framework/core/task_store.py` | `TaskStore.lock()` | 72–108 |
| same | `_transaction`, recovery | 365–537 |

### Verified behavior

- Web blocking calls are bounded by AnyIO `CapacityLimiter`.
- SSE connections use `threading.BoundedSemaphore`; connection lifetime and polling are bounded.
- Same-vault mutations use process-local `RLock` plus cross-process file locking.
- Task transitions use optimistic `expected_revision`.
- Task idempotency replays the original event result rather than appending a duplicate.

### Findings

1. **Timeout does not cancel the underlying operation.**  
   `run_power_call()` uses `abandon_on_cancel=True` at `offload.py:35-45`. A Web request can return timeout while a mutation continues in the worker. Core deadline validation occurs only after completion: `core/application.py:1052-1069`.

2. **Web rate limiting is login-only.**  
   `LoginRateLimiter` is used only by `auth.py:58-130`. Search, source reads, graph, federation and SSE have concurrency limits but no per-client request-rate policy.

3. **Core `RateLimiter` is not thread-safe.**  
   `utils.py:439-463` mutates `_windows` without a lock. It is called by asynchronous MCP handlers, e.g. `mcp/power_server.py:342-348` and `:389-393`.

4. **Memory apply and TaskStore use different lock planes.**  
   `memory_api.py:169-177` invokes `TaskStore._transaction()` directly while holding only `execute_vault_mutation()` at `:264`. Task operations use `.power/tasks/.lock`. Both transaction manifests live under `.power/tasks/.tx`.

5. **Recovery trusts manifest paths.**  
   `_rollback_tx()` and `_reconcile_tx()` use `self.vault_dir / t["rel"]` without revalidating containment: `task_store.py:434-471`.

6. **Rollback failure can destroy recovery evidence.**  
   `_transaction()` suppresses rollback exceptions and removes the transaction directory in `finally`: `task_store.py:427-432`.

### Tests

- Web limiter/timeout: `tests/web/unit/test_contract_boundaries.py:66-102`.
- Login lockout: `tests/web/contract/test_security_hardening.py:88-113`.
- SSE bounds: `tests/web/contract/test_security_hardening.py:243-264`.
- SSE cursor: `tests/web/contract/test_read_only_and_e2e.py:264-302`.
- Cross-process mutation: `tests/test_cross_process_mutation.py:27-75`.
- Task revision/idempotency: `tests/test_task_service.py:195-235`.
- Event-chain tamper detection: `tests/test_task_service.py:238-320`.
- Crash recovery: `tests/test_crash_recovery_task.py:46-156`.

Missing tests: mutation after Web timeout, concurrent memory/task transactions, malicious recovery manifest paths, multi-process rate-limit behavior and rate-limiter races.

### PSE extension point

Reuse `execute_vault_mutation()`, `TaskStore.lock()` and Task event idempotency. Do not add a parallel PSE writer. First requirement is a unified lock/transaction boundary for task, memory and PSE ledger artifacts.

---

## Dimension 15 — CPU/resource throttling & hardware guards

### Verified symbols/contracts

| Path | Symbol | Lines |
|---|---|---:|
| `src/power_framework/core/utils.py` | `get_cpu_worker_limit(max_cap: int \| None = None) -> int` | 507–517 |
| same | `enforce_cpu_throttling_env() -> None` | 520–546 |
| `src/power_framework/__init__.py` | import-time enforcement | 47–48 |
| `src/power_framework/experimental/embeddings.py` | `EMBED_NUM_THREADS` | 44–48 |
| same | `select_onnx_providers(...)` | 200–260 |
| same | `verify_bound_provider(...)` | 167–197 |
| same | BGE ONNX session setup | 641–723 |
| `src/power_framework/experimental/reranker.py` | ONNX session/thread setup | 141–245 |
| same | `get_reranker()` | 366–388 |
| `src/power_framework/experimental/rot_scoring.py` | bounded `ThreadPoolExecutor` | 476–484 |
| `src/power_framework/core/cli.py` | optional `RLIMIT_AS` cap | 491–513 |
| `src/power_framework/experimental/benchmark_resources.py` | RSS/GPU snapshot | 62–100 |

### Verified behavior

- CPU worker limit is `max(1, cpu_count // 2)`.
- OpenMP/BLAS/MKL/NumExpr/embedding thread env vars are clamped.
- ONNX `intra_op_num_threads` is bounded and `inter_op_num_threads=1`.
- Explicit ONNX provider mismatch fails closed.
- Optional CLI address-space limit uses `POWER_SYNC_VMEM_LIMIT_MB`, default disabled.
- `nvidia-smi` is used only for benchmark GPU-memory telemetry.

### Findings

1. `src/power_framework/core/cpu_throttling.py` does not exist. The mission path is stale; implementation is in `core/utils.py`.

2. No `CUDA_MPS_ACTIVE_THREAD_PERCENTAGE`, `CUDA_DEVICE_MAX_CONNECTIONS` or repository-level MPS guard exists in `src/`.

3. CPU limit uses host `os.cpu_count()` and does not inspect cgroup quota, cpuset or `sched_getaffinity`.

4. Memory limit is opt-in and CLI-only. Web and MCP paths do not apply `RLIMIT_AS`.

5. `POWER_EMBED_NUM_THREADS` is converted at module import: `embeddings.py:46-48`; malformed values can abort import.

6. `POWER_EMBED_BATCH_SIZE` and `POWER_EMBED_COMMIT_EVERY` are parsed without validation: `index_sync.py:426-428`. Zero/negative values can produce invalid loop or modulo behavior.

7. `BGEM3OnnxManager` and `BGEM3Reranker` can load model snapshots through Hugging Face without calling `require_remote_egress()`:
   - embedding: `embeddings.py:671-688`;
   - reranker: `reranker.py:163-205`.

### Tests

- CPU scaling/env clamping: `tests/test_cpu_throttling.py:16-90`.
- Provider selection/binding: `tests/test_embeddings.py:53-328`.
- Reranker pin/default/license gates: `tests/test_reranker.py:186-225`.

No tests cover MPS, cgroup-aware limits, Web memory caps, invalid batch env values or model-download egress policy.

### PSE extension point

PSE background work should consume the existing CPU limit and provider-binding functions, while emitting resource-budget fields in its receipts. A separate hard-coded GPU policy should not be duplicated inside PSE; it needs one shared runtime budget interface.

---

## Dimension 16 — Python/platform support matrix

### Verified declarations

- Python contract: `pyproject.toml:11-24` → `>=3.13,<3.15`.
- CI Python matrix: `.github/workflows/ci.yml:94-107` → 3.13 and 3.14.
- Release upgrade runner: `.github/workflows/release.yml:357-387` → Ubuntu only.
- Release platform constants: `scripts/release_platforms.py:5-7`:
  - supported: `linux`;
  - deferred: `macos`, `windows`.
- Lock metadata: `uv.lock:1-7`.
- Documentation boundary: `docs/support-matrix.md:8-15`.

### Platform gap

`core/mutation.py` contains an `msvcrt` branch at `:19-67`, and `utils.py:233-255` contains a Windows atomic-write path. However, `TaskStore` depends on `fcntl`:

- import/fallback: `task_store.py:24-27`;
- lock failure when unavailable: `task_store.py:81-88`, `:102-106`.

Therefore Windows is not a certified Task v2 write/recovery platform despite partial portability code.

### Evidence/test observations

- `tests/test_ci_policy.py:31-66` checks Linux-only CI and the 3.13/3.14 contract. Its function name still says “starts at 3.11”, while assertions require 3.13+.
- `tests/test_upgrade_matrix.py:46-54` explicitly verifies that macOS/Windows are deferred.
- Existing `release/evidence/python-matrix-3.7.1.json:4-35` is historical and not a 3.7.11 matrix.

### PSE extension point

PSE must inherit the current release boundary: Linux + Python 3.13/3.14 only. Any Windows/macOS claim requires a separate runner, migration, locking and rollback matrix; Python wheel availability alone is insufficient.

---

## Dimension 17 — State migration & schema evolution

### Read-only state migration

`src/power_framework/core/state_migration.py`:

- schema/constants: `:18-20`;
- `StateEntry`: `:22-42`;
- `StateMigrationPlan`: `:44-67`;
- plan construction: `:70-115`;
- disabled apply: `:118-123`;
- path classification/tree hashing: `:126-175`.

CLI exposes only inventory:

- `_cmd_migrate_state`: `core/cli.py:650-658`;
- parser registration: `core/cli.py:1780-1784`.

### Migration findings

1. `build_state_migration_plan()` checks only `root.is_dir()` at `:77-80`; it does not use `validate_vault_path()`.
2. It scans all descendants at `:81-88`, including hidden/control/repository files.
3. `_entry_for_path()` reads each regular file fully at `:131-149`; there is no per-file byte limit.
4. The plan contains hashes and paths but no actor, session ID, source revision or durable event ID.
5. `apply_state_migration_plan()` is permanently fail-closed; no PSE migration is executable through this boundary.

### Task v1 → v2 migration

Implementation:

- `TaskService.migrate_v1_work_packets()`: `task_service.py:393-492`;
- `rollback_v1_migration()`: `:509-535`.

Positive tests:

- `tests/test_migration_recovery.py:17-55`;
- `tests/test_task_service.py:323-342`, `:397-425`.

Gaps:

- migration manifest write is non-atomic: `task_service.py:502-507`;
- no outer lock around the migration loop;
- backup/source SHA is recorded but not verified during rollback;
- rollback trusts manifest task IDs when constructing paths: `:523-531`;
- rollback deletes tasks directly: `:525-527`;
- no CLI/MCP/Web registration was found for either migration method.

### Database schema evolution

| Schema | Evidence |
|---|---|
| Vault identity v1 | `vault_storage.py:16`, `:51-87` |
| Graph migration `m1.2-reclassify-legacy-heuristic-relations` | `db.py:11-85` |
| Main SQLite tables | `db.py:88-261` |
| Generation store v2 and additive columns | `generation_index.py:40-43`, `:172-241` |
| Active generation verification | `generation_index.py:433-500` |
| Source projection schema `"1"` | `source_projection.py:287-295` |
| Dense index schema `"3"` | `constants.py:71-74` |
| Dense stale/reset handling | `index_sync.py:104-121`, `:290-305` |

There is no general schema registry or `PRAGMA user_version` migration mechanism. Evolution is distributed across `CREATE TABLE IF NOT EXISTS`, selected `ALTER TABLE` calls and independent schema constants.

### Temporal model

`MemoryMetadata` supports `valid_from`, `valid_until`, `supersedes`, `sources`, `evidence`, `write_policy` and `sensitivity`: `models.py:99-125`.

Temporal status resolution:

- enums/record: `temporal.py:24-46`;
- normalization: `:48-69`;
- indexed-record loading: `:87-135`;
- resolution/conflict logic: `:138-216`.

No `invalidates`, transaction-time, bitemporal model or global supersession ledger was found.

### Tests

- state plan: `tests/test_state_migration.py:20-54`;
- v1 migration rollback: `tests/test_migration_recovery.py:17-55`;
- temporal contract: `tests/test_memory_contract.py:108-163`;
- temporal projection refresh: `tests/test_memory_contract.py:166-202`;
- generation recovery/publication: `tests/test_generation_index.py` and `tests/test_crash_recovery_task.py:46-156`.

### PSE extension point

Use `StateMigrationPlan` as a read-only preflight, but persist PSE state only after a separately versioned migration contract is accepted. Reuse TaskStore’s event/hash-chain and existing vault mutation lock; do not introduce a parallel migration database.

---

## Dimension 18 — Release evidence, attestation & public surface

### Verify-script contracts

| Script | Symbols/contract | Lines |
|---|---|---:|
| `scripts/verify_release.py` | `main()`; native contract + installer plan | 13–47 |
| `scripts/verify_release_contract.py` | `validate_release_contract(...)`, `main()` | 197–453, 456–513 |
| `scripts/verify_attestation_provenance.py` | `verify_attestation_payload`, `verify_attestation_file`, `main` | 305–429, 396–429, 448–481 |
| `scripts/verify_public_release_bindings.py` | `REQUIRED_ARTIFACTS`, `verify_public_release_bindings`, `main` | 35–43, 609–857, 860–910 |
| `scripts/verify_benchmark_manifest.py` | `validate_manifest`, `main` | 35–77, 80–113 |
| `scripts/verify_neural_contract.py` | `verify_report`, `main` | 11–37 |
| `scripts/verify_phase8_evidence.py` | real/technical/full evidence validators | 128–258, 293–490, 502–559 |
| `scripts/verify_test2_artifacts.py` | historical TEST-2 `REQUIRED` set and `main` | 13–172 |
| `scripts/verify_upgrade_matrix.py` | `build_matrix`, `build_interrupted_upgrade_matrix`, `main` | 100–181, 334–398 |

### Strong workflow gates

`.github/workflows/release.yml` verifies:

- signed annotated tag and exact remote target: `:36-166`;
- validation and pending mandatory gates: `:168-356`;
- Linux upgrade aggregate: `:357-443`;
- exact release manifest/receipt/checksums before publication: `:842-986`;
- release creation and tag readback: `:1041-1153`;
- public asset/OCI binding: `:1156-1199`;
- package/Web attestations and exact workflow identity: `:1201-1284`.

The current control-plane diff from the tag target changes:

- unsigned GitHub merge admission to exact-tree signed PR-head admission;
- `--signer-workflow` to full certificate identity;
- attestation source revision to `$GITHUB_SHA`.

### Local evidence state

- Candidate template: `release/power-release-manifest.json:1-48`.
- Unified release plan: `release/unified-release-plan.json:1-22`.
- Pinned model metadata: `release/models.lock.json:1-63`.
- Evidence policy: `release/evidence/README.md:21-32`, `:73-112`.
- Historical public readback: `release/evidence/public-readback-3.7.1.json:1-50`.
- Historical native failure evidence: `release/evidence/public-native-failure-3.7.1.json:1-38`.
- Historical Python matrix: `release/evidence/python-matrix-3.7.1.json:1-36`.
- Baseline files are only `v3.2.4` through `v3.4.5`.
- No `release/evidence/3.7.11*` and no local `dist/*` were found.

The repository intentionally generates final 3.7.11 assets under CI `dist/`; local checkout alone cannot prove current public bytes.

### Validator gaps

1. **Per-line hash validation is aggregate.**  
   The same condition appears in:
   - `scripts/build_release_manifest.py:48-73`;
   - `core/integrations.py:338-367`;
   - `scripts/verify_public_release_bindings.py:426-460`.

   They require total `hashes >= requirements`, not one hash for each requirement entry.

2. **Standalone strictness is optional.**
   - `verify_release_contract.py` defaults `require_tag=False`, `require_signed_tag=False`: `:197-210`, CLI flags `:467-485`.
   - `verify_public_release_bindings()` defaults `require_release_provenance=False`: `:609-629`.
   - Legacy result is explicitly possible: `:844-856`.

   The workflow supplies strict flags, but the standalone tools do not enforce them by default.

3. **Benchmark artifact bytes are not recomputed.**  
   `verify_benchmark_manifest.py:35-77` verifies referenced SHA strings but does not open artifact paths and compare bytes.

4. **PSE is absent from the release contract.**  
   `REQUIRED_ARTIFACTS` is fixed to package/Web/profile artifacts at `verify_public_release_bindings.py:35-43`. A PSE ledger/schema/receipt would currently require explicit manifest and verifier changes.

5. **Final baseline can inherit stale environment metadata.**  
   `generate_release_baseline.py:41-54`, `:183-205` copies the old `v3.4.5` template. Its environment claims Python 3.11–3.14 at `release/evidence/baselines/v3.4.5.json:10-18`, while current release support starts at 3.13. `verify_release_contract.py:345-452` does not reconcile that field.

### Tests

- Public bindings: `tests/test_public_release_bindings.py:52-450`.
- Attestation policy: `tests/test_attestation_provenance.py:104-225`.
- Baseline generation/verification: `tests/test_release_baseline.py:23-563`.
- Release receipt: `tests/test_release_receipt.py:18-167`.
- Upgrade matrix: `tests/test_upgrade_matrix.py:11-97`.
- Phase 8 evidence: `tests/test_phase8_evidence.py:102-354`.
- CI/release policy: `tests/test_ci_policy.py:69-585`.
- No dedicated test was found for `verify_release.py` or `verify_test2_artifacts.py`.

### PSE extension point

PSE release integration should add:

1. versioned PSE schema and materialized-state artifact;
2. content-free PSE receipt bound to source commit/tree and state hash;
3. explicit release-gate ID;
4. package/Web or dedicated PSE attestation subject;
5. public verifier binding for the exact PSE artifact.

Until then, PSE state remains outside the attested public surface.
