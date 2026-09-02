---
type: Resource
title: "Міграція для AI-агента: будь-яка Markdown-база знань у P.O.W.E.R. v3.7.11"
description: "Fail-closed manifest-driven протокол міграції наявної Markdown-бази знань у перевірений P.O.W.E.R. vault без зміни джерела."
tags: [power, migration, guide, ai-agents, safety, verification]
timestamp: 2026-08-17T12:00:00+03:00
---

# Міграція для AI-агента: будь-яка Markdown-база знань у P.O.W.E.R. v3.7.11

Цей гід є execution contract для будь-якого AI-агента з доступом до файлової
системи. Він переносить Markdown або Obsidian knowledge base у канонічну
структуру P.O.W.E.R. зі збереженням source content, attachments, provenance і
rollback path.

Для нового порожнього vault використовуйте
[«Початок роботи»](getting-started.ua.md). Для runtime setup на Windows 11 25H2
спочатку виконайте [Windows-гід](windows-11-installation.ua.md).

Цей гід стосується релізу `v3.7.11`. Обирайте гід чистої
установки, коли destination порожній. Обирайте цей гід, коли потрібно зберегти
будь-яку наявну нотатку, attachment або configuration. Ніколи не запускайте
`power init` усередині наявної бази знань.

## Індекс інструкцій репозиторію

Перед зміною даних агент має прочитати релевантні документи:

1. [Чиста установка](getting-started.ua.md) — isolated runtime, empty vault,
   перша нотатка, validation, FTS і MCP preflight.
2. Цей migration guide — discovery, backup, manifest, transformation,
   canonical placement, link repair і acceptance gates.
3. [Windows 11 25H2](windows-11-installation.ua.md) — точні PowerShell-шляхи,
   Visual C++ requirement і target-host checks.
4. [CLI reference](cli.md) і [MCP server contract](mcp-server.md) — актуальні
   команди, параметри, rate limits і security boundaries.

## Що означає «міграція будь-якої бази знань»

- P.A.R.A., C.O.D.E., GTD, Zettelkasten, LYT, Johnny.Decimal, flat folders та
  hybrid trees підтримуються як **класифікації джерела**.
- Destination використовує канонічні top-level folders P.O.W.E.R., щоб
  hierarchical index і 20 MCP tools мали задокументовану поведінку.
- Не-Markdown система має спочатку експортувати нотатки у Markdown, а
  attachments — у файли. Vendor database extraction не реалізовано в CLI.
- Невідомі frontmatter fields можна зберегти, але required OKF fields мають
  пройти validation.
- Source ніколи не мігрується in place. Він залишається незмінним до окремого
  рішення користувача щодо retention.

## Реальна межа інструментів

- `power init` приймає лише новий або порожній каталог.
- `power index` каталогізує `00_Inbox`, `01_Projects`, `02_Areas`,
  `03_Resources`, `04_Archive`, `06_Daily_Logs` і `PROTOCOLS`.
- MCP `ingest_note` пише лише у дозволені P.A.R.A. folders, має rate limit,
  регенерує index, дописує `log.md` та запускає lint.
- MCP `read_sub_index` і `ensure_sub_index` приймають канонічні P.A.R.A.
  categories, а не довільні source folders.
- CLI `power ingest` створює нову нотатку, але не імпортує body наявної. Для
  bounded batch import використовуйте `power import`: це єдина команда, яка
  приймає source directory і формує preflight report.
- `power import` сканує лише Markdown-файли. Він не копіює attachments,
  configuration files або vendor databases; інвентаризуйте й копіюйте їх у
  Фазі 2 та Фазі 4 з окремими hash-перевірками.
- `power heal` виправляє missing/invalid frontmatter fields, але не класифікує
  довільні top-level folders, не ремонтує wikilinks і не викликає LLM.
- `power rename` за замовчуванням працює як dry run і оновлює paths у metadata
  `related`. Він не гарантує повний rewrite кожного Markdown/Obsidian link.

Саме тому протокол використовує staging vault і migration manifest, а не
видає одну команду за lossless migration.

## Версійовані executable facts

Цей гід перевірено проти contract релізу `v3.7.11`. CI звіряє ці факти з
executable capability manifest, щоб агент не успадковував старий migration
recipe:

