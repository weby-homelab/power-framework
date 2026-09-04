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