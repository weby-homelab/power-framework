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
- `audit_hook`: extension point для content-free PSE event attribution.
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
- Existing fields usable for adapter: `vault_id`, `tenant_id`, `kind`, `scope`, `dependencies`, `open_gates`, `external_refs`, `artifact_refs`, `completion_policy`.
- `TaskEvent` — candidate source for PSE event ledger, але потребує extension для correlation/session/causation.
- `revision` + `expected_revision` — base для deterministic optimistic concurrency.
- `TaskCompletionReceipt` — base для DoD evidence adapter.

## Gaps

1. **Немає project-level lifecycle engine**  
   Task states не дорівнюють PSE phases `DISCOVERY → PLANNING → EXECUTION → MONITORING → CLOSING → CLOSED`. Немає project ID, phase gates або DoR/DoD engine.

2. **Немає deterministic state replay API**  
   Current state читається з mutable snapshot (`task_store.py:232-241`). Немає функції, яка відновлює `PowerTask` виключно з event journal і перевіряє snapshot проти replay.

3. **Event hash chain неповний**  
   `canonical_payload_digest` хешує лише payload (`task_models.py:206-209`). `actor`, `event_type`, `event_id`, `created_at` не входять у digest і не захищені від тихої зміни.

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