---
name: power
version: 2.0.2
description: Maintains and validates the P.O.W.E.R. knowledge base (P.A.R.A. + OKF Overlay + LLM-Wiki + Execution Rules).
---

# ⚡ P.O.W.E.R. Knowledge Management Skill

Цей скілл призначений для автоматизації управління, перевірки та підтримки життєвого циклу бази знань Obsidian Second Brain за гібридною методологією **P.O.W.E.R.**

## 🚀 Основні сценарії використання

Скілл автоматично активується ШІ-агентами (Antigravity CLI та OpenCode) або вручну користувачем при виконанні наступних завдань:
1.  **Ingest (Імпорт знань)** — додавання або редагування документів у базі знань.
2.  **Indexing (Переіндексація)** — оновлення змісту та переліку концепцій.
3.  **Linting (Перевірка здоров'я)** — пошук битих посилань, помилок у метаданих чи сторінок-сиріт.
4.  **ROT Audit** — виявлення дублікатів, застарілих та тривіальних нотаток.
5.  **Auto-Archive** — автоматичне архівування застарілих нотаток до `04_Archive/`.
6.  **Relation Suggestions** — аналіз перетину ключових слів та тегів для Graph RAG.
7.  **Cron Maintenance** — автоматичне виконання lint + index + rot audit.
8.  **Sync & Commit** — фіксація змін у Git згідно з правилами безпеки хоста.

---

## 🛠️ Доступні інструменти (Scripts + CLI)

Скілл містить автоматизовані скрипти у каталозі `scripts/` та CLI:

### Scripts
1.  **`lint_brain.py`** — скрипт лінтера + ROT аудиту (v2.0.2):
    ```bash
    python3 .agents/skills/power/scripts/lint_brain.py
    ```
2.  **`generate_index.py`** — скрипт автоматичної побудови ієрархічного індексу:
    ```bash
    python3 .agents/skills/power/scripts/generate_index.py
    ```

### CLI (power, 11 команд)
1. `power init <path>` — створити структуру vault
2. `power lint <path>` — перевірка метаданих, посилань, orphan
3. `power index <path>` — генерація ієрархічного індексу
4. `power ingest <path>` — створення нотатки з OKF метаданими
5. `power search <path> <query>` — повнотекстовий пошук
6. `power rot <path>` — ROT аудит (дублікати, застарілі, тривіальні)
7. `power archive <path>` — архівування застарілих нотаток
8. `power heal <path>` — автовиправлення frontmatter (новe в v1.7.1)
9. `power markdown-check <path>` — перевірка якості Markdown (новe в v1.7.1)
10. `power suggest-related <path>` — пропозиції зв'язків (Graph RAG)
11. `power cron <path>` — автоматичне обслуговування (lint + index + rot)

### MCP Tools (12) — FastMCP 3.x (v2.0.2)
- `lint_vault`, `generate_index`, `read_sub_index`, `ensure_sub_index`, `ingest_note`
- `search_vault_tool`, `synthesize_session`
- `rot_audit`, `archive_notes`, `suggest_related_tool`
- `heal_frontmatter_tool`, `check_markdown_tool`

### Конфігурація (v2.0.2+)
- **Модель ембеддінгів** — за замовчуванням `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` (384 dim, ~680MB RAM). Підтримує українську + англійську мову. Змінювати через `POWER_EMBEDDING_MODEL` у `.env`.
- **ROT аудит (A2)** — перевірка external-лінків тепер паралельна через `ThreadPoolExecutor(max_workers=16)`, що прискорює час виконання з кількох хвилин до секунд.
- **MCP ентрі-поінт** — `/root/geminicli/.agents/mcp_servers/power_server.py` → `power_framework.mcp`

---

## 📖 Hierarchical Navigation Protocol (On-Demand Sub-Index Reading)

P.O.W.E.R. використовує **ієрархічну індексацію** для оптимізації контексту AI-агентів:

```
vault/
├── index.md              # Navigation map (small, ~2KB)
├── 01_Projects/
│   └── _index.md         # Detailed entries for Projects
├── 02_Areas/
│   └── _index.md         # Detailed entries for Areas
├── 03_Resources/
│   └── _index.md         # Detailed entries for Resources
└── 06_Daily_Logs/
    └── _index.md         # Detailed entries for Daily Logs
```

### Step-by-Step Agent Navigation Rules:

1.  **Direct Reading / Search First:** If the path is known or a specific file is needed, read it directly or search using `grep_search`.
2.  **Use Indices Only if Unknown:** Read `index.md` or call `read_sub_index` (read `folder/_index.md`) only if the path is unknown and `grep_search` yields no results.
3.  **NEVER glob all `.md` files / list large folders:** Use `grep_search` instead of `list_dir` for large categories to preserve tokens.

### Token Efficiency Comparison:

| Approach | Token Cost | Context Quality |
|----------|-----------|-----------------|
| Read all `.md` files | 🔴 ~50K+ | Full but wasteful |
| Read only `index.md` | 🟢 ~2K | Insufficient |
| `index.md` + relevant `_index.md` | 🟡 ~5-8K | **Optimal balance** |
| + specific notes | 🟡 ~10-15K | **Precise, targeted** |

---

## 📋 Інструкції для ШІ-агента (Step-by-Step Rules)

Коли ви працюєте з базою знань у просторі ваулта (Workspace/Vault Root), ЗАВЖДИ дотримуйтеся наступного ланцюжка дій (PAV + P.O.W.E.R.):

### Крок 1. Перевірка метаданих (OKF Frontmatter)
При створенні або редагуванні файлів упевнитись, що файл починається з правильної плашки:
```yaml
---
type: Project | Area | Resource | Daily Log | Archive | System Guide
title: "Назва сторінки"
description: "Опис в один рядок для каталогу"
timestamp: YYYY-MM-DDTHH:MM:SS+TZ
---
```

### Крок 2. Автоматична генерація ієрархічного каталогу (Index)
Після додавання/зміни файлу виконайте скрипт генерації індексу. Він автоматично оновить `index.md` та всі `_index.md` файли:
```bash
python3 .agents/skills/power/scripts/generate_index.py
```

### Крок 3. Додавання запису у Change Log
Запишіть виконану дію в кінець файлу `log.md` у хронологічному форматі:
```markdown
## [YYYY-MM-DD] <operation_type> | <action_title>
- **Action:** Стислий опис того, що зроблено
- **Result:** Які файли змінено/створено
```

### Крок 4. Валідація лінтером (Lint check)
Запустіть скрипт лінтера, щоб перевірити, чи не з'явилися нові биті посилання чи сторінки-сироти:
```bash
python3 .agents/skills/power/scripts/lint_brain.py
```
*Якщо лінтер звітує про помилки (наприклад, broken links у Home.md), негайно виправте їх.*

### Крок 5. Git Commit & Push (Execution Rules)
*   Коміти виконуються **лише в окремі гілки** `feature/*` or `fix/*`.
*   Git налаштовується на GPG-підпис комітів за допомогою ключів розробника з `.env` файлу.
*   Після пушу відкривається Pull Request та здійснюється злиття.
*   Обов'язково запускається скілл `cleanup-branches` для прибирання злитих гілок.
