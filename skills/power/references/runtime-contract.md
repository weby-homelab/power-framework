# P.O.W.E.R. Runtime Contract

Версіонований виконуваний контракт бази знань P.O.W.E.R. Додаток до
[SKILL.md](../SKILL.md): тут описані фактичний CLI/MCP інвентар та
sync/doctor правила. Авторитетна правда — `power doctor <path> --json`.

## Runtime version

`v3.4.5` — runtime contract: **20 CLI commands** + **20 MCP tools** (FastMCP 3.x).

## CLI (20 команд)

1. `power init <path>` — створити структуру vault
2. `power lint <path>` — перевірка метаданих, посилань, orphan
3. `power index <path> [--strict]` — генерація ієрархічного каталогу
4. `power ingest <path>` — створення нотатки з OKF метаданими
5. `power import <source> --into <folder>` — preflight-імпорт дерева Markdown
6. `power search <path> <query>` — пошук (`semantic` за замовчуванням)
7. `power cache list|prune [--no-dry-run] [--include-unknown]` — аудит і очищення cache namespace
8. `power memory <sub> <path>` — керована транзакційна пам'ять
9. `power handoff <create|list|show|resume|checkpoint|input-required|complete|fail|cancel>` — durable cross-agent work packet
10. `power sync <path> [--fts-only] [--accept-dense-loss] [--strict|--allow-partial]` — побудова індексу пошуку
11. `power rot <path> [--extended]` — ROT аудит (дублікати, застарілі, тривіальні)
12. `power archive <path> [--dry-run|--no-dry-run]` — архівування застарілих нотаток
13. `power status [<path>]` — панель стану vault
14. `power cron <path>` — автоматичне обслуговування (lint + index + rot)
15. `power heal <path>` — автовиправлення frontmatter
16. `power markdown-check <path>` — перевірка якості Markdown
17. `power suggest-related <path>` — пропозиції зв'язків Graph RAG
18. `power synthesize <path>` — підсумкова нотатка сесії
19. `power rename <path> --old <old> --new <new>` — перейменування з оновленням зв'язків
20. `power doctor [<path>] [--json]` — read-only діагностика runtime, ONNX provider, індексу та ledger виключених нотаток

## MCP Tools (20) — FastMCP 3.x

- Discovery: `get_server_info` — versioned runtime, configured vault, coverage,
  and embedding configuration; `probe_provider=true` is an explicit no-download
  provider-binding probe.
- Індекси й каталог: `generate_index`, `read_sub_index`, `ensure_sub_index`
- Запис: `ingest_note`, `synthesize_session`
- Пошук: `search_vault_tool`, `sync_vault`, `suggest_related_tool`
- Здоров'я: `lint_vault`, `heal_frontmatter_tool`, `check_markdown_tool`
- Обслуговування: `rot_audit`, `archive_notes`
- Керована пам'ять: `get_memory_context`, `propose_memory_change`,
  `apply_memory_change`, `validate_memory_state`, `read_memory_history`
- Handoff: `handoff_work` — content-free Markdown packet, checkpoints,
  resume/cancel/input-required semantics та idempotency keys

`get_server_info` is the MCP equivalent of the CLI doctor discovery contract.
Its default call is lightweight and does not load ONNX Runtime, open a model
session, create cache state, or access the network. A configured or listed
provider is never treated as an active binding; use `probe_provider=true` when
an actual no-download session binding receipt is required.

**Канонічний запис замикає пошук.** `ingest_note`, `synthesize_session` та
`apply_memory_change` в одному transaction workflow оновлюють note, index,
blocking lint, search generation і receipt. Окремий `sync_vault` потрібен для
імпорту, вже змінених зовнішнім способом нотаток або явного dense rebuild.

