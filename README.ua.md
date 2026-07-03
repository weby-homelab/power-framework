<p align="center">
  <a href="README.md">ENG</a> | <b>UKR</b>
</p>

# P.O.W.E.R. — AI-Native Toolkit для Obsidian

Валідуйте, індексуйте, шукайте та керуйте вашим vault Obsidian з терміналу — або дозвольте AI-агентам робити це через MCP. Створено для людей, які хочуть машиночитабельні нотатки, автоматичну перевірку якості та токен-ефективний AI-доступ до свого Second Brain.

[![CI](https://github.com/weby-homelab/P.O.W.E.R/actions/workflows/ci.yml/badge.svg)](https://github.com/weby-homelab/P.O.W.E.R/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-90%25-brightgreen?logo=pytest)](https://github.com/weby-homelab/P.O.W.E.R/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/weby-homelab/P%2EO%2EW%2EE%2ER?logo=github)](https://github.com/weby-homelab/P.O.W.E.R/releases)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CodeQL](https://github.com/weby-homelab/P.O.W.E.R/actions/workflows/codeql.yml/badge.svg)](https://github.com/weby-homelab/P.O.W.E.R/actions/workflows/codeql.yml)
[![Docs](https://img.shields.io/badge/docs-mkdocs--material-8A2BE2?logo=materialformkdocs)](https://weby-homelab.github.io/P.O.W.E.R/)

## Чому P.O.W.E.R.?

На відміну від звичайних Obsidian-інструментів, P.O.W.E.R. спроектовано для **AI-орієнтованого керування знаннями**:

- **AI-нативні метадані** — Pydantic v2 схеми забезпечують строгий OKF frontmatter; кожна нотатка машиночитабельна
- **Токен-ефективна індексація** — ієрархічний `index.md` + `_index.md` скорочує використання контексту AI-агентів на ~75%
- **MCP-нативний** — всі інструменти доступні будь-якому MCP-клієнту (Claude, OpenCode, Cursor) без додаткового коду
- **Продакшн-якість** — 144 тести, 90% покриття, CodeQL сканування, OIDC-підписані PyPI релізи

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
| **MCP Server** | Надає `lint_vault`, `generate_index`, `read_sub_index`, `ingest_note`, `search_vault` будь-якому AI-агенту (Claude, Cursor, OpenCode) |
| **OKF Validation** | Pydantic v2 схеми забезпечують строгу валідацію метаданих кожної нотатки |
| **Повнотекстовий пошук** | Пошук з релевантним ранжуванням по заголовку, тілу та тегам з контекстними снипетами |
| **Hierarchical Index** | `index.md` (навігаційна карта) + `*/_index.md` (детальні каталоги) для економії токенів AI-агентів (~75-94%) |
| **CI/CD** | 144 тести, 90% покриття, CodeQL SAST, OIDC Trusted Publishing до PyPI |
| **Документація** | Повний [mkdocs-material сайт](https://weby-homelab.github.io/P.O.W.E.R/) з API reference та гайдами |

## Звіт міграції

Повний технічний звіт про перехід від плоского до ієрархічного індексування:
- **[English: Hierarchical Index Migration Report](docs/hierarchical-index-migration.md)** — performance metrics, architecture, insights
- **[Українська: Звіт міграції на ієрархічний індекс](docs/hierarchical-index-migration.ua.md)** — детальний технічний звіт з метриками

### Ґайд міграції для AI-агента

Покроковий протокол для будь-якого AI-агента (Claude, GPT, Gemini, OpenCode) для автономної міграції існуючого Obsidian Vault у структуру P.O.W.E.R.:

- **[English: AI Agent Migration Guide](docs/migration-guide.md)** — 5-phase protocol with MCP tools, classification heuristics, and troubleshooting
- **[Українська: Ґайд міграції для AI-агента](docs/migration-guide.ua.md)** — покроковий протокол з MCP-інструментами, евристиками класифікації та вирішенням проблем

## Для кого це

- **Користувачі Obsidian**, які хочуть щоб AI-агенти розуміли та підтримували їх vault
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
        "POWER_VAULT_DIR": "/path/to/your/obsidian/vault"
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
├── 00_Inbox/          # Швидкі захоплення та сирий матеріал
├── 01_Projects/       # Активні проєкти з дедлайнами
├── 02_Areas/          # Постійні сфери відповідальності
├── 03_Resources/      # Довідники та матеріали для повторного використання
├── 04_Archive/        # Завершені або архівовані нотатки
├── 05_Templates/      # Шаблони нотаток з OKF frontmatter
├── 06_Daily_Logs/     # Хронологічні логи сесій
├── PROTOCOLS/         # Системні специфікації для AI-агентів
├── index.md           # Авто-згенерований каталог
└── log.md             # Хронологічний лог змін
```

Кожна нотатка починається з валідованого YAML frontmatter:

```yaml
---
type: Project
title: "Мій Додаток"
description: "Новий проєкт з чіткими цілями"
tags: [active, dev]
timestamp: 2026-07-02T19:00:00
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
graph TB
    subgraph Human ["👤 Human (Obsidian UI)"]
        PARA["P.A.R.A. Directory Structure"]
    end

    subgraph OKF ["📄 OKF Overlay (Metadata Schema)"]
        YAML["YAML Frontmatter"]
    end

    subgraph Wiki ["📖 LLM-Wiki (філософія Karpathy)"]
        IndexMD["index.md (Авто-каталог)"]
        LogMD["log.md (Лог змін)"]
        Lint["Лінтинг посилань"]
    end

    subgraph AI ["🤖 AI Agent (Local / Cloud)"]
        Ingest["Ingest Note"]
        Index["Rebuild Index"]
    end

    subgraph ER ["🔐 Execution Rules"]
        GPG["GPG-підписані коміти"]
        PR["PR-Only Workflow"]
        Sync["Cron Auto-Sync"]
    end

    Human -- Writes Notes --> YAML
    YAML -- Parsed by --> AI
    AI -- Updates --> IndexMD
    AI -- Appends --> LogMD
    AI -- Runs Checks --> Lint
    IndexMD -. Synced via .-> Sync
    LogMD -. Synced via .-> Sync
    Sync --> GPG
    GPG --> PR
```

### Бібліотека (`src/power_framework/`)

| Модуль | Призначення |
|--------|------------|
| `core/models.py` | Pydantic v2 схеми для OKF валідації метаданих |
| `core/parser.py` | Безпечний YAML frontmatter парсинг (PyYAML) |
| `core/indexer.py` | Сканування vault та генерація index.md |
| `core/linter.py` | Перевірки: биті посилання, відсутні метадані, сироти |
| `core/searcher.py` | Повнотекстовий пошук з релевантним ранжуванням |
| `core/utils.py` | Захист від path traversal, атомарний запис, бекапи |
| `core/cli.py` | Командний рядок (init, lint, index, ingest, search) |
| `mcp/server.py` | FastMCP сервер, що надає всі інструменти AI-агентам |

Всі компоненти використовують `power_framework.core` як єдине джерело правди.

</details>

## Розробка

```bash
git clone https://github.com/weby-homelab/P.O.W.E.R.git
cd P.O.W.E.R
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Запуск тестів (144 тести, 90%+ покриття)
pytest tests/ -v

# Лінтинг та форматування
ruff check src/ tests/
ruff format src/ tests/

# Перевірка типів
mypy src/power_framework/
```

## Ліцензія

MIT — використовуйте для особистої або корпоративної бази знань.

<p align="center">
  Створено в Україні під час повітряних тривог та блекаутів ⚡<br>
  &copy; 2026 Weby Homelab
</p>
