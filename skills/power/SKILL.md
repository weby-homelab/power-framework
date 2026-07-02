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
    python3 /root/geminicli/.agents/skills/power/scripts/lint_brain.py
    ```
2.  **`generate_index.py`** — скрипт автоматичної побудови індексу:
    ```bash
    python3 /root/geminicli/.agents/skills/power/scripts/generate_index.py
    ```

---

## 📋 Інструкції для ШІ-агента (Step-by-Step Rules)

Коли ви працюєте з базою знань у просторі `/root/geminicli/brain/`, ЗАВЖДИ дотримуйтеся наступного ланцюжка дій (PAV + P.O.W.E.R.):

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

### Крок 2. Автоматична генерація каталогу (Index)
Після додавання/зміни файлу виконайте скрипт генерації індексу. Він автоматично оновить реєстр у `index.md`:
```bash
python3 /root/geminicli/.agents/skills/power/scripts/generate_index.py
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
python3 /root/geminicli/.agents/skills/power/scripts/lint_brain.py
```
*Якщо лінтер звітує про помилки (наприклад, broken links у Home.md), негайно виправте їх.*

### Крок 5. Git Commit & Push (Execution Rules)
*   Коміти виконуються **лише в окремі гілки** `feature/*` або `fix/*`.
*   Git налаштовується на GPG-підпис комітів за допомогою ключів розробника з `.env` файлу.
*   Після пушу відкривається Pull Request та здійснюється злиття.
*   Обов'язково запускається скілл `cleanup-branches` для прибирання злитих гілок.
