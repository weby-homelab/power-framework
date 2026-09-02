"""Contract and end-to-end integration tests for POWER Web UI routes."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from power_framework.web.app import create_app
from power_framework.web.config import Settings

if TYPE_CHECKING:
    from pathlib import Path


def _extract_csrf(response) -> str:
    """Helper to extract csrf_token value from HTML form response."""
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', response.text)
    return match.group(1) if match else ""


@pytest.fixture
def test_vault(tmp_path: Path) -> Path:
    """Create a hermetic synthetic vault for GUI route testing."""
    vault = tmp_path / "gui_vault"
    vault.mkdir()
    (vault / ".power").mkdir()
    (vault / "01_Projects").mkdir()
    (vault / "03_Resources").mkdir()

    # Note 1
    (vault / "01_Projects" / "Project_Alpha.md").write_text(
        """---
type: Project
title: "Project Alpha"
description: "Core test project"
tags: [alpha, power]
timestamp: 2026-08-13T12:00:00+00:00
---

# Project Alpha
This links to [[Resource_Beta]].
""",
        encoding="utf-8",
    )

    # Note 2
    (vault / "03_Resources" / "Resource_Beta.md").write_text(
        """---
type: Resource
title: "Resource Beta"
description: "Reference material"
tags: [beta]
timestamp: 2026-08-13T12:00:00+00:00
---

# Resource Beta
Reference material for Alpha.
""",
        encoding="utf-8",
    )

    return vault


@pytest.fixture
def client(test_vault: Path) -> TestClient:
    """Instantiate TestClient bound to synthetic vault."""
    settings = Settings(
        vault_path=test_vault,
        auth_enabled=False,
        cookie_secure=False,
    )
    app = create_app(settings)
    return TestClient(app)


def test_dashboard_route_and_headers(client: TestClient) -> None:
    """Test dashboard route and verification of security headers."""
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    assert "P.O.W.E.R." in resp.text
    assert "Web UI" in resp.text
    assert "3.7.11" in resp.text
    assert "01_Projects" in resp.text
    assert 'class="lang-switcher"' in resp.text
    assert 'aria-label="Language selection"' in resp.text
    assert 'id="liveClock"' in resp.text
    assert 'class="live-clock"' in resp.text
    assert 'role="status"' in resp.text
    assert "text-decoration: underline" in resp.text

    # Check CSP and security headers
    assert resp.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert "Content-Security-Policy" in resp.headers


def test_notes_listing_and_read(client: TestClient) -> None:
    """Test notes browser and secure note view."""
    resp_list = client.get("/notes")
    assert resp_list.status_code == 200
    assert "Project Alpha" in resp_list.text

    resp_read = client.get("/notes/read?path=01_Projects/Project_Alpha.md")
    assert resp_read.status_code == 200
    assert "Project Alpha" in resp_read.text

    # Test wikilink / note stem resolution
    resp_stem = client.get("/notes/read?path=Project_Alpha")
    assert resp_stem.status_code == 200
    assert "Project Alpha" in resp_stem.text

    resp_stem2 = client.get("/notes/read?path=Resource_Beta")
    assert resp_stem2.status_code == 200
    assert "Resource Beta" in resp_stem2.text
    assert 'class="wikilink"' in resp_read.text


def test_notes_edit_and_proposal_flow(client: TestClient) -> None:
    """Test transactional note edit and proposal review."""
    resp_edit = client.get("/notes/edit?path=01_Projects/Project_Alpha.md")
    assert resp_edit.status_code == 200
    assert "Транзакційний редактор" in resp_edit.text
    csrf = _extract_csrf(resp_edit)

    # Submit proposal
    resp_prop = client.post(
        "/notes/propose",
        data={
            "csrf_token": csrf,
            "path": "01_Projects/Project_Alpha.md",
            "content": """---
