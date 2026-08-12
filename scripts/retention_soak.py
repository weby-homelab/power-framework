#!/usr/bin/env python3
"""Run a content-free bounded retention and restore soak on a temporary vault."""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path
from typing import Any

from power_framework.core.utils import create_backup, prune_backups, restore_backup

RETENTION_COUNT = 4
INITIAL_BACKUPS = 12
SOAK_CYCLES = 20


def _manifest_hash(paths: list[Path], root: Path) -> str:
    names = [path.relative_to(root).as_posix() for path in paths]
    return hashlib.sha256(json.dumps(names, sort_keys=True).encode("utf-8")).hexdigest()


def run_retention_soak() -> dict[str, Any]:
    """Prove preview/apply bounds and newest-backup restore without raw content."""
    with tempfile.TemporaryDirectory(prefix="power-retention-") as temporary:
        root = Path(temporary)
        source = root / "01_Projects" / "source.md"
        control = root / "POWER_STATUS.md"
        backup_dir = source.parent / ".backups"
        restore_target = root / "restored.md"
        source.parent.mkdir(parents=True)
        source.write_text("source baseline\n", encoding="utf-8")
        control.write_text("control sentinel\n", encoding="utf-8")
        control_before = control.read_bytes()

        for number in range(INITIAL_BACKUPS):
            source.write_text(f"fixture revision {number}\n", encoding="utf-8")
            if create_backup(source, backup_dir=backup_dir) is None:
                raise RuntimeError("retention fixture backup creation failed")

        candidates = sorted(backup_dir.glob("*.md"), key=lambda path: path.name)
        preview = prune_backups(
            backup_dir,
            max_count=RETENTION_COUNT,
            max_age_days=None,
            max_bytes=None,
            dry_run=True,
        )
        preview_paths = list(preview)
        before_preview = sorted(backup_dir.glob("*.md"), key=lambda path: path.name)
        if before_preview != candidates:
            raise RuntimeError("retention preview changed the candidate set")

        removed = prune_backups(
            backup_dir,
            max_count=RETENTION_COUNT,
            max_age_days=None,
            max_bytes=None,
            dry_run=False,
        )
        kept = sorted(backup_dir.glob("*.md"), key=lambda path: path.name)
        if len(removed) != len(preview_paths) or len(kept) != RETENTION_COUNT:
            raise RuntimeError("retention apply diverged from its preview manifest")

        newest = max(kept, key=lambda path: (path.stat().st_mtime_ns, path.name))
        restore_backup(newest, restore_target)
        restored_sha = hashlib.sha256(restore_target.read_bytes()).hexdigest()
        newest_sha = hashlib.sha256(newest.read_bytes()).hexdigest()
        if restored_sha != newest_sha:
            raise RuntimeError("newest retained backup did not restore exactly")

        max_retained = len(kept)
        for number in range(SOAK_CYCLES):
            source.write_text(f"soak revision {number}\n", encoding="utf-8")
            if create_backup(source, backup_dir=backup_dir) is None:
                raise RuntimeError("retention soak backup creation failed")
            prune_backups(
                backup_dir,
                max_count=RETENTION_COUNT,
                max_age_days=None,
                max_bytes=None,
                dry_run=False,
            )
            max_retained = max(max_retained, len(list(backup_dir.glob("*.md"))))

        final_kept = sorted(backup_dir.glob("*.md"), key=lambda path: path.name)
        return {
            "schema_version": "power.retention-soak.v1",
            "content_free": True,
            "policy": {"max_count": RETENTION_COUNT, "max_age_days": None, "max_bytes": None},
            "preview": {
                "candidate_count": len(candidates),
                "prune_count": len(preview_paths),
                "kept_count": RETENTION_COUNT,
                "prune_manifest_sha256": _manifest_hash(preview_paths, root),
            },
            "apply": {
                "removed_count": len(removed),
                "remaining_count": len(kept),
                "removed_manifest_sha256": _manifest_hash(removed, root),
            },
            "restore": {"status": "ok", "restored_sha256": restored_sha},
            "bounded_growth": {
                "cycles": SOAK_CYCLES,
                "max_retained": max_retained,
                "final_retained": len(final_kept),
                "within_policy": max_retained <= RETENTION_COUNT,
            },
            "source_preserved": source.is_file(),
            "control_preserved": control.read_bytes() == control_before,
            "raw_content_in_report": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    rendered = json.dumps(run_retention_soak(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
