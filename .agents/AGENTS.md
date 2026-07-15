# 🚀 Antigravity Developer Rules & Verification Mandate

## 🔍 HOLISTIC ANALYSIS & STEP-BY-STEP VERIFIED EXECUTION
1. **Аналіз по черзі:** Спочатку прочитай та проаналізуй всі дотичні файли по черзі. Випиши список проблем/багів.
2. **Покрокові зміни:** Впроваджуй по одній зміні за раз, не міксуй непов'язані виправлення.
3. **Валідація:** Після кожної зміни перевіряй працездатність (компіляція, тести, логи).
4. **Аудит якості:** Перед здачею перевір: валідацію вхідних даних (Pydantic), відсутність зайвого I/O на гарячих шляхах, використання `ThreadPoolExecutor`, чистоту образу від зайвих пакетів.

## 🔀 GIT BRANCH CLEANUP
- **Видалення гілок:** Після злиття PR негайно видаляй злиті гілки локально та на GitHub за допомогою скрипта `.agents/skills/cleanup-branches/scripts/cleanup_branches.py`.

## 🤖 AI AGENT OFFLOADING & TOKEN ECONOMY
- **Використання OpenCode як субагента:** З метою економії власного контекстного вікна та токенів Gemini, девелоперський агент має обов'язково використовувати локальний CLI-інструмент OpenCode (`/root/.opencode/bin/opencode run --auto "задача"`) як субагента для виконання допоміжних завдань розробки, написання/тестування скриптів або рефакторингу коду.


## 🧠 SECOND BRAIN & HIERARCHICAL INDEX MANDATE (v11.0)
- **Навігація `/root/geminicli/brain/`:**
  - **Пряме читання:** Якщо шлях відомий, читай файл напряму.
  - **Grep-пошук:** Шукай через `grep_search`, не зчитуй індекси категорій (`06_Daily_Logs/_index.md`) без потреби.
  - **🚫 Заборонено:** `list_dir` / `glob` великих папок (>10 файлів), `glob **/*.md`, створювати нотатки без OKF frontmatter.
- **OKF Metadata:** Кожна нотатка має містити frontmatter:
  ```yaml
  ---
  type: Project | Area | Resource | Daily Log | Archive | System Guide
  title: "Назва"
  description: "Опис (макс 150 симв)"
  tags: [tag1]
  timestamp: YYYY-MM-DDTHH:MM:SS
  ---
  ```
- **Індекс та Log:** Після будь-якої зміни обов'язково:
  1. Онови індекс: `python3 .agents/skills/power/scripts/generate_index.py` (або FastMCP).
  2. Запиши в `log.md`: `## [YYYY-MM-DD] <type> | <title>` з Action/Result.
  3. Для сесій створюй нотатку `06_Daily_Logs/YYYY-MM-DD_session_name.md`.
- **Commit:** Заборонено комітити зміни в Obsidian без GPG-підпису (`git commit -S`).
