"""Fail-closed, import-compatible migration of foreign Markdown notes."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import ValidationError

from .constants import EXCLUDED_DIRS, SKIP_FILES
from .models import NoteStatus, OKFMetadata
from .parser import (
    FRONTMATTER_PATTERN,
    build_frontmatter,
    extract_frontmatter_raw,
    parse_frontmatter,
)
from .utils import atomic_write

if TYPE_CHECKING:
    from collections.abc import Mapping


class ImportPolicy(StrEnum):
    """Policy used to handle source notes that do not match OKF exactly."""

    STRICT = "strict"
    QUARANTINE = "quarantine"


@dataclass(frozen=True)
class QuarantineChange:
    """One foreign value retained under an additive ``x-`` key."""

    field: str
    quarantine_field: str
    reason: str


@dataclass
class ImportItem:
    """Preflight result for one source note."""

    source: Path
    relative_path: str
    destination: Path
    content: str | None = None
    output: str | None = None
    changes: list[QuarantineChange] = field(default_factory=list)
    excluded_reason: str | None = None
    collision: bool = False
    unchanged: bool = False

    @property
    def importable(self) -> bool:
        """Whether this item can be copied without overwriting another note."""
        return self.output is not None and self.excluded_reason is None and not self.collision


@dataclass
class ImportPlan:
    """Complete deterministic import plan, built before any target write."""

    source_dir: Path
    target_dir: Path
    policy: ImportPolicy
    items: list[ImportItem]

    @property
    def scanned(self) -> int:
        """Number of source Markdown notes considered by the plan."""
        return len(self.items)

    @property
    def excluded(self) -> list[ImportItem]:
        """Items that cannot be imported under the selected policy."""
        return [item for item in self.items if item.excluded_reason or item.collision]

    @property
    def candidates(self) -> list[ImportItem]:
        """Items that are valid and safe to import or leave unchanged."""
        return [item for item in self.items if item.output is not None and not item.excluded_reason]

    @property
    def quarantined(self) -> list[ImportItem]:
        """Items whose frontmatter needs an explicit additive quarantine."""
        return [item for item in self.items if item.changes]

    @property
    def will_write(self) -> list[ImportItem]:
        """Items that will create a new or changed destination note."""
        return [item for item in self.candidates if item.importable and not item.unchanged]

    @property
    def reason_counts(self) -> Counter[str]:
        """Stable counts for the human-readable import report."""
        counts: Counter[str] = Counter()
        for item in self.items:
            if item.excluded_reason:
                counts[item.excluded_reason] += 1
            elif item.collision:
                counts["destination_exists_with_different_content"] += 1
            for change in item.changes:
                counts[f"{change.field}: {change.reason}"] += 1
        return counts


def _source_notes(source_dir: Path) -> list[tuple[Path, str]]:
    """Return source notes in deterministic order without applying vault scope."""
    notes: list[tuple[Path, str]] = []
    for path in sorted(source_dir.rglob("*.md")):
        if not path.is_file():
            continue
        relative = path.relative_to(source_dir).as_posix()
        if path.name in SKIP_FILES or any(part in EXCLUDED_DIRS for part in Path(relative).parts):
            continue
        notes.append((path, relative))
    return notes


def _safe_quarantine_field(data: dict[str, object], base: str, value: object) -> str:
    """Choose an additive key without overwriting an existing user value."""
    candidate = base
    suffix = 1
    while candidate in data and data[candidate] != value:
        suffix += 1
        candidate = f"{base}-{suffix}"
    data[candidate] = value
    return candidate


def normalize_foreign_fields(
    source: Mapping[str, object],
    policy: ImportPolicy,
) -> tuple[dict[str, object], list[QuarantineChange]]:
    """Move known foreign optional values to additive ``x-`` fields."""
    data = dict(source)
    changes: list[QuarantineChange] = []
    if policy is ImportPolicy.STRICT:
        return data, changes

    status = data.get("status")
    if status is not None:
        valid_status = isinstance(status, NoteStatus)
        if isinstance(status, str):
            try:
                NoteStatus(status)
            except ValueError:
                valid_status = False
            else:
                valid_status = True
        if not valid_status:
            data.pop("status", None)
            quarantined = _safe_quarantine_field(data, "x-status", status)
            changes.append(QuarantineChange("status", quarantined, "foreign status value"))

    related = data.get("related")
    if related is not None:
        try:
            OKFMetadata.coerce_related(related)
        except (TypeError, ValueError, ValidationError):
            data.pop("related", None)
            quarantined = _safe_quarantine_field(data, "x-related", related)
            changes.append(QuarantineChange("related", quarantined, "foreign relation shape"))

    return data, changes


def _validation_reason(data: Mapping[str, object], error: ValidationError) -> str:
    """Create a stable, non-sensitive exclusion reason from Pydantic errors."""
    if "type" not in data:
        return "missing_type"
    fields = sorted({".".join(str(part) for part in issue["loc"]) for issue in error.errors()})
    if fields == ["type"]:
        return "invalid_type"
    return "invalid_metadata:" + ",".join(fields)


def _replace_frontmatter(content: str, metadata: OKFMetadata) -> str:
    """Render normalized metadata while preserving the original Markdown body."""
    match = FRONTMATTER_PATTERN.match(content)
    if match is None:
        raise ValueError("source frontmatter disappeared during import preflight")
    return f"{build_frontmatter(metadata)}\n{content[match.end() :]}"


def _plan_item(source: Path, relative: str, destination: Path, policy: ImportPolicy) -> ImportItem:
    """Build one import item without touching the destination."""
    item = ImportItem(source=source, relative_path=relative, destination=destination)
    try:
        content = source.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        item.excluded_reason = "read_error"
        return item
    item.content = content

    if extract_frontmatter_raw(content) is None:
        item.excluded_reason = "missing_or_malformed_frontmatter"
        return item
    data = parse_frontmatter(content)
    if data is None:
        item.excluded_reason = "invalid_yaml"
        return item

    normalized, changes = normalize_foreign_fields(data, policy)
    item.changes = changes
    try:
        metadata = OKFMetadata.model_validate(normalized)
    except ValidationError as error:
        item.excluded_reason = _validation_reason(normalized, error)
        return item

    item.output = _replace_frontmatter(content, metadata) if changes else content
    if destination.exists():
        try:
            item.unchanged = destination.read_text(encoding="utf-8") == item.output
        except (OSError, UnicodeError):
            item.collision = True
        if not item.unchanged and not item.collision:
            item.collision = True
    return item


def build_import_plan(source_dir: Path, target_dir: Path, policy: ImportPolicy) -> ImportPlan:
    """Preflight every source note and return a deterministic, write-free plan."""
    source = source_dir.expanduser().resolve()
    target = target_dir.expanduser().resolve()
    items = [
        _plan_item(path, relative, target / relative, policy)
        for path, relative in _source_notes(source)
    ]
    return ImportPlan(source, target, policy, items)


def apply_import_plan(plan: ImportPlan, *, allow_partial: bool = False) -> int:
    """Apply a preflighted plan and return the number of newly written notes."""
    if plan.excluded and not allow_partial:
        raise ValueError("import plan contains excluded notes; pass --allow-partial to apply")
    written = 0
    for item in plan.will_write:
        if item.content is None or item.output is None:
            continue
        if item.destination.exists():
            try:
                current = item.destination.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                raise ValueError(f"cannot recheck destination: {item.relative_path}") from exc
            if current == item.output:
                continue
            raise ValueError(f"destination changed during import: {item.relative_path}")
        atomic_write(item.destination, item.output)
        written += 1
    return written


def format_import_report(plan: ImportPlan, *, dry_run: bool) -> str:
    """Render the deterministic preflight/apply summary and warnings."""
    lines = [
        f"Import {'dry run' if dry_run else 'plan'}:",
        f"  source: {plan.source_dir}",
        f"  target: {plan.target_dir}",
        f"  policy: {plan.policy.value}",
        f"  notes scanned: {plan.scanned}",
        f"  will import: {len(plan.will_write)}",
        f"  will quarantine: {len(plan.quarantined)}",
        f"  unchanged: {sum(item.unchanged for item in plan.items)}",
        f"  excluded: {len(plan.excluded)}",
    ]
    for key, count in sorted(plan.reason_counts.items()):
        lines.append(f"    {key}: {count}")
    for item in plan.items:
        lines.extend(
            f"  WARN {item.relative_path}: {change.field} -> {change.quarantine_field} "
            f"({change.reason})"
            for change in item.changes
        )
        if item.excluded_reason:
            lines.append(f"  EXCLUDE {item.relative_path}: {item.excluded_reason}")
        elif item.collision:
            lines.append(f"  EXCLUDE {item.relative_path}: destination collision")
    return "\n".join(lines)
