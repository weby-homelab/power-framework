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