"""Deterministic fault-injection harness tests (Phase C).

Arms a named crash point and verifies the operation leaves a recoverable
(prepared) manifest that :meth:`TaskStore.recover` reconciles deterministically.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from power_framework.core.decision_service import DecisionService
from power_framework.core.fault_injection import InjectedFaultError, fault_injector
from power_framework.core.memory_api import commit_note_change
from power_framework.core.task_service import TaskService
from power_framework.core.task_store import TaskStore

if TYPE_CHECKING:
    from pathlib import Path

OKF = "---\ntype: Resource\ntitle: N\ndescription: d\ntimestamp: 2026-01-01T00:00:00\n---\n\n"
OLD = OKF + "old\n"
NEW = OKF + "new\n"


def test_fault_injection_task_create_rolls_back(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "01_Projects").mkdir(parents=True)
    svc = TaskService(vault)
    fault_injector.arm("task.create")
    try:
        svc.create_task(task_id="T1", title="title")
        raise AssertionError("expected InjectedFaultError")
    except InjectedFaultError:
        pass
    finally:
        fault_injector.reset()
    store = TaskStore(vault)
    store.recover()
    assert svc.get_task("T1") is None
    assert not list(store.tx_dir.iterdir())


def test_fault_injection_decision_resolve_rolls_back(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "01_Projects").mkdir(parents=True)
    TaskService(vault).create_task(task_id="T1", title="parent task")
    ds = DecisionService(vault)
    dec = ds.create_decision(
        decision_id="dec_1a2b3c4",
        task_id="T1",
        title="Should we?",
        requested_by="local",
    )
    fault_injector.arm("decision.resolve")
    try:
        ds.resolve_decision(dec.decision_id, action="approve", actor="local", authority="apply")
        raise AssertionError("expected InjectedFaultError")
    except InjectedFaultError:
        pass
    finally:
        fault_injector.reset()
    ds2 = DecisionService(vault)
    assert ds2.get_decision("dec_1a2b3c4").status == "pending"
    store = TaskStore(vault)
    store.recover()
    assert not list(store.tx_dir.iterdir())


def test_fault_injection_memory_apply_rolls_back(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "01_Projects").mkdir(parents=True)
    note = vault / "01_Projects" / "n.md"
    note.write_text(OLD, encoding="utf-8")
    fault_injector.arm("memory.apply")
    try:
        commit_note_change(vault, "01_Projects/n.md", NEW, idempotency_key="m1")
        raise AssertionError("expected InjectedFaultError")
    except InjectedFaultError:
        pass
    finally:
        fault_injector.reset()
    assert note.read_text() == OLD
    store = TaskStore(vault)
    store.recover()
    assert not list(store.tx_dir.iterdir())


def test_fault_injection_is_inert_by_default(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    (vault / "01_Projects").mkdir(parents=True)
    svc = TaskService(vault)
    # No crash armed -> normal create succeeds, no leftover manifest.
    svc.create_task(task_id="T2", title="title")
    assert svc.get_task("T2") is not None
    store = TaskStore(vault)
    assert not list(store.tx_dir.iterdir())
