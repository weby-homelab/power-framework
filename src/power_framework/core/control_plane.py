"""Human-visible, content-free control-plane materialization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from .handoff import list_work_packets
from .memory_api import read_history
from .mutation import execute_vault_mutation
from .utils import atomic_write

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


CONTROL_PLANE_FILENAME = "POWER_STATUS.md"
CONTROL_PLANE_MARKER = "<!-- power-control-plane:v1 -->"
OBSIDIAN_BASE_FILENAME = "POWER Control.base"
OBSIDIAN_BASE_MARKER = "# power-obsidian-base:v1"


def build_control_plane(vault_dir: Path) -> str:
    """Render stable Markdown summaries without note or prompt content."""
    root = Path(vault_dir).expanduser().resolve()
    packets = list_work_packets(root)
    history = read_history(root)
    active = [
        packet
        for packet in packets
        if packet.get("state") not in {"completed", "failed", "canceled"}
    ]
    needs_review = [packet for packet in active if packet.get("state") == "input-required"]
    degraded: list[str] = []
    if not history:
        degraded.append("no_change_receipts_yet")

    lines = [
        CONTROL_PLANE_MARKER,
        "# POWER Status",
        "",
        "Generated control view. Source notes and prompts are not copied here.",
        "",
        "## Active Work",
    ]
    lines.extend(_render_packets(active))
    lines.extend(["", "## Needs Review"])
    lines.extend(_render_packets(needs_review))
    lines.extend(["", "## Stale Evidence"])
    lines.extend(_render_stale_evidence(root))
    lines.extend(["", "## Degraded"])
    if degraded:
        lines.extend(f"- `{item}`" for item in degraded)
    else:
        lines.append("- None.")
    lines.extend(["", "## Recent Change Receipts"])
    receipt_lines = _render_receipts(history[-10:])
    lines.extend(receipt_lines or ["- None."])
    lines.append("")
    return "\n".join(lines)


def build_obsidian_base() -> str:
    """Render optional Obsidian Bases views without reading vault content.

    The generated queries expose only control-plane metadata and file
    properties. ``POWER_STATUS.md`` remains the source-visible fallback when
    Obsidian Bases is unavailable.
    """
    payload = {
        "filters": 'file.path != "POWER Control.base"',
        "views": [
            {
                "type": "table",
                "name": "Active Work",
                "filters": {
                    "and": [
                        'file.inFolder(".power/work-packets")',
                        'note.state != "completed"',
                        'note.state != "failed"',
                        'note.state != "canceled"',
                    ]
                },
                "order": [
                    "note.task_id",
                    "note.state",
                    "note.next_action",
                    "note.required_approval",
                    "file.mtime",
                ],
            },
            {
                "type": "table",
                "name": "Needs Human Decision",
                "filters": {
                    "and": [
                        'file.inFolder(".power/work-packets")',
                        'note.state == "input-required"',
                    ]
                },
                "order": [
                    "note.task_id",
                    "note.required_approval",
                    "note.next_action",
                    "file.mtime",
                ],
            },
            {
                "type": "table",
                "name": "Stale Evidence",
                "filters": {
                    "and": [
                        'file.inFolder(".power/evidence/records")',
                        'file.ext == "json"',
                        'file.mtime < now() - "30d"',
                    ]
                },
                "order": ["file.name", "file.mtime", "file.path"],
            },
            {
                "type": "table",
                "name": "Recent Changes",
                "filters": {
                    "and": [
                        'file.mtime > now() - "7d"',
                        'file.path != "POWER_STATUS.md"',
                    ]
                },
                "order": ["file.mtime", "file.path"],
            },
        ],
    }
    rendered = yaml.safe_dump(
        payload,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return f"{OBSIDIAN_BASE_MARKER}\n{rendered}"


def write_obsidian_base(vault_dir: Path) -> Path:
    """Materialize the optional Bases asset without overwriting user files."""
    root = Path(vault_dir).expanduser().resolve()
    target = root / OBSIDIAN_BASE_FILENAME
    rendered = build_obsidian_base()

    def publish() -> Path:
        if target.exists():
            existing = target.read_text(encoding="utf-8")
            if not existing.startswith(OBSIDIAN_BASE_MARKER + "\n"):
                raise FileExistsError(f"refusing to overwrite manual Obsidian Base: {target.name}")
            if existing == rendered:
                return target
        atomic_write(target, rendered)
        return target

    return execute_vault_mutation(root, publish)


def remove_obsidian_base(vault_dir: Path) -> bool:
    """Remove only the generated Bases asset; never touch user notes."""
    root = Path(vault_dir).expanduser().resolve()
    target = root / OBSIDIAN_BASE_FILENAME

    def remove() -> bool:
        if not target.exists():
            return False
        existing = target.read_text(encoding="utf-8")
        if not existing.startswith(OBSIDIAN_BASE_MARKER + "\n"):
            raise FileExistsError(f"refusing to remove manual Obsidian Base: {target.name}")
        target.unlink()
        return True

    return execute_vault_mutation(root, remove)


def write_control_plane(vault_dir: Path) -> Path:
    """Materialize the view idempotently and refuse to overwrite manual files."""
    root = Path(vault_dir).expanduser().resolve()
    target = root / CONTROL_PLANE_FILENAME
    rendered = build_control_plane(root)

    def publish() -> Path:
        if target.exists():
            existing = target.read_text(encoding="utf-8")
            if not existing.startswith(CONTROL_PLANE_MARKER + "\n"):
                raise FileExistsError(
                    f"refusing to overwrite manual control-plane file: {target.name}"
                )
            if existing == rendered:
                return target
        atomic_write(target, rendered)
        return target

    return execute_vault_mutation(root, publish)


def _render_packets(packets: Sequence[Mapping[str, object]]) -> list[str]:
    if not packets:
        return ["- None."]
    return [
        "- "
        + " — ".join(
            [
                f"`{packet.get('task_id', 'unknown')}`",
                str(packet.get("state", "unknown")),
                f"next: {packet.get('next_action', 'unknown')}",
            ]
        )
        for packet in packets
    ]


def _render_receipts(receipts: Sequence[Mapping[str, object]]) -> list[str]:
    lines = []
    for receipt in receipts:
        fields = {
            key: receipt.get(key)
            for key in ("operation", "path", "after_sha256", "at", "status")
            if receipt.get(key) is not None
        }
        lines.append(f"- `{json.dumps(fields, ensure_ascii=False, sort_keys=True)}`")
    return lines


def _render_stale_evidence(vault_dir: Path) -> list[str]:
    """List explicitly stale evidence records without exposing their payload."""
    records_dir = vault_dir / ".power" / "evidence" / "records"
    if not records_dir.is_dir():
        return ["- None."]
    stale: list[str] = []
    for path in sorted(records_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict) and payload.get("freshness") == "stale":
            stale.append(f"- `{path.name}` — freshness: `stale`")
    return stale or ["- None."]


__all__ = [
    "CONTROL_PLANE_FILENAME",
    "CONTROL_PLANE_MARKER",
    "OBSIDIAN_BASE_FILENAME",
    "OBSIDIAN_BASE_MARKER",
    "build_control_plane",
    "build_obsidian_base",
    "remove_obsidian_base",
    "write_control_plane",
    "write_obsidian_base",
]