type: Project
title: "Alpha Updated"
description: "Updated project description"
tags: [alpha, power]
timestamp: 2026-08-13T12:00:00+00:00
---

# Updated
""",
        },
    )
    assert resp_prop.status_code == 200
    assert "Перевірка пропозиції" in resp_prop.text


def test_notes_empty_path_redirect(client: TestClient) -> None:
    """Ensure empty path query redirects to /notes without validation crash."""
    resp_read = client.get("/notes/read?path=", follow_redirects=False)
    assert resp_read.status_code == 303
    assert resp_read.headers["location"] == "/notes"

    resp_edit = client.get("/notes/edit?path=", follow_redirects=False)
    assert resp_edit.status_code == 303
    assert resp_edit.headers["location"] == "/notes"


def test_search_and_graph_routes(client: TestClient) -> None:
    """Test search and knowledge graph projection endpoints."""
    # Search
    resp_search = client.get("/search?q=Alpha&mode=fts")
    assert resp_search.status_code == 200
    assert 'href="/notes/read?path=' in resp_search.text
    assert 'href="/notes/read?path="' not in resp_search.text
    assert "Project_Alpha" in resp_search.text

    # Search with Ukrainian locale
    resp_search_uk = client.get("/search?q=Alpha&mode=fts&lang=uk")
    assert resp_search_uk.status_code == 200
    assert "Результати пошуку для" in resp_search_uk.text

    # Graph UI
    resp_graph_ui = client.get("/graph")
    assert resp_graph_ui.status_code == 200
    assert "Graph" in resp_graph_ui.text

    # Graph API
    resp_graph_data = client.get("/api/graph/data")
    assert resp_graph_data.status_code == 200
    data = resp_graph_data.json()
    assert "nodes" in data
    assert "links" in data
    assert len(data["nodes"]) == 2


def test_task_manager_cockpit(client: TestClient) -> None:
    """Test task creation, board listing, detail view, and state transitions."""
    # List tasks
    resp_tasks = client.get("/tasks")
    assert resp_tasks.status_code == 200

    # New task form
    resp_new = client.get("/tasks/new")
    assert resp_new.status_code == 200
    csrf_new = _extract_csrf(resp_new)

    # Create task
    resp_create = client.post(
        "/tasks/new",
        data={
            "csrf_token": csrf_new,
            "task_id": "test_gui_task_01",
            "title": "GUI Integration Task",
            "objective": "Verify task creation from GUI",
            "owner": "tester",
            "priority": "high",
            "authority": "propose",
        },
        follow_redirects=True,
    )
    assert resp_create.status_code == 200
    assert "GUI Integration Task" in resp_create.text

    # Detail page (default English)
    resp_detail = client.get("/tasks/test_gui_task_01")
    assert resp_detail.status_code == 200
    assert "Event Journal" in resp_detail.text
    csrf_detail = _extract_csrf(resp_detail)

    # Detail page (Ukrainian)
    resp_detail_uk = client.get("/tasks/test_gui_task_01?lang=uk")
    assert resp_detail_uk.status_code == 200
    assert "Журнал подій" in resp_detail_uk.text

    # Direct transition state: backlog -> working
    resp_trans = client.post(
        "/tasks/test_gui_task_01/transition",
        data={"csrf_token": csrf_detail, "new_state": "working", "expected_revision": 1},
        follow_redirects=True,
    )
    assert resp_trans.status_code == 200
    assert "working" in resp_trans.text


def test_decisions_and_receipts(client: TestClient) -> None:
    """Test decision queue, audit receipts, and federation live status."""
    resp_dec = client.get("/decisions")
    assert resp_dec.status_code == 200

    resp_rec = client.get("/receipts")
    assert resp_rec.status_code == 200

    # Federation HTML view
    resp_fed = client.get("/federation")
    assert resp_fed.status_code == 200
    assert "local-core" in resp_fed.text
    assert "remote-ws" in resp_fed.text
    assert "docker-plane" in resp_fed.text

    # Federation Ukrainian view (read-only discovery copy)
    resp_fed_uk = client.get("/federation?lang=uk")
    assert resp_fed_uk.status_code == 200
    assert "discovery" in resp_fed_uk.text.lower() or "флоту" in resp_fed_uk.text

    # Experimental custom discovery metadata endpoints (not A2A 1.0)
    resp_card = client.get("/federation/agent.json")
    assert resp_card.status_code == 200
    card_data = resp_card.json()
    assert card_data["protocol"] == "experimental/custom-discovery"
    assert card_data["node_id"] == "local-core"
    assert "power.search" in card_data["capabilities"]

    resp_well_known = client.get("/.well-known/agent.json")
    assert resp_well_known.status_code == 200
    assert resp_well_known.json()["protocol"] == "experimental/custom-discovery"


def test_authentication_enforcement_and_login(test_vault: Path) -> None:
    """Test that auth_enabled enforces login redirect and authenticates valid sessions."""
    settings = Settings(
        vault_path=test_vault,
        auth_enabled=True,
        admin_password="test-secret-password",
        cookie_secure=False,
    )
    app = create_app(settings)
    auth_client = TestClient(app)

    # 1. Unauthenticated request to private route redirects to /login (303)
    resp = auth_client.get("/dashboard", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/login"

    # 2. Login page itself is accessible with zero info-leak (stealth pre-auth)
    resp_login_page = auth_client.get("/login")
    assert resp_login_page.status_code == 200
    assert "Authorization" in resp_login_page.text
    assert "<nav" not in resp_login_page.text
    assert 'href="/notes"' not in resp_login_page.text
    assert 'href="/graph"' not in resp_login_page.text
    assert 'href="/tasks"' not in resp_login_page.text
    assert "power-framework" not in resp_login_page.text
    assert "Fail-Closed" not in resp_login_page.text
    assert "3.7.11" not in resp_login_page.text
    csrf_login = _extract_csrf(resp_login_page)

    # 3. Invalid password fails with 401
    resp_invalid = auth_client.post(
        "/login",
        data={"password": "wrong-password", "csrf_token": csrf_login},
    )
    assert resp_invalid.status_code == 401
    assert "Invalid access password" in resp_invalid.text

    # 4. Correct password redirects to /dashboard with session cookie
    resp_valid = auth_client.post(
        "/login",
        data={"password": "test-secret-password", "csrf_token": csrf_login},
        follow_redirects=False,
    )
    assert resp_valid.status_code == 303
    assert resp_valid.headers["location"] == "/dashboard"
    cookie = resp_valid.cookies.get("power_web_session")
    assert cookie is not None

    # 5. Authenticated request with session cookie succeeds and displays full UI
    auth_client.cookies.set("power_web_session", cookie)
    resp_authed = auth_client.get("/dashboard")
    assert resp_authed.status_code == 200
    assert "P.O.W.E.R." in resp_authed.text
    assert "3.7.11" in resp_authed.text
    assert "<nav" in resp_authed.text
    assert 'href="/notes"' in resp_authed.text
    assert "power-framework" in resp_authed.text
    assert "Fail-Closed" in resp_authed.text


def test_language_switch_and_defaults(client: TestClient) -> None:
    """Test default English UI and switching to Ukrainian via /set-lang."""
    # 1. Default request without cookies uses English
    resp_en = client.get("/dashboard")
    assert resp_en.status_code == 200
    assert "Dashboard" in resp_en.text
    assert "Notes" in resp_en.text
    assert "Tasks" in resp_en.text
    assert 'lang="en"' in resp_en.text

    # 2. Switch to Ukrainian via /set-lang
    resp_switch = client.get("/set-lang?lang=uk&next=/dashboard", follow_redirects=False)
    assert resp_switch.status_code == 303
    assert resp_switch.headers["location"] == "/dashboard"
    lang_cookie = resp_switch.cookies.get("power_web_lang")
    assert lang_cookie == "uk"

    # 3. Request with Ukrainian cookie uses Ukrainian
    client.cookies.set("power_web_lang", "uk")
    resp_uk = client.get("/dashboard")
    assert resp_uk.status_code == 200
    assert "Дашборд" in resp_uk.text
    assert "Нотатки" in resp_uk.text
    assert "Завдання" in resp_uk.text
    assert 'lang="uk"' in resp_uk.text

    # 4. Switch back to English
    resp_switch_en = client.get("/set-lang?lang=en&next=/dashboard", follow_redirects=False)
    assert resp_switch_en.cookies.get("power_web_lang") == "en"


def test_theme_switch_and_defaults(client: TestClient) -> None:
    """Test default Dark theme and switching to Light theme via /set-theme."""
    # 1. Default request without cookies uses Dark mode
    resp_dark = client.get("/dashboard")
    assert resp_dark.status_code == 200
    assert 'class="dark"' in resp_dark.text
    assert 'data-theme="dark"' in resp_dark.text

    # 2. Switch to Light theme via /set-theme
    resp_switch = client.get("/set-theme?theme=light&next=/dashboard", follow_redirects=False)
    assert resp_switch.status_code == 303
    assert resp_switch.headers["location"] == "/dashboard"
    theme_cookie = resp_switch.cookies.get("power_web_theme")
    assert theme_cookie == "light"

    # 3. Request with Light theme cookie renders light mode
    client.cookies.set("power_web_theme", "light")
    resp_light = client.get("/dashboard")
    assert resp_light.status_code == 200
    assert 'class="light"' in resp_light.text
    assert 'data-theme="light"' in resp_light.text

    # 4. Switch back to Dark theme
    resp_switch_dark = client.get("/set-theme?theme=dark&next=/dashboard", follow_redirects=False)
    assert resp_switch_dark.cookies.get("power_web_theme") == "dark"


def test_arbitrary_custom_categories_and_vault_paths(tmp_path: Path) -> None:
    """Ensure GUI seamlessly handles dynamic vault structures and categories."""
    custom_vault = tmp_path / "custom_user_vault"
    custom_vault.mkdir()
    (custom_vault / ".power").mkdir()
    (custom_vault / "00_Inbox").mkdir()
    (custom_vault / "06_Daily_Logs").mkdir()

    (custom_vault / "00_Inbox" / "Post1.md").write_text(
        """---