- поточна surface — 26 top-level CLI commands і 20 MCP tools;
- режим пошуку за замовчуванням — `auto`; він використовує verified dense лише
  коли runtime готовий, інакше повертає labelled FTS; `semantic` та `reranked` є
  explicit opt-in;
- database і cache paths належать runtime. Для active paths і state використовуйте
  `power doctor DESTINATION --json`; не hard-code-ьте vault-local database
  filename;
- `power heal` виправляє frontmatter, але не ремонтує wikilinks. Для foreign
  frontmatter shapes `power import --policy quarantine` зберігає values як
  `x-status` або `x-related` до strict validation gate;
- VRAM, latency і dense/reranked readiness — evidence конкретного host, а не
  фіксована обіцянка. Записуйте `power doctor` і sync result для actual host.

### Обмежений fast path імпорту

Якщо destination folder і mapping імен уже відомі, `power import` дає
виконуваний preflight без зміни source:

```bash
power import /absolute/path/to/source --into 03_Resources \
  --path /absolute/path/to/vault --policy quarantine --dry-run
```

Політика `strict` за замовчуванням відхиляє note, якщо відоме поле має
foreign value. Явна `quarantine` переносить foreign `status` у `x-status`, а
foreign shape `related` — у `x-related`, зберігаючи оригінальне значення та
Markdown body. `type`, malformed YAML/frontmatter та інші schema failures
залишаються excluded. Звіт до будь-якого write показує scanned, importable,
quarantined, unchanged, excluded, collision і field-level counts.

Після перевірки звіту застосуйте імпорт:

```bash
power import /absolute/path/to/source --into 03_Resources \
  --path /absolute/path/to/vault --policy quarantine
power index /absolute/path/to/vault --strict
power search /absolute/path/to/vault "known phrase" --mode fts
```

`--allow-partial` використовуйте лише коли названі exclusions прийнятні.
Source залишається незмінним; destination collision ніколи не перезаписується.

Цей fast path не є повною міграцією методології. Він зберігає source-relative
Markdown tree під однією обраною canonical folder. Якщо нотаткам потрібні
classification, filename mapping, link rewrites, обробка attachments або
rollback record, використовуйте шестифазний протокол.

## Шестифазний протокол

1. Авторизація й незмінний snapshot джерела
2. Інвентаризація та classification manifest
3. Ініціалізація destination і staged transformation
4. Attachments, links і graph relations
5. Executable validation та reconciliation
6. Cutover, rollback record і maintenance

Не пропускайте фазу. Успіх пізнішого gate не компенсує відсутній попередній.

---

## Фаза 1: Авторизація й незмінний snapshot джерела

### 1.1 Визначте точні шляхи

Запишіть абсолютні шляхи:

- `SOURCE` — наявна база знань;
- `DESTINATION` — новий sibling directory;
- `BACKUP` — snapshot поза source і destination;
- `WORK` — manifests, reports і тимчасові transformed copies.

Відхиліть план, якщо шлях порожній, дорівнює `/`, є home directory або ancestor
іншої цілі. Не використовуйте unresolved environment variables чи broad globs
для delete/overwrite operations.

### 1.2 Зафіксуйте стан source

До будь-яких змін запишіть:

- UTC timestamp, host, OS і P.O.W.E.R. version;
- count і total bytes за extension;
- Git commit/status, якщо source є Git repository;
- unreadable files, symlinks, duplicate relative paths і case-only filename
  collisions, особливо перед перенесенням на Windows;
- excluded/generated directories: `.git`, `.obsidian`, `.venv`,
  `node_modules`, caches і наявні search databases.

### 1.3 Створіть і перевірте backup

Використайте filesystem snapshot або archive/copy, відповідний хосту. Backup
має бути поза source tree і не повинен захоплювати secrets, виключені scope.

Verification вимагає:

- exit code backup-команди `0`;
- backup можна прочитати, перелічити або змонтувати;
- source і backup inventories збігаються для всіх authorized files;
- SHA-256 збігаються для attachments і original Markdown bytes.

Не починайте Фазу 2 з неперевіреним backup. Не кладіть archive у vault, де він
може потрапити в index або Git.

