#!/usr/bin/env python3
"""Run the local, content-free 3.6.5 -> 3.6.6 upgrade safety matrix.

The script proves invariants available on the current runner and records
the declared release platform boundary. Deferred platforms are never treated
as supported or passed by this report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing, contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

from power_framework.core.generation_index import (
    STALE_BUILD_TTL_ENV,
    _state_db_path,
    resolve_active_generation_path,
    sync_vault_atomically,
)
from power_framework.core.maintenance import apply_maintenance_plan, build_maintenance_plan
from power_framework.core.searcher import search_vault
from power_framework.core.state_migration import build_state_migration_plan

REPO_ROOT = Path(__file__).resolve().parents[1]
try:
    from release_platforms import (
        DEFERRED_RELEASE_PLATFORMS,
        DEFERRED_RELEASE_POLICY,
        SUPPORTED_RELEASE_PLATFORMS,
    )
except ModuleNotFoundError:  # pragma: no cover - package import path in tests/tools.
    from scripts.release_platforms import (
        DEFERRED_RELEASE_PLATFORMS,
        DEFERRED_RELEASE_POLICY,
        SUPPORTED_RELEASE_PLATFORMS,
    )

_INTERRUPTED_UPGRADE_WORKER = r"""
import os
import time
from pathlib import Path

from power_framework.core import generation_index

vault = Path(os.environ["POWER_UPGRADE_VAULT"])
marker = Path(os.environ["POWER_UPGRADE_MARKER"])
point = os.environ["POWER_UPGRADE_POINT"]

if point == "before_move":
    original = generation_index.os.replace

    def pause(src, dst):
        if Path(src).parent.name == "staging" and Path(dst).parent.name == "generations":
            marker.write_text("before_move", encoding="utf-8")
            time.sleep(30)
        return original(src, dst)

    generation_index.os.replace = pause
elif point == "after_move":
    original = generation_index._fsync_directory

    def pause(path):
        if Path(path).name == "generations":
            marker.write_text("after_move", encoding="utf-8")
            time.sleep(30)
        return original(path)

    generation_index._fsync_directory = pause
else:
    original = generation_index._cleanup_generations

    def pause(root):
        marker.write_text("after_pointer", encoding="utf-8")
        time.sleep(30)
        return original(root)

    generation_index._cleanup_generations = pause

