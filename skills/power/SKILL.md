---
name: power
description: Maintains and validates the P.O.W.E.R. knowledge base (P.A.R.A. + OKF Overlay + LLM-Wiki + Execution Rules).
---

# ⚡ P.O.W.E.R. Knowledge Management Skill

Цей скілл призначений для автоматизації управління, перевірки та підтримки життєвого циклу бази знань Obsidian Second Brain за гібридною методологією **P.O.W.E.R.**

## 🚀 Основні сценарії використання

Скілл автоматично активується ШІ-агентами (Antigravity CLI та OpenCode) або вручну користувачем при виконанні наступних завдань:
1.  **Ingest (Імпорт знань)** — додавання або редагування документів у базі знань.
2.  **Indexing (Переіндексація)** — оновлення змісту та переліку концепцій.
3.  **Linting (Перевірка здоров'я)** — пошук битих посилань, помилок у метаданих чи сторінок-сиріт.
4.  **Sync & Commit** — фіксація змін у Git згідно з правилами безпеки хоста.

---

## 🛠️ Доступні інструменти (Scripts)

Скілл містить два автоматизовані скрипти у каталозі `scripts/`:

1.  **`lint_brain.py`** — скрипт лінтера зв'язків та метаданих:
    ```bash
    python3 .agents/skills/power/scripts/lint_brain.py
    ```
2.  **`generate_index.py`** — скрипт автоматичної побудови ієрархічного індексу:
    ```bash
    python3 .agents/skills/power/scripts/generate_index.py
    ```

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

1.  **Read `index.md`** — identify the relevant P.A.R.A. category by note counts.
2.  **Call `read_sub_index` MCP tool** (or read `folder/_index.md` directly) — get detailed entries with paths, descriptions, tags, and timestamps.
3.  **Read specific notes** — only when the sub-index indicates relevance to the user query.
4.  **NEVER glob all `.md` files** — this burns tokens. Use sub-indexes as a map.

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