**Receipt Фази 1:** exact paths, source Git state, inventory totals, backup
location, verification command, exit code і digest/count comparison.

---

## Фаза 2: Інвентаризація та classification manifest

### 2.1 Побудуйте повний inventory

Без редагування зафіксуйте:

- кожний Markdown file: relative path, size, SHA-256;
- кожний attachment: relative path, size, SHA-256;
- encoding/BOM і line-ending anomalies;
- existing YAML frontmatter та validity required fields;
- wikilinks, embeds, Markdown links і `related` paths;
- filename stems, неоднозначні для basename wikilinks;
- external URLs; не надсилайте private content remote service.

Виключайте лише явно authorized generated/vendor trees. Збережіть exclusion
list у manifest, щоб counts були пояснюваними.

### 2.2 Визначте source methodology

Directory/content signals — лише hints, а не доказ:

| Source pattern | Типовий signal | Початковий POWER target |
| --- | --- | --- |
| P.A.R.A. | Projects, Areas, Resources, Archive | відповідний canonical folder |
| C.O.D.E. | Capture, Organize, Distill, Express | Inbox/Resource/Area/Project за content |
| GTD | Inbox, Next Actions, Waiting, Someday, Projects | Inbox/Project/Area/Archive |
| Zettelkasten | fleeting, literature, permanent, UID names | Resource; hubs можуть бути Area/System Guide |
| LYT | Home, MOCs, Notes, Archives | System Guide/Area/Resource/Archive |
| Johnny.Decimal | numeric category ranges | Area/Project/Resource за semantic role |
| Flat/hybrid | немає надійного folder contract | note-by-note; fallback Resource |

### 2.3 Створіть migration manifest

Мінімальні поля для кожного source item:

```text
source_path
source_kind                 # markdown | attachment | config | excluded
source_sha256
detected_methodology
target_path
okf_type
title
description
link_rewrites_planned
status                      # planned | transformed | verified | blocked
reason
```

Для нотатки також запишіть нормалізований **body hash** після вилучення лише
старого frontmatter. Це дозволяє змінити destination frontmatter і водночас
довести, що body не було непомітно втрачено.

### 2.4 Класифікуйте OKF metadata

Required fields:

```yaml
type: Project | Area | Resource | Daily Log | Archive | System Guide
title: "Людинозрозумілий заголовок"
description: "Однорядковий catalog summary"
timestamp: 2026-08-08T12:00:00+03:00
```

Поточні optional fields: `resource`, `tags`, `owner`, `status`, `expiry`,
`related`, `okf_version` і `memory`. Зберігайте unknown metadata, якщо воно не
небезпечне й не конфліктує з validated schema.

Classification rules:

- active outcome з finish condition → `Project`;
- ongoing responsibility → `Area`;
- reference, atomic note, clipping або uncertain item → `Resource`;
- temporal journal/session record → `Daily Log`;
- completed або intentionally retired material → `Archive`;
- agent protocol, MOC/system hub або operating rule → `System Guide`.

Не вигадуйте provenance, owner, dates або relations. Позначайте uncertain rows
як `blocked` або використовуйте conservative `Resource` із записаною причиною.

**Receipt Фази 2:** total/excluded/classified/blocked counts, collision report,
manifest checksum і нуль unaccounted authorized files.

---

## Фаза 3: Ініціалізація destination і staged transformation

### 3.1 Встановіть і перевірте P.O.W.E.R.

Використовуйте `v3.7.11` environment із clean-install гіда:

```bash
POWER_PYTHON=/absolute/path/to/venv/bin/python
POWER_CLI=/absolute/path/to/venv/bin/power
"$POWER_CLI" --version
"$POWER_PYTHON" -c 'import power_framework; print("lean FTS import: OK")'
```

`POWER_PYTHON` має бути тим interpreter, якому належить executable
`POWER_CLI`. Використовуйте ці змінні в усіх наступних командах.

### 3.2 Ініціалізуйте порожній destination

```bash
"$POWER_CLI" init /absolute/path/to/destination
```

Команда має завершитися з кодом `0`. Не копіюйте source files до цього кроку й
не обходьте non-empty-directory guard.

