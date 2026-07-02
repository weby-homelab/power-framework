# 🚀 P.O.W.E.R. Framework — Hybrid Knowledge Management System

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Format: GFM](https://img.shields.io/badge/Format-GFM-blue.svg)](https://github.github.com/gfm/)

Гібридна система управління знаннями (Obsidian Second Brain), що поєднує зручність структури для людини та строгу машиночитаність для ШІ-агентів. 

Побудована на поєднанні **P.A.R.A.** + **OKF Overlay** + **LLM-Wiki** + **Execution Rules**.

---

## 🎯 Архітектура системи (P.O.W.E.R.)

Фреймворк складається з чотирьох взаємодоповнюючих компонентів:

*   **P** — **P.A.R.A.** (Projects, Areas, Resources, Archive) — логічна структура папок для організації нотаток людиною.
*   **O** — **OKF Overlay** (Open Knowledge Format) — метадані (YAML frontmatter) у заголовку кожного файлу для парсингу ШІ.
*   **W** — **LLM-Wiki** (філософія А. Карпати) — автоматичний індекс, журнал змін та лінтінг зв'язків.
*   **E.R.** — **Execution Rules / Enforced Routines** (авторські правила автоматизації) — суворий GPG-підпис комітів, PR-only workflow, автоматичний 5-хвилинний sync-brain та правила очищення гілок.

### 📊 Візуальна схема фреймворку

```mermaid
graph TB
    subgraph Human ["👤 Human (Obsidian UI)"]
        PARA["P.A.R.A. Directory Structure"]
        PARA_P["01_Projects"]
        PARA_A["02_Areas"]
        PARA_R["03_Resources"]
        PARA_AR["04_Archive"]
        PARA --> PARA_P
        PARA --> PARA_A
        PARA --> PARA_R
        PARA --> PARA_AR
    end

    subgraph AI ["🤖 AI Agent (OpenCode / Antigravity)"]
        Ingest["Ingest Note"]
        Lint["Lint Vault (lint_brain.py)"]
        Index["Rebuild Index (generate_index.py)"]
    end

    subgraph OKF ["📄 OKF Overlay (Metadata Schema)"]
        YAML["YAML Frontmatter"]
        IndexMD["index.md (Catalog)"]
        LogMD["log.md (Change Log)"]
    end

    subgraph ER ["🔐 Execution Rules & Enforced Routines"]
        GPG["GPG Signature (Verified Commit)"]
        PR["PR-Only Workflow (GitHub)"]
        Sync["Cron Autosync (sync-brain.sh)"]
        Clean["Branch Cleanup (cleanup_branches.py)"]
    end

    Human -- Writes Notes --> YAML
    YAML -- Parsed by --> AI
    AI -- Updates --> IndexMD
    AI -- Appends --> LogMD
    AI -- Runs Checks --> Lint
    
    IndexMD -- Synchronized via --> Sync
    LogMD -- Synchronized via --> Sync
    
    Sync -- Requires --> GPG
    Sync -- Follows --> PR
    PR -- Triggers --> Clean
    
    classDef human fill:#1A365D,stroke:#3182CE,stroke-width:2px,color:#FFF;
    classDef ai fill:#2C3E50,stroke:#E74C3C,stroke-width:2px,color:#FFF;
    classDef okf fill:#1B4D3E,stroke:#2ECC71,stroke-width:2px,color:#FFF;
    classDef er fill:#5D3F6A,stroke:#BB8FCE,stroke-width:2px,color:#FFF;
    
    class PARA,PARA_P,PARA_A,PARA_R,PARA_AR human;
    class Ingest,Lint,Index ai;
    class YAML,IndexMD,LogMD okf;
    class GPG,PR,Sync,Clean er;
```

---

## 📂 Структура каталогів бази знань

База знань розгортається у репозиторії у наступному вигляді:

```text
/brain
├── 00_Inbox/                    # Тимчасова папка для швидких нотаток та сирих даних
├── 01_Projects/                 # Активні проєкти з чіткими дедлайнами та цілями
├── 02_Areas/                    # Сфери відповідальності (інфраструктура, фінанси, здоров'я)
├── 03_Resources/                # Загальні ресурси (гайди, інструкції, сниппети, скрипти)
│   └── lint_brain.py            # Скрипт валідації та очищення зв'язків
├── 04_Archive/                  # Архів закритих проєктів та застарілих нотаток
├── 05_Templates/                # Шаблони нотаток із предзаповненим OKF-форматом
├── 06_Daily_Logs/               # Щоденні звіти ШІ-сесій та уроки (MASTER-LESSONS-LEARNED)
├── PROTOCOLS/                   # Системні специфікації для ШІ-агентів
│   └── LLM_WIKI_SCHEMA.md       # Суворі правила форматування та лінтінгу
├── index.md                     # Автоматично генерований каталог усіх документів
└── log.md                       # Хронологічний журнал змін бази знань (append-only)
```

---

## 📄 Специфікація метаданих (OKF)

Кожна нотатка повинна містити суворий YAML-блок (frontmatter) на початку файлу. Це дозволяє ШІ-агентам миттєво індексувати та фільтрувати інформацію:

```yaml
---
type: Project | Area | Resource | Daily Log | Archive | System Guide  # Тип документа
title: "Назва документа"                                               # Візуальний заголовок
description: "Опис в один рядок (до 150 символів) для каталогу"       # Коротке резюме
resource: "https://github.com/..."                                    # Посилання на код або джерело
tags: [active, guide]                                                 # Теги для Obsidian
timestamp: YYYY-MM-DDTHH:MM:SS+TZ                                      # Мітка останньої зміни
---
```

---

## 🤖 Процес лінтінгу (Health Linting)

Скрипт `lint_brain.py` використовується для періодичної (або за запитом) перевірки цілісності бази знань.

### Можливості перевірки:
1.  **Биті посилання (Broken Links)**: Виявляє внутрішні лінки `[[Note]]` та `[Title](Path.md)`, які вказують на неіснуючі файли.
2.  **Валідація метаданих**: Знаходить файли з відсутнім YAML-заголовком або некоректним полем `type`.
3.  **Виявлення сторінок-сиріт (Orphans)**: Показує сторінки, на які немає жодного вхідного посилання (за винятком індексу).

---

## 🔐 Налаштування безпеки та автоматизації (E.R.)

1.  **Zero-Secrets**: Жодних паролів, API-ключів та внутрішніх IP-адрес у репозиторії. Усі чутливі змінні середовища зберігаються в локальному файлі `.env` на сервері та додані до `.gitignore`.
2.  **Verified Commits (GPG)**: Усі коміти повинні бути підписані персональним GPG-ключем розробника для запобігання підміні авторів у публічному середовищі.
3.  **PR-only Workflow**: Зміни вносяться в окремі гілки `feature/*`, пушаться на GitHub і зливаються через Pull Request після перевірки.
4.  **Auto-Sync Cron**: На сервері налаштовано cron-задачу, яка кожні 5 хвилин синхронізує локальні зміни у ваулті з віддаленим репозиторієм GitHub.

---

## 📄 Ліцензія

Цей проєкт поширюється за ліцензією MIT. Ви можете вільно використовувати його для побудови власних персональних або корпоративних систем знань.
