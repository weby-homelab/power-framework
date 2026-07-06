<p align="center">
  <a href="README.md">ENG</a> | <b>UKR</b>
</p>

# P.O.W.E.R. — AI-Native Toolkit для Second Brain

Валідуйте, індексуйте, шукайте та керуйте вашою базою знань з терміналу — або дозвольте AI-агентам робити це через MCP. Створено для людей, які хочуть машиночитабельні нотатки, автоматичну перевірку якості та токен-ефективний AI-доступ до свого Second Brain.

[![CI](https://github.com/weby-homelab/power-framework/actions/workflows/ci.yml/badge.svg)](https://github.com/weby-homelab/power-framework/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-90%25-brightgreen?logo=pytest)](https://github.com/weby-homelab/power-framework/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/weby-homelab/power-framework?logo=github)](https://github.com/weby-homelab/power-framework/releases)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![CodeQL](https://github.com/weby-homelab/power-framework/actions/workflows/codeql.yml/badge.svg)](https://github.com/weby-homelab/power-framework/actions/workflows/codeql.yml)
[![Docs](https://img.shields.io/badge/docs-mkdocs--material-8A2BE2?logo=materialformkdocs)](https://weby-homelab.github.io/power-framework/)

## Про P.O.W.E.R. - Hybrid Knowledge Management Framework

P.O.W.E.R. — це гібридна система, створена для подолання прірви між людськими робочими процесами, автоматичними скриптами та автономними ШІ-агентами на базі LLM. Назва є абревіатурою, що розшифровується за її ключовими компонентами: **P**.A.R.A., **O**KF, **W**iki та **E**xecution **R**ules. Вона об'єднує ці архітектурні підходи в цілісний, самовалідований та токен-ефективний Second Brain:

*   **P (Метод P.A.R.A.)** — організовує файли за рівнем їх активності на **P**rojects (Проєкти), **A**reas (Сфери відповідальності), **R**esources (Ресурси) та **A**rchives (Архіви). P.O.W.E.R. використовує цю структуру каталогів для визначення життєвого циклу нотаток. Інформація природним чином перетікає від швидких записів в Inbox до активних проєктів, довгострокових довідників та, зрештою, архівів.
*   **O (OKF Overlay - Open Knowledge Format)** — накладає строгий рівень схем метаданих поверх стандартних Markdown файлів. Побудований на базі Pydantic v2 схем, OKF вимагає, щоб кожна нотатка мала чітко визначений тип та проходила валідацію метаданих (обов'язкові атрибути YAML frontmatter: заголовок, опис, теги та мітка часу). Це перетворює неструктуровані текстові папки на передбачувану локальну базу знань, придатну для машинного аналізу.
*   **W (LLM-Wiki)** — перетворює базу знань на ієрархічний каталог, зрозумілий для штучного інтелекту. Завдяки генерації загального навігаційного файлу `index.md` та локальних підкаталогів `_index.md` у кожній папці, система забезпечує токен-ефективну навігацію, яка скорочує використання контексту ШІ-агентами на **75-94%**.
*   **E.R. (Execution Rules - Правила Виконання)** — впроваджує операційні інструкції та правила безпечної поведінки, розроблені спеціально для ШІ-агентів (наприклад, `RULES.md`, `PROMPTS.md` та системні гайди). Вони встановлюють безпечні межі для автономного редагування та визначають, як саме люди й ШІ мають взаємодіяти з системою.



## Чому P.O.W.E.R.?

На відміну від звичайних інструментів для баз знань, P.O.W.E.R. спроектовано для **AI-орієнтованого керування знаннями**:

- **AI-нативні метадані** — Pydantic v2 схеми забезпечують строгий OKF frontmatter з полями governance (`owner`, `status`, `expiry`) та Graph RAG (`related`)
- **Токен-ефективна індексація** — ієрархічний `index.md` + `_index.md` скорочує використання контексту AI-агентів на ~75%
- **Knowledge Graph** — поле `related` зв'язує нотатки між собою для Graph RAG
- **Freshness Monitoring** — лінтер виявляє застарілі нотатки за полем `expiry`
- **Agent Auto-Ingest** — MCP інструмент `synthesize_session` для автономного створення нотаток агентами з governance + graph links + index
- **MCP-нативний** — всі інструменти доступні будь-якому MCP-клієнту (Claude, OpenCode, Cursor) без додаткового коду
- **Продакшн-якість** — 160 тестів, 90%+ покриття, CodeQL сканування, OIDC-підписані GitHub релізи

## Швидкий старт

```bash
pip install power-framework

power init ~/my-vault      # Створити структуру vault
power lint ~/my-vault      # Перевірити биті посилання та метадані
power index ~/my-vault     # Згенерувати каталог index.md
```

## Що всередині

| Функція | Що робить |
|---------|-----------|
| **CLI** | `power init`, `lint`, `index`, `ingest`, `search` — повне керування vault з терміналу |
| **MCP Server** | Надає `lint_vault`, `generate_index`, `read_sub_index`, `ingest_note`, `search_vault`, `synthesize_session` будь-якому AI-агенту |
| **OKF Validation** | Pydantic v2 схеми з полями governance (`owner`, `status`, `expiry`) |
| **Knowledge Graph (Graph RAG)** | Поле `related` для явних зв'язків між нотатками. Відображається в sub-indexes для AI-навігації |
| **Freshness Monitoring** | Лінтер виявляє застарілі нотатки за полем `expiry` |
| **Agent Auto-Ingest** | `synthesize_session` — агенти автономно створюють нотатки з governance + graph links + перебудовою індексу |
| **Повнотекстовий пошук** | Пошук з релевантним ранжуванням по заголовку, тілу та тегам з контекстними снипетами |
| **Hierarchical Index** | `index.md` (навігаційна карта) + `*/_index.md` (детальні каталоги) для економії токенів AI-агентів (~75-94%) |
| **CI/CD** | 160 тестів, 90%+ покриття, CodeQL SAST, Автоматизовані GitHub релізи |
| **Документація** | Повний [mkdocs-material сайт](https://weby-homelab.github.io/power-framework/) з API reference та гайдами |

## Звіт міграції

Повний технічний звіт про перехід від плоского до ієрархічного індексування:
- **[English: Hierarchical Index Migration Report](https://github.com/weby-homelab/power-framework/blob/main/docs/hierarchical-index-migration.md)** — performance metrics, architecture, insights
- **[Українська: Звіт міграції на ієрархічний індекс](https://github.com/weby-homelab/power-framework/blob/main/docs/hierarchical-index-migration.ua.md)** — детальний технічний звіт з метриками

### Ґайд міграції для AI-агента

Покроковий протокол для будь-якого AI-агента (Claude, GPT, Gemini, OpenCode) для автономної міграції існуючої бази знань у структуру P.O.W.E.R.:

- **[English: AI Agent Migration Guide](https://github.com/weby-homelab/power-framework/blob/main/docs/migration-guide.md)** — 5-phase protocol with MCP tools, classification heuristics, and troubleshooting
- **[Українська: Ґайд міграції для AI-агента](https://github.com/weby-homelab/power-framework/blob/main/docs/migration-guide.ua.md)** — покроковий протокол з MCP-інструментами, евристиками класифікації та вирішенням проблем

## Для кого це

- **Користувачі баз знань**, які хочуть щоб AI-агенти розуміли та підтримували їх базу знань
- **Розробники**, що будують структурований Second Brain з машиночитабельними метаданими
- **Команди**, яким потрібне консистентне форматування нотаток та автоматична перевірка якості

## Команди

```
power init <path>              Створити новий vault зі структурою P.A.R.A.
power lint <path>              Сканування на биті посилання, відсутні метадані, сиріт
power index <path>             Перебудувати каталог index.md з усіх нотаток
power search <path> <query>    Повнотекстовий пошук з релевантним ранжуванням
power ingest <path> [опції]    Створити нову нотатку з валідованими OKF метаданими
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

Підключіть P.O.W.E.R. до будь-якого MCP-сумісного AI-клієнта:

```bash
pip install power-framework
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

Кожна нотатка починається з валідованого YAML frontmatter. Обов'язкові поля + опціональні governance та графові зв'язки:

```yaml
---
type: Project
title: "Мій Додаток"
description: "Новий проєкт з чіткими цілями"
tags: [active, dev]
timestamp: 2026-07-02T19:00:00
owner: "team-alpha"                    # опціонально: хто відповідальний
status: active                         # опціонально: active | review | archived
expiry: 2026-12-31                     # опціонально: коли переглянути
related: [01_Projects/Other.md]        # опціонально: Graph RAG зв'язки
---
```

## Деталі архітектури

<details>
<summary><strong>Методологія P.O.W.E.R. — натисніть для розгортання</strong></summary>

Фреймворк поєднує чотири комплементарні методології:

- **P** — **P.A.R.A.** (Projects, Areas, Resources, Archive) — логічна структура папок для людського сприйняття
- **O** — **OKF Overlay** (Open Knowledge Format) — YAML frontmatter на кожному файлі для миттєвого AI-парсингу
- **W** — **LLM-Wiki** (філософія A. Karpathy) — підхід до бази знань як до wiki, яку LLM можуть читати, писати та підтримувати через автоматичну індексацію каталогу, хронологічний лог та структурний лінтинг посилань
- **E.R.** — **Execution Rules** — GPG-підписані коміти, PR-only workflow, cron-sync, очищення гілок

### Візуальна діаграма

```mermaid
flowchart TD
    %% Modern 2026 Styling
    classDef human fill:#6366f1,stroke:#4338ca,stroke-width:2px,color:#fff,rx:8
    classDef data fill:#0ea5e9,stroke:#0369a1,stroke-width:2px,color:#fff,rx:8
    classDef wiki fill:#10b981,stroke:#047857,stroke-width:2px,color:#fff,rx:8
    classDef agent fill:#f59e0b,stroke:#b45309,stroke-width:2px,color:#fff,rx:8
    classDef security fill:#ef4444,stroke:#b91c1c,stroke-width:2px,color:#fff,rx:8
    
    subgraph Human ["👤 Людина (Markdown UI)"]
        PARA[["📁 Структура каталогів P.A.R.A."]]:::human
    end

    subgraph OKF ["📄 OKF Overlay (Схема Метаданих)"]
        YAML[/"📝 YAML Frontmatter"\]:::data
    end

    subgraph Wiki ["📖 LLM-Wiki (Філософія Karpathy)"]
        IndexMD[("🗂️ index.md (Навігаційна карта)")]:::wiki
        SubIndex[("📂 _index.md (Локальні каталоги)")]:::wiki
        LogMD[("📜 log.md (Лог змін)")]:::wiki
        Lint{{"🛠️ Лінтинг посилань"}}:::wiki
    end

    subgraph AI ["🤖 AI-Агент (Local / Cloud)"]
        Ingest>"📥 Створення нотатки"]:::agent
        Index>"🔄 Перебудова індексу"]:::agent
        ReadSub>"🔍 Читання під-індексу"]:::agent
    end

    subgraph ER ["🔐 Execution Rules (Правила)"]
        GPG(("🔑 GPG-підписані коміти")):::security
        PR(("🛡️ PR-Only Workflow")):::security
        Sync(("⏱️ Cron Auto-Sync")):::security
    end

    %% Data Flow
    Human -- "Пише нотатки" --> YAML
    YAML -- "Парситься через" --> AI
    
    %% AI Operations
    AI -- "Оновлює карту" --> IndexMD
    AI -- "Оновлює каталог" --> SubIndex
    AI -- "Дописує в" --> LogMD
    AI -- "Перевіряє" --> Lint
    ReadSub -- "На вимогу" --> SubIndex
    
    %% Sync & Security
    IndexMD -. "Синхронізується" .-> Sync
    SubIndex -. "Синхронізується" .-> Sync
    LogMD -. "Синхронізується" .-> Sync
    Sync -- "Запускає" --> GPG
    GPG -- "Вимагає" --> PR
```

### Бібліотека (`src/power_framework/`)

| Модуль | Призначення |
|--------|------------|
| `core/models.py` | Pydantic v2 схеми для OKF валідації метаданих |
| `core/parser.py` | Безпечний YAML frontmatter парсинг (PyYAML) |
| `core/indexer.py` | Сканування vault та генерація index.md |
| `core/linter.py` | Перевірки: биті посилання, відсутні метадані, сироти, застарілі нотатки |
| `core/searcher.py` | Повнотекстовий пошук з релевантним ранжуванням |
| `core/utils.py` | Захист від path traversal, атомарний запис, бекапи |
| `core/cli.py` | Командний рядок (init, lint, index, ingest, search) |
| `mcp/server.py` | FastMCP сервер, що надає всі інструменти AI-агентам |

Всі компоненти використовують `power_framework.core` як єдине джерело правди.

</details>

## Розробка

```bash
git clone https://github.com/weby-homelab/power-framework.git
cd power-framework
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Запуск тестів (160 тестів, 90%+ покриття)
pytest tests/ -v

# Лінтинг та форматування
ruff check src/ tests/
ruff format src/ tests/

# Перевірка типів
mypy src/power_framework/
```

## Ліцензія

GPLv3 — Створено в Україні ⚡

<p align="center">
  Створено в Україні під час повітряних тривог та блекаутів ⚡<br>
  &copy; 2026 Weby Homelab
</p>
