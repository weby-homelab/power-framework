"""
Two-browser end-to-end harness for the POWER Web UI.

Simulates two independent browsers (separate cookie jars / sessions) talking to a
LIVE POWER Web UI server and verifies:

  1. Fail-closed auth/CSRF gate:
       - unauthenticated mutation is rejected (redirect/401/403)
       - authenticated request with a bogus CSRF token is rejected with 403
  2. Two-browser idempotent transition:
       both browsers submit the SAME logical transition (same idempotency key)
       -> exactly one side effect (the task revision stays at 1, not 2)
  3. Read-only gate (optional, skip unless configured):
       against a server started with POWER_WEB_READ_ONLY_MODE=true the same
       mutation returns 405.

The harness only talks to a live server; it is SKIPPABLE. If POWER_WEB_E2E_URL
is unreachable the tests skip instead of failing, so the suite stays green in CI
without a live server.

Env:
  POWER_WEB_E2E_URL           base URL (default http://localhost:8011)
  POWER_WEB_E2E_PASSWORD      admin password (required when a live URL is configured)
  POWER_WEB_E2E_READONLY_URL  optional read-only server URL for the 405 test
"""

import os
import re
import uuid

import pytest
import requests

BASE = os.environ.get("POWER_WEB_E2E_URL", "http://localhost:8011").rstrip("/")
PASSWORD = os.environ.get("POWER_WEB_E2E_PASSWORD")
READONLY_URL = (os.environ.get("POWER_WEB_E2E_READONLY_URL", "") or "").rstrip("/") or None

TIMEOUT = 30
# Unique per-process id so repeated local runs never collide on a persistent vault.
TASK_ID = f"T_E2E_{uuid.uuid4().hex[:10]}"


def _reachable(url: str) -> bool:
    try:
        requests.get(url + "/healthz", timeout=5)
        return True
    except Exception:
        return False


def _csrf_from_html(text: str) -> str:
    m = re.search(r'name="csrf_token"\s+value="([^"]+)"', text)
    return m.group(1) if m else ""


def login(session: requests.Session, base: str) -> str:
    if not PASSWORD:
        pytest.skip("POWER_WEB_E2E_PASSWORD is required for live E2E")
    r = session.get(base + "/login", timeout=TIMEOUT)
    assert r.status_code == 200, f"login page returned {r.status_code}"
    csrf = _csrf_from_html(r.text)
    r = session.post(
        base + "/login",
        data={"password": PASSWORD, "csrf_token": csrf},
        allow_redirects=False,
        timeout=TIMEOUT,
    )
    assert r.status_code in (302, 303), f"login returned {r.status_code}"
    return csrf


def get_csrf(session: requests.Session, base: str) -> str:
    r = session.get(base + "/tasks/new", timeout=TIMEOUT)
    assert r.status_code == 200, f"/tasks/new returned {r.status_code}"
    return _csrf_from_html(r.text)


def create_task(session, base, csrf, task_id):
    return session.post(
        base + "/tasks/new",
        data={
            "task_id": task_id,
            "title": "E2E two-browser",
            "objective": "verify idempotency",
            "owner": "local",
            "priority": "normal",
            "authority": "apply",
            "csrf_token": csrf,
        },
        allow_redirects=False,
        timeout=TIMEOUT,
    )


def transition(session, base, csrf, task_id, expected_revision):
    return session.post(
        base + f"/tasks/{task_id}/transition",
        data={
            "new_state": "ready",
            "expected_revision": str(expected_revision),
            "authority": "apply",
            "csrf_token": csrf,
        },
        allow_redirects=False,
        timeout=TIMEOUT,
    )


def revision_of(session, base, task_id):
    r = session.get(base + f"/tasks/{task_id}", timeout=TIMEOUT)
    m = re.search(r"Rev:\s*v(\d+)", r.text)
    return int(m.group(1)) if m else None


@pytest.mark.skipif(
    not _reachable(BASE), reason=f"live POWER Web UI server not reachable at {BASE}"
)
def test_auth_csrf_gate_fail_closed():
    # Unauthenticated mutation must never succeed.
    anon = requests.Session()
    r = anon.post(
        BASE + "/tasks/new",
        data={"task_id": TASK_ID, "title": "x", "csrf_token": "bogus"},
        allow_redirects=False,
        timeout=TIMEOUT,
    )
    assert r.status_code in (302, 303, 401, 403), (
        f"unauthenticated mutation returned {r.status_code}"
    )

    # Authenticated but with a bogus CSRF token -> fail-closed 403.
    a = requests.Session()
    login(a, BASE)
    r = a.post(
        BASE + "/tasks/new",
        data={"task_id": TASK_ID, "title": "x", "csrf_token": "bogus"},
        allow_redirects=False,
        timeout=TIMEOUT,
    )
    assert r.status_code == 403, f"bad CSRF token mutation returned {r.status_code}: {r.text[:120]}"


@pytest.mark.skipif(
    not _reachable(BASE), reason=f"live POWER Web UI server not reachable at {BASE}"
)
def test_two_browser_idempotent_transition():
    a = requests.Session()
    b = requests.Session()
    login(a, BASE)
    login(b, BASE)
    csrf_a = get_csrf(a, BASE)

    # Create the task from browser A.
    r = create_task(a, BASE, csrf_a, TASK_ID)
    assert r.status_code in (302, 303), f"create returned {r.status_code}: {r.text[:200]}"

    # Read the post-create revision so both browsers issue the SAME logical
    # transition (identical idempotency key). Whatever the create leaves the
    # task at, both submit expected_revision == that value.
    rev0 = revision_of(a, BASE, TASK_ID)
    assert rev0 is not None, "could not read post-create revision"

    # Browser A transitions ready (rev0 -> rev0+1).
    r1 = transition(a, BASE, csrf_a, TASK_ID, rev0)
    assert r1.status_code in (302, 303), f"A transition returned {r1.status_code}: {r1.text[:300]}"

    # Browser B submits the SAME logical transition (same idempotency key):
    # it must be idempotent and NOT produce a second side effect.
    csrf_b = get_csrf(b, BASE)
    r2 = transition(b, BASE, csrf_b, TASK_ID, rev0)
    assert r2.status_code in (302, 303), f"B transition returned {r2.status_code}: {r2.text[:300]}"

    # Exactly one side effect: revision advances by exactly one, not two.
    rev = revision_of(a, BASE, TASK_ID)
    assert rev == rev0 + 1, f"expected idempotent revision {rev0 + 1}, got {rev}"


@pytest.mark.skipif(
    not READONLY_URL or not _reachable(READONLY_URL),
    reason="POWER_WEB_E2E_READONLY_URL not set or unreachable",
)
def test_readonly_gate_405():
    s = requests.Session()
    login(s, READONLY_URL)
    csrf = get_csrf(s, READONLY_URL)
    r = s.post(
        READONLY_URL + "/tasks/new",
        data={
            "task_id": TASK_ID,
            "title": "x",
            "objective": "x",
            "owner": "local",
            "priority": "normal",
            "authority": "apply",
            "csrf_token": csrf,
        },
        allow_redirects=False,
        timeout=TIMEOUT,
    )
    assert r.status_code == 405, f"read-only mutation returned {r.status_code} (expected 405)"