### 3.3 Трансформуйте малими batches

Для кожної Markdown note:

1. прочитайте source bytes один раз;
2. відокремте old frontmatter від body без зміни body;
3. побудуйте validated OKF frontmatter з approved manifest row;
4. оберіть unique target у canonical P.O.W.E.R. folder;
5. запишіть temporary/staging file і лише потім atomically place result;
6. запишіть destination byte hash і normalized body hash;
7. позначте row `transformed`, але ще не `verified`.

Batch має бути достатньо малим для review/retry. Не регенеруйте весь index
після кожної нотатки у великій міграції.

### 3.4 Коли доречний MCP `ingest_note`

Він придатний для невеликої кількості окремих notes, якщо:

- target починається з дозволеного P.A.R.A. folder;
- `content` є повним body без old frontmatter;
- rate limit і per-note index/lint cost прийнятні;
- агент читає returned lint report.

Для великого vault використовуйте controlled filesystem transformation і CLI
gates раз на batch. Не заявляйте підтримку arbitrary target folders через MCP.

### 3.5 Reconcile кожний batch

Доведіть:

- кожен transformed source row має рівно один destination;
- кожен destination має valid required frontmatter;
- normalized source/destination body hashes збігаються;
- target collision не перезаписав попередню note;
- blocked rows залишаються видимими в manifest.

**Receipt Фази 3:** batch range, created files, matching body hashes, failed rows
і retry actions.

---

## Фаза 4: Attachments, links і graph relations

### 4.1 Скопіюйте attachments losslessly

Збережіть bytes і, де можливо, relative layout. Після copy перевірте SHA-256.
Не вставляйте attachment contents у prompts лише заради перенесення.

### 4.2 Перепишіть links за manifest mapping

Опрацьовуйте синтаксиси окремо:

- `[[Note]]` і `[[folder/Note|Alias]]` wikilinks;
- `![[attachment.png]]` embeds;
- `[label](relative/path.md)` Markdown links;
- image/file paths;
- OKF `related[].path`.

Source-relative Markdown links і vault/basename wikilinks мають різну
семантику. Якщо дві notes мають однаковий basename, не вгадуйте: використайте
manifest target або залиште link `blocked`.

`power rename` може допомогти з `related` для одного known rename, але не є
універсальним wikilink migration engine.

### 4.3 Створюйте graph relations консервативно

Підтримується legacy path string або typed relation:

```yaml
related:
  - path: 02_Areas/Infrastructure.md
    relation: depends_on
    confidence: 0.95
```

Переносьте або додавайте relation лише за наявності evidence. Однакове слово у
filenames не є достатнім доказом graph edge.

**Receipt Фази 4:** attachment count/hash reconciliation, links examined,
rewritten, ambiguous/blocked і remaining broken-link count.

---

## Фаза 5: Executable validation та reconciliation

### 5.1 Markdown і OKF gates

```bash
"$POWER_CLI" index /absolute/path/to/destination --strict
"$POWER_CLI" lint /absolute/path/to/destination
"$POWER_CLI" markdown-check /absolute/path/to/destination
"$POWER_CLI" status /absolute/path/to/destination
```

Required result:

- кожна команда завершується з кодом `0`;
- strict index пропускає нуль invalid notes;
- broken internal links = 0;
- orphan/stale warnings пояснено індивідуально, а не приховано;
- status counts збігаються з verified Markdown rows у manifest.

### 5.2 Search gates

Спочатку доведіть FTS без model downloads:

```bash
"$POWER_CLI" sync /absolute/path/to/destination --fts-only
"$POWER_CLI" search /absolute/path/to/destination "known phrase" --mode fts
```

Використайте кілька known phrases із різних source categories і запишіть
expected target paths. Лише за наявності ресурсів перевіряйте dense search:

```bash
"$POWER_CLI" sync /absolute/path/to/destination
"$POWER_CLI" search /absolute/path/to/destination "known concept" --mode semantic
"$POWER_CLI" search /absolute/path/to/destination "known concept" --mode reranked
```

Semantic/reranked readiness залишається pending, якщо model download,
validation або search падає. FTS pass не доводить dense quality.

### 5.3 Фінальна losslessness reconciliation

