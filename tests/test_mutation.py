"""Regression tests for per-vault mutation isolation and cleanup."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from power_framework.core.mutation import (
    execute_vault_mutation,
    reset_mutation_registry_for_test,
    vault_mutation,
)


@pytest.fixture(autouse=True)
def _reset_locks():
    reset_mutation_registry_for_test()
    yield
    reset_mutation_registry_for_test()


def test_same_vault_mutations_are_serialized(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    active = 0
    peak = 0
    guard = threading.Lock()

    def mutation() -> None:
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with guard:
            active -= 1

    threads = [
        threading.Thread(target=execute_vault_mutation, args=(vault, mutation)) for _ in range(6)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert peak == 1


def test_different_vault_mutations_remain_parallel(tmp_path: Path) -> None:
    vault_a = tmp_path / "vault-a"
    vault_b = tmp_path / "vault-b"
    vault_a.mkdir()
    vault_b.mkdir()
    started = threading.Barrier(2)
    completed: list[str] = []

    def mutation(label: str) -> None:
        started.wait(timeout=2)
        time.sleep(0.02)
        completed.append(label)

    threads = [
        threading.Thread(target=execute_vault_mutation, args=(vault_a, lambda: mutation("a"))),
        threading.Thread(target=execute_vault_mutation, args=(vault_b, lambda: mutation("b"))),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(completed) == ["a", "b"]


def test_lock_is_released_after_failure(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()

    with pytest.raises(RuntimeError, match="expected"):
        execute_vault_mutation(vault, lambda: (_ for _ in ()).throw(RuntimeError("expected")))

    with vault_mutation(vault):
        assert (vault / ".power" / "mutation.lock").exists()


def test_os_lock_serializes_another_process(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    marker = vault / "child-complete"
    script = (
        "from pathlib import Path; "
        "from power_framework.core.mutation import execute_vault_mutation; "
        "import sys; "
        "root = Path(sys.argv[1]); "
        "execute_vault_mutation(root, lambda: (root / 'child-complete').write_text('ok'))"
    )
    env = os.environ.copy()
    source_root = Path(__file__).resolve().parents[1] / "src"
    env["PYTHONPATH"] = str(source_root) + os.pathsep + env.get("PYTHONPATH", "")

    with vault_mutation(vault):
        child = subprocess.Popen(  # noqa: S603
            [sys.executable, "-c", script, str(vault)], env=env
        )
        time.sleep(0.1)
        assert child.poll() is None

    try:
        assert child.wait(timeout=10) == 0
    except Exception:
        child.kill()
        child.wait()
        raise
    assert marker.read_text(encoding="utf-8") == "ok"
