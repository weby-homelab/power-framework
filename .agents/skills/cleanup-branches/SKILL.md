---
name: cleanup-branches
description: Cleans up obsolete, merged git branches in the local repository and deletes them from GitHub.
---

# 🗑️ Git Branch Cleanup Skill

Цей скілл призначений для автоматичного очищення застарілих та вже злитих гілок з локального середовища та віддаленого репозиторію на GitHub.

## 🚀 Як використовувати

Скілл автоматично активується, коли:
1. Завершено роботу над Pull Request (PR) або злиттям змін.
2. Запущено процес розгортання/деплою.
3. Користувач просить видалити зайві гілки або навести лад у репозиторії.

Ви можете запустити скрипт очищення безпосередньо з терміналу:
```bash
/root/geminicli/.agents/skills/cleanup-branches/scripts/cleanup_branches.py
```

Скрипт самостійно:
- Перевірить, чи перебуваєте ви в Git репозиторії.
- Отримає токен `GITHUB_RELEASE_TOKEN` з файлу `.env`.
- Отримає назву репозиторію та його власника.
- Визначить список гілок, які вже злиті в `main` або `master`.
- Видалить ці гілки на GitHub через API.
- Виконає команду `git fetch origin --prune` для очищення локальних посилань.