Міграція не завершена, доки не виконано все:

- authorized source Markdown count = verified destination note count;
- кожна source note має один manifest target або approved exclusion;
- normalized body hashes збігаються для кожної migrated note;
- attachment hashes source/destination збігаються;
- немає unexpected destination files;
- blocked/ambiguous items = 0 або user explicitly accepts documented exception;
- source tree досі збігається з inventory Фази 1.

Spot checks корисні, але не замінюють full manifest reconciliation.

**Receipt Фази 5:** command outputs/exit codes, lint issue counts, index counts,
search cases, manifest totals і hash reconciliation.

---

## Фаза 6: Cutover, rollback record і maintenance

### 6.1 Cutover

Переналаштовуйте applications і MCP clients на destination лише після проходу
Фази 5. Канонічна variable:

```text
POWER_VAULT_DIR=/absolute/path/to/destination
```

Перезапустіть long-lived MCP clients і запустіть preflight через точно
configured Python. Source і verified backup залишайте read-only протягом
observation period.

### 6.2 Git опційний і потребує окремої авторизації

Local vault не потребує remote repository. Якщо Git publication авторизовано:

- виключіть `.env`, credentials, private keys, model/search databases, backups
  і raw private evaluation data;
- перевірте `git diff --cached` перед commit;
- працюйте у feature branch за review/signing policy репозиторію;
- не імпортуйте private signing key і не push лише тому, що migration passed.

Синхронізація private vault не є public publication.

### 6.3 Rollback record

Запишіть:

- source, backup, destination і manifest paths;
- source/destination Git state, якщо застосовно;
- exact last passing gate і timestamps;
- як repoint clients на unchanged source;
- unresolved exceptions та owner.

Не видаляйте source або backup у межах цього протоколу. Retention/destruction
потребують окремого explicit decision.

### 6.4 Ongoing maintenance

Після structural changes:

```bash
"$POWER_CLI" index /absolute/path/to/destination --strict
"$POWER_CLI" lint /absolute/path/to/destination
"$POWER_CLI" markdown-check /absolute/path/to/destination
```

Запускайте `power sync`, коли retrieval indexes треба оновити. Читайте
`index.md`, потім релевантний canonical `_index.md`, потім specific notes.
Зберігайте dated change record за local operating rules vault.

## Фінальний acceptance checklist

- Verified backup існує поза source і destination.
- Manifest враховує кожний authorized source file без unexplained rows.
- Source незмінний і придатний до restore/read.
- Destination notes лежать у canonical folders і мають valid OKF metadata.
- Body й attachment hash reconciliation проходить.
- Link ambiguity = 0 або explicitly accepted; broken links = 0.
- `index --strict`, `lint` і `markdown-check` завершуються з кодом `0`.
- FTS sync/search проходять із записаними known-result cases.
- Dense/reranked status позначено verified або pending за target-host evidence.
- MCP використовує точний installed interpreter і `POWER_VAULT_DIR`.
- Cutover і Git/publication відбулися лише з explicit authorization.
- Rollback instructions і retained backup paths записано.

## Усунення проблем

| Проблема | Коректна дія |
| --- | --- |
| `power init` відхиляє source | Очікувано: він непорожній. Створіть окремий destination. |
| `ingest_note` відхиляє custom folder | MCP write обмежено дозволеними P.A.R.A. folders. Зіставте note з canonical target. |
| `read_sub_index` відхиляє source category | Він приймає canonical P.A.R.A. categories. Використайте destination mapping та generated canonical index. |
| `power heal` залишає notes invalid | Custom folders можуть не мати type hint. Додайте approved `type`, `title`, `description`, `timestamp` із manifest і validate again. |
| Links ламаються після move | Застосуйте source→target mapping окремо до wikilinks, Markdown links, embeds і `related`; не вважайте, що `power rename` переписує все. |
| `index --strict` падає | Дослідіть кожний skipped path; не робіть cutover із partial catalog. |
| Dense sync падає | Позначте semantic/reranked pending і залиште FTS operational; не знижуйте evidence claim мовчки. |
| Counts збігаються, hashes — ні | Міграція не lossless. Відновіть/перетрансформуйте mismatched rows до cutover. |
