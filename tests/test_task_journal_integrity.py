"""Comprehensive regression test matrix for Task Journal Integrity (Section 8)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from power_framework.core.errors import TaskJournalIntegrityError
from power_framework.core.task_models import canonical_payload_digest
from power_framework.core.task_service import TaskService
from power_framework.web.app import create_app
from power_framework.web.config import Settings


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_valid_task(vault: Path, task_id: str = "task_valid_01") -> tuple[TaskService, Path, Path]:
    service = TaskService(vault)
    service.create_task(
        task_id=task_id,
        title="Valid Test Task",
        objective="Verify normal behavior",
        owner="tester",
    )
    service.transition_task(
        task_id=task_id,
        new_state="ready",
        expected_revision=1,
    )
    snapshot = vault / ".power" / "tasks" / f"{task_id}.json"
    journal = vault / ".power" / "tasks" / "events" / f"{task_id}.jsonl"
    return service, snapshot, journal


def test_matrix_valid_journal(tmp_path: Path) -> None:
    """Valid journal: normal task read, events read, and transition succeed."""
    service, snapshot, journal = _seed_valid_task(tmp_path)
    assert snapshot.is_file()
    assert journal.is_file()

    task = service.get_task("task_valid_01")
    assert task is not None
    assert task.state == "ready"

    events = service.get_events("task_valid_01")
    assert len(events) == 2
    assert [e.sequence for e in events] == [1, 2]

    # Mutate succeeds
    advanced = service.transition_task("task_valid_01", "working", expected_revision=2)
    assert advanced.state == "working"
    assert advanced.revision == 3


def test_matrix_nonexistent_task(tmp_path: Path) -> None:
    """Nonexistent task: raises FileNotFoundError, not TaskJournalIntegrityError."""
    service = TaskService(tmp_path)
    assert service.get_task("nonexistent_task") is None

    with pytest.raises(FileNotFoundError):
        service.get_events("nonexistent_task")

    with pytest.raises(FileNotFoundError):
        service.transition_task("nonexistent_task", "ready", expected_revision=1)


@pytest.mark.parametrize(
    "corruption_type",
    [
        "sequence_gap_1_3_4",
        "missing_journal",
        "empty_journal",
        "malformed_json",
        "schema_invalid",
        "wrong_task_id",
        "broken_prev_digest",
        "wrong_payload_digest",
    ],
)
def test_matrix_corrupted_conditions_fail_closed(tmp_path: Path, corruption_type: str) -> None:
    """Verify all corrupted conditions raise TaskJournalIntegrityError and preserve bytes."""
    vault = tmp_path / corruption_type
    task_id = f"task_{corruption_type}"
    service, snapshot, journal = _seed_valid_task(vault, task_id=task_id)

    # Apply corruption
    if corruption_type == "sequence_gap_1_3_4":
        lines = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
        # Create gap: sequence 1, 3, 4
        lines[1]["sequence"] = 3
        # Add 4th event with proper hash chain to test [1, 3, 4]
        ev4 = {
            "event_id": f"evt_{task_id}_4",
            "task_id": task_id,
            "sequence": 4,
            "actor": "tester",
            "event_type": "state_transition",
            "payload": {"from_state": "ready", "to_state": "working"},
            "payload_digest": canonical_payload_digest(
                {"from_state": "ready", "to_state": "working"}
            ),
            "prev_event_digest": lines[1]["payload_digest"],
            "created_at": "2026-09-15T12:00:00+00:00",
        }
        lines.append(ev4)
        journal.write_text("\n".join(json.dumps(entry) for entry in lines) + "\n", encoding="utf-8")
    elif corruption_type == "missing_journal":
        journal.unlink()
    elif corruption_type == "empty_journal":
        journal.write_text("", encoding="utf-8")
    elif corruption_type == "malformed_json":
        journal.write_text("NOT_JSON\n", encoding="utf-8")
    elif corruption_type == "schema_invalid":
        # Missing required fields like sequence, actor
        journal.write_text(json.dumps({"task_id": task_id}) + "\n", encoding="utf-8")
    elif corruption_type == "wrong_task_id":
        lines = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
        lines[0]["task_id"] = "different_task_id"
        journal.write_text("\n".join(json.dumps(entry) for entry in lines) + "\n", encoding="utf-8")
    elif corruption_type == "broken_prev_digest":
        lines = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
        lines[1]["prev_event_digest"] = "bad_prev_digest_value"
        journal.write_text("\n".join(json.dumps(entry) for entry in lines) + "\n", encoding="utf-8")
    elif corruption_type == "wrong_payload_digest":
        lines = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
        lines[0]["payload_digest"] = "bad_payload_digest_value"
        journal.write_text("\n".join(json.dumps(entry) for entry in lines) + "\n", encoding="utf-8")

    # Record hashes before mutation attempt
    orig_snapshot_sha = _sha256(snapshot)
    orig_journal_sha = _sha256(journal) if journal.is_file() else None

    # 1. get_events fails with TaskJournalIntegrityError
    with pytest.raises(TaskJournalIntegrityError) as exc_info:
        service.get_events(task_id)
    assert exc_info.value.code == "task_journal_integrity"
    assert exc_info.value.status_code == 409

    # 2. transition_task fails before persistence (ZERO MUTATION)
    with pytest.raises(TaskJournalIntegrityError) as exc_info:
        service.transition_task(task_id, "working", expected_revision=2)
    assert exc_info.value.code == "task_journal_integrity"
    assert exc_info.value.status_code == 409

    # 3. Verify byte-level preservation
    assert _sha256(snapshot) == orig_snapshot_sha
    if orig_journal_sha is not None:
        assert _sha256(journal) == orig_journal_sha


def test_test_gui_task_01_fixture_sequence_1_3_4(tmp_path: Path) -> None:
    """Known test_gui_task_01 sequence [1,3,4] fixture copy triggers integrity error and read-only view."""
    tasks_dir = tmp_path / ".power" / "tasks"
    events_dir = tasks_dir / "events"
    events_dir.mkdir(parents=True, exist_ok=True)

    snapshot_file = tasks_dir / "test_gui_task_01.json"
    snapshot_content = {
        "task_id": "test_gui_task_01",
        "title": "GUI Integration Task",
        "objective": "Test GUI workflows",
        "state": "working",
        "revision": 4,
        "owner": "tester",
        "authority": "apply",
        "priority": "normal",
        "created_at": "2026-08-13T22:19:41.064521+00:00",
        "updated_at": "2026-08-14T13:35:09.852494+00:00",
    }
    snapshot_file.write_text(json.dumps(snapshot_content), encoding="utf-8")

    events_file = events_dir / "test_gui_task_01.jsonl"
    events_lines = [
        {
            "event_id": "evt_1",
            "task_id": "test_gui_task_01",
            "sequence": 1,
            "actor": "gui",
            "event_type": "task_created",
            "payload": {
                "initial_state": "backlog",
                "title": "GUI Integration Task",
                "owner": "tester",
            },
            "payload_digest": "f99cda39175e09613e6770a089a6262115f42fe8cde1327ba044ae0a8a96d725",
            "prev_event_digest": "",
            "created_at": "2026-08-13T22:19:41.064521+00:00",
        },
        {
            "event_id": "evt_3",
            "task_id": "test_gui_task_01",
            "sequence": 3,
            "actor": "gui",
            "event_type": "state_transition",
            "payload": {
                "from_state": "working",
                "to_state": "ready",
                "receipt_id": None,
                "next_action": "inspect",
            },
            "payload_digest": "9c0acf67995048995f0e18e95eb5fa4897857daa8e735ff97f16fd6927d55e4e",
            "prev_event_digest": "f99cda39175e09613e6770a089a6262115f42fe8cde1327ba044ae0a8a96d725",
            "created_at": "2026-08-14T13:35:09.243824+00:00",
        },
        {
            "event_id": "evt_4",
            "task_id": "test_gui_task_01",
            "sequence": 4,
            "actor": "gui",
            "event_type": "state_transition",
            "payload": {
                "from_state": "ready",
                "to_state": "working",
                "receipt_id": None,
                "next_action": "inspect",
            },
            "payload_digest": "abd52e53384c7c6f7804002e280f241c5d5cac17c100eebe123df89f64710123",
            "prev_event_digest": "9c0acf67995048995f0e18e95eb5fa4897857daa8e735ff97f16fd6927d55e4e",
            "created_at": "2026-08-14T13:35:09.852494+00:00",
        },
    ]
    events_file.write_text("\n".join(json.dumps(e) for e in events_lines) + "\n", encoding="utf-8")

    initial_snap_sha = _sha256(snapshot_file)
    initial_event_sha = _sha256(events_file)

    service = TaskService(tmp_path)
    # Direct transition fails before persistence
    with pytest.raises(TaskJournalIntegrityError):
        service.transition_task("test_gui_task_01", "ready", expected_revision=4)

    assert _sha256(snapshot_file) == initial_snap_sha
    assert _sha256(events_file) == initial_event_sha


def test_web_corrupt_task_degraded_view_and_mutation_block(tmp_path: Path) -> None:
    """Web degraded view renders 200, integrity warning, no transition form, and blocks POST."""
    _seed_valid_task(tmp_path, task_id="corrupt_web_task")
    journal = tmp_path / ".power" / "tasks" / "events" / "corrupt_web_task.jsonl"
    lines = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    lines[1]["sequence"] = 3
    journal.write_text("\n".join(json.dumps(entry) for entry in lines) + "\n", encoding="utf-8")

    settings = Settings(vault_path=tmp_path, auth_enabled=False, cookie_secure=False)
    client = TestClient(create_app(settings))

    # EN view
    resp_en = client.get("/tasks/corrupt_web_task")
    assert resp_en.status_code == 200
    assert "Event journal integrity failure" in resp_en.text
    assert "The task snapshot is shown read-only" in resp_en.text
    assert "Event history is unavailable" in resp_en.text
    assert 'action="/tasks/corrupt_web_task/transition"' not in resp_en.text

    # UK view
    resp_uk = client.get("/tasks/corrupt_web_task?lang=uk")
    assert resp_uk.status_code == 200
    assert "Порушення цілісності журналу подій" in resp_uk.text
    assert "Snapshot завдання показано лише для читання" in resp_uk.text
    assert 'action="/tasks/corrupt_web_task/transition"' not in resp_uk.text

    # Valid task remains unchanged
    _seed_valid_task(tmp_path, task_id="healthy_task")
    resp_healthy = client.get("/tasks/healthy_task")
    assert resp_healthy.status_code == 200
    assert "Event journal integrity failure" not in resp_healthy.text
    assert 'action="/tasks/healthy_task/transition"' in resp_healthy.text

    # Direct mutation POST blocked with 409 Conflict
    csrf_resp = client.get("/tasks/new")
    import re

    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', csrf_resp.text)
    csrf_token = match.group(1) if match else ""

    resp_post = client.post(
        "/tasks/corrupt_web_task/transition",
        data={"csrf_token": csrf_token, "new_state": "working", "expected_revision": 2},
    )
    assert resp_post.status_code == 409
    err = resp_post.json()["error"]
    assert err["code"] == "task_journal_integrity"
    # Ensure no internal leaks
    assert "path" not in err["message"].lower()
    assert "digest" not in err["message"].lower()
    assert "sequence" not in err["message"].lower()
    assert ".jsonl" not in err["message"]


def test_template_packaging_and_inclusion() -> None:
    """Verify task_detail_integrity.html is present in wheel/package builds."""
    template_path = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "power_framework"
        / "web"
        / "templates"
        / "task_detail_integrity.html"
    )
    assert template_path.is_file(), f"Template missing: {template_path}"
    content = template_path.read_text(encoding="utf-8")
    assert "event_journal_integrity_title" in content
    assert "event_journal_integrity_events" in content
    assert "transition_gate" in content
