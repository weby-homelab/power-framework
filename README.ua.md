<p align="center">
  <a href="README.md">ENG</a> | <b>UKR</b>
</p>

# P.O.W.E.R. — AI-Native Toolkit для Second Brain

Валідуйте, індексуйте, шукайте та керуйте вашою базою знань з терміналу — або дозвольте AI-агентам робити це через MCP. Створено для людей, які хочуть машиночитабельні нотатки, автоматичну перевірку якості та токен-ефективний AI-доступ до свого Second Brain.

[![CI](https://github.com/weby-homelab/power-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/weby-homelab/power-framework/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/weby-homelab/power-framework?logo=github)](https://github.com/weby-homelab/power-framework/releases)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![CodeQL](https://github.com/weby-homelab/power-framework/actions/workflows/codeql.yml/badge.svg)](https://github.com/weby-homelab/power-framework/actions/workflows/codeql.yml)
[![Docs](https://img.shields.io/badge/docs-mkdocs--material-8A2BE2?logo=materialformkdocs)](https://weby-homelab.github.io/power-framework/)

## Про P.O.W.E.R. - Hybrid Knowledge Management Framework

P.O.W.E.R. — це гібридна система, створена для подолання прірви між людськими робочими процесами, автоматичними скриптами та автономними ШІ-агентами на базі LLM. Назва є абревіатурою, що розшифровується за її ключовими компонентами: **P**.A.R.A., **O**KF, **W**iki та **E**xecution **R**ules. Вона об'єднує ці архітектурні підходи в цілісний, самовалідований та токен-ефективний Second Brain.

## Чому P.O.W.E.R.?

На відміну від звичайних інструментів для баз знань, P.O.W.E.R. спроектовано для **AI-орієнтованого керування знаннями**:

- **AI-нативні метадані** — Pydantic v2 схеми забезпечують строгий OKF frontmatter з полями governance (`owner`, `status`, `expiry`) та Graph RAG (`related`)
- **Токен-ефективна індексація** — ієрархічний `index.md` + `_index.md` скорочує використання контексту AI-агентів на ~75%
- **Knowledge Graph** — поле `related` зв'язує нотатки між собою для Graph RAG
- **Freshness Monitoring** — лінтер виявляє застарілі нотатки за полем `expiry`
- **Agent Auto-Ingest** — MCP інструмент `synthesize_session` для автономного створення нотаток агентами з governance + graph links + index
- **MCP-нативний** — всі 12 інструментів доступні будь-якому MCP-клієнту (Claude, OpenCode, Cursor) через FastMCP 3.x без додаткового коду
- **Beta з явними release gates** — hermetic тести й security checks відстежуються у CI; [baseline trust-release P.O.W.E.R. 3.1](docs/adr/0001-power-3.1-trust-release-baseline.md) фіксує gates, що залишилися.

## Швидкий старт

```bash
pip install git+https://github.com/weby-homelab/power-framework.git@v3.2.1

power init ~/my-vault      # Створити структуру vault
power lint ~/my-vault      # Перевірити биті посилання та метадані
power index ~/my-vault     # Згенерувати каталог index.md
power heal ~/my-vault      # Автовиправлення відсутнього/невалідного frontmatter
power markdown-check ~/my-vault  # Перевірка якості Markdown
```

## Розробницька установка (editable + легке оновлення)

Для **постійного, завжди оновлюваного** CLI на робочій станції (WS) встановіть
у _editable_ режимі з локальної копії. Це прив'язує `power` до репо, тож зміни
коду набирають чинності одразу — перевстановлення не потрібне.

```bash
# 1. Клонуйте одного разу
git clone https://github.com/weby-homelab/power-framework.git /tmp/power-framework
cd /tmp/power-framework

# 2. Editable-встановлення у user-site (переживає reboot, без venv)
pip install --user --break-system-packages -e ".[dev]"

# 3. Перевірка — `power` тепер у PATH (через ~/.local/bin)
power --version
```

Оновити до останнього коду будь-коли:

```bash
cd /tmp/power-framework && git pull origin main && power --version
# Якщо змінився pyproject.toml (нові залежності/версія) — перевстановіть:
pip install --user --break-system-packages -e ".[dev]"
```

> 💡 **Оновлювач в один рядок.** Збережіть це як `/root/.local/bin/power-update`,
> зробіть `chmod +x`, і просто запускайте `power-update` для авто-pull + reinstall:
>
> ```bash
> #!/usr/bin/env bash
> set -euo pipefail
> REPO="/tmp/power-framework"
> cd "$REPO"
> git fetch origin main && git reset --hard origin/main
> if git diff --name-only HEAD@{1} HEAD | grep -q pyproject.toml; then
>   pip install --user --break-system-packages -e ".[dev]" >/dev/null 2>&1
> fi
> power --version
> ```

## Що всередині

| Функція                         | Що робить                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **CLI**                         | `power init`, `lint`, `index`, `ingest`, `search`, `rot`, `status`, `archive`, `cron`, `heal`, `markdown-check`, `suggest-related` — 12 команд для керування vault                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| **MCP Server**                  | Надає `lint_vault`, `generate_index`, `read_sub_index`, `ensure_sub_index`, `ingest_note`, `search_vault_tool`, `synthesize_session`, `rot_audit`, `archive_notes`, `suggest_related_tool`, `heal_frontmatter_tool`, `check_markdown_tool` — 12 інструментів для AI-агентів                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| **OKF Validation**              | Pydantic v2 схеми з полями governance (`owner`, `status`, `expiry`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| **Knowledge Graph (Graph RAG)** | Поле `related` в OKF frontmatter з підтримкою `TypedRelation` (path, relation, confidence), BFS обходом та експортом підграфів у Mermaid-діаграми (`to_mermaid`)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| **Freshness Monitoring**        | Лінтер виявляє застарілі нотатки за полем `expiry`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| **Agent Auto-Ingest**           | `synthesize_session` — агенти автономно створюють нотатки з governance + graph links + перебудовою індексу                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| **Режими retrieval**            | Доступні FTS5 (BM25), локальний TF vector, Hybrid (RRF), Semantic і **Reranked** режими. Default POWER 3.1 — pinned semantic BGE-M3; потрібен сумісний dense index, а за відсутніх чи несумісних assets пошук fail-closed з remediation `power sync`. Для навмисного контракту використовуйте explicit `fts`, `vector` або `hybrid`. Якісні та ресурсні показники потребують versioned evidence перед release claim. |
| **Cross-Encoder реранкер**      | Локальний `jinaai/jina-reranker-v2-base-multilingual` має CC-BY-NC-4.0 і потребує явного `POWER_ALLOW_NONCOMMERCIAL_MODELS=1` лише для дозволеного non-commercial use. Це не production default: перед commercial deployment потрібен ліцензований reranker. |
| **Graph RAG v2**                | Фаза 3 suggester зв'язків: явні OKF `related` посилання дають сильний куратований сигнал, злитий з перетином ключових слів/тегів у **зважений двонаправлений граф подібності** зі зваженим BFS та центральністю за ступенем/вагою (`power suggest-related --v2`). Лише впевнені передбачення, без вигаданих зв'язків.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| **ColBERT Opt-In реранкер**     | Фаза 3 `POWER_RERANKER=colbert` вмикає late-interaction ColBERT реранкинг (потрібно ≥16 GB RAM, інакше пропускається); **вимкнено за замовчуванням**, канонічний Jina v2 реранкер залишається fallback.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| **Synthesize Auto-Ingest**      | Фаза 3 CLI `power synthesize <path>` (дзеркалить MCP-інструмент `synthesize_session`) автокласифікує OKF метадані, пише атомарно, регенерує ієрархічний індекс, дописує `log.md` та запускає lint-звіт — Auto-Ingest Feedback Loop.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| **Статус метрики якості пошуку** | Колишнє значення `UDCG@5` — це legacy normalised discounted lexical proxy, а не EACL-2026 UDCG; воно лише діагностичне. Release-quality claims відкладено до paper-backed reference vectors справжньої UDCG. |
| **ROT Audit**                   | Виявляє дублікати за допомогою векторного косинусного порівняння та перевіряє семантичні суперечності за допомогою LLM або метаданих                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| **Auto-Archive**                | Автоматично архівує застарілі нотатки до `04_Archive/` — `power archive <path>` з dry-run переглядом                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| **Healer**                      | Автоматично виправляє відсутні/невалідні поля frontmatter — `power heal <path>`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| **Markdown Checks**             | Перевіряє якість Markdown: trailing whitespace, списки, заголовки, мова коду — `power markdown-check <path>`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| **Relation Suggestions**        | Аналіз перетину ключових слів та тегів для Graph RAG — `power suggest-related <path>`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| **Cron Maintenance**            | Запускає lint + index + rot audit однією командою — `power cron <path>`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| **Hierarchical Index**          | `index.md` (навігаційна карта) + `*/_index.md` (детальні каталоги) для економії токенів AI-агентів (~75-94%)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| **CI/CD**                       | Hermetic тести, CodeQL SAST і автоматизовані GitHub-релізи; release evidence перевіряється versioned harness `benchmarks/power31` та pinned model manifest. |
| **Документація**                | Повний [mkdocs-material сайт](https://weby-homelab.github.io/power-framework/) з API reference та гайдами                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |

> **Статус evidence для POWER 3.1:** historical figures у feature-table,
> model comparisons, resource limits і benchmark recommendations не є поточним
> release evidence. Framework лишається beta/research, доки P0/P1 gates плану
> 3.1 не закриті versioned artifacts.

## Звіт міграції

Повний технічний звіт про перехід від плоского до ієрархічного індексування:

- **[English: Hierarchical Index Migration Report](https://github.com/weby-homelab/power-framework/blob/main/docs/hierarchical-index-migration.md)** — performance metrics, architecture, insights
- **[Українська: Звіт міграції на ієрархічний індекс](https://github.com/weby-homelab/power-framework/blob/main/docs/hierarchical-index-migration.ua.md)** — детальний технічний звіт з метриками

### Ґайд міграції для AI-агента

Покроковий протокол для будь-якого AI-агента (Antigravity, OpenCode, Claude Code CLI, Gemini 2.0, DeepSeek-R1, Devin) для автономної міграції існуючої бази знань у структуру P.O.W.E.R.:

- **[English: AI Agent Migration Guide](https://github.com/weby-homelab/power-framework/blob/main/docs/migration-guide.md)** — 5-phase protocol with MCP tools, classification heuristics, and troubleshooting
- **[Українська: Ґайд міграції для AI-агента](https://github.com/weby-homelab/power-framework/blob/main/docs/migration-guide.ua.md)** — покроковий протокол з MCP-інструментами, евристиками класифікації та вирішенням проблем

### Чому P.O.W.E.R. 3.2.1

Детальний опис та технічна порівняльна матриця з іншими фреймворками:

- **[English: Why P.O.W.E.R. 3.2.1](https://github.com/weby-homelab/power-framework/blob/main/WHY_POWER_3.2.1.en.md)** — comparison matrix, 5 super features, token economy, P.A.R.A. flexibility FAQ
- **[Українська: Чому P.O.W.E.R. 3.2.1](https://github.com/weby-homelab/power-framework/blob/main/WHY_POWER_3.2.1.md)** — огляд, порівняльна таблиця, 5 супер фішок, економія токенів, FAQ по гнучкості P.A.R.A.

## 🗂️ Підтримка Методологій: Оберіть Свою Систему

P.O.W.E.R. не прив'язує вас до однієї методології. Ініціалізуйте сховище з будь-якою популярною системою організації знань однією командою:

```bash
power init /шлях/до/vault --template para          # P.A.R.A. — орієнтація на проєкти та дедлайни
power init /шлях/до/vault --template code          # C.O.D.E. — синтез та дистиляція контенту
power init /шлях/до/vault --template gtd           # GTD — обробка задач і Inbox Zero
power init /шлях/до/vault --template zettelkasten  # Zettelkasten — атомарні нотатки з UID-графом
power init /шлях/до/vault --template lyt           # LYT — карти контенту MOC / Hubs
power init /шлях/до/vault --template johnny-decimal # Johnny.Decimal — сувора десяткова ієрархія
```

| Методологія      | Головний Фокус              | Скелет Папок за замовчуванням                              | Основна Метрика         |
| :--------------- | :-------------------------- | :--------------------------------------------------------- | :---------------------- |
| **P.A.R.A.**     | Дії та Дедлайни             | `01_Projects`, `02_Areas`, `03_Resources`, `04_Archive`   | Завершення проєктів     |
| **C.O.D.E.**     | Дистиляція контенту         | `01_Capture`, `02_Organize`, `03_Distill`, `04_Express`   | Швидкість генерації ідей|
| **GTD**          | Опрацювання задач           | `00_Inbox`, `01_Next_Actions`, `02_Waiting_For`, `03_Someday` | Inbox Zero & Потік  |
| **Zettelkasten** | Атомарний граф ідей         | `fleeting/`, `literature/`, `permanent/`, `index/`        | Густота зв'язків та UID |
| **LYT**          | Карти контенту (MOC)        | `Home.md`, `MOCs/`, `Notes/`, `Archives/`                 | Покриття MOC-картами    |
| **Johnny.Decimal** | Суворий десятичний індекс | `10-19_Admin/`, `20-29_Engineering/`, `30-39_Ops/`        | Десятична адресація     |

OKF-валідація метаданих, векторний пошук BGE-M3, лінтер та всі 12 MCP-інструментів працюють **незалежно від обраної методології** — без компромісів!

## Для кого це

- **Користувачі баз знань**, які хочуть щоб AI-агенти розуміли та підтримували їх базу знань
- **Розробники**, що будують структурований Second Brain з машиночитабельними метаданими
- **Команди**, яким потрібне консистентне форматування нотаток та автоматична перевірка якості

## Команди

```
power init <path>              Створити новий vault зі структурою P.A.R.A.
power lint <path>              Сканування на биті посилання, відсутні метадані, сиріт
power index <path>             Згенерувати ієрархічний індекс (index.md + _index.md)
power search <path> <query>    Повнотекстовий пошук з релевантним ранжуванням
power ingest <path> [опції]    Створити нову нотатку з валідованими OKF метаданими
power rot <path>               ROT Audit — виявити дублікати, застарілі, тривіальні
power status [path]            Показати інформаційну панель стану vault (статистика та здоров'я)
power heal <path>              Автоматично виправити відсутній/невалідний frontmatter
power markdown-check <path>    Перевірити якість Markdown
power archive <path>           Автоматично архівувати застарілі нотатки в 04_Archive/
power suggest-related <path>   Запропонувати Graph RAG зв'язки між нотатками
power cron <path>              Автоматичне обслуговування (lint + index + rot)
```

### Приклади ingest

```bash
power ingest ~/my-vault --type Project --title "Мій Додаток" --description "Новий проєкт"
power ingest ~/my-vault --type Resource --title "Docker Гайд" --description "Найкращі практики Docker" --tags devops,docker --resource "https://docs.docker.com"
```

### Приклади пошуку

```bash
power search ~/my-vault "api аутентифікація"
power search ~/my-vault "гайд деплой" --max-results 5
```

## Налаштування MCP Server

Підключіть P.O.W.E.R. до будь-якого MCP-сумісного AI-клієнта (локальний stdio або Docker HTTP транспорт):

```bash
pip install git+https://github.com/weby-homelab/power-framework.git@v3.2.1
```

**Claude Desktop** (`~/.config/Claude/claude_desktop_config.json`):

```json
{
    "mcpServers": {
        "power": {
            "command": "python3",
            "args": ["-m", "power_framework.mcp"],
            "env": {
                "POWER_VAULT_DIR": "/path/to/your/my-vault"
            }
        }
    }
}
```

**OpenCode** (`~/.config/opencode/opencode.jsonc`):

```jsonc
"mcp": {
  "power": {
    "type": "local",
    "command": ["python3", "-m", "power_framework.mcp"],
    "enabled": true
  }
}
```

## Структура Vault

P.O.W.E.R. організовує ваш vault за методом **P.A.R.A.** з **OKF метаданими** на кожній нотатці:

```
~/my-vault
├── 00_Inbox/
│   └── _index.md        # Детальний під-індекс для Inbox
├── 01_Projects/
│   └── _index.md        # Детальний під-індекс для Проєктів
├── 02_Areas/
│   └── _index.md        # Детальний під-індекс для Сфер
├── 03_Resources/
│   └── _index.md        # Детальний під-індекс для Ресурсів
├── 04_Archive/
│   └── _index.md        # Детальний під-індекс для Архіву
├── 05_Templates/        # Шаблони нотаток з OKF frontmatter
├── 06_Daily_Logs/
│   └── _index.md        # Детальний під-індекс для Логів сесій
├── PROTOCOLS/           # Системні специфікації для AI-агентів
├── index.md             # Навігаційна карта (посилання на під-індекси)
└── log.md               # Хронологічний лог змін
```

### Протокол ієрархічного індексу

AI-агенти читають vault ефективно за цим алгоритмом:

1. **Прочитати `index.md`** — визначити релевантну категорію за кількістю нотаток
2. **Викликати MCP `read_sub_index`** — отримати детальні записи для категорії
3. **Читати конкретні нотатки** — тільки коли під-індекс вказує на релевантність
4. **НІКОЛИ не glob усі `.md` файли** — використовуйте під-індекси як карту (~75% економії токенів)

Кожна нотатка починається з валідованого YAML frontmatter. Обов'язкові поля + опціональні governance та графові зв'язки:

```yaml
---
type: Project
title: "Мій Додаток"
description: "Новий проєкт з чіткими цілями"
tags: [active, dev]
timestamp: 2026-07-02T19:00:00
owner: "team-alpha" # опціонально: хто відповідальний
status: active # опціонально: active | review | archived
expiry: 2026-12-31 # опціонально: коли переглянути
related:
    - path: 01_Projects/Other.md
      relation: depends_on # опціонально: тип зв'язку
      confidence: 1.0 # опціонально: оцінка впевненості
---
```

## Деталі архітектури

<details>
<summary><strong>Методологія P.O.W.E.R. — натисніть для розгортання</strong></summary>

Фреймворк поєднує чотири комплементарні методології:

- **P** — **P.A.R.A.** (Projects, Areas, Resources, Archive) — організовує файли за рівнем їх активності на Projects (Проєкти), Areas (Сфери відповідальності), Resources (Ресурси) та Archives (Архіви). P.O.W.E.R. використовує цю структуру каталогів для визначення життєвого циклу нотаток. Інформація природним чином перетікає від швидких записів в Inbox до активних проєктів, довгострокових довідників та, зрештою, архівів.
- **O** — **OKF Overlay** (Open Knowledge Format) — накладає строгий рівень схем метаданих поверх стандартних Markdown файлів. Побудований на базі Pydantic v2 схем, OKF вимагає, щоб кожна нотатка мала чітко визначений тип та проходила валідацію метаданих (обов'язкові атрибути YAML frontmatter: заголовок, опис, теги та мітка часу). Це перетворює неструктуровані текстові папки на передбачувану локальну базу знань, придатну для машинного аналізу.
- **W** — **LLM-Wiki** (філософія A. Karpathy) — перетворює базу знань на ієрархічний каталог, зрозумілий для штучного інтелекту. Завдяки генерації загального навігаційного файлу `index.md` та локальних підкаталогів `_index.md` у кожній папці, система забезпечує токен-ефективну навігацію, яка скорочує використання контексту ШІ-агентами на 75-94%.
- **E.R.** — **Execution Rules** (Правила Виконання) — впроваджує операційні інструкції та правила безпечної поведінки, розроблені спеціально для ШІ-агентів (наприклад, `RULES.md`, `PROMPTS.md` та системні гайди), що встановлюють безпечні межі для автономного редагування. GPG-підписані коміти, PR-only workflow, cron-based sync, очищення гілок.

### 🧠 Взаємозв'язок та співпраця: Другий мозок vs P.O.W.E.R. Framework

**Другий мозок (Obsidian Vault)** та **P.O.W.E.R. Framework** утворюють єдину систему управління знаннями (Knowledge Management System), де **Другий мозок є пасивним сховищем даних**, а **P.O.W.E.R. Framework — активним ШІ-двигуном**.

```mermaid
graph TD
    A[🤖 AI-Агенти: Antigravity / OpenCode / Codex] <-->|MCP Protocol / Skills / CLI| B[⚡ P.O.W.E.R. Framework Engine]
    B <-->|1. Hybrid Search BM25 + BGE-M3 + Reranker| C[(🧠 Obsidian Second Brain Vault)]
    B <-->|2. OKF Frontmatter Linter & Healer| C
    B <-->|3. Indexer & Graph Builder| C
    B <-->|4. ROT Audit & Maintenance| C
```

#### 1. Другий мозок (Obsidian Vault) — *Пасивне сховище пам'яті*
- **Що це:** Локальна база знань у файловій системі (`/root/geminicli/brain`), побудована на базі стандартних Markdown-файлів (`.md`).
- **Структура:**
  - **P.A.R.A. каталоги:** `00_Inbox/`, `01_Projects/`, `02_Areas/`, `03_Resources/`, `04_Archive/`, `06_Daily_Logs/`.
  - **OKF Overlay (Open Knowledge Format):** Стандартизовані метадані YAML frontmatter для кожної нотатки (тип, заголовок, опис, теги, таймштамп).
- **Призначення:** Довгострокове збереження пам'яті, засвоєних уроків, архітектурних рішень (ADRs), планів дій та логів сесій.

#### 2. P.O.W.E.R. Framework — *Активний двигун та ШІ-інструментарій*
- **Що це:** Python-двигун та MCP-сервер (`power-framework`), спроектований спеціально для ШІ-агентів (Antigravity, OpenCode, Codex) для безпечної та інтелектуальної взаємодії з Другим мозком.
- **Ключові можливості:**
  1. **Гібридний пошук (RAG):** Поєднує повнотекстовий пошук SQLite FTS5 (BM25), локальні векторні ембедінги (**BGE-M3** 1024d) та крос-енкодер переранжування **BGE Reranker v2 M3** через Reciprocal Rank Fusion (RRF). Забезпечує високу точність без перевантаження контекстного вікна LLM.
  2. **Перевірка цілісності ваулту (`power lint`):** Сканує ваулт на відсутність OKF-метаданих, пошкоджені вікі-посилання, орфанні нотатки та застарілий контент.
  3. **Ієрархічна індексація та GraphRAG (`power index`):** Автоматично формує навігаційні карти (`index.md`), локальні підкаталоги (`_index.md`) та Mermaid-графи зв'язків.
  4. **Автоматичне лікування та аудит (`power heal` / `power audit`):** Виправляє помилки у frontmatter, форматує дати й теги, а також виявляє дубльовані та застарілі нотатки (ROT Scoring).

#### 3. Матриця співпраці

| Сценарій | Роль Другого мозку | Роль P.O.W.E.R. Framework |
| :--- | :--- | :--- |
| **Ініціалізація сесії (Booting)** | Зберігає правила та `MASTER-LESSONS-LEARNED.md`. | Витягує релевантний контекст для ШІ-агента через MCP-інструмент `search_vault_tool`. |
| **Збереження сесії (`ingest`)** | Приймає нову нотатку в `06_Daily_Logs/YYYY-MM-DD_name.md`. | Валідує OKF frontmatter, перевіряє унікальність і додає новий запис у `log.md`. |
| **Підтримка структури** | Зберігає зв'язки між сутностями та проєктами. | Виконує `power index` для оновлення навігаційних карт і графа зв'язків. |
| **Контроль якості (CI/CD)** | Слугує єдиним джерелом правди для всіх вузлів флоту (PRXMX, WS, HTZNR). | Виконує `power lint`, гарантуючи відсутність помилок перед GPG-підписаним комітом та релізом. |

### Візуальна діаграма

```mermaid
flowchart TD
    %% Modern 2026 Styling
    classDef human fill:#6366f1,stroke:#4338ca,stroke-width:2px,color:#fff,rx:8
    classDef data fill:#0ea5e9,stroke:#0369a1,stroke-width:2px,color:#fff,rx:8
    classDef wiki fill:#10b981,stroke:#047857,stroke-width:2px,color:#fff,rx:8
    classDef rag fill:#8b5cf6,stroke:#6d28d9,stroke-width:2px,color:#fff,rx:8
    classDef agent fill:#f59e0b,stroke:#b45309,stroke-width:2px,color:#fff,rx:8
    classDef security fill:#ef4444,stroke:#b91c1c,stroke-width:2px,color:#fff,rx:8

    subgraph Human ["👤 Людина (Markdown UI)"]
        PARA[["📁 Структура каталогів P.A.R.A."]]:::human
    end

    subgraph OKF ["📄 OKF Overlay (Схема Метаданих & GraphRAG)"]
        YAML[/"📝 YAML Frontmatter з типізованими зв'язками"\]:::data
    end

    subgraph RAG ["🔍 Конвеєр RAG & GraphRAG"]
        Chunker["✂️ Семантичний чанкер (Anthropic Contextual)"]:::rag
        Embeddings["🧠 Dense ембеддінги<br/>(BGE-M3 1024d, прямий ONNX)"]:::rag
        SQLite[("🗄️ SQLite (FTS5 + chunk_embeddings)")]:::rag
        Expander["🔄 Розширювач запитів (Synonyms / LLM)"]:::rag
        Reranker["🎯 Cross-Encoder реранкер (Jina v2 multilingual)"]:::rag
        KG["🕸️ Граф знань (BFS / Mermaid Graph)"]:::rag
    end

    subgraph Wiki ["📖 LLM-Wiki (Ієрархічний каталог)"]
        IndexMD[("🗂️ index.md (Навігаційна карта)")]:::wiki
        SubIndex[("📂 _index.md (Локальні каталоги)")]:::wiki
        LogMD[("📜 log.md (Лог змін)")]:::wiki
    end

    subgraph AI ["🤖 AI-Агент (FastMCP 3.x)"]
        Tools[["🔌 12 асинхронних інструментів MCP"]]:::agent
        Search[["🔍 Гібридний / Reranked пошук"]]:::agent
        ROT{{"🛠️ Аудит ROT та суперечностей (Semantic/LLM)"}}:::agent
    end

    subgraph ER ["🔐 Execution Rules (Правила)"]
        GPG(("🔑 GPG-підписані коміти")):::security
        PR(("🛡️ PR-Only Workflow")):::security
        Sync(("⏱️ Cron Auto-Sync")):::security
    end

    %% Data Flow
    Human -- "Пише нотатки" --> PARA
    PARA -- "Забезпечує OKF" --> YAML
    YAML -- "Парситься через" --> Chunker

    %% RAG Pipeline
    Chunker -- "Контекстні чанки" --> Embeddings
    Embeddings -- "Зберігає вектори" --> SQLite

    %% Search Pipeline
    Tools -- "Робить запит" --> Expander
    Expander -- "Мульти-запити" --> SQLite
    SQLite -- "Кандидати FTS5 + Вектори" --> Reranker
    Reranker -- "Відсортовані результати" --> Search

    %% GraphRAG Pipeline
    YAML -- "Визначає зв'язки" --> KG
    KG -- "Будує підграфи" --> Tools

    %% Wiki Operations
    Tools -- "Авто-імпорт та індексація" --> IndexMD
    Tools -- "Оновлює" --> SubIndex
    Tools -- "Дописує лог" --> LogMD

    %% ROT Audit
    Tools -- "Запускає аудит" --> ROT
    ROT -- "Знаходить дублікати" --> Embeddings
    ROT -- "Шукає суперечності" --> SQLite

    %% Sync & Security
    IndexMD -. "Синхронізується" .-> Sync
    SubIndex -. "Синхронізується" .-> Sync
    LogMD -. "Синхронізується" .-> Sync
    Sync -- "Запускає" --> GPG
    GPG -- "Вимагає" --> PR
```

### Бібліотека (`src/power_framework/`)

| Модуль                    | Призначення                                                                                                                                                                                                                                            |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `core/models.py`          | Pydantic v2 схеми для OKF валідації метаданих                                                                                                                                                                                                          |
| `core/parser.py`          | Безпечний YAML frontmatter парсинг (PyYAML)                                                                                                                                                                                                            |
| `core/indexer.py`         | Сканування vault та генерація ієрархічного індексу                                                                                                                                                                                                     |
| `core/linter.py`          | Перевірки: биті посилання, відсутні метадані, сироти, застарілі нотатки                                                                                                                                                                                |
| `core/searcher.py`        | Повнотекстовий пошук (FTS5/Vector/Hybrid/Reranked); WAL mode + `busy_timeout` для паралельного доступу                                                                                                                                                 |
| `core/embeddings.py`      | Підключний менеджер dense-ембеддінгів: **BGE-M3 (за замовчуванням, 1024d, прямий ONNX Runtime — `BGEM3OnnxManager`)** / Qwen3-0.6B / MiniLM-L12-v2 (light) через `POWER_EMBED_PROVIDER`, lazy init, приборкана BFCArena, adaptive batch halving на OOM |
| `core/reranker.py`        | Cross-Encoder реранкер: **`jina-reranker-v2-base-multilingual`** (за замовчуванням) / `Qwen3-Reranker-0.6B-ONNX` (provider=qwen3) / `ms-marco-MiniLM-L-6-v2` fallback                                                                                  |
| `core/metrics/discounted_lexical_gain.py` | Legacy normalised discounted lexical proxy; `udcg.py` — deprecated compatibility alias, не EACL-2026 UDCG |
| `core/query_expansion.py` | Словник синонімів (EN/UK) та розширення запитів Multi-Query через OpenRouter                                                                                                                                                                           |
| `core/chunker.py`         | Семантичне та контекстне розбиття нотаток на чанки (патерн Contextual Retrieval)                                                                                                                                                                       |
| `core/healer.py`          | Автовиправлення відсутніх/невалідних полів frontmatter                                                                                                                                                                                                 |
| `core/relations.py`       | Побудова KnowledgeGraph, BFS обхід зв'язків та експорт у Mermaid                                                                                                                                                                                       |
| `core/rot_scoring.py`     | A2 scoring: семантична дедублікація, freshness, лінт суперечностей                                                                                                                                                                                     |
| `core/markdown_checks.py` | Перевірки якості Markdown: trailing whitespace, списки, заголовки                                                                                                                                                                                      |
| `core/constants.py`       | Централізовані списки виключень та системні константи                                                                                                                                                                                                  |
| `core/utils.py`           | Захист від path traversal, атомарний запис, бекапи, rate limiter                                                                                                                                                                                       |
| `core/cli.py`             | Командний рядок (12 команд через argparse)                                                                                                                                                                                                             |
| `mcp/power_server.py`     | FastMCP 3.x сервер з 12 асинхронними тулами + HTTP транспорт + /health                                                                                                                                                                                 |

Всі компоненти використовують `power_framework.core` як єдине джерело правди.

</details>

## Розробка

```bash
git clone https://github.com/weby-homelab/power-framework.git
cd power-framework
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Запуск тестів
pytest tests/ -v

# Лінтинг та форматування
ruff check src/ tests/
ruff format src/ tests/

# Перевірка типів
mypy src/power_framework/
```

### Звіти про тестування та бенчмарки

Для детального аналізу та результатів продуктивності фреймворку P.O.W.E.R.:

- [Звіт про тестування та бенчмарки швидкості P.O.W.E.R. v2.0.1](docs/tests/P.O.W.E.R.2.0.1-TEST-1.md) — оцінка розуміння української семантики моделлю `BAAI/bge-m3`, результати тестів та оптимізація VRAM.
- [Аналіз деградації векторного пошуку та архітектурних лімітів](docs/tests/P.O.W.E.R.2.0.1-TEST-2.md) — порівняння лінійного NumPy-пошуку з `sqlite-vec` (SIMD C), FAISS (HNSW) та базою даних Qdrant.
- [Звіт про тестування пам'яті ШІ-агентів у P.O.W.E.R. v2.0.3-TEST](docs/tests/P.O.W.E.R.2.0.3-TEST.md) — інтерактивне багатокрокове тестування на основі SOTA стандартів MemoryAgentBench (ICLR 2026), LoCoMo, LongMemEval та BEAM.
- [P.O.W.E.R. v3.0.0 — Розширений звіт про якість пошуку UA↔EN](docs/tests/P.O.W.E.R.3.0.0-TEST.md) — historical report; його UDCG naming і real-vault quality claims не є поточним release evidence.

## Низько-RAM розгортання (8–12 GB)

Команда `power sync` будує плотні (dense) векторні ембеддінги для всієї бази знань. Ліміти потоків та розмір батчу конфігуруються; валідуйте їх на цільовому апаратному забезпеченні перед використанням у продакшні. Ключові налаштування:

```bash
export POWER_EMBED_PROVIDER=bge-m3           # Провайдер за замовчуванням (aapot/bge-m3-onnx)
export POWER_EMBED_NUM_THREADS=2             # Обмеження кількості потоків CPU
export POWER_EMBED_BATCH_SIZE=8              # Розмір батчу для генерації ембеддінгів
# export POWER_SYNC_VMEM_LIMIT_MB=6144       # Опціональний ліміт віртуальної пам'яті (RLIMIT_AS)
```

Канонічним провайдером за замовчуванням є **`bge-m3`** через прямий ONNX Runtime + `tokenizers` (`BGEM3OnnxManager`), який працює в парі з реранкером Apache-2.0 `onnx-community/bge-reranker-v2-m3-ONNX`. Синхронізація та плотний пошук вимагають наявності сумісних моделей; якщо артефакти відсутні або пошкоджені, пошук працює за принципом fail-closed. Для завантаження та перевірки зафіксованих моделей виконайте `power sync`.

> **⚠️ Примітка щодо ресурсів:** Налаштовуйте `POWER_EMBED_NUM_THREADS` та `POWER_EMBED_BATCH_SIZE` відповідно до можливостей хоста. Поточний реліз гарантує суворий контроль контракту fail-closed; пікове використання RAM та затримка залежать від цільового заліза.

## Ліцензія

P.O.W.E.R. Framework розповсюджується під ліцензією [GNU General Public License v3.0 (GPLv3)](LICENSE).

---

<p align="center">
  Створено в Україні під час повітряних тривог та блекаутів ⚡<br>
  &copy; 2026 Weby Homelab
</p>

<!--
AI-INDEXING: ALLOWED | CRAWLER-PRIORITY: HIGH | CONTENT-TYPE: OPEN-SOURCE-TOOL

@context: https://schema.org
@type: SoftwareApplication
name: P.O.W.E.R. — Hybrid Knowledge Management Framework
alternateName: power-framework
description: P.O.W.E.R. - Hybrid Knowledge Management Framework (P.A.R.A. + OKF Overlay + LLM-Wiki + Execution Rules)
applicationCategory: DeveloperApplication
applicationSubCategory: KnowledgeManagement
operatingSystem: Linux
softwareVersion: 3.2.1
keywords: knowledge-management, second-brain, obsidian, para, okf, llm-wiki, mcp, ai-agents, python, execution-rules
author: Weby Homelab (https://github.com/weby-homelab)
codeRepository: https://github.com/weby-homelab/power-framework
downloadUrl: https://github.com/weby-homelab/power-framework/releases
license: GPL-3.0
isAccessibleForFree: true
-->

<p align="center">
  Створено в Україні під час повітряних тривог та блекаутів ⚡<br>
  &copy; 2026 Weby Homelab
</p>