type: Resource
title: "Inbox Item 1"
description: "Inbox category test"
tags: [inbox]
timestamp: 2026-08-14T12:00:00+00:00
---

# Inbox Note
""",
        encoding="utf-8",
    )

    (custom_vault / "06_Daily_Logs" / "2026-08-14_log.md").write_text(
        """---
type: Daily Log
title: "Daily Log Note"
description: "Daily log test note"
tags: [log]
timestamp: 2026-08-14T12:00:00+00:00
---

# Daily Log Content
""",
        encoding="utf-8",
    )

    settings = Settings(vault_path=custom_vault, auth_enabled=False, cookie_secure=False)
    app = create_app(settings)
    custom_client = TestClient(app)

    # 1. Dashboard renders custom categories dynamically
    resp_dash = custom_client.get("/dashboard")
    assert resp_dash.status_code == 200
    assert "00_Inbox" in resp_dash.text
    assert "06_Daily_Logs" in resp_dash.text

    # 2. Notes page lists dynamic filter chips for discovered categories
    resp_notes = custom_client.get("/notes")
    assert resp_notes.status_code == 200
    assert "00_Inbox" in resp_notes.text
    assert "06_Daily_Logs" in resp_notes.text

    # 3. Filtering by category works
    resp_filtered = custom_client.get("/notes?category=00_Inbox")
    assert resp_filtered.status_code == 200
    assert "Inbox Item 1" in resp_filtered.text