**Керована mutation-транзакція замкнена.** `power memory apply` та
`apply_memory_change` після явного схвалення виконують в одному fail-closed
workflow: перевірка OKF, запис note, ієрархічний index, blocking lint, пошукова
generation і content-free receipt. При помилці index/lint/sync/receipt note,
каталоги, history та активна пошукова projection відновлюються. На vault з
активною dense projection оновлюється semantic generation; без неї публікується
FTS generation і receipt має `search_mode=fts`.

`propose_memory_change` спочатку валідовує post-image і зберігає його в
`.power/proposals/<proposal_id>.json`. Це окремий керований ledger: proposal
можна переглядати й схвалювати, але він не пише target note, catalog або search.
`apply_memory_change` приймає лише payload, що відповідає durable record.
Повторний apply з тим самим `idempotency_key` повертає попередній receipt без
дублювання note або history entry. Receipt має `receipt_schema`, `trace_id`,
`span_id`, `status` і `duration_ms`; усі поля залишаються content-free.

`handoff_work` змінює лише packet state і immutable checkpoints; він ніколи не
виконує `next_action`. Retrieved note text є untrusted data і не підвищує
authority. Maintenance profile проходить `detect → dry-run → repair → verify →
receipt`, а repair потребує explicit approval.

## Sync contract

`power sync` будує активну генерацію пошуку атомарно:

```text
power sync PATH [--fts-only] [--force] [--strict | --allow-partial] [--accept-dense-loss]
```

- `--fts-only` — лише FTS-індекс без ембеддінгів.
- `--accept-dense-loss` — дозволяє `--fts-only` замінити існуючий dense-індекс;
  без цього прапора такий запуск відхиляється (fail-closed).
- `--strict` — fail-closed coverage (non-zero при виключеннях).
- `--allow-partial` — прийняти виключені нотатки з попередженням; mutually
  exclusive з `--strict`.
- `--force` — повний dense rebuild (наприклад, після зміни моделі/dimension).

`--fts-only` публікує генерацію з нулем chunks; якщо джерела змінилися, вона
суперседить dense-генерацію і всі dense-режими пошуку падають. Тому `--fts-only`
відхиляється на vault з активним dense-індексом без явного `--accept-dense-loss`.

## Index / lint / doctor rules

- `power index <path> [--strict]` — рекурсивна генерація `index.md`, `_index.md`
  та `_index-N.md` (кожна сторінка каталогу ≤32 KiB).
- `power lint <path>` — перевірка OKF-метаданих, битих лінків та orphan-нотаток.
- `power doctor [<path>] [--json]` — read-only діагностика. Report має
  `read_only=true` і `network_access=false`, включає повний ledger
  `excluded_notes` та стабільні issue codes для агентів і CI.
- MCP `get_server_info` — той самий versioned doctor JSON для довгоживучого
  агента; за замовчуванням discovery не пробує model/provider, а
  `probe_provider=true` явно запитує no-download binding probe.

## Models / environment

- Embedder: canonical `bge-m3` (BGE-M3 ONNX, 1024 dim) via direct ONNX Runtime;
  провайдер змінюється через `POWER_EMBED_PROVIDER`; `fastembed`/MiniLM лишається
  полегшеним opt-in fallback.
- Reranker: `onnx-community/bge-reranker-v2-m3-ONNX` (SHA-pinned, Apache-2.0);
  `jinaai/jina-reranker-v2-base-multilingual` (CC-BY-NC) — явний opt-in.
- Search default: `semantic`; канонічні режими та registry — у `power doctor`.
- MCP entry-point: `python -m power_framework.mcp`; `POWER_VAULT_DIR` обов'язковий
  і задає єдиний доступний vault.
- Device: `POWER_EMBED_DEVICE` / `POWER_RERANKER_DEVICE`
  (`auto`, `cpu`, `cuda`, `rocm`, `directml`).
- Resource control: `POWER_EMBED_BATCH_SIZE`, `POWER_EMBED_NUM_THREADS`,
  `POWER_EMBED_COMMIT_EVERY`, `POWER_SYNC_VMEM_LIMIT_MB`.
- Повний environment contract (`environment.variables`) — у `power doctor --json`.