generation_index.sync_vault_atomically(vault, sync_embeddings=False)
"""

_UPGRADE_CHECKPOINTS = ("before_move", "after_move", "after_pointer")


def build_matrix(*, from_version: str = "3.6.5", to_version: str = "3.6.6") -> dict[str, Any]:
    """Return local matrix evidence without exposing vault content."""
    current = _platform_name()
    with tempfile.TemporaryDirectory(prefix="power-upgrade-") as temporary:
        vault = Path(temporary)
        note_dir = vault / "01_Projects"
        note_dir.mkdir()
        note = note_dir / "upgrade-fixture.md"
        note.write_text("# Needs repair\n", encoding="utf-8")

        state_plan_first = build_state_migration_plan(vault)
        state_plan_second = build_state_migration_plan(vault)
        state_first = state_plan_first.as_dict()
        state_second = state_plan_second.as_dict()
        state_idempotent = state_first == state_second
        required_copy_bytes = max(state_plan_first.disk_budget_bytes, 1)
        free_space_bytes = shutil.disk_usage(vault).free
        free_space_sufficient = free_space_bytes >= required_copy_bytes

        maintenance_plan = build_maintenance_plan(vault)
        before = note.read_text(encoding="utf-8")
        note.write_text(before + "changed after planning\n", encoding="utf-8")
        stale_rejected = False
        try:
            apply_maintenance_plan(vault, maintenance_plan, approved=True)
        except RuntimeError:
            stale_rejected = True

        current_result = {
            "platform": current,
            "status": "pass"
            if state_idempotent and stale_rejected and free_space_sufficient
            else "fail",
            "checks": {
                "state_plan_idempotent": state_idempotent,
                "dirty_source_rejected_by_hash": stale_rejected,
                "free_space_sufficient": free_space_sufficient,
                "source_content_unchanged_after_rejection": note.read_text(encoding="utf-8")
                == before + "changed after planning\n",
            },
            "preflight": {
                "migration_preview": "pass" if state_idempotent else "fail",
                "required_copy_bytes": required_copy_bytes,
                "free_space_bytes": free_space_bytes,
                "free_space_sufficient": free_space_sufficient,
                "apply_available": False,
            },
        }

    platforms = {
        platform_name: "executed" if platform_name == current else "not-executed"
        for platform_name in SUPPORTED_RELEASE_PLATFORMS
    }
    interrupted = build_interrupted_upgrade_matrix(
        from_version=from_version,
        to_version=to_version,
    )
    return {
        "schema_version": "power.upgrade-matrix.v1",
        "from_version": from_version,
        "to_version": to_version,
        "source_content": "not captured",
        "current_runner": current_result,
        "interrupted_upgrade": interrupted,
        "supported_platforms": list(SUPPORTED_RELEASE_PLATFORMS),
        "deferred_platforms": list(DEFERRED_RELEASE_PLATFORMS),
        "platforms": platforms,
        "dense_profile": {
            "status": "not evaluated",
            "reason": "dense provider/model availability is an optional gate",
        },
        "release_gate": {
            "local_invariants": current_result["status"] == "pass"
            and interrupted["gate"]["all_checkpoints_pass"],
            "all_platforms_executed": all(value == "executed" for value in platforms.values()),
            "publish_ready": False,
            "reason": (
                f"macOS and Windows are deferred with {DEFERRED_RELEASE_POLICY} policy for "
                f"{to_version}; tag-bound clean source and remote readback are release steps"
            ),
        },
    }


def _write_upgrade_fixture(vault: Path, token: str) -> Path:
    """Write one content-free upgrade fixture and return its source path."""
    note = vault / "01_Projects" / "upgrade-fixture.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    note.write_text(
        "---\n"
        "type: Project\n"
        "title: Upgrade fixture\n"
        "description: Content-free upgrade matrix fixture\n"
        "timestamp: 2026-08-11T00:00:00Z\n"
        "---\n\n"
        f"{token}\n",
        encoding="utf-8",
    )
    return note


def _run_interrupted_worker(
    vault: Path,
    marker: Path,
    checkpoint: str,
    cache_home: Path,
) -> None:
    """Kill a child at one publication checkpoint, modelling interruption."""
    environment = os.environ.copy()
    environment.update(
        {
            "POWER_UPGRADE_VAULT": str(vault),
            "POWER_UPGRADE_MARKER": str(marker),
            "POWER_UPGRADE_POINT": checkpoint,
            "XDG_CACHE_HOME": str(cache_home),
        }
    )
    environment.pop("POWER_SEARCH_DB", None)
    process = subprocess.Popen(  # noqa: S603 -- fixed local worker and arguments.
        [sys.executable, "-c", _INTERRUPTED_UPGRADE_WORKER],
        cwd=REPO_ROOT,
        env=environment,
    )
    try:
        deadline = time.monotonic() + 15
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not marker.exists() or marker.read_text(encoding="utf-8") != checkpoint:
            raise RuntimeError(f"interrupted upgrade checkpoint was not reached: {checkpoint}")
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)


@contextmanager
def _temporary_xdg_cache_home(cache_home: Path) -> Iterator[None]:
    """Keep parent and interrupted child on the same hermetic cache namespace."""
    previous = os.environ.get("XDG_CACHE_HOME")
    os.environ["XDG_CACHE_HOME"] = str(cache_home)
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("XDG_CACHE_HOME", None)
        else:
            os.environ["XDG_CACHE_HOME"] = previous


def _build_interrupted_upgrade_case(
    case_root: Path, checkpoint: str, cache_home: Path
) -> dict[str, Any]:
    """Execute one interruption case while sharing only its temporary cache."""
    with _temporary_xdg_cache_home(cache_home):
        vault = case_root / "vault"
        vault.mkdir(parents=True)
        note = _write_upgrade_fixture(vault, "previous-release-marker")
        sync_vault_atomically(vault, sync_embeddings=False, allow_partial=False)
        active_before = resolve_active_generation_path(vault)
        if active_before is None:
            raise RuntimeError("initial upgrade fixture did not publish an active generation")
        active_before_sha = hashlib.sha256(active_before.read_bytes()).hexdigest()

        note.write_text(
            note.read_text(encoding="utf-8").replace(
                "previous-release-marker", "current-release-marker"
            ),
            encoding="utf-8",
        )
        source_after_change = note.read_bytes()
        marker = case_root / "checkpoint.marker"
        _run_interrupted_worker(vault, marker, checkpoint, cache_home)

        active_after_interrupt = resolve_active_generation_path(vault)
        if active_after_interrupt is None:
            raise RuntimeError(f"active generation disappeared at {checkpoint}")
        active_after_sha = hashlib.sha256(active_after_interrupt.read_bytes()).hexdigest()
        expected_new_visible = checkpoint == "after_pointer"
        legacy_visible = bool(search_vault(vault, "previous-release-marker", mode="fts"))
        upgraded_visible = bool(search_vault(vault, "current-release-marker", mode="fts"))
        expected_pre_restart = upgraded_visible if expected_new_visible else legacy_visible
        if not expected_pre_restart:
            raise RuntimeError(
                f"unexpected active readback at {checkpoint}: "
                f"legacy={legacy_visible}, upgraded={upgraded_visible}"
            )

        previous_ttl = os.environ.get(STALE_BUILD_TTL_ENV)
        os.environ[STALE_BUILD_TTL_ENV] = "0"
        data_loss = True
        try:
            sync_vault_atomically(vault, sync_embeddings=False, allow_partial=False)
        finally:
            if previous_ttl is None:
                os.environ.pop(STALE_BUILD_TTL_ENV, None)
            else:
                os.environ[STALE_BUILD_TTL_ENV] = previous_ttl
        recovered_note = note.read_bytes()
        recovered_new = bool(search_vault(vault, "current-release-marker", mode="fts"))
        recovered_legacy = bool(search_vault(vault, "previous-release-marker", mode="fts"))
        restart_recovered = recovered_new and not recovered_legacy
        with closing(sqlite3.connect(_state_db_path(vault))) as conn:
            stale_build_rows_cleared = (
                conn.execute(
                    "SELECT COUNT(*) FROM index_generations WHERE state = 'building'"
                ).fetchone()[0]
                == 0
            )
        source_preserved = recovered_note == source_after_change
        active_pointer_consistent = (
            active_after_sha != active_before_sha
            if expected_new_visible
            else active_after_sha == active_before_sha
        )
        data_loss = not (source_preserved and restart_recovered)
        return {
            "checkpoint": checkpoint,
            "status": "pass"
            if (
                source_preserved
                and restart_recovered
                and active_pointer_consistent
                and stale_build_rows_cleared
            )
            else "fail",
            "pre_restart_expected": "new" if expected_new_visible else "previous",
            "active_pointer_consistent": active_pointer_consistent,
            "source_preserved": source_preserved,
            "restart_recovered": restart_recovered,
            "stale_build_rows_cleared": stale_build_rows_cleared,
            "data_loss": data_loss,
        }


def build_interrupted_upgrade_matrix(
    *, from_version: str = "3.6.5", to_version: str = "3.6.6"
) -> dict[str, Any]:
    """Prove interrupted publication recovery without exposing fixture content."""
    with tempfile.TemporaryDirectory(prefix="power-upgrade-interrupted-") as temporary:
        root = Path(temporary)
        cache_home = root / "cache"
        checkpoint_rows = [
            _build_interrupted_upgrade_case(root / checkpoint, checkpoint, cache_home)
            for checkpoint in _UPGRADE_CHECKPOINTS
        ]

    return {
        "schema_version": "power.upgrade-interrupted-matrix.v1",
        "from_version": from_version,
        "to_version": to_version,
        "synthetic": True,
        "content_free": True,
        "checkpoints": checkpoint_rows,
        "gate": {
            "all_checkpoints_pass": all(row["status"] == "pass" for row in checkpoint_rows),
            "source_preserved": all(row["source_preserved"] for row in checkpoint_rows),
            "restart_recovered": all(row["restart_recovered"] for row in checkpoint_rows),
            "stale_build_rows_cleared": all(
                row["stale_build_rows_cleared"] for row in checkpoint_rows
            ),
            "no_data_loss": all(not row["data_loss"] for row in checkpoint_rows),
        },
        "physical_previous_runtime": False,
        "raw_content_in_report": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-version", default="3.6.5")
    parser.add_argument("--to-version", default="3.6.6")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args(argv)

    report = build_matrix(from_version=args.from_version, to_version=args.to_version)
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")

    if not report["release_gate"]["local_invariants"]:
        return 1
    return 0


def _platform_name() -> str:
    """Normalize Python platform names to the release support matrix."""
    name = platform.system().lower()
    if name == "darwin":
        return "macos"
    if name in {"linux", "windows"}:
        return name
    return name or "unknown"


if __name__ == "__main__":
    raise SystemExit(main())
