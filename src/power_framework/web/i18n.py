"""Internationalization support for the POWER Web UI with English and Ukrainian."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import Request

DEFAULT_LANG = "en"
SUPPORTED_LANGS = {"en", "uk"}

TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "html_lang": "en",
        "app_name": "P.O.W.E.R. — Web UI",
        "skip_to_content": "Skip to content",
        "dashboard": "Dashboard",
        "notes": "Notes",
        "search": "Search",
        "graph": "Graph",
        "tasks": "Tasks",
        "decisions": "Decisions",
        "receipts": "Receipts",
        "federation": "Discovery",
        "login": "Login",
        "logout": "Logout",
        "authorization": "Authorization",
        "login_subtitle": "Enter administrator password to access cockpit",
        "admin_password": "Administrator Password:",
        "sign_in": "Sign In →",
        "invalid_password": "Invalid access password",
        "lang_switch_label": "Language",
        "theme_dark": "Dark",
        "theme_light": "Light",
        "toggle_theme": "Toggle theme",
        # Dashboard
        "system_status": "System Status",
        "system_healthy": "System Healthy",
        "vault_metrics": "Vault Metrics",
        "total_notes": "Total Notes",
        "active_projects": "Active Projects",
        "recent_updates": "Recent Knowledge Updates",
        "categories": "Categories",
        "quick_search": "Quick Search…",
        "view_all": "View All →",
        # Tasks
        "task_manager": "Task Manager v2",
        "new_task": "+ New Task",
        "backlog": "Backlog",
        "ready": "Ready",
        "in_progress": "In Progress",
        "completed": "Completed",
        "failed": "Failed",
        "revision": "Revision",
        "event_journal": "Event Journal",
        "task_title": "Task Title",
        "create_task": "Create Task",
        "back_to_tasks": "← Back to tasks",
        "task_objective": "Task Objective",
        "objective_empty": "No objective specified.",
        "next_action": "Next Action",
        "transition_gate": "State Transition Gate",
        "start_working": "▶️ Start Working",
        "mark_ready": "📋 Mark Ready",
        "move_to_backlog": "📥 Move to Backlog",
        "complete_task": "✅ Complete",
        "request_input": "❓ Request Input",
        "block_task": "⏸️ Block Task",
        "fail_task": "❌ Mark Failed",
        "resume_task": "▶️ Resume Working",
        "cancel_task": "🚫 Cancel Task",
        "terminal_state_msg": "Task is in a terminal immutable state",
        "parameters": "Parameters",
        "owner": "Owner",
        "assignee": "Assignee",
        "unassigned": "Unassigned",
        "priority": "Priority",
        "authority": "Authority",
        "event_seq": "Seq",
        "event_type": "Event Type",
        "event_actor": "Actor",
        "event_digest": "Digest",
        "no_events": "No events recorded yet.",
        # Notes
        "note_browser": "Notes Browser",
        "edit_note": "Edit Note",
        "propose_change": "Propose Change",
        "read_mode": "Read Mode",
        "save": "Save",
        "cancel": "Cancel",
        "status": "Status",
        "created": "Created",
        "modified": "Modified",
        "tags": "Tags",
        "path": "Path",
        "category": "Category",
        "filter": "Filter",
        "all": "All",
        # Search
        "search_vault": "Search Knowledge Vault",
        "search_title": "Multimodal Knowledge Retrieval",
        "search_subtitle": "Search across semantic, dense, and full-text (FTS) engines of P.O.W.E.R",
        "search_placeholder": "Search notes by title, tag, or fulltext…",
        "search_input_placeholder": "Enter search query…",
        "search_input_label": "Search notes",
        "search_btn": "🔍 Search",
        "results": "Results",
        "search_results_for": "Search results for",
        "mode_label": "Mode",
        "fallback_label": "Fallback",
        "no_results_found": "No notes found matching your query.",
        "score_label": "Score",
        "mode_auto": "Mode: Auto (Dense + FTS fallback)",
        "mode_fts": "Mode: FTS (Deterministic)",
        "mode_semantic": "Mode: Semantic (Dense only)",
        "mode_reranked": "Mode: Reranked (Cross-Encoder)",
        # Graph
        "knowledge_graph": "Knowledge Graph",
        "graph_subtitle": "Interactive 2D visualization of Obsidian note relationships",
        "reset_view": "Reset View",
        # Decisions & Receipts
        "decision_queue": "Operator Decision Queue",
        "receipts_ledger": "Receipts & Audit Ledger",
        "fleet_registry": "Fleet Registry",
        # Fleet discovery (read-only probes; not A2A 1.0)
        "federation_title": "Fleet discovery map (read-only probes)",
        "federation_subtitle": "Real-time health probing and multi-node registry across the Weby Homelab fleet (experimental/custom-discovery only)",
        "fleet_nodes_registered": "Registered Fleet Nodes",
        "node_id": "Node ID",
        "role_host": "Role / Host",
        "endpoint": "Endpoint",
        "latency": "Latency",
        "trust_authority": "Trust & Authority",
        "a2a_protocol": "Experimental custom discovery",
        "a2a_description": "The node publishes bounded read-only custom discovery metadata. This is not an A2A 1.0.1 conformance claim.",
        "view_agent_card": "View discovery metadata (JSON)",
        "probe_refresh": "Refresh Status",
    },
    "uk": {
        "html_lang": "uk",
        "app_name": "P.O.W.E.R. — Web UI",
        "skip_to_content": "Перейти до вмісту",
        "dashboard": "Дашборд",
        "notes": "Нотатки",
        "search": "Пошук",
        "graph": "Граф",
        "tasks": "Завдання",
        "decisions": "Рішення",
        "receipts": "Чеки",
        "federation": "Discovery",
        "login": "Вхід",
        "logout": "Вийти",
        "authorization": "Авторизація",
        "login_subtitle": "Введіть пароль для доступу до панелі",
        "admin_password": "Пароль адміністратора:",
        "sign_in": "Увійти →",
        "invalid_password": "Невірний пароль доступу",
        "lang_switch_label": "Мова",
        "theme_dark": "Темна",
        "theme_light": "Світла",
        "toggle_theme": "Перемкнути тему",
        # Dashboard
        "system_status": "Стан системи",
        "system_healthy": "Система в нормі",
        "vault_metrics": "Метрики бази знань",
        "total_notes": "Всього нотаток",
        "active_projects": "Активних проєктів",
        "recent_updates": "Останні оновлення знань",
        "categories": "Категорії",
        "quick_search": "Швидкий пошук…",
        "view_all": "Переглянути всі →",
        # Tasks
        "task_manager": "Task Manager v2",
        "new_task": "+ Нове завдання",
        "backlog": "Беклог",
        "ready": "Готово",
        "in_progress": "В роботі",
        "completed": "Виконано",
        "failed": "Помилка",
        "revision": "Ревізія",
        "event_journal": "Журнал подій",
        "task_title": "Назва завдання",
        "create_task": "Створити завдання",
        "back_to_tasks": "← Назад до завдань",
        "task_objective": "Мета завдання",
        "objective_empty": "Ціль не вказана.",
        "next_action": "Наступна дія",
        "transition_gate": "Зміна стану (Transition Gate)",
        "start_working": "▶️ Взяти в роботу",
        "mark_ready": "📋 Готово до роботи",
        "move_to_backlog": "📥 Відкласти в беклог",
        "complete_task": "✅ Завершити",
        "request_input": "❓ Запитати дані",
        "block_task": "⏸️ Заблокувати",
        "fail_task": "❌ Позначити збій",
        "resume_task": "▶️ Продовжити",
        "cancel_task": "🚫 Скасувати",
        "terminal_state_msg": "Завдання у фінальному незмінному стані",
        "parameters": "Параметри",
        "owner": "Власник",
        "assignee": "Виконавець",
        "unassigned": "Не призначено",
        "priority": "Пріоритет",
        "authority": "Повноваження",
        "event_seq": "Seq",
        "event_type": "Тип події",
        "event_actor": "Актор",
        "event_digest": "Digest",
        "no_events": "Подій поки що немає.",
        # Notes
        "note_browser": "Перегляд нотаток",
        "edit_note": "Редагувати нотатку",
        "propose_change": "Запропонувати зміну",
        "read_mode": "Режим читання",
        "save": "Зберегти",
        "cancel": "Скасувати",
        "status": "Статус",
        "created": "Створено",
        "modified": "Змінено",
        "tags": "Теги",
        "path": "Шлях",
        "category": "Категорія",
        "filter": "Фільтр",
        "all": "Всі",
        # Search
        "search_vault": "Пошук по базі знань",
        "search_title": "Мультимодальний пошук знань",
        "search_subtitle": "Пошук через семантичний, щільний (dense) та повнотекстовий (FTS) рушії P.O.W.E.R",
        "search_placeholder": "Пошук нотаток за назвою, тегом чи текстом…",
        "search_input_placeholder": "Введіть пошуковий запит…",
        "search_input_label": "Пошук нотаток",
        "search_btn": "🔍 Шукати",
        "results": "Результати",
        "search_results_for": "Результати пошуку для",
        "mode_label": "Режим",
        "fallback_label": "Fallback",
        "no_results_found": "За вашим запитом нічого не знайдено.",
        "score_label": "Score",
        "mode_auto": "Режим: Auto (Dense + FTS fallback)",
        "mode_fts": "Режим: FTS (Deterministic)",
        "mode_semantic": "Режим: Semantic (Dense only)",
        "mode_reranked": "Режим: Reranked (Cross-Encoder)",
        # Graph
        "knowledge_graph": "Граф знань",
        "graph_subtitle": "Інтерактивна 2D візуалізація зв'язків між нотатками Obsidian",
        "reset_view": "Скинути вигляд",
        # Decisions & Receipts
        "decision_queue": "Черга рішень оператора",
        "receipts_ledger": "Журнал аудиторських чеків",
        "fleet_registry": "Реєстр вузлів флоту",
        # Fleet discovery (read-only probes; not A2A 1.0)
        "federation_title": "Карта discovery флоту (read-only зонди)",
        "federation_subtitle": "Моніторинг доступності в реальному часі та реєстр вузлів флоту Weby Homelab (лише experimental/custom-discovery)",
        "fleet_nodes_registered": "Зареєстровані вузли флоту",
        "node_id": "ID вузла",
        "role_host": "Роль / Хост",
        "endpoint": "Ендпоінт",
        "latency": "Затримка",
        "trust_authority": "Рівень довіри",
        "a2a_protocol": "Експериментальне custom discovery",
        "a2a_description": "Вузол публікує обмежені read-only метадані custom discovery. Це не заява про відповідність A2A 1.0.1.",
        "view_agent_card": "Переглянути discovery metadata (JSON)",
        "probe_refresh": "Оновити статус",
    },
}


def normalize_lang(code: str | None) -> str:
    """Normalize language code to supported set, defaulting to 'en'."""
    if not code:
        return DEFAULT_LANG
    cleaned = code.strip().lower()
    if cleaned in {"uk", "ua", "ukr", "ukrainian"}:
        return "uk"
    return DEFAULT_LANG


def get_request_lang(request: Request) -> str:
    """Extract language from request query param or cookie, defaulting to 'en'."""
    query_lang = request.query_params.get("lang")
    if query_lang:
        return normalize_lang(query_lang)
    cookie_lang = request.cookies.get("power_web_lang")
    if cookie_lang:
        return normalize_lang(cookie_lang)
    return DEFAULT_LANG


DEFAULT_THEME = "dark"
SUPPORTED_THEMES = {"dark", "light"}


def normalize_theme(theme: str | None) -> str:
    """Normalize theme code to supported set, defaulting to 'dark'."""
    if not theme:
        return DEFAULT_THEME
    cleaned = theme.strip().lower()
    if cleaned in {"light", "day", "white"}:
        return "light"
    return DEFAULT_THEME


def get_request_theme(request: Request) -> str:
    """Extract theme from request query param or cookie, defaulting to 'dark'."""
    query_theme = request.query_params.get("theme")
    if query_theme:
        return normalize_theme(query_theme)
    cookie_theme = request.cookies.get("power_web_theme")
    if cookie_theme:
        return normalize_theme(cookie_theme)
    return DEFAULT_THEME


def translate(key: str, lang: str = DEFAULT_LANG) -> str:
    """Lookup translation key with fallback to English then raw key."""
    norm_lang = normalize_lang(lang)
    lang_dict = TRANSLATIONS.get(norm_lang, TRANSLATIONS[DEFAULT_LANG])
    if key in lang_dict:
        return lang_dict[key]
    return TRANSLATIONS[DEFAULT_LANG].get(key, key)


def jinja_translate(context: dict[str, Any], key: str, lang: str | None = None) -> str:
    """Jinja2 helper to automatically translate using context request language."""
    if lang is None:
        req = context.get("request")
        if req is not None:
            if hasattr(req, "state") and hasattr(req.state, "lang"):
                lang = req.state.lang
            else:
                lang = get_request_lang(req)
        elif "current_lang" in context:
            lang = context["current_lang"]
    return translate(key, lang=lang or DEFAULT_LANG)


__all__ = [
    "DEFAULT_LANG",
    "DEFAULT_THEME",
    "SUPPORTED_LANGS",
    "SUPPORTED_THEMES",
    "TRANSLATIONS",
    "get_request_lang",
    "get_request_theme",
    "jinja_translate",
    "normalize_lang",
    "normalize_theme",
    "translate",
]
